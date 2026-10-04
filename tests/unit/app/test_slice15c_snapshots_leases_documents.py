"""Phase 15C — publication registry, leases, documents, candidate recovery."""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.candidate_recovery import recover_abandoned_candidates
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.leases import CorpusMutationLease
from offline_rag.app.publication import (
    ProductPublicationRegistry,
    current_pointer_path,
)
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.snapshot import (
    CanonicalSnapshotManifest,
    compute_snapshot_id,
)
from offline_rag.chunking.tokenize import TiktokenTokenCounter
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.domain.chunking import ChunkSetManifest
from offline_rag.domain.corpus import CorpusDocumentEntry, CorpusManifest, CorpusState
from offline_rag.domain.indexing import DenseIndexManifest, LexicalIndexManifest
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.ingestion.persistence import corpus_state_path, write_corpus_state
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.rerank.config_hash import build_reranker_config_hash

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"


class _FakeCloseable:
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
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
        }
    )
    settings = settings.model_copy(update={"generation": generation})
    _provision_assets(settings)
    return settings


def _factories(qdrant: _FakeQdrant | None = None) -> ResourceFactories:
    q = qdrant if qdrant is not None else _FakeQdrant()

    def _q(_settings: AppSettings) -> _FakeQdrant:
        return q

    return ResourceFactories(
        embedder=lambda _s: _FakeCloseable(),
        reranker=lambda _s: _FakeCloseable(),
        generator_client=lambda _s: _FakeCloseable(),
        qdrant=_q,
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
    lexical_expected_child_count: int | None = None,
    lexical_indexed_child_count: int | None = None,
    build_lexical: bool = True,
) -> CanonicalSnapshotManifest:
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
        expected_child_count=(
            expected_child_count
            if lexical_expected_child_count is None
            else lexical_expected_child_count
        ),
        indexed_child_count=(
            indexed_child_count
            if lexical_indexed_child_count is None
            else lexical_indexed_child_count
        ),
        document_count=max(
            indexed_child_count
            if lexical_indexed_child_count is None
            else lexical_indexed_child_count,
            0,
        ),
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
    if build_lexical:
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
    else:
        # Invalid directory-only remnant (must not certify grounded readiness).
        (settings.paths.lexical_indexes / lexical_index_id).mkdir(
            parents=True, exist_ok=True
        )
        (settings.paths.lexical_indexes / lexical_index_id / "index").write_text(
            "ok", encoding="utf-8"
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


def test_identical_constituents_yield_identical_snapshot_id(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    a = _write_scientific_stack(settings)
    b = CanonicalSnapshotManifest.model_validate(a.model_dump())
    assert compute_snapshot_id(a) == compute_snapshot_id(b)


def test_identity_change_changes_snapshot_id(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    base = _write_scientific_stack(settings)
    changed = base.model_copy(update={"chunk_set_id": "chunkset_other"})
    assert compute_snapshot_id(base) != compute_snapshot_id(changed)


def test_stage_state_without_publication_is_corpus_unknown(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    identity = _write_scientific_stack(settings)
    # Legacy mutable stage pointer present — product publication absent.
    write_corpus_state(
        corpus_state_path(settings.paths.corpora, "engineering"),
        CorpusState(
            corpus_name="engineering",
            current_corpus_id=identity.corpus_id,
            current_manifest=identity.corpus_manifest,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
        ),
    )
    registry = ProductPublicationRegistry(settings, qdrant=_FakeQdrant())
    with pytest.raises(AppError) as exc:
        registry.resolve("engineering")
    assert exc.value.code is ErrorCode.CORPUS_UNKNOWN


def test_atomic_publish_and_resolve_pinning(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    n = _write_scientific_stack(
        settings,
        dense_index_id="denseindex_n",
        collection_name="col_n",
        lexical_index_id="lexical_n",
    )
    qdrant.counts["col_n"] = 1
    sid_n = registry.publish("engineering", n)
    snap_n = registry.resolve("engineering")
    assert snap_n.snapshot_id == sid_n

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
    qdrant.counts["col_n1"] = 1
    sid_n1 = registry.publish("engineering", n1)
    assert sid_n1 != sid_n
    snap_new = registry.resolve("engineering")
    assert snap_new.snapshot_id == sid_n1
    # Previously resolved object remains N.
    assert snap_n.snapshot_id == sid_n
    assert snap_n.identity.corpus_id == n.corpus_id


def test_publish_failure_before_pointer_leaves_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_a"] = 1
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    n = _write_scientific_stack(
        settings,
        dense_index_id="denseindex_a",
        lexical_index_id="lexical_a",
        collection_name="col_a",
    )
    sid_n = registry.publish("engineering", n)

    n1 = _write_scientific_stack(
        settings,
        corpus_id="corpus_b",
        chunk_set_id="chunkset_b",
        dense_index_id="denseindex_b",
        lexical_index_id="lexical_b",
        collection_name="col_b",
    )
    qdrant.counts["col_b"] = 1

    from offline_rag.ingestion import io as io_mod

    real = io_mod.atomic_write_text

    def selective(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        if path.name == "current.json":
            raise RuntimeError("pointer write failed")
        return real(path, text, encoding=encoding)

    monkeypatch.setattr("offline_rag.app.publication.atomic_write_text", selective)
    with pytest.raises(RuntimeError, match="pointer write failed"):
        registry.publish("engineering", n1)
    assert registry.resolve("engineering").snapshot_id == sid_n


def test_incompatible_published_snapshot_corpus_not_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(settings)
    registry.publish("engineering", identity)
    # Provenance drift on an immutable backing artifact → not grounded-ready.
    dense_path = settings.paths.index_manifests / identity.dense_index_manifest
    dense = DenseIndexManifest.model_validate_json(dense_path.read_text(encoding="utf-8"))
    dense = dense.model_copy(update={"chunk_set_id": "chunkset_wrong"})
    dense_path.write_text(dense.model_dump_json(), encoding="utf-8")
    with pytest.raises(AppError) as exc:
        registry.resolve("engineering")
    assert exc.value.code is ErrorCode.CORPUS_NOT_READY


def test_missing_artifact_snapshot_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(settings)
    registry.publish("engineering", identity)
    (settings.paths.manifests / identity.corpus_manifest).unlink()
    with pytest.raises(AppError) as exc:
        registry.resolve("engineering")
    assert exc.value.code is ErrorCode.SNAPSHOT_UNAVAILABLE


def test_same_corpus_lease_busy_and_different_corpus_coexist(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.paths.locks.mkdir(parents=True, exist_ok=True)
    a = CorpusMutationLease(settings, "alpha")
    b = CorpusMutationLease(settings, "alpha")
    c = CorpusMutationLease(settings, "beta")
    a.acquire()
    with pytest.raises(AppError) as exc:
        b.acquire()
    assert exc.value.code is ErrorCode.CORPUS_BUSY
    assert exc.value.retryable is True
    c.acquire()
    assert c.held
    a.release()
    c.release()


def test_holder_process_death_releases_lease(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.paths.locks.mkdir(parents=True, exist_ok=True)
    lock_path = settings.paths.locks / "corpus.crashdemo.lock"
    script = textwrap.dedent(
        f"""
        import fcntl, os, time
        path = {str(lock_path)!r}
        os.makedirs({str(settings.paths.locks)!r}, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(1, b"HELD\\n")
        time.sleep(60)
        """
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    line = proc.stdout.readline()
    assert line.strip() == b"HELD"
    # Contending acquire while holder alive must fail.
    busy = CorpusMutationLease(settings, "crashdemo")
    with pytest.raises(AppError) as exc:
        busy.acquire()
    assert exc.value.code is ErrorCode.CORPUS_BUSY
    proc.kill()
    proc.wait(timeout=5)
    # After death, lease is acquirable.
    winner = CorpusMutationLease(settings, "crashdemo")
    winner.acquire()
    assert winner.held
    winner.release()


def test_abandoned_candidate_recovery_never_changes_pointer(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(settings)
    sid = registry.publish("engineering", identity)
    cand = settings.paths.corpora / "engineering" / "candidates" / "cand_1"
    cand.mkdir(parents=True)
    (cand / "note.txt").write_text("partial", encoding="utf-8")
    pointer_before = current_pointer_path(settings.paths.corpora, "engineering").read_text(
        encoding="utf-8"
    )
    moved = recover_abandoned_candidates(settings)
    assert moved
    assert not cand.exists()
    assert (settings.paths.corpora / "engineering" / "abandoned").exists()
    pointer_after = current_pointer_path(settings.paths.corpora, "engineering").read_text(
        encoding="utf-8"
    )
    assert pointer_before == pointer_after
    assert registry.resolve("engineering").snapshot_id == sid


def test_documents_http_surface(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    runtime = ApplicationRuntime(settings=settings, factories=_factories(qdrant))
    runtime.start()
    identity = _write_scientific_stack(settings)
    sid = runtime.publication.publish("engineering", identity)
    app = create_app(runtime=runtime)
    # Runtime already started; TestClient lifespan will start again — make idempotent READY.
    with TestClient(app, raise_server_exceptions=False) as client:
        missing = client.get("/v1/documents")
        assert missing.status_code == 422
        body = missing.json()
        assert body["error"]["code"] == "request_invalid"
        assert body["retryable"] is False

        # Stage state alone must not expose product inventory.
        write_corpus_state(
            corpus_state_path(settings.paths.corpora, "ghost"),
            CorpusState(
                corpus_name="ghost",
                current_corpus_id=identity.corpus_id,
                current_manifest=identity.corpus_manifest,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            ),
        )
        ghost = client.get("/v1/documents", params={"corpus": "ghost"})
        assert ghost.status_code == 404
        assert ghost.json()["error"]["code"] == "corpus_unknown"

        listed = client.get("/v1/documents", params={"corpus": "engineering"})
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["corpus"] == "engineering"
        assert payload["snapshot_id"] == sid
        assert len(payload["documents"]) == 1
        doc = payload["documents"][0]
        assert doc["document_id"] == "doc_001"
        assert doc["source_name"] == "spec.pdf"
        assert "source_path" not in doc
        assert "/secret/" not in listed.text

        one = client.get(
            "/v1/documents/doc_001", params={"corpus": "engineering"}
        )
        assert one.status_code == 200
        assert one.json()["document"]["document_id"] == "doc_001"
        assert "source_path" not in one.json()["document"]

        unknown = client.get(
            "/v1/documents/missing", params={"corpus": "engineering"}
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "document_unknown"

        openapi = client.get("/openapi.json").json()
        paths = set(openapi.get("paths", {}))
        assert "/v1/documents" in paths
        assert "/v1/documents/{document_id}" in paths
        assert "/health/ready" in paths
        # /v1/ingest is owned by Phase 15D; still forbid later product surfaces.
        for forbidden in (
            "/v1/query",
            "/v1/trace/{trace_id}",
            "/eval/run",
        ):
            assert forbidden not in paths
    runtime.shutdown()


def test_startup_recovers_candidates_without_publish(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    cand = settings.paths.corpora / "engineering" / "candidates" / "leftover"
    cand.mkdir(parents=True)
    (cand / "x").write_text("1", encoding="utf-8")
    runtime = ApplicationRuntime(settings=settings, factories=_factories())
    runtime.start()
    assert runtime.is_ready
    assert not cand.exists()
    assert list((settings.paths.corpora / "engineering" / "abandoned").iterdir())
    assert not current_pointer_path(settings.paths.corpora, "engineering").exists()
    runtime.shutdown()


def test_incomplete_dense_count_is_not_grounded_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 70
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(
        settings,
        expected_child_count=100,
        indexed_child_count=70,
        lexical_expected_child_count=1,
        lexical_indexed_child_count=1,
    )
    with pytest.raises(AppError) as exc:
        registry.publish("engineering", identity)
    assert exc.value.code is ErrorCode.CORPUS_NOT_READY


def test_qdrant_count_mismatch_is_snapshot_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 20
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(
        settings,
        expected_child_count=100,
        indexed_child_count=100,
        lexical_expected_child_count=1,
        lexical_indexed_child_count=1,
    )
    with pytest.raises(AppError) as exc:
        registry.publish("engineering", identity)
    assert exc.value.code is ErrorCode.SNAPSHOT_UNAVAILABLE


def test_invalid_lexical_backing_is_snapshot_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    registry = ProductPublicationRegistry(settings, qdrant=qdrant)
    identity = _write_scientific_stack(settings, build_lexical=False)
    with pytest.raises(AppError) as exc:
        registry.publish("engineering", identity)
    assert exc.value.code is ErrorCode.SNAPSHOT_UNAVAILABLE


def test_recovery_skips_candidates_while_lease_held(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    settings.paths.locks.mkdir(parents=True, exist_ok=True)
    cand = settings.paths.corpora / "engineering" / "candidates" / "live_build"
    cand.mkdir(parents=True)
    marker = cand / "partial.txt"
    marker.write_text("building", encoding="utf-8")
    holder = CorpusMutationLease(settings, "engineering")
    holder.acquire()
    try:
        moved = recover_abandoned_candidates(settings)
        assert moved == []
        assert cand.exists()
        assert marker.exists()
    finally:
        holder.release()
    moved = recover_abandoned_candidates(settings)
    assert moved
    assert not cand.exists()
    assert (settings.paths.corpora / "engineering" / "abandoned").exists()


def test_unsafe_unknown_document_id_still_document_unknown(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    qdrant = _FakeQdrant()
    qdrant.counts["col_ccc"] = 1
    runtime = ApplicationRuntime(settings=settings, factories=_factories(qdrant))
    runtime.start()
    identity = _write_scientific_stack(settings)
    runtime.publication.publish("engineering", identity)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/documents/not$canonical", params={"corpus": "engineering"}
        )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "document_unknown"
    assert "validation error" not in response.text.lower()
    assert "SafeErrorDetails" not in response.text
    runtime.shutdown()
