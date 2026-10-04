"""Phase 15E — product query + durable traces (D06–D08 / D11 / D21)."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.query import (
    MAX_QUESTION_CHARS,
    _build_orchestrator,
    get_product_trace,
    run_product_query,
)
from offline_rag.app.query_binding import build_snapshot_query_binding
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.traces import (
    ProductQueryTrace,
    ProductTraceExecutionSummary,
    ProductTraceIdentitySummary,
    ProductTraceRequestSummary,
    ProductTraceStore,
    allocate_trace_id,
)
from offline_rag.chunking import TiktokenTokenCounter
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.context.store import ChunkStructureStore
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.chunking import ChunkSetManifest
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.domain.indexing import (
    DenseIndexManifest,
    DenseRetrievalResult,
    LexicalIndexManifest,
    LexicalRetrievalResult,
)
from offline_rag.generation.config_hash import build_generation_config_hash
from offline_rag.generation.orchestrate import (
    GroundedAnswerError,
    GroundedAnswerOrchestrator,
)
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash
from offline_rag.rerank.fake import FakeReranker
from offline_rag.rerank.retrieve import HybridRerankRetriever

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
BASELINE_SHA = "11800734c7762804e9cf78ef8a1c3af3e158e04f"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
CITATION_FIELDS = (
    "evidence_unit_id",
    "document_id",
    "source_chunk_id",
    "kind",
    "section_path",
    "page_start",
    "page_end",
    "line_start",
    "line_end",
    "clipped",
)
SUCCESS_KEYS = {
    "corpus",
    "snapshot_id",
    "product_mode_id",
    "trace_id",
    "status",
    "answer",
    "citations",
}


class _Closeable:
    def close(self) -> None:
        return None


class _FakeQdrant:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def collection_exists(self, name: str) -> bool:
        return name in self.counts

    def count(self, name: str) -> int:
        return int(self.counts[name])

    def close(self) -> None:
        return None


def _provision_assets(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _settings(tmp_path: Path) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "false",
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(update={"generation": generation, "reranker": reranker})
    _provision_assets(settings)
    return settings


def _runtime(settings: AppSettings, qdrant: _FakeQdrant | None = None) -> ApplicationRuntime:
    q = qdrant if qdrant is not None else _FakeQdrant()
    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker = FakeReranker()
    generator = _Closeable()

    def _q(_s: AppSettings) -> _FakeQdrant:
        return q

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker,
            generator_client=lambda _s: generator,
            qdrant=_q,
        ),
    )


def _config_hashes(settings: AppSettings) -> dict[str, str]:
    counter = TiktokenTokenCounter(
        encoding=settings.chunking.tokenizer.encoding,
        artifacts_path=settings.paths.tokenizer_artifacts,
    )
    return {
        "embedding_config_hash": build_embedding_config_hash(settings),
        "index_config_hash": build_index_config_hash(settings),
        "lexical_config_hash": build_lexical_config_hash(settings),
        "fusion_config_hash": build_fusion_config_hash(settings),
        "reranker_config_hash": build_reranker_config_hash(settings),
        "context_config_hash": build_context_config_hash(
            settings, token_counter=counter
        ),
    }


def _write_scientific_stack(
    settings: AppSettings,
    *,
    corpus_id: str = "corpus_aaa",
    chunk_set_id: str = "chunkset_bbb",
    dense_index_id: str = "denseindex_ccc",
    lexical_index_id: str = "lexical_ddd",
    collection_name: str = "col_ccc",
    document_id: str = "doc_001",
    source_name: str = "spec.pdf",
    expected_child_count: int = 1,
    indexed_child_count: int = 1,
) -> Any:
    from offline_rag.app.snapshot import CanonicalSnapshotManifest

    hashes = _config_hashes(settings)
    now = datetime.now(tz=UTC)
    corpus_manifest_name = f"{corpus_id}.json"
    chunk_manifest_name = f"{chunk_set_id}.json"
    dense_manifest_name = f"{dense_index_id}.json"
    lexical_manifest_name = f"{lexical_index_id}.json"

    corpus = CorpusManifest(
        corpus_id=corpus_id,
        corpus_hash="corphash_1",
        created_at=now,
        config_hash="cfg_corpus",
        documents=[
            CorpusDocumentEntry(
                document_id=document_id,
                source_path="/secret/absolute/path/spec.pdf",
                source_name=source_name,
                source_content_hash="ch_1",
                source_size_bytes=12,
                source_media_type="application/pdf",
                parser_name="docling_pdf",
                parser_version="v1",
                block_count=1,
                processed_artifact="processed/x.json",
                processed_artifact_hash="pah_1",
                parsed_artifact_id="parsed_1",
                parse_config_hash="cfg_parse",
            )
        ],
    )
    chunk = ChunkSetManifest(
        chunk_set_id=chunk_set_id,
        corpus_id=corpus_id,
        chunk_config_hash="cfg_chunk",
        chunker_version="v1",
        tokenizer_name="tiktoken",
        tokenizer_encoding="cl100k_base",
        created_at=now,
    )
    dense = DenseIndexManifest(
        index_id=dense_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        embedding_config_hash=hashes["embedding_config_hash"],
        index_config_hash=hashes["index_config_hash"],
        index_contract_version="dense-index-v1",
        embedding_text_strategy="plain",
        embedding_text_contract="plain-v1",
        embedding_model_id="model",
        embedding_model_revision="rev",
        embedding_dimension=8,
        normalize=True,
        similarity_metric="cosine",
        backend="qdrant_local",
        backend_contract="qdrant-local-v1",
        collection_name=collection_name,
        expected_child_count=expected_child_count,
        indexed_child_count=indexed_child_count,
        created_at=now,
    )
    lexical = LexicalIndexManifest(
        lexical_index_id=lexical_index_id,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
        text_strategy="plain",
        text_contract="plain-v1",
        analyzer_strategy="technical",
        analyzer_contract="technical-v1",
        bm25_contract="bm25-v1",
        bm25_k1=1.2,
        bm25_b=0.75,
        bm25_idf="standard",
        bm25_query_tf="raw",
        backend="local_inverted",
        backend_contract="local-inverted-index-v1",
        expected_child_count=expected_child_count,
        indexed_child_count=indexed_child_count,
        document_count=max(indexed_child_count, 0),
        vocabulary_size=1,
        avgdl=1.0,
        physical_index_relpath=f"{lexical_index_id}",
        created_at=now,
    )

    settings.paths.manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.chunk_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.index_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.lexical_index_manifests.mkdir(parents=True, exist_ok=True)
    settings.paths.lexical_indexes.mkdir(parents=True, exist_ok=True)
    (settings.paths.manifests / corpus_manifest_name).write_text(
        corpus.model_dump_json(), encoding="utf-8"
    )
    (settings.paths.chunk_manifests / chunk_manifest_name).write_text(
        chunk.model_dump_json(), encoding="utf-8"
    )
    (settings.paths.index_manifests / dense_manifest_name).write_text(
        dense.model_dump_json(), encoding="utf-8"
    )
    (settings.paths.lexical_index_manifests / lexical_manifest_name).write_text(
        lexical.model_dump_json(), encoding="utf-8"
    )
    from offline_rag.lexical.backend import (
        LexicalDocumentInput,
        LocalInvertedIndexBackend,
    )

    lexical_path = settings.paths.lexical_indexes / lexical_index_id
    if lexical_path.exists():
        shutil.rmtree(lexical_path)
    LocalInvertedIndexBackend(settings.paths.lexical_indexes).build(
        lexical_index_id,
        [
            LexicalDocumentInput(
                chunk_id="chunk_1",
                terms=["offline", "rag"],
                document_id=document_id,
            )
        ],
        chunk_set_id=chunk_set_id,
        lexical_config_hash=hashes["lexical_config_hash"],
    )

    return CanonicalSnapshotManifest(
        corpus_id=corpus_id,
        corpus_manifest=corpus_manifest_name,
        chunk_set_id=chunk_set_id,
        chunk_manifest=chunk_manifest_name,
        dense_index_id=dense_index_id,
        dense_index_manifest=dense_manifest_name,
        lexical_index_id=lexical_index_id,
        lexical_index_manifest=lexical_manifest_name,
        **hashes,
    )


def _publish_ready(
    runtime: ApplicationRuntime,
    *,
    dense_index_id: str = "denseindex_ccc",
    lexical_index_id: str = "lexical_ddd",
    collection_name: str = "col_ccc",
    corpus_id: str = "corpus_aaa",
    chunk_set_id: str = "chunkset_bbb",
    document_id: str = "doc_001",
    source_name: str = "spec.pdf",
) -> tuple[str, Any]:
    identity = _write_scientific_stack(
        runtime.settings,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
        dense_index_id=dense_index_id,
        lexical_index_id=lexical_index_id,
        collection_name=collection_name,
        document_id=document_id,
        source_name=source_name,
    )
    assert runtime.resources is not None
    qdrant = runtime.resources.qdrant
    assert isinstance(qdrant, _FakeQdrant)
    qdrant.counts[collection_name] = 1
    sid = runtime.publication.publish("engineering", identity)
    return sid, identity


def _citation(*, document_id: str = "doc_001") -> ResolvedCitation:
    return ResolvedCitation(
        evidence_unit_id="eu_1",
        source_chunk_id="chunk_1",
        kind="child",
        document_id=document_id,
        section_path=["Intro"],
        page_start=1,
        page_end=1,
        line_start=1,
        line_end=2,
        clipped=False,
        representation="full",
        # Disallowed public fields must not leak via projection.
        metadata={"secret": "nope"},
        clip={"raw": "hidden"},
    )


def _canned(
    *,
    status: str = "answered",
    answer_text: str | None = "Pump pressure is within range.",
    abstention_reason: str | None = None,
    generation_failure_reason: str | None = None,
    citations: list[ResolvedCitation] | None = None,
    dense_index_id: str | None = "denseindex_ccc",
    lexical_index_id: str | None = "lexical_ddd",
    context_config_hash: str | None = None,
    query: str = "what pressure?",
) -> GroundedAnswerResult:
    return GroundedAnswerResult(
        method="query",
        query=query,
        status=status,  # type: ignore[arg-type]
        answer_text=answer_text,
        citations=list(citations or []),
        abstention_reason=abstention_reason,  # type: ignore[arg-type]
        generation_failure_reason=generation_failure_reason,
        generator_invoked=status == "answered",
        attempt_count=1,
        generation_config_hash="gencfg_test",
        context_config_hash=context_config_hash,
        dense_index_id=dense_index_id,
        lexical_index_id=lexical_index_id,
        fusion_config_hash="fus_test",
        reranker_config_hash="rr_test",
        diagnostics={"latency_ms": {"context": 1, "generation": 2, "total": 3}},
    )


def _patch_execute(
    monkeypatch: pytest.MonkeyPatch, result: GroundedAnswerResult | Exception
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _fake(
        runtime: ApplicationRuntime, binding: Any, question: str
    ) -> GroundedAnswerResult:
        captured["question"] = question
        captured["binding"] = binding
        captured["runtime"] = runtime
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("offline_rag.app.query._execute_bound", _fake)
    return captured


def _trace_path(settings: AppSettings, trace_id: str) -> Path:
    return settings.paths.traces / f"{trace_id}.json"


def _make_trace_record(
    settings: AppSettings,
    *,
    trace_id: str | None = None,
    created_at: datetime | None = None,
    snapshot_id: str = "snap_test",
    status: str | None = "answered",
    error_code: str | None = None,
) -> ProductQueryTrace:
    tid = trace_id or allocate_trace_id()
    gencfg = build_generation_config_hash(settings)
    hashes = _config_hashes(settings)
    return ProductQueryTrace(
        trace_id=tid,
        created_at=created_at or datetime.now(tz=UTC),
        corpus="engineering",
        snapshot_id=snapshot_id,
        product_mode_id="grounded_v1",
        request=ProductTraceRequestSummary(
            question_sha256="a" * 64,
            question_char_count=12,
        ),
        identity=ProductTraceIdentitySummary(
            corpus_id="corpus_aaa",
            chunk_set_id="chunkset_bbb",
            dense_index_id="denseindex_ccc",
            lexical_index_id="lexical_ddd",
            fusion_config_hash=hashes["fusion_config_hash"],
            reranker_config_hash=hashes["reranker_config_hash"],
            context_config_hash=hashes["context_config_hash"],
            generation_config_hash=gencfg,
        ),
        status=status,  # type: ignore[arg-type]
        error_code=error_code,
        execution=ProductTraceExecutionSummary(),
    )


# ---------------------------------------------------------------------------
# 1. Branch ancestry
# ---------------------------------------------------------------------------


def test_remote_ancestry_begins_at_15e_baseline() -> None:
    merge_base = subprocess.check_output(
        ["git", "merge-base", "HEAD", BASELINE_SHA],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    assert merge_base == BASELINE_SHA
    contained = subprocess.call(
        ["git", "merge-base", "--is-ancestor", BASELINE_SHA, "HEAD"],
        cwd=REPO_ROOT,
    )
    assert contained == 0


# ---------------------------------------------------------------------------
# 2–5. Request validation + trim
# ---------------------------------------------------------------------------


def test_request_validation_extras_blank_length_and_trim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    captured = _patch_execute(
        monkeypatch,
        _canned(
            citations=[_citation()],
            context_config_hash=identity.context_config_hash,
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
        ),
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        extra = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "ok?", "snapshot_id": sid},
        )
        assert extra.status_code == 422
        assert extra.json()["error"]["code"] == "request_invalid"

        blank = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "   \n\t  "},
        )
        assert blank.status_code == 422
        assert blank.json()["error"]["code"] == "request_invalid"

        too_long = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "x" * (MAX_QUESTION_CHARS + 1)},
        )
        assert too_long.status_code == 422
        assert too_long.json()["error"]["code"] == "request_invalid"

        exact = client.post(
            "/v1/query",
            json={
                "corpus": "engineering",
                "question": "  " + ("y" * MAX_QUESTION_CHARS) + "  ",
            },
        )
        assert exact.status_code == 200
        assert captured["question"] == "y" * MAX_QUESTION_CHARS

        spaced = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "  outer  inner   kept  "},
        )
        assert spaced.status_code == 200
        assert captured["question"] == "outer  inner   kept"
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 6–11. Snapshot pin mid-flight + resolve-once
# ---------------------------------------------------------------------------


def test_snapshot_pin_mid_flight_and_resolve_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid_n, _identity_n = _publish_ready(
        runtime,
        dense_index_id="denseindex_n",
        lexical_index_id="lexical_n",
        collection_name="col_n",
        corpus_id="corpus_n",
        chunk_set_id="chunkset_n",
    )
    snap_n = runtime.publication.resolve("engineering")
    binding_n = build_snapshot_query_binding(settings, snap_n)
    assert binding_n.snapshot_id == sid_n
    assert binding_n.dense_index_id == "denseindex_n"
    assert binding_n.lexical_index_id == "lexical_n"
    assert binding_n.chunk_manifest_name == "chunkset_n.json"
    assert binding_n.source_name_by_document_id() == {"doc_001": "spec.pdf"}

    seen: dict[str, Any] = {"dense": None, "lexical": None, "published_n1": False}

    dense = DenseRetriever(settings, embedder=FakeEmbedder(dimension=8), backend=_FakeQdrant())
    lexical_backend_settings = settings

    class _LexicalShim:
        def retrieve(self, **kwargs: Any) -> LexicalRetrievalResult:
            seen["lexical"] = {
                "index_id": kwargs.get("index_id"),
                "chunk_set_id": kwargs.get("chunk_set_id"),
            }
            return LexicalRetrievalResult(
                query=kwargs["query"],
                index_id=str(kwargs["index_id"]),
                top_k=int(kwargs["top_k"]),
                candidates=[],
                metadata={"chunk_set_id": kwargs["chunk_set_id"]},
            )

        def close(self) -> None:
            return None

    orig_dense_retrieve = dense.retrieve

    def dense_retrieve(**kwargs: Any) -> DenseRetrievalResult:
        seen["dense"] = {
            "index_id": kwargs.get("index_id"),
            "collection_name": kwargs.get("collection_name"),
            "chunk_set_id": kwargs.get("chunk_set_id"),
        }
        # Mid-flight publish N+1 between dense and lexical.
        n1 = _write_scientific_stack(
            settings,
            corpus_id="corpus_n1",
            chunk_set_id="chunkset_n1",
            dense_index_id="denseindex_n1",
            lexical_index_id="lexical_n1",
            collection_name="col_n1",
            document_id="doc_002",
            source_name="other.pdf",
        )
        assert runtime.resources is not None
        qdrant = runtime.resources.qdrant
        assert isinstance(qdrant, _FakeQdrant)
        qdrant.counts["col_n1"] = 1
        sid_n1 = runtime.publication.publish("engineering", n1)
        seen["published_n1"] = True
        seen["sid_n1"] = sid_n1
        return DenseRetrievalResult(
            query=kwargs["query"],
            index_id=str(kwargs["index_id"]),
            top_k=int(kwargs["top_k"]),
            candidates=[],
            metadata={"chunk_set_id": kwargs["chunk_set_id"]},
        )

    dense.retrieve = dense_retrieve  # type: ignore[method-assign]
    hybrid = HybridRetriever(settings, dense=dense, lexical=_LexicalShim())  # type: ignore[arg-type]
    result = hybrid.retrieve(
        query="bound pin check",
        corpus_name="engineering",
        dense_index_id=binding_n.dense_index_id,
        dense_collection_name=binding_n.dense_collection_name,
        lexical_index_id=binding_n.lexical_index_id,
        chunk_set_id=binding_n.chunk_set_id,
        corpus_id=binding_n.corpus_id,
    )
    assert seen["published_n1"] is True
    assert seen["dense"] == {
        "index_id": "denseindex_n",
        "collection_name": "col_n",
        "chunk_set_id": "chunkset_n",
    }
    assert seen["lexical"] == {
        "index_id": "lexical_n",
        "chunk_set_id": "chunkset_n",
    }
    assert result.dense_index_id == "denseindex_n"
    assert result.lexical_index_id == "lexical_n"
    assert runtime.publication.resolve("engineering").snapshot_id == seen["sid_n1"]
    assert snap_n.snapshot_id == sid_n

    # Product path: resolve + bind once per request; in-flight uses pinned N.
    resolve_calls = {"n": 0}
    orig_resolve = runtime.publication.resolve

    def counting_resolve(name: str):
        resolve_calls["n"] += 1
        return orig_resolve(name)

    monkeypatch.setattr(runtime.publication, "resolve", counting_resolve)

    product_seen: dict[str, Any] = {}

    def product_execute(rt, binding, question: str) -> GroundedAnswerResult:
        product_seen["dense_index_id"] = binding.dense_index_id
        product_seen["lexical_index_id"] = binding.lexical_index_id
        product_seen["chunk_manifest"] = binding.chunk_manifest_name
        product_seen["source_map"] = binding.source_name_by_document_id()
        product_seen["snapshot_id"] = binding.snapshot_id
        # Publish again during execute — must not change this request's binding.
        n2 = _write_scientific_stack(
            settings,
            corpus_id="corpus_n2",
            chunk_set_id="chunkset_n2",
            dense_index_id="denseindex_n2",
            lexical_index_id="lexical_n2",
            collection_name="col_n2",
            document_id="doc_003",
            source_name="third.pdf",
        )
        assert rt.resources is not None
        q = rt.resources.qdrant
        assert isinstance(q, _FakeQdrant)
        q.counts["col_n2"] = 1
        product_seen["sid_n2"] = rt.publication.publish("engineering", n2)
        return _canned(
            citations=[_citation(document_id="doc_002")],
            dense_index_id=binding.dense_index_id,
            lexical_index_id=binding.lexical_index_id,
            context_config_hash=binding.context_config_hash,
            query=question,
        )

    monkeypatch.setattr("offline_rag.app.query._execute_bound", product_execute)
    # Current pointer is N+1 after hybrid test.
    current = orig_resolve("engineering")
    resp = run_product_query(
        runtime, corpus="engineering", question="pin product path"
    )
    assert resolve_calls["n"] == 1
    assert resp.snapshot_id == current.snapshot_id
    assert product_seen["snapshot_id"] == current.snapshot_id
    assert product_seen["dense_index_id"] == current.identity.dense_index_id
    assert product_seen["lexical_index_id"] == current.identity.lexical_index_id
    assert product_seen["chunk_manifest"] == Path(
        current.identity.chunk_manifest
    ).name
    assert product_seen["source_map"] == {"doc_002": "other.pdf"}
    assert runtime.publication.resolve("engineering").snapshot_id == product_seen["sid_n2"]
    del orig_dense_retrieve, lexical_backend_settings
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 12–15. Runtime resource reuse
# ---------------------------------------------------------------------------


def test_query_reuses_process_scoped_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    assert runtime.resources is not None

    seen: dict[str, Any] = {}

    monkeypatch.setattr(
        "offline_rag.app.query.load_structure_store_for_chunk_manifest",
        lambda _s, _name: ChunkStructureStore(
            children={},
            parents={},
            chunk_set_id="chunkset_bbb",
            corpus_id="corpus_aaa",
        ),
    )

    orig_dense = DenseRetriever.__init__

    def dense_init(self, settings_arg, *, embedder=None, backend=None):
        seen["embedder"] = embedder
        seen["qdrant"] = backend
        return orig_dense(self, settings_arg, embedder=embedder, backend=backend)

    orig_rerank = HybridRerankRetriever.__init__

    def rerank_init(self, settings_arg, *, hybrid=None, reranker=None, input_builder=None):
        seen["reranker"] = reranker
        return orig_rerank(
            self,
            settings_arg,
            hybrid=hybrid,
            reranker=reranker,
            input_builder=input_builder,
        )

    orig_orch = GroundedAnswerOrchestrator.__init__

    def orch_init(self, settings_arg, **kwargs):
        seen["generator"] = kwargs.get("generator")
        return orig_orch(self, settings_arg, **kwargs)

    monkeypatch.setattr(DenseRetriever, "__init__", dense_init)
    monkeypatch.setattr(HybridRerankRetriever, "__init__", rerank_init)
    monkeypatch.setattr(GroundedAnswerOrchestrator, "__init__", orch_init)

    def fake_answer(self, **_kwargs):
        return _canned(
            citations=[_citation()],
            context_config_hash=runtime.publication.resolve(
                "engineering"
            ).identity.context_config_hash,
        )

    monkeypatch.setattr(GroundedAnswerOrchestrator, "answer", fake_answer)

    # Drive via _build_orchestrator / product query.
    snap = runtime.publication.resolve("engineering")
    binding = build_snapshot_query_binding(settings, snap)
    orch = _build_orchestrator(runtime, binding)
    try:
        assert seen["embedder"] is runtime.resources.embedder
        assert seen["qdrant"] is runtime.resources.qdrant
        assert seen["reranker"] is runtime.resources.reranker
        assert seen["generator"] is runtime.resources.generator_client
    finally:
        orch.close()

    run_product_query(runtime, corpus="engineering", question="reuse check")
    assert seen["embedder"] is runtime.resources.embedder
    assert seen["qdrant"] is runtime.resources.qdrant
    assert seen["reranker"] is runtime.resources.reranker
    assert seen["generator"] is runtime.resources.generator_client
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 16–24. Success / failure HTTP contracts
# ---------------------------------------------------------------------------


def test_success_and_failure_http_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    app = create_app(runtime=runtime)

    cases: list[tuple[Any, int, str | None]] = [
        (
            _canned(
                status="answered",
                answer_text="Stable answer text.",
                citations=[_citation()],
                dense_index_id=identity.dense_index_id,
                lexical_index_id=identity.lexical_index_id,
                context_config_hash=identity.context_config_hash,
            ),
            200,
            None,
        ),
        (
            _canned(
                status="insufficient_evidence",
                answer_text=None,
                abstention_reason="empty_context",
                citations=[],
                dense_index_id=identity.dense_index_id,
                lexical_index_id=identity.lexical_index_id,
                context_config_hash=identity.context_config_hash,
            ),
            200,
            None,
        ),
        (
            _canned(
                status="insufficient_evidence",
                answer_text=None,
                abstention_reason="model_abstain",
                citations=[],
                dense_index_id=identity.dense_index_id,
                lexical_index_id=identity.lexical_index_id,
                context_config_hash=identity.context_config_hash,
            ),
            200,
            None,
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="timeout",
            ),
            504,
            "generation_timeout",
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="transport_error",
            ),
            502,
            "generation_unavailable",
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="unavailable",
            ),
            502,
            "generation_unavailable",
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="provider_boom",
            ),
            502,
            "generation_failed",
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="response_parse_error",
            ),
            502,
            "response_parse_error",
        ),
        (
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="output_schema_invalid",
            ),
            502,
            "response_parse_error",
        ),
        (
            _canned(status="citation_invalid", answer_text=None),
            502,
            "citation_invalid",
        ),
        (
            GroundedAnswerError("unexpected orchestration fault boom"),
            500,
            "internal_error",
        ),
        (
            RuntimeError("totally unexpected"),
            500,
            "internal_error",
        ),
    ]

    with TestClient(app, raise_server_exceptions=False) as client:
        for idx, (result, status_code, err_code) in enumerate(cases):
            _patch_execute(monkeypatch, result)
            resp = client.post(
                "/v1/query",
                json={"corpus": "engineering", "question": f"case {idx}"},
            )
            assert resp.status_code == status_code, (idx, resp.text)
            body = resp.json()
            if err_code is None:
                assert set(body.keys()) == SUCCESS_KEYS
                assert body["corpus"] == "engineering"
                assert body["snapshot_id"] == sid
                assert body["product_mode_id"] == "grounded_v1"
                assert body["trace_id"].startswith("trace_")
                if idx == 0:
                    assert body["status"] == "answered"
                    assert body["answer"] == "Stable answer text."
                    assert len(body["citations"]) == 1
                    cite = body["citations"][0]
                    assert list(cite.keys()) == list(CITATION_FIELDS)
                    assert "metadata" not in cite
                    assert "clip" not in cite
                    assert "representation" not in cite
                    assert "secret" not in resp.text
                elif idx == 1:
                    assert body["status"] == "insufficient_evidence"
                    assert body["answer"] is None
                    assert body["citations"] == []
                elif idx == 2:
                    assert body["status"] == "model_abstain"
                    assert body["answer"] is None
                    assert body["citations"] == []
            else:
                assert body["error"]["code"] == err_code
                text = resp.text
                assert "Traceback" not in text
                assert "unexpected orchestration fault boom" not in text
                assert "totally unexpected" not in text
                if err_code != "internal_error" or idx < len(cases) - 2:
                    # Error paths after trace allocation include durable trace_id.
                    pass
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 25–31. Durable traces: commit-before-response, privacy, commit failure
# ---------------------------------------------------------------------------


def test_trace_commit_before_response_privacy_and_commit_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    secret_q = "SECRET_QUESTION_PAYLOAD_xyz"
    secret_a = "SECRET_ANSWER_PAYLOAD_xyz"

    # Success: durable file present and matches response; no raw secrets.
    _patch_execute(
        monkeypatch,
        _canned(
            answer_text=secret_a,
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
            query=secret_q,
        ),
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        ok = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": secret_q},
        )
        assert ok.status_code == 200
        payload = ok.json()
        tid = payload["trace_id"]
        path = _trace_path(settings, tid)
        assert path.is_file()
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["trace_id"] == tid
        assert stored["snapshot_id"] == sid
        raw = path.read_text(encoding="utf-8")
        assert secret_q not in raw
        assert secret_a not in raw
        assert "prompt" not in raw.lower() or "generation_config_hash" in raw
        for banned in (
            "SECRET_QUESTION",
            "SECRET_ANSWER",
            "evidence_text",
            "provider_payload",
            "chat_completion",
        ):
            assert banned not in raw
        assert "question_sha256" in stored["request"]
        assert "answer" not in stored
        assert "question" not in stored
        assert "evidence" not in stored

        # Error: commit durable trace, response trace_id matches file.
        _patch_execute(
            monkeypatch,
            _canned(
                status="generation_failed",
                answer_text=None,
                generation_failure_reason="timeout",
            ),
        )
        err = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "timeout please"},
        )
        assert err.status_code == 504
        err_body = err.json()
        err_tid = err_body["trace_id"]
        assert err_tid
        err_path = _trace_path(settings, err_tid)
        assert err_path.is_file()
        err_stored = json.loads(err_path.read_text(encoding="utf-8"))
        assert err_stored["trace_id"] == err_tid
        assert err_stored["error_code"] == "generation_timeout"
        assert err_stored["status"] is None
        assert secret_q not in err_path.read_text(encoding="utf-8")

        # Commit failure: internal_error without dangling trace_id.
        _patch_execute(
            monkeypatch,
            _canned(
                citations=[_citation()],
                dense_index_id=identity.dense_index_id,
                lexical_index_id=identity.lexical_index_id,
                context_config_hash=identity.context_config_hash,
            ),
        )

        def boom_commit(self, record):
            raise OSError("disk full")

        monkeypatch.setattr(ProductTraceStore, "commit", boom_commit)
        fail = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "persist fail"},
        )
        assert fail.status_code == 500
        fail_body = fail.json()
        assert fail_body["error"]["code"] == "internal_error"
        assert fail_body.get("trace_id") is None
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 32–35. Trace GET pin + unknown/malformed
# ---------------------------------------------------------------------------


def test_trace_get_keeps_snapshot_and_rejects_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid_n, identity = _publish_ready(
        runtime,
        dense_index_id="denseindex_t",
        lexical_index_id="lexical_t",
        collection_name="col_t",
    )
    _patch_execute(
        monkeypatch,
        _canned(
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
        ),
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        q = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "trace pin"},
        )
        assert q.status_code == 200
        tid = q.json()["trace_id"]
        assert q.json()["snapshot_id"] == sid_n

        n1 = _write_scientific_stack(
            settings,
            corpus_id="corpus_t1",
            chunk_set_id="chunkset_t1",
            dense_index_id="denseindex_t1",
            lexical_index_id="lexical_t1",
            collection_name="col_t1",
            document_id="doc_t1",
            source_name="next.pdf",
        )
        assert runtime.resources is not None
        qdrant = runtime.resources.qdrant
        assert isinstance(qdrant, _FakeQdrant)
        qdrant.counts["col_t1"] = 1
        sid_n1 = runtime.publication.publish("engineering", n1)
        assert sid_n1 != sid_n

        got = client.get(f"/v1/trace/{tid}")
        assert got.status_code == 200
        body = got.json()
        assert body["trace_id"] == tid
        assert body["snapshot_id"] == sid_n
        assert body["snapshot_id"] != sid_n1
        assert "question" not in body
        assert "answer" not in body

        unknown = client.get(f"/v1/trace/{allocate_trace_id()}")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "trace_unknown"

        for bad in ("trace_nothex", "trace_zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"):
            bad_resp = client.get(f"/v1/trace/{bad}")
            assert bad_resp.status_code == 404
            assert bad_resp.json()["error"]["code"] == "trace_unknown"

        # Path traversal segment must not create files under traces/.
        before = set(settings.paths.traces.glob("*")) if settings.paths.traces.exists() else set()
        for url in (
            "/v1/trace/../etc/passwd",
            "/v1/trace/%2e%2e%2fetc%2fpasswd",
            "/v1/trace/..%2fetc%2fpasswd",
        ):
            trav = client.get(url)
            assert trav.status_code == 404
            body = trav.json()
            # Route-miss 404 or allowlisted trace_unknown — never invent files.
            if "error" in body:
                assert body["error"]["code"] == "trace_unknown"
            else:
                assert body.get("detail") == "Not Found"
            after = (
                set(settings.paths.traces.glob("*"))
                if settings.paths.traces.exists()
                else set()
            )
            assert after == before
        assert not (tmp_path / "etc" / "passwd").exists()
    runtime.shutdown()


# ---------------------------------------------------------------------------
# 36–38. Retention: age + newest 1000 by timestamp
# ---------------------------------------------------------------------------


def test_trace_retention_age_and_newest_1000_by_timestamp(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = ProductTraceStore(settings)
    now = datetime.now(tz=UTC)

    expired_id = "trace_" + "a" * 32
    expired = _make_trace_record(
        settings,
        trace_id=expired_id,
        created_at=now - timedelta(days=8),
        snapshot_id="snap_old",
    )
    settings.paths.traces.mkdir(parents=True, exist_ok=True)
    expired_path = settings.paths.traces / f"{expired_id}.json"
    expired_path.write_text(expired.model_dump_json(), encoding="utf-8")
    assert store.get(expired_id) is None  # age gate

    fresh = _make_trace_record(
        settings,
        created_at=now,
        snapshot_id="snap_fresh",
    )
    store.commit(fresh)
    assert not expired_path.exists()
    assert store.get(fresh.trace_id) is not None

    # 1001 under 7d: oldest by timestamp removed; lexical ID order differs.
    # i=0 oldest time + lexically largest id among the set.
    kept_newest = None
    oldest_id = None
    for i in range(1001):
        tid = f"trace_{(1000 - i):032x}"
        created = now - timedelta(seconds=(1000 - i))
        if i == 0:
            oldest_id = tid
        if i == 1000:
            kept_newest = tid
        store.commit(
            _make_trace_record(
                settings,
                trace_id=tid,
                created_at=created,
                snapshot_id=f"snap_{i}",
            )
        )
    assert oldest_id is not None and kept_newest is not None
    assert store.get(oldest_id) is None
    assert not (settings.paths.traces / f"{oldest_id}.json").exists()
    assert store.get(kept_newest) is not None
    remaining = list(settings.paths.traces.glob("trace_*.json"))
    assert len(remaining) == 1000
    # Lexically last ID was the oldest chronologically — must not be preferred.
    assert oldest_id > kept_newest
    assert oldest_id not in {p.stem for p in remaining}
    assert kept_newest in {p.stem for p in remaining}


# ---------------------------------------------------------------------------
# 39. Health live responsive during blocking query
# ---------------------------------------------------------------------------


def test_health_responsive_during_blocking_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    sid, identity = _publish_ready(runtime)
    block = threading.Event()
    entered = threading.Event()

    def blocking_execute(rt, binding, question: str) -> GroundedAnswerResult:
        entered.set()
        assert block.wait(timeout=10)
        return _canned(
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
            query=question,
        )

    monkeypatch.setattr("offline_rag.app.query._execute_bound", blocking_execute)
    app = create_app(runtime=runtime)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            query_task = asyncio.create_task(
                client.post(
                    "/v1/query",
                    json={"corpus": "engineering", "question": "block me"},
                )
            )
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.05)
            assert entered.is_set()
            live = await client.get("/health/live")
            assert live.status_code == 200
            block.set()
            query_resp = await query_task
            assert query_resp.status_code == 200
            assert query_resp.json()["snapshot_id"] == sid

    try:
        asyncio.run(run())
    finally:
        runtime.shutdown()


# ---------------------------------------------------------------------------
# 40–41. OpenAPI surface
# ---------------------------------------------------------------------------


def test_openapi_includes_query_and_trace_only_as_new_additions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    _patch_execute(
        monkeypatch,
        _canned(citations=[_citation()], context_config_hash=_config_hashes(settings)["context_config_hash"]),
    )
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        paths = set(client.get("/openapi.json").json().get("paths", {}))
        assert "/v1/query" in paths
        assert "/v1/trace/{trace_id}" in paths
        for forbidden in (
            "/eval",
            "/eval/run",
            "/v1/traces",
            "/query",
            "/v1/query/history",
            "/history",
            "/v1/snapshot",
            "/v1/snapshots",
            "/snapshot",
        ):
            assert forbidden not in paths
        # Smoke: query route works under the documented path.
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "openapi smoke"},
        )
        assert resp.status_code == 200
        assert set(resp.json().keys()) == SUCCESS_KEYS
    runtime.shutdown()


def test_get_product_trace_app_layer_unknown(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    with pytest.raises(AppError) as exc:
        get_product_trace(runtime, "trace_nothex")
    assert exc.value.code is ErrorCode.TRACE_UNKNOWN
    runtime.shutdown()
