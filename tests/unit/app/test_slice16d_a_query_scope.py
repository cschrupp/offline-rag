"""Slice 16D-A — workspace source scope + pre-ranking dense/lexical filters."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.query import _resolve_workspace_source_scope, run_workspace_query
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.app.traces import (
    ProductTraceRequestSummary,
    ProductTraceSourceScope,
    ProductTraceStore,
)
from offline_rag.app.workspace.models import SourceVersionRecord, WorkspaceRecord
from offline_rag.app.workspace.store import WorkspaceStore
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.generation.fake import FakeGenerator
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.lexical.backend import LexicalDocumentInput, LocalInvertedIndexBackend
from offline_rag.lexical.retrieve import LexicalRetriever
from offline_rag.rerank.fake import FakeReranker
from offline_rag.rerank.retrieve import HybridRerankRetriever


def _source(
    source_id: str,
    *,
    document_id: str,
    active: bool = True,
) -> SourceVersionRecord:
    return SourceVersionRecord(
        source_id=source_id,
        version=1,
        display_name=f"{source_id}.pdf",
        content_type="application/pdf",
        byte_size=100,
        content_hash=f"hash-{source_id}",
        document_id=document_id,
        vault_object_id=f"vault_{source_id}",
        active=active,
        active_from_revision=1,
        active_from_snapshot_id="snap_1",
        created_at="2026-01-01T00:00:00Z",
    )


def _workspace(*sources: SourceVersionRecord) -> WorkspaceRecord:
    return WorkspaceRecord(
        workspace_id="ws_scope",
        title="Scope Desk",
        description="",
        revision=3,
        status="active",
        backing_corpus_name="ws_scope_corpus",
        current_snapshot_id="snap_1",
        sources=list(sources),
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-02T00:00:00Z",
    )


def test_omitted_source_ids_resolves_all_active() -> None:
    record = _workspace(
        _source("src_a", document_id="doc_alpha"),
        _source("src_b", document_id="doc_beta"),
        _source("src_inactive", document_id="doc_gamma", active=False),
    )
    scope, logical, docs = _resolve_workspace_source_scope(record, source_ids=None)
    assert scope.mode == "all_active"
    assert scope.workspace_revision == 3
    assert logical == frozenset({"src_a", "src_b"})
    assert docs == frozenset({"doc_alpha", "doc_beta"})
    assert scope.source_ids == ["src_a", "src_b"]
    assert scope.document_ids == ["doc_alpha", "doc_beta"]


def test_empty_source_ids_rejected() -> None:
    record = _workspace(_source("src_a", document_id="doc_alpha"))
    with pytest.raises(AppError) as exc:
        _resolve_workspace_source_scope(record, source_ids=[])
    assert exc.value.code == ErrorCode.REQUEST_INVALID


def test_unknown_and_inactive_source_fail_closed() -> None:
    record = _workspace(
        _source("src_a", document_id="doc_alpha"),
        _source("src_b", document_id="doc_beta", active=False),
    )
    with pytest.raises(AppError) as exc:
        _resolve_workspace_source_scope(record, source_ids=["src_missing"])
    assert exc.value.code == ErrorCode.SOURCE_UNKNOWN
    with pytest.raises(AppError) as exc2:
        _resolve_workspace_source_scope(record, source_ids=["src_b"])
    assert exc2.value.code == ErrorCode.SOURCE_UNKNOWN


def test_duplicate_source_ids_rejected() -> None:
    record = _workspace(_source("src_a", document_id="doc_alpha"))
    with pytest.raises(AppError) as exc:
        _resolve_workspace_source_scope(record, source_ids=["src_a", "src_a"])
    assert exc.value.code == ErrorCode.REQUEST_INVALID


def test_selected_scope_resolves_document_ids() -> None:
    record = _workspace(
        _source("src_a", document_id="doc_alpha"),
        _source("src_b", document_id="doc_beta"),
    )
    scope, logical, docs = _resolve_workspace_source_scope(
        record, source_ids=["src_b"]
    )
    assert scope.mode == "selected"
    assert logical == frozenset({"src_b"})
    assert docs == frozenset({"doc_beta"})


def test_shared_document_id_selected_scope() -> None:
    record = _workspace(
        _source("src_a", document_id="doc_shared"),
        _source("src_b", document_id="doc_shared"),
    )
    _, logical, docs = _resolve_workspace_source_scope(
        record, source_ids=["src_a"]
    )
    assert logical == frozenset({"src_a"})
    assert docs == frozenset({"doc_shared"})
    _, logical2, docs2 = _resolve_workspace_source_scope(
        record, source_ids=["src_a", "src_b"]
    )
    assert logical2 == frozenset({"src_a", "src_b"})
    assert docs2 == frozenset({"doc_shared"})


def test_old_traces_without_source_scope_remain_readable() -> None:
    summary = ProductTraceRequestSummary.model_validate(
        {
            "question_sha256": "a" * 64,
            "question_char_count": 12,
        }
    )
    assert summary.source_scope is None
    with_scope = ProductTraceRequestSummary(
        question_sha256="b" * 64,
        question_char_count=3,
        source_scope=ProductTraceSourceScope(
            workspace_id="ws_1",
            workspace_revision=1,
            mode="selected",
            source_ids=["src_a"],
            document_ids=["doc_a"],
        ),
    )
    assert with_scope.source_scope is not None
    assert with_scope.source_scope.mode == "selected"


def test_lexical_scoped_bm25_excludes_unselected_before_ranking(tmp_path: Path) -> None:
    backend = LocalInvertedIndexBackend(tmp_path / "lex")
    docs = [
        LexicalDocumentInput(
            chunk_id="chk_alpha",
            terms=["alpha_scope_marker", "shared"],
            document_id="doc_alpha",
        ),
        LexicalDocumentInput(
            chunk_id="chk_beta",
            terms=["beta_scope_marker", "shared"],
            document_id="doc_beta",
        ),
    ]
    backend.build(
        "lex_scope",
        docs,
        chunk_set_id="cs_1",
        lexical_config_hash="hash",
    )
    backend.open("lex_scope")

    unscoped = backend.search(["shared"], top_k=10)
    assert {hit.document_id for hit in unscoped} == {"doc_alpha", "doc_beta"}

    scoped = backend.search(
        ["shared"],
        top_k=10,
        document_ids=frozenset({"doc_alpha"}),
    )
    assert [hit.document_id for hit in scoped] == ["doc_alpha"]
    assert all(hit.chunk_id == "chk_alpha" for hit in scoped)

    alpha_only = backend.search(
        ["alpha_scope_marker"],
        top_k=10,
        document_ids=frozenset({"doc_beta"}),
    )
    assert alpha_only == []

    beta_only = backend.search(
        ["beta_scope_marker"],
        top_k=10,
        document_ids=frozenset({"doc_beta"}),
    )
    assert [hit.document_id for hit in beta_only] == ["doc_beta"]


def test_lexical_scoped_stats_use_eligible_n_avgdl_df(tmp_path: Path) -> None:
    backend = LocalInvertedIndexBackend(tmp_path / "lex")
    docs = [
        LexicalDocumentInput(
            chunk_id="chk_a",
            terms=["term", "term", "only_a"],
            document_id="doc_a",
        ),
        LexicalDocumentInput(
            chunk_id="chk_b",
            terms=["term"],
            document_id="doc_b",
        ),
        LexicalDocumentInput(
            chunk_id="chk_c",
            terms=["term", "term", "term", "only_c"],
            document_id="doc_c",
        ),
    ]
    backend.build(
        "lex_stats",
        docs,
        chunk_set_id="cs_1",
        lexical_config_hash="hash",
    )
    backend.open("lex_stats")

    captured: dict[str, Any] = {}
    original = backend._scorer.accumulate

    def _capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return original(**kwargs)

    backend._scorer.accumulate = _capture  # type: ignore[method-assign]
    backend.search(["term"], top_k=5, document_ids=frozenset({"doc_a", "doc_b"}))
    assert captured["n"] == 2
    assert captured["avgdl"] == pytest.approx((3 + 1) / 2)
    assert captured["dfs"]["term"] == 2
    assert set(captured["doc_lengths"]) == {"chk_a", "chk_b"}
    assert "chk_c" not in captured["doc_lengths"]
    for postings in captured["postings_by_term"].values():
        assert all(chunk_id in {"chk_a", "chk_b"} for chunk_id, _tf in postings)


def test_qdrant_search_emits_native_document_id_filter(tmp_path: Path) -> None:
    backend = QdrantLocalBackend(tmp_path / "qdrant")
    calls: list[dict[str, Any]] = []

    class _FakeClient:
        def query_points(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            result = MagicMock()
            result.points = []
            return result

        def search(self, **kwargs: Any) -> list[Any]:
            calls.append(kwargs)
            return []

    backend._client = _FakeClient()  # type: ignore[assignment]
    backend.search(
        "col",
        query_vector=[0.1, 0.2],
        top_k=5,
        document_ids=frozenset({"doc_alpha", "doc_beta"}),
    )
    assert calls
    query_filter = calls[0].get("query_filter") or calls[0].get("filter")
    assert query_filter is not None
    must = query_filter.must
    assert len(must) == 1
    condition = must[0]
    assert condition.key == "document_id"
    assert sorted(condition.match.any) == ["doc_alpha", "doc_beta"]


def test_qdrant_unscoped_preserves_no_filter(tmp_path: Path) -> None:
    backend = QdrantLocalBackend(tmp_path / "qdrant")
    calls: list[dict[str, Any]] = []

    class _FakeClient:
        def query_points(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            result = MagicMock()
            result.points = []
            return result

    backend._client = _FakeClient()  # type: ignore[assignment]
    backend.search("col", query_vector=[0.1], top_k=3, document_ids=None)
    assert calls
    assert calls[0].get("query_filter") is None


# ---------------------------------------------------------------------------
# Independent review rework — F3 / F4
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
ALPHA_SCOPE_MARKER = "ALPHA_SCOPE_MARKER"
BETA_SCOPE_MARKER = "BETA_SCOPE_MARKER"


def _provision_query_assets(settings: AppSettings) -> None:
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"unit")
    write_provisioning_manifest(settings.paths.docling_artifacts, docling_version="test")
    if not (TIKTOKEN_SRC / "offline-rag-tokenizer.json").exists():
        pytest.skip("tiktoken artifacts not provisioned")
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(TIKTOKEN_SRC, settings.paths.tokenizer_artifacts)


def _query_settings(tmp_path: Path) -> AppSettings:
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
            "OFFLINE_RAG_STRICT_OFFLINE": "false",
        },
    )
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
    settings = settings.model_copy(
        update={"generation": generation, "reranker": reranker}
    )
    _provision_query_assets(settings)
    return settings


def _wait_op(client: TestClient, op_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/v1/operations/{op_id}").json()
        if body["status"] in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise AssertionError(f"op {op_id} did not terminate")


@contextmanager
def _scope_client(tmp_path: Path) -> Iterator[tuple[TestClient, ApplicationRuntime, dict]]:
    settings = _query_settings(tmp_path)
    captures: dict[str, list] = {
        "dense_docs": [],
        "dense_text": [],
        "lexical_docs": [],
        "lexical_text": [],
        "hybrid_docs": [],
        "rerank_text": [],
        "context_text": [],
        "generator_text": [],
    }

    class _RecordingReranker(FakeReranker):
        def score_pairs(self, pairs):
            for pair in pairs:
                captures["rerank_text"].append(getattr(pair, "passage_text", "") or "")
            return super().score_pairs(pairs)

    original_dense = DenseRetriever.retrieve
    original_lexical = LexicalRetriever.retrieve
    original_hybrid = HybridRetriever.retrieve
    original_rerank = HybridRerankRetriever.retrieve
    original_assemble = HybridRerankContextAssembler.assemble

    def dense_retrieve(self, *args, **kwargs):
        result = original_dense(self, *args, **kwargs)
        captures["dense_docs"].append({c.document_id for c in result.candidates})
        captures["dense_text"].append(
            " ".join(getattr(c, "text", "") or "" for c in result.candidates)
        )
        return result

    def lexical_retrieve(self, *args, **kwargs):
        result = original_lexical(self, *args, **kwargs)
        captures["lexical_docs"].append({c.document_id for c in result.candidates})
        captures["lexical_text"].append(
            " ".join(getattr(c, "text", "") or "" for c in result.candidates)
        )
        return result

    def hybrid_retrieve(self, *args, **kwargs):
        result = original_hybrid(self, *args, **kwargs)
        captures["hybrid_docs"].append({c.document_id for c in result.candidates})
        return result

    def rerank_retrieve(self, *args, **kwargs):
        return original_rerank(self, *args, **kwargs)

    def assemble(self, *args, **kwargs):
        ctx = original_assemble(self, *args, **kwargs)
        captures["context_text"].append(
            " ".join(unit.text for unit in ctx.evidence_units)
        )
        return ctx

    def _response_fn(request):
        blob = "\n".join(message.content for message in request.messages)
        captures["generator_text"].append(blob)
        ids = re.findall(r"\bev_[A-Za-z0-9._-]+\b", blob)
        unique = list(dict.fromkeys(ids))
        if not unique:
            return json.dumps({"abstain": True, "answer": None, "citation_ids": []})
        return json.dumps(
            {
                "abstain": False,
                "answer": f"Alpha-only answer citing {ALPHA_SCOPE_MARKER}.",
                "citation_ids": [unique[0]],
            }
        )

    DenseRetriever.retrieve = dense_retrieve  # type: ignore[method-assign]
    LexicalRetriever.retrieve = lexical_retrieve  # type: ignore[method-assign]
    HybridRetriever.retrieve = hybrid_retrieve  # type: ignore[method-assign]
    HybridRerankRetriever.retrieve = rerank_retrieve  # type: ignore[method-assign]
    HybridRerankContextAssembler.assemble = assemble  # type: ignore[method-assign]

    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker = _RecordingReranker()
    generator = FakeGenerator(response_fn=_response_fn)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker,
            generator_client=lambda _s: generator,
            qdrant=_qdrant,
        ),
    )
    app = create_app(runtime=runtime)
    try:
        with TestClient(app) as client:
            yield client, runtime, captures
    finally:
        DenseRetriever.retrieve = original_dense  # type: ignore[method-assign]
        LexicalRetriever.retrieve = original_lexical  # type: ignore[method-assign]
        HybridRetriever.retrieve = original_hybrid  # type: ignore[method-assign]
        HybridRerankRetriever.retrieve = original_rerank  # type: ignore[method-assign]
        HybridRerankContextAssembler.assemble = original_assemble  # type: ignore[method-assign]


def test_f3_canonical_source_isolation_end_to_end(tmp_path: Path) -> None:
    with _scope_client(tmp_path) as (client, runtime, captures):
        created = client.post(
            "/v1/workspaces",
            json={"title": "Scope Desk", "description": "markers"},
            headers={"Idempotency-Key": "scope-create"},
        )
        assert created.status_code == 201, created.text
        wid = created.json()["workspace_id"]

        alpha_bytes = (
            f"{ALPHA_SCOPE_MARKER} alpha pump torque procedure for station A.\n"
        ).encode()
        beta_bytes = (
            f"{BETA_SCOPE_MARKER} beta valve isolation procedure for station B.\n"
        ).encode()
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "scope-add", "If-Match": '"1"'},
            files=[
                ("files", ("alpha.txt", alpha_bytes, "text/plain")),
                ("files", ("beta.txt", beta_bytes, "text/plain")),
            ],
        )
        assert add.status_code == 202, add.text
        terminal = _wait_op(client, add.json()["operation_id"])
        assert terminal["status"] == "succeeded", terminal

        sources = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"]
        assert len(sources) == 2
        by_name = {row["display_name"]: row for row in sources}
        alpha = by_name["alpha.txt"]
        beta = by_name["beta.txt"]
        alpha_sid = alpha["source_id"]
        alpha_doc = alpha["document_id"]
        beta_doc = beta["document_id"]
        assert alpha_doc != beta_doc

        record = WorkspaceStore(runtime.settings).get(wid)
        assert record.revision >= 2

        # Clear captures from any warmup; exercise scoped canonical path.
        for key in captures:
            captures[key].clear()

        outcome = run_workspace_query(
            runtime,
            workspace_id=wid,
            question=f"What procedure is described for {ALPHA_SCOPE_MARKER}?",
            source_ids=[alpha_sid],
        )
        assert outcome.workspace_id == wid
        assert outcome.workspace_revision == record.revision
        assert outcome.snapshot_id == record.current_snapshot_id

        # Dense / lexical / hybrid must never include Beta document under Alpha scope.
        assert captures["dense_docs"], "dense must run"
        assert all(beta_doc not in docs for docs in captures["dense_docs"])
        assert all(
            docs <= {alpha_doc} or docs == set() for docs in captures["dense_docs"]
        )
        assert all(BETA_SCOPE_MARKER not in text for text in captures["dense_text"])

        assert captures["lexical_docs"], "lexical must run"
        assert all(beta_doc not in docs for docs in captures["lexical_docs"])
        assert all(BETA_SCOPE_MARKER not in text for text in captures["lexical_text"])

        assert captures["hybrid_docs"], "hybrid must run"
        assert all(beta_doc not in docs for docs in captures["hybrid_docs"])

        assert captures["rerank_text"], "reranker must receive candidates"
        assert all(BETA_SCOPE_MARKER not in text for text in captures["rerank_text"])

        assert captures["context_text"], "context must assemble"
        assert all(BETA_SCOPE_MARKER not in text for text in captures["context_text"])
        assert any(ALPHA_SCOPE_MARKER in text for text in captures["context_text"])

        assert captures["generator_text"], "generator must receive evidence"
        for blob in captures["generator_text"]:
            blocks = re.findall(
                r"### BEGIN EVIDENCE.*?### END EVIDENCE[^\n]*",
                blob,
                flags=re.DOTALL,
            )
            assert blocks, "generator prompt must include evidence blocks"
            assert all(BETA_SCOPE_MARKER not in block for block in blocks)
            assert any(ALPHA_SCOPE_MARKER in block for block in blocks)

        packed = json.dumps(outcome.as_dict())
        assert BETA_SCOPE_MARKER not in packed
        assert beta_doc not in packed
        if outcome.status == "answered":
            assert outcome.citations
            for citation in outcome.citations:
                assert citation["document_id"] == alpha_doc
                assert citation.get("source_id") == alpha_sid

        store = ProductTraceStore(runtime.settings)
        trace = store.get(outcome.trace_id)
        assert trace is not None
        assert trace.request.source_scope is not None
        scope = trace.request.source_scope
        assert scope.workspace_id == wid
        assert scope.workspace_revision == record.revision
        assert scope.mode == "selected"
        assert scope.source_ids == [alpha_sid]
        assert scope.document_ids == [alpha_doc]

        # Omitted source_ids → all active sources form effective trace scope.
        for key in captures:
            captures[key].clear()
        both = run_workspace_query(
            runtime,
            workspace_id=wid,
            question=f"Summarize both {ALPHA_SCOPE_MARKER} and {BETA_SCOPE_MARKER}.",
            source_ids=None,
        )
        both_trace = store.get(both.trace_id)
        assert both_trace is not None
        both_scope = both_trace.request.source_scope
        assert both_scope is not None
        assert both_scope.mode == "all_active"
        assert set(both_scope.source_ids) == {alpha_sid, beta["source_id"]}
        assert set(both_scope.document_ids) == {alpha_doc, beta_doc}
        # Unscoped path is allowed to see Beta in the stack.
        assert any(
            beta_doc in docs or ALPHA_SCOPE_MARKER in " ".join(captures["context_text"])
            for docs in captures["hybrid_docs"]
        ) or any(BETA_SCOPE_MARKER in text for text in captures["context_text"])


@pytest.mark.parametrize(
    "bad_id",
    ["", "../../etc/passwd", "source id with spaces", "x" * 200],
)
def test_f4_malformed_source_ids_return_safe_validation_error(
    tmp_path: Path, bad_id: str
) -> None:
    settings = _query_settings(tmp_path)
    embedder = FakeEmbedder(dimension=8, normalize=True)

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    runtime = ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: None,
            generator_client=lambda _s: FakeGenerator(
                default_response=json.dumps(
                    {"abstain": True, "answer": None, "citation_ids": []}
                )
            ),
            qdrant=_qdrant,
        ),
    )
    with TestClient(create_app(runtime=runtime)) as client:
        created = client.post(
            "/v1/workspaces",
            json={"title": "Bad Ids", "description": ""},
            headers={"Idempotency-Key": "bad-ids"},
        )
        assert created.status_code == 201
        wid = created.json()["workspace_id"]
        # EMPTY workspace query still validates transport before readiness.
        response = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "anything", "source_ids": [bad_id]},
        )
        assert response.status_code == 422, response.text
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] in {
            "request_invalid",
            "document_invalid",
            "settings_invalid",
        }
        # Never a raw framework 500 / pydantic traceback body.
        assert "ValidationError" not in response.text
        assert "Traceback" not in response.text


def test_f4_unknown_and_duplicate_source_ids_preserve_product_codes(
    tmp_path: Path,
) -> None:
    with _scope_client(tmp_path) as (client, _runtime, _captures):
        created = client.post(
            "/v1/workspaces",
            json={"title": "Codes", "description": ""},
            headers={"Idempotency-Key": "codes"},
        )
        wid = created.json()["workspace_id"]
        add = client.post(
            f"/v1/workspaces/{wid}/sources",
            headers={"Idempotency-Key": "codes-add", "If-Match": '"1"'},
            files={"files": ("only.txt", b"only alpha pumps\n", "text/plain")},
        )
        assert _wait_op(client, add.json()["operation_id"])["status"] == "succeeded"
        src = client.get(f"/v1/workspaces/{wid}/sources").json()["sources"][0]
        sid = src["source_id"]

        unknown = client.post(
            f"/v1/workspaces/{wid}/query",
            json={
                "question": "what pumps?",
                "source_ids": ["src_deadbeefdeadbeefdeadbeefdeadbeef"],
            },
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "source_unknown"

        dup = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "what pumps?", "source_ids": [sid, sid]},
        )
        assert dup.status_code == 422
        assert dup.json()["error"]["code"] == "request_invalid"

        empty = client.post(
            f"/v1/workspaces/{wid}/query",
            json={"question": "what pumps?", "source_ids": []},
        )
        assert empty.status_code == 422
        assert empty.json()["error"]["code"] == "request_invalid"


# ---------------------------------------------------------------------------
# Independent review rework 2 — F8 fail-closed scope invariants
# ---------------------------------------------------------------------------


from offline_rag.dense.retrieve import DenseRetrievalError
from offline_rag.domain.indexing import (
    DenseCandidate,
    FusionProvenance,
    HybridCandidate,
    HybridRetrievalResult,
    LexicalCandidate,
)
from offline_rag.hybrid.retrieve import HybridRetrievalError
from offline_rag.lexical.retrieve import LexicalRetrievalError
from offline_rag.rerank.retrieve import HybridRerankRetrievalError


def _dense_candidate(document_id: str, *, chunk_id: str = "chk_x") -> DenseCandidate:
    return DenseCandidate(
        rank=1,
        score=0.9,
        chunk_id=chunk_id,
        document_id=document_id,
        text="marker text",
        point_id="point_1",
        chunk_artifact_id="art_1",
    )


def _lexical_candidate(document_id: str, *, chunk_id: str = "chk_x") -> LexicalCandidate:
    return LexicalCandidate(
        rank=1,
        score=0.8,
        chunk_id=chunk_id,
        document_id=document_id,
        text="marker text",
        chunk_artifact_id="art_1",
    )


def _hybrid_candidate(document_id: str, *, chunk_id: str = "chk_x") -> HybridCandidate:
    return HybridCandidate(
        rank=1,
        score=0.05,
        chunk_id=chunk_id,
        document_id=document_id,
        text="marker text",
        fusion=FusionProvenance(
            rrf_score=0.05,
            dense_rank=1,
            dense_score=0.9,
            lexical_rank=None,
            lexical_score=None,
        ),
    )


def test_f8_dense_escaped_candidate_fails_closed() -> None:
    settings = AppSettings()
    backend = MagicMock()
    hit = MagicMock()
    hit.score = 1.0
    hit.payload = {"chunk_id": "chk_beta", "chunk_artifact_id": "art"}
    hit.point_id = "pt"
    backend.search.return_value = [hit]
    embedder = FakeEmbedder(dimension=8, normalize=True)
    retriever = DenseRetriever(settings, embedder=embedder, backend=backend)
    retriever._hit_to_candidate = (  # type: ignore[method-assign]
        lambda hit, rank: _dense_candidate("doc_beta", chunk_id="chk_beta")
    )
    with pytest.raises(DenseRetrievalError, match="escaped"):
        retriever.retrieve(
            query="scope query",
            corpus_name="eng",
            top_k=3,
            index_id="dense_idx",
            collection_name="col",
            chunk_set_id="cs",
            document_ids=frozenset({"doc_alpha"}),
        )


def test_f8_lexical_escaped_candidate_fails_closed() -> None:
    settings = AppSettings()
    backend = MagicMock()
    backend.search.return_value = [MagicMock(chunk_id="chk_beta", chunk_artifact_id="art", score=1.0)]
    analyzer = MagicMock()
    analyzer.analyze_query_terms.return_value = ["scope"]
    retriever = LexicalRetriever(settings, backend=backend, analyzer=analyzer)
    retriever._open_index_id = "lex_idx"
    retriever._hit_to_candidate = (  # type: ignore[method-assign]
        lambda hit, rank: _lexical_candidate("doc_beta", chunk_id="chk_beta")
    )
    with pytest.raises(LexicalRetrievalError, match="escaped"):
        retriever.retrieve(
            query="scope query",
            corpus_name="eng",
            top_k=3,
            index_id="lex_idx",
            chunk_set_id="cs",
            document_ids=frozenset({"doc_alpha"}),
        )


def test_f8_hybrid_escaped_branch_fails_before_fusion() -> None:
    settings = AppSettings()
    dense = MagicMock()
    dense.retrieve.return_value = MagicMock(
        candidates=[_dense_candidate("doc_beta")],
        index_id="d",
        metadata={"chunk_set_id": "cs"},
    )
    lexical = MagicMock()
    lexical.retrieve.return_value = MagicMock(
        candidates=[_lexical_candidate("doc_alpha")],
        index_id="l",
        metadata={"chunk_set_id": "cs"},
    )
    hybrid = HybridRetriever(settings, dense=dense, lexical=lexical)
    with pytest.raises(HybridRetrievalError, match="hybrid-dense-branch"):
        hybrid.retrieve(
            query="scope query",
            corpus_name="eng",
            top_k=3,
            dense_index_id="d",
            dense_collection_name="col",
            lexical_index_id="l",
            chunk_set_id="cs",
            corpus_id="corp",
            document_ids=frozenset({"doc_alpha"}),
        )


def test_f8_rerank_rejects_malicious_hybrid_pool_before_scoring() -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"enabled": True, "implementation": "fake", "input_k": 5, "output_k": 3}
            )
        }
    )
    hybrid = MagicMock()
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="q",
        top_k=5,
        candidates=[_hybrid_candidate("doc_beta")],
        dense_index_id="d",
        lexical_index_id="l",
        fusion_config_hash="fuscfg_x",
        metadata={"chunk_set_id": "cs", "latency_ms": {}},
    )
    scored = []

    class _GuardReranker(FakeReranker):
        def score_pairs(self, pairs):
            scored.append(True)
            return super().score_pairs(pairs)

    retriever = HybridRerankRetriever(
        settings, hybrid=hybrid, reranker=_GuardReranker()
    )
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(HybridRerankRetrievalError, match="hybrid-rerank-input"):
        retriever.retrieve(
            query="q",
            corpus_name="eng",
            top_k=3,
            check_ready=False,
            document_ids=frozenset({"doc_alpha"}),
        )
    assert scored == []


def test_f8_rerank_rejects_out_of_contract_result_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings().model_copy(
        update={
            "reranker": AppSettings().reranker.model_copy(
                update={"enabled": True, "implementation": "fake", "input_k": 5, "output_k": 3}
            )
        }
    )
    good = _hybrid_candidate("doc_alpha", chunk_id="chk_alpha")
    hybrid = MagicMock()
    hybrid.retrieve.return_value = HybridRetrievalResult(
        query="q",
        top_k=5,
        candidates=[good],
        dense_index_id="d",
        lexical_index_id="l",
        fusion_config_hash="fuscfg_x",
        metadata={"chunk_set_id": "cs", "latency_ms": {}},
    )
    import offline_rag.rerank.retrieve as rr_mod

    original_sort = rr_mod._sort_scored

    def _evil_sort(pool, scores):
        ordered = original_sort(pool, scores)
        evil = _hybrid_candidate("doc_beta", chunk_id="chk_beta")
        return [(evil, 99.0), *ordered]

    monkeypatch.setattr(rr_mod, "_sort_scored", _evil_sort)
    retriever = HybridRerankRetriever(
        settings, hybrid=hybrid, reranker=FakeReranker(score_map={("q", "chk_alpha"): 1.0})
    )
    retriever._require_ready = lambda _name: None  # type: ignore[method-assign]
    with pytest.raises(HybridRerankRetrievalError, match="hybrid-rerank"):
        retriever.retrieve(
            query="q",
            corpus_name="eng",
            top_k=3,
            check_ready=False,
            document_ids=frozenset({"doc_alpha"}),
        )
