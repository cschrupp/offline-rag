"""Grounded-query internal_error observability remediation tests."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.query_failure import classify_grounded_query_failure
from offline_rag.app.traces import (
    ProductQueryTrace,
    ProductTraceInternalFailure,
    ProductTraceStore,
)
from offline_rag.context.assemble import HybridRerankContextError
from offline_rag.dense.retrieve import DenseRetrievalError
from offline_rag.generation.executor import GroundedGenerationError
from offline_rag.generation.orchestrate import GroundedAnswerError
from offline_rag.rerank.cross_encoder import CrossEncoderRerankerError
from offline_rag.rerank.retrieve import HybridRerankRetrievalError

# Reuse 15E harness without duplicating the scientific stack.
from test_slice15e_product_query_traces import (  # type: ignore[import-not-found]
    _canned,
    _citation,
    _make_trace_record,
    _patch_execute,
    _publish_ready,
    _runtime,
    _settings,
    _trace_path,
)


def test_classify_nested_rerank_chain_preserves_inner_stage() -> None:
    inner = CrossEncoderRerankerError("score boom")
    mid = HybridRerankRetrievalError("rerank failed")
    mid.__cause__ = inner
    ctx = HybridRerankContextError("assemble failed")
    ctx.__cause__ = mid
    outer = GroundedAnswerError("orchestration fault")
    outer.__cause__ = ctx

    classified = classify_grounded_query_failure(outer, stage_breadcrumb="execution")
    assert classified.stage == "rerank"
    assert classified.failure_class == "reranker_failure"
    assert classified.exception_type == "GroundedAnswerError"
    assert classified.causal_exception_types == [
        "HybridRerankContextError",
        "HybridRerankRetrievalError",
        "CrossEncoderRerankerError",
    ]
    assert classified.cuda_related is False
    assert classified.cuda_failure_class is None


def test_classify_dense_cuda_oom_is_orthogonal() -> None:
    class OutOfMemoryError(RuntimeError):
        """Synthetic stand-in for torch.cuda.OutOfMemoryError."""

    oom = OutOfMemoryError("CUDA out of memory")
    dense = DenseRetrievalError("embedding failed")
    dense.__cause__ = oom
    classified = classify_grounded_query_failure(dense, stage_breadcrumb="execution")
    assert classified.stage == "dense_query"
    assert classified.failure_class == "dense_query_failure"
    assert classified.cuda_related is True
    assert classified.cuda_failure_class == "out_of_memory"
    assert "CUDA out of memory" not in classified.model_dump_json()


def test_classify_cublas_marker_without_stage_maps_cuda_runtime_failure() -> None:
    exc = RuntimeError("CUBLAS_STATUS_EXECUTION_FAILED cublasGemmEx")
    classified = classify_grounded_query_failure(exc, stage_breadcrumb="execution")
    assert classified.stage == "unknown"
    assert classified.failure_class == "cuda_runtime_failure"
    assert classified.cuda_related is True
    assert classified.cuda_failure_class == "cublas"
    assert "cublasGemmEx" not in classified.model_dump_json()


def test_historical_v1_json_without_internal_failure_loads(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    record = _make_trace_record(settings, status="answered", error_code=None)
    payload = json.loads(record.model_dump_json(exclude={"internal_failure"}))
    assert "internal_failure" not in payload
    loaded = ProductQueryTrace.model_validate(payload)
    assert loaded.internal_failure is None


def test_store_omits_null_internal_failure_and_public_projection_excludes_it(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    store = ProductTraceStore(settings)

    ok = _make_trace_record(settings, status="answered", error_code=None)
    store.commit(ok)
    raw_ok = json.loads(_trace_path(settings, ok.trace_id).read_text(encoding="utf-8"))
    assert "internal_failure" not in raw_ok
    assert store.public_projection(store.get(ok.trace_id)).get("internal_failure") is None

    failed = _make_trace_record(settings, status=None, error_code="internal_error")
    failed = failed.model_copy(
        update={
            "internal_failure": ProductTraceInternalFailure(
                stage="dense_query",
                failure_class="dense_query_failure",
                exception_type="DenseRetrievalError",
                causal_exception_types=["OutOfMemoryError"],
                cuda_related=True,
                cuda_failure_class="out_of_memory",
            )
        }
    )
    store.commit(failed)
    stored = store.get(failed.trace_id)
    assert stored is not None
    assert stored.internal_failure is not None
    assert stored.internal_failure.stage == "dense_query"
    public = store.public_projection(stored)
    assert "internal_failure" not in public
    assert set(public) == {
        "schema_version",
        "trace_id",
        "created_at",
        "corpus",
        "snapshot_id",
        "product_mode_id",
        "request",
        "identity",
        "status",
        "error_code",
        "execution",
    }


@pytest.mark.parametrize(
    ("fault", "stage", "failure_class"),
    [
        (DenseRetrievalError("dense boom"), "dense_query", "dense_query_failure"),
        (
            HybridRerankRetrievalError("rerank boom"),
            "rerank",
            "reranker_failure",
        ),
        (
            HybridRerankContextError("context boom"),
            "context_assembly",
            "context_assembly_failure",
        ),
        (
            GroundedGenerationError("gen boom"),
            "generation",
            "generation_failure",
        ),
        (RuntimeError("generic boom"), "unknown", "unexpected_internal_failure"),
    ],
)
def test_injected_execute_failures_persist_internal_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: Exception,
    stage: str,
    failure_class: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    _patch_execute(monkeypatch, fault)
    app = create_app(runtime=runtime)
    with caplog.at_level(logging.ERROR), TestClient(
        app, raise_server_exceptions=False
    ) as client:
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "what pressure?"},
        )
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "internal_error"
        assert "Traceback" not in resp.text
        assert "boom" not in resp.text
        tid = body["trace_id"]
        assert tid
        stored = json.loads(_trace_path(settings, tid).read_text(encoding="utf-8"))
        assert stored["error_code"] == "internal_error"
        assert stored["status"] is None
        assert stored["internal_failure"]["stage"] == stage
        assert stored["internal_failure"]["failure_class"] == failure_class
        assert "boom" not in json.dumps(stored["internal_failure"])
        got = client.get(f"/v1/trace/{tid}")
        assert got.status_code == 200
        assert "internal_failure" not in got.json()
    assert any("grounded_query_internal_failure" in r.message for r in caplog.records)
    runtime.shutdown()


def test_projection_failure_classified_via_breadcrumb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    identity = _publish_ready(runtime)[1]
    # answered with empty answer_blocks → projection INTERNAL_ERROR
    _patch_execute(
        monkeypatch,
        _canned(
            status="answered",
            answer_text="x",
            citations=[_citation()],
            dense_index_id=identity.dense_index_id,
            lexical_index_id=identity.lexical_index_id,
            context_config_hash=identity.context_config_hash,
        ),
    )

    def boom_project(*_a, **_k):
        raise AppError(ErrorCode.INTERNAL_ERROR)

    monkeypatch.setattr("offline_rag.app.query._project_success", boom_project)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "project fail"},
        )
    assert resp.status_code == 500
    tid = resp.json()["trace_id"]
    stored = json.loads(_trace_path(settings, tid).read_text(encoding="utf-8"))
    assert stored["internal_failure"]["stage"] == "projection"
    assert stored["internal_failure"]["failure_class"] == "projection_failure"
    runtime.shutdown()


def test_trace_persistence_failure_logs_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    identity = _publish_ready(runtime)[1]
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
    app = create_app(runtime=runtime)
    with caplog.at_level(logging.ERROR), TestClient(
        app, raise_server_exceptions=False
    ) as client:
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "persist fail"},
        )
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "internal_error"
    assert body.get("trace_id") is None
    assert any(
        "grounded_query_trace_persistence_failure" in r.message for r in caplog.records
    )
    runtime.shutdown()


def test_nested_grounded_answer_error_via_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    _publish_ready(runtime)
    inner = CrossEncoderRerankerError("score")
    mid = HybridRerankRetrievalError("rr")
    mid.__cause__ = inner
    ctx = HybridRerankContextError("ctx")
    ctx.__cause__ = mid
    outer = GroundedAnswerError("orch")
    outer.__cause__ = ctx
    _patch_execute(monkeypatch, outer)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/v1/query",
            json={"corpus": "engineering", "question": "nested"},
        )
        assert resp.status_code == 500
        assert "score" not in resp.text
        tid = resp.json()["trace_id"]
        stored = json.loads(_trace_path(settings, tid).read_text(encoding="utf-8"))
        assert stored["internal_failure"]["stage"] == "rerank"
        assert stored["internal_failure"]["failure_class"] == "reranker_failure"
        assert stored["internal_failure"]["exception_type"] == "GroundedAnswerError"
        public = client.get(f"/v1/trace/{tid}").json()
        assert "internal_failure" not in public
    runtime.shutdown()


def test_conversation_turn_shared_core_failure_uses_product_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conversation route must surface product trace_id with internal_failure."""
    from test_slice16d_b3_conversation import (  # type: ignore[import-not-found]
        _conversation_client,
        _seed_workspace,
    )

    with _conversation_client(tmp_path) as (client, runtime, _captures, _gen):
        wid, _, _, _ = _seed_workspace(client)
        fault = DenseRetrievalError("dense via conversation")
        _patch_execute(monkeypatch, fault)
        before_conversation = list(
            (runtime.settings.paths.traces / "conversation").glob("trace_*.json")
        ) if (runtime.settings.paths.traces / "conversation").exists() else []
        resp = client.post(
            f"/v1/workspaces/{wid}/conversation/turn",
            json={"question": "what is common valor?", "prior_turns": []},
        )
        assert resp.status_code == 500, resp.text
        body = resp.json()
        assert body["error"]["code"] == "internal_error"
        tid = body["trace_id"]
        assert tid and tid.startswith("trace_")
        stored = json.loads(_trace_path(runtime.settings, tid).read_text(encoding="utf-8"))
        assert stored["internal_failure"]["stage"] == "dense_query"
        # No requirement to create a conversation diagnostic schema/object.
        after = list(
            (runtime.settings.paths.traces / "conversation").glob("trace_*.json")
        ) if (runtime.settings.paths.traces / "conversation").exists() else []
        assert len(after) == len(before_conversation)
