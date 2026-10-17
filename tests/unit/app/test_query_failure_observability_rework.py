"""IR-001 rework tests: production dense/context boundaries + CUDA/invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from offline_rag.app.query_failure import classify_grounded_query_failure
from offline_rag.app.traces import ProductQueryTrace, ProductTraceInternalFailure
from offline_rag.context.assemble import (
    HybridRerankContextAssembler,
    HybridRerankContextError,
)
from offline_rag.context.store import ContextStructureError
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.retrieve import DenseRetrievalError, DenseRetriever
from offline_rag.domain.indexing import HybridRerankRetrievalResult
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.rerank.retrieve import HybridRerankRetriever

from test_slice15e_product_query_traces import (  # type: ignore[import-not-found]
    _make_trace_record,
    _settings,
)


def _cuda_oom(message: str = "CUDA out of memory") -> RuntimeError:
    cls = type("OutOfMemoryError", (RuntimeError,), {"__module__": "torch.cuda"})
    return cls(message)


class _BoomQueryEmbedder(FakeEmbedder):
    def __init__(self, *, exc: BaseException, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._exc = exc

    def embed_query(self, query: str) -> list[float]:
        raise self._exc


class _BoomSearchBackend:
    def __init__(self, *, exc: BaseException) -> None:
        self._exc = exc

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        raise self._exc


def test_dense_retrieve_wraps_raw_embed_query_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = _cuda_oom()
    retriever = DenseRetriever(
        settings,
        embedder=_BoomQueryEmbedder(exc=raw, dimension=8, normalize=True),
        backend=_BoomSearchBackend(exc=AssertionError("search must not run")),
    )
    with pytest.raises(DenseRetrievalError, match="dense query execution failed") as fi:
        retriever.retrieve(
            query="what pressure?",
            index_id="denseindex_ccc",
            collection_name="col_ccc",
            chunk_set_id="chunkset_bbb",
        )
    assert fi.value.__cause__ is raw


def test_dense_retrieve_wraps_raw_backend_search_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = RuntimeError("qdrant search exploded")
    retriever = DenseRetriever(
        settings,
        embedder=FakeEmbedder(dimension=8, normalize=True),
        backend=_BoomSearchBackend(exc=raw),
    )
    with pytest.raises(DenseRetrievalError, match="dense query execution failed") as fi:
        retriever.retrieve(
            query="what pressure?",
            index_id="denseindex_ccc",
            collection_name="col_ccc",
            chunk_set_id="chunkset_bbb",
        )
    assert fi.value.__cause__ is raw


def test_dense_retrieve_does_not_double_wrap_dense_retrieval_error(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    original = DenseRetrievalError("already dense-stage")
    retriever = DenseRetriever(
        settings,
        embedder=_BoomQueryEmbedder(exc=original, dimension=8, normalize=True),
        backend=_BoomSearchBackend(exc=AssertionError("unused")),
    )
    with pytest.raises(DenseRetrievalError, match="already dense-stage") as fi:
        retriever.retrieve(
            query="what pressure?",
            index_id="denseindex_ccc",
            collection_name="col_ccc",
            chunk_set_id="chunkset_bbb",
        )
    assert fi.value is original
    assert fi.value.__cause__ is None


def test_hybrid_dense_embed_cuda_oom_classifies_dense_stage(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    raw = _cuda_oom()
    dense = DenseRetriever(
        settings,
        embedder=_BoomQueryEmbedder(exc=raw, dimension=8, normalize=True),
        backend=_BoomSearchBackend(exc=AssertionError("unused")),
    )
    hybrid = HybridRetriever(settings, dense=dense)
    with pytest.raises(DenseRetrievalError) as fi:
        hybrid.retrieve(
            query="what pressure?",
            dense_index_id="denseindex_ccc",
            dense_collection_name="col_ccc",
            lexical_index_id="lexical_ddd",
            chunk_set_id="chunkset_bbb",
            corpus_id="corpus_aaa",
        )
    assert isinstance(fi.value, DenseRetrievalError)
    assert fi.value.__cause__ is raw
    classified = classify_grounded_query_failure(fi.value, stage_breadcrumb="execution")
    assert classified.stage == "dense_query"
    assert classified.failure_class == "dense_query_failure"
    assert classified.cuda_related is True
    assert classified.cuda_failure_class == "out_of_memory"
    assert "OutOfMemoryError" in classified.causal_exception_types


def test_context_expand_wraps_raw_structure_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    assembler = HybridRerankContextAssembler(settings)

    class _Upstream:
        candidates = []

    def fake_retrieve(self, **_kwargs):
        return HybridRerankRetrievalResult(
            query="q",
            top_k=1,
            candidates=[],
            dense_index_id="denseindex_ccc",
            lexical_index_id="lexical_ddd",
            fusion_config_hash="fuscfg_test",
            reranker_config_hash="rrkcfg_test",
            metadata={},
        )

    monkeypatch.setattr(HybridRerankRetriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(
        assembler,
        "_require_ready",
        lambda _name: None,
    )
    monkeypatch.setattr(assembler, "_structure", lambda _name: object())

    class _BoomExpander:
        def expand(self, candidates):
            raise ContextStructureError("missing child chunk: chunk_x")

    monkeypatch.setattr(
        "offline_rag.context.assemble.ContextExpander",
        lambda **_k: _BoomExpander(),
    )

    with pytest.raises(HybridRerankContextError, match="context expansion failed") as fi:
        assembler.assemble(query="what pressure?", check_ready=False)
    assert isinstance(fi.value.__cause__, ContextStructureError)
    classified = classify_grounded_query_failure(fi.value, stage_breadcrumb="execution")
    assert classified.stage == "context_assembly"
    assert classified.failure_class == "context_assembly_failure"
    assert "ContextStructureError" in classified.causal_exception_types


def test_internal_failure_requires_internal_error_and_null_status(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    failure = ProductTraceInternalFailure(
        stage="dense_query",
        failure_class="dense_query_failure",
        exception_type="DenseRetrievalError",
        causal_exception_types=[],
        cuda_related=False,
        cuda_failure_class=None,
    )
    answered = _make_trace_record(settings, status="answered", error_code=None)
    payload = answered.model_dump(mode="python")
    payload["internal_failure"] = failure.model_dump(mode="python")
    with pytest.raises(ValidationError):
        ProductQueryTrace.model_validate(payload)

    timed_out = _make_trace_record(
        settings, status=None, error_code="generation_timeout"
    )
    payload2 = timed_out.model_dump(mode="python")
    payload2["internal_failure"] = failure.model_dump(mode="python")
    with pytest.raises(ValidationError):
        ProductQueryTrace.model_validate(payload2)

    # Historical shape: internal_error without internal_failure remains valid.
    ok = _make_trace_record(settings, status=None, error_code="internal_error")
    assert ok.internal_failure is None
    ProductQueryTrace.model_validate(ok.model_dump(mode="python"))

    # Valid new shape: internal_error + internal_failure.
    valid = ok.model_dump(mode="python")
    valid["internal_failure"] = failure.model_dump(mode="python")
    ProductQueryTrace.model_validate(valid)


def test_cuda_related_requires_matching_failure_class() -> None:
    with pytest.raises(ValidationError):
        ProductTraceInternalFailure(
            stage="unknown",
            failure_class="cuda_runtime_failure",
            exception_type="RuntimeError",
            cuda_related=True,
            cuda_failure_class=None,
        )
    with pytest.raises(ValidationError):
        ProductTraceInternalFailure(
            stage="unknown",
            failure_class="unexpected_internal_failure",
            exception_type="RuntimeError",
            cuda_related=False,
            cuda_failure_class="out_of_memory",
        )
