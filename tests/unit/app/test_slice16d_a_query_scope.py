"""Slice 16D-A — workspace source scope + pre-ranking dense/lexical filters."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.query import _resolve_workspace_source_scope
from offline_rag.app.traces import ProductTraceRequestSummary, ProductTraceSourceScope
from offline_rag.app.workspace.models import SourceVersionRecord, WorkspaceRecord
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.lexical.backend import LexicalDocumentInput, LocalInvertedIndexBackend


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
    scope, logical, docs = _resolve_workspace_source_scope(
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
    for _term, postings in captured["postings_by_term"].items():
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
