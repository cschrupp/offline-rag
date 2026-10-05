"""Phase 15H — integration acceptance / Slice 15 closeout evidence harness."""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import logging
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.errors import ERROR_CATALOG, AppError, ErrorCode
from offline_rag.app.ingest import ProductIngestResult, run_product_replace_ingest
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.ingest_upload import spool_local_files
from offline_rag.app.query import ProductQueryResponse, run_product_query
from offline_rag.app.runtime import ApplicationRuntime, ResourceFactories
from offline_rag.cli import cmd_ingest, cmd_query
from offline_rag.config import load_settings
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.domain.generation import GroundedAnswerResult, ResolvedCitation
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.fake import FakeReranker

REPO_ROOT = Path(__file__).resolve().parents[3]
TIKTOKEN_SRC = REPO_ROOT / "models" / "tokenizers" / "tiktoken"
BASELINE_SHA = "b6fe122a34367b39f44405012f022971cc53d858"
APPROVED_MODEL = "local-test-model"
APPROVED_ENDPOINT = "http://127.0.0.1:11434/v1"
SENTINEL_API_KEY = "SENTINEL_LLM_API_KEY_15H_DO_NOT_LEAK"
SENTINEL_HF = "SENTINEL_HF_TOKEN_15H_DO_NOT_LEAK"
SUCCESS_KEYS = {
    "corpus",
    "snapshot_id",
    "product_mode_id",
    "trace_id",
    "status",
    "answer",
    "citations",
}
ALLOWED_OPENAPI_PATHS = {
    "/health",
    "/health/live",
    "/health/ready",
    "/v1/ingest",
    "/v1/query",
    "/v1/documents",
    "/v1/documents/{document_id}",
    "/v1/trace/{trace_id}",
}
FORBIDDEN_OPENAPI_PATHS = {
    "/eval",
    "/eval/run",
    "/v1/eval",
    "/v1/eval/run",
    "/ingest",
    "/query",
    "/v1/query/history",
    "/history",
    "/chat",
    "/v1/chat",
    "/v1/snapshot",
    "/v1/snapshots",
    "/snapshot",
    "/v1/mode",
    "/v1/modes",
    "/v1/admin",
    "/v1/debug",
    "/v1/traces",
}

# D08 closeout evidence matrix: code → (http, retryable, evidence location).
D08_EVIDENCE: dict[ErrorCode, tuple[int | None, bool, str]] = {
    ErrorCode.REQUEST_INVALID: (422, False, "tests/unit/app/test_slice15d_product_ingest.py::test_malformed_non_multipart_is_request_invalid; 15H OpenAPI/D08 smoke"),
    ErrorCode.DOCUMENT_INVALID: (422, False, "tests/unit/app/test_slice15d_product_ingest.py (empty/unsupported/too-large); 15H local spool"),
    ErrorCode.DOCUMENT_UNKNOWN: (404, False, "tests/unit/app/test_slice15c_snapshots_leases_documents.py"),
    ErrorCode.CORPUS_UNKNOWN: (404, False, "tests/unit/app/test_slice15c_snapshots_leases_documents.py"),
    ErrorCode.CORPUS_NOT_READY: (409, False, "tests/unit/app/test_slice15c_snapshots_leases_documents.py"),
    ErrorCode.CORPUS_BUSY: (409, True, "tests/unit/app/test_slice15d_product_ingest.py / test_slice15f_*"),
    ErrorCode.SNAPSHOT_UNAVAILABLE: (409, False, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.INGEST_FAILED: (500, False, "tests/unit/app/test_slice15d_product_ingest.py::test_stage_failure_leaves_published_n"),
    ErrorCode.GENERATION_UNAVAILABLE: (502, True, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.GENERATION_TIMEOUT: (504, True, "tests/unit/app/test_slice15e_product_query_traces.py; test_slice15f_* generation_timeout vs request_timeout"),
    ErrorCode.GENERATION_FAILED: (502, False, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.RESPONSE_PARSE_ERROR: (502, False, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.CITATION_INVALID: (502, False, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.RUNTIME_NOT_READY: (503, True, "tests/unit/app/test_slice15b_runtime_health.py; 15H strict-offline missing asset"),
    ErrorCode.SERVICE_OVERLOADED: (503, True, "tests/unit/app/test_slice15f_admission_deadlines_shutdown.py; 15H overload smoke"),
    ErrorCode.REQUEST_TIMEOUT: (504, True, "tests/unit/app/test_slice15f_admission_deadlines_shutdown.py::test_short_deadline_maps_to_request_timeout"),
    ErrorCode.REQUEST_CANCELLED: (None, True, "tests/unit/app/test_slice15f_admission_deadlines_shutdown.py (trace-terminal; no HTTP status)"),
    ErrorCode.TRACE_UNKNOWN: (404, False, "tests/unit/app/test_slice15e_product_query_traces.py"),
    ErrorCode.INTERNAL_ERROR: (500, False, "tests/unit/app/test_slice15a_foundation.py / test_slice15e_*"),
}


class _Closeable:
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


def _settings(tmp_path: Path, **api_overrides: object) -> AppSettings:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        "OFFLINE_RAG_LLM_API_KEY": SENTINEL_API_KEY,
        "HF_TOKEN": SENTINEL_HF,
    }
    settings = load_settings(yaml_paths=[], environ=environ)
    generation = settings.generation.model_copy(
        update={
            "base_url": APPROVED_ENDPOINT,
            "model": APPROVED_MODEL,
            "approved_endpoints": [APPROVED_ENDPOINT],
            "approved_models": [APPROVED_MODEL],
            "api_key": SENTINEL_API_KEY,
        }
    )
    api = settings.api.model_copy(update=api_overrides) if api_overrides else settings.api
    reranker = settings.reranker.model_copy(
        update={"enabled": True, "implementation": "fake"}
    )
    settings = settings.model_copy(
        update={"generation": generation, "api": api, "reranker": reranker}
    )
    _provision_assets(settings)
    return settings


def _runtime(settings: AppSettings) -> ApplicationRuntime:
    embedder = FakeEmbedder(dimension=8, normalize=True)
    reranker = FakeReranker()

    def _qdrant(s: AppSettings) -> QdrantLocalBackend:
        return QdrantLocalBackend(s.paths.qdrant_storage)

    return ApplicationRuntime(
        settings=settings,
        factories=ResourceFactories(
            embedder=lambda _s: embedder,
            reranker=lambda _s: reranker,
            generator_client=lambda _s: _Closeable(),
            qdrant=_qdrant,
        ),
    )


def _multipart(
    parts: list[tuple[str, bytes | None, str | None]], boundary: str = "----15h"
) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    for name, body, filename in parts:
        chunks.append(f"--{boundary}\r\n".encode())
        if filename is None:
            chunks.append(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
        else:
            chunks.append(
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                    f"Content-Type: application/octet-stream\r\n\r\n"
                ).encode()
            )
        if body:
            chunks.append(body)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post_ingest(client: TestClient, parts: list[tuple[str, bytes | None, str | None]]):
    body, ct = _multipart(parts)
    return client.post("/v1/ingest", content=body, headers={"Content-Type": ct})


def _citation_for(document_id: str) -> ResolvedCitation:
    return ResolvedCitation(
        evidence_unit_id="eu_15h",
        source_chunk_id="chunk_15h",
        kind="child",
        document_id=document_id,
        section_path=["Overview"],
        page_start=1,
        page_end=1,
        line_start=1,
        line_end=2,
        clipped=False,
        representation="full",
        metadata={"secret": SENTINEL_API_KEY},
        clip={"raw": SENTINEL_HF},
    )


def _canned_answered(
    document_id: str,
    *,
    answer: str = "Pump pressure is 42 psi.",
    dense_index_id: str | None = None,
    lexical_index_id: str | None = None,
    context_config_hash: str | None = None,
    fusion_config_hash: str | None = None,
    reranker_config_hash: str | None = None,
) -> GroundedAnswerResult:
    return GroundedAnswerResult(
        method="query",
        query="what is pump pressure?",
        status="answered",
        answer_text=answer,
        citations=[_citation_for(document_id)],
        generator_invoked=True,
        attempt_count=1,
        generation_config_hash="gencfg_15h",
        context_config_hash=context_config_hash,
        dense_index_id=dense_index_id,
        lexical_index_id=lexical_index_id,
        fusion_config_hash=fusion_config_hash,
        reranker_config_hash=reranker_config_hash,
        diagnostics={"latency_ms": {"context": 1, "generation": 2, "total": 3}},
    )


def _patch_execute_for_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    runtime: ApplicationRuntime,
    *,
    corpus: str,
    document_id: str,
    answer: str = "Pump pressure is 42 psi.",
) -> None:
    def _fake(handle: Any, question: str, *, control: object | None = None) -> GroundedAnswerResult:
        del question, control
        binding = handle.binding
        assert binding.corpus_name == corpus
        return _canned_answered(
            document_id,
            answer=answer,
            dense_index_id=binding.dense_index_id,
            lexical_index_id=binding.lexical_index_id,
            context_config_hash=binding.context_config_hash,
            fusion_config_hash=binding.fusion_config_hash,
            reranker_config_hash=binding.reranker_config_hash,
        )

    monkeypatch.setattr("offline_rag.app.query._execute_snapshot_query", _fake)


# ---------------------------------------------------------------------------
# Ancestry / governance
# ---------------------------------------------------------------------------


def test_remote_ancestry_begins_at_15h_baseline() -> None:
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
# CLI → app migration
# ---------------------------------------------------------------------------


def test_cli_source_forbids_scientific_bypass() -> None:
    cli_path = REPO_ROOT / "src" / "offline_rag" / "cli.py"
    tree = ast.parse(cli_path.read_text(encoding="utf-8"))
    ingest_fn = None
    query_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_ingest":
            ingest_fn = node
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_query":
            query_fn = node
    assert ingest_fn is not None
    assert query_fn is not None
    ingest_src = ast.get_source_segment(cli_path.read_text(encoding="utf-8"), ingest_fn) or ""
    query_src = ast.get_source_segment(cli_path.read_text(encoding="utf-8"), query_fn) or ""
    assert "run_product_replace_ingest" in ingest_src
    assert "run_ingestion(" not in ingest_src
    assert "run_product_query" in query_src
    assert "GroundedAnswerOrchestrator" not in query_src


def test_cli_ingest_uses_app_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    calls: list[dict[str, Any]] = []

    def fake_run(rt: ApplicationRuntime, upload: Any, *, hooks=None, control=None):
        calls.append(
            {
                "runtime": rt,
                "corpus": upload.corpus_name,
                "files": len(upload.files),
                "control": control,
            }
        )
        return ProductIngestResult(
            corpus=upload.corpus_name,
            snapshot_id="snap_cli_15h",
            document_count=len(upload.files),
        )

    monkeypatch.setattr("offline_rag.cli._build_product_runtime", lambda _s: runtime)
    monkeypatch.setattr("offline_rag.cli.run_product_replace_ingest", fake_run)

    src = tmp_path / "a.txt"
    src.write_text("CLI ingest source A.\n", encoding="utf-8")
    args = argparse.Namespace(
        paths=[str(src)],
        corpus="manuals",
        recursive=False,
        root=None,
        json=True,
        config=None,
    )
    code = cmd_ingest(args)
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload == {
        "corpus": "manuals",
        "snapshot_id": "snap_cli_15h",
        "document_count": 1,
    }
    assert len(calls) == 1
    assert calls[0]["runtime"] is runtime
    assert calls[0]["control"] is not None
    runtime.shutdown()


def test_cli_query_uses_app_layer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    calls: list[dict[str, Any]] = []

    def fake_query(
        rt: ApplicationRuntime,
        *,
        corpus: str,
        question: str,
        control=None,
    ) -> ProductQueryResponse:
        calls.append(
            {
                "runtime": rt,
                "corpus": corpus,
                "question": question,
                "control": control,
            }
        )
        return ProductQueryResponse(
            corpus=corpus,
            snapshot_id="snap_q",
            product_mode_id="grounded_v1",
            trace_id="tr_cli",
            status="answered",
            answer="42",
            citations=[
                {
                    "evidence_unit_id": "eu_1",
                    "document_id": "doc_1",
                    "source_chunk_id": "chunk_1",
                    "kind": "child",
                    "section_path": [],
                    "page_start": None,
                    "page_end": None,
                    "line_start": None,
                    "line_end": None,
                    "clipped": False,
                }
            ],
        )

    class Boom:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            raise AssertionError("CLI must not construct GroundedAnswerOrchestrator")

    monkeypatch.setattr("offline_rag.cli._build_product_runtime", lambda _s: runtime)
    monkeypatch.setattr("offline_rag.cli.run_product_query", fake_query)
    monkeypatch.setattr(
        "offline_rag.generation.orchestrate.GroundedAnswerOrchestrator", Boom
    )

    args = argparse.Namespace(
        corpus="manuals",
        query="what pressure?",
        json=True,
        config=None,
    )
    code = cmd_query(args)
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["product_mode_id"] == "grounded_v1"
    assert payload["trace_id"] == "tr_cli"
    assert len(calls) == 1
    assert calls[0]["control"] is not None
    runtime.shutdown()


def test_spool_local_files_feeds_product_ingest(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    runtime.start()
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("Local spool document A.\n", encoding="utf-8")
    b.write_text("Local spool document B.\n", encoding="utf-8")
    upload = spool_local_files(
        settings=settings,
        corpus_name="manuals",
        files=[(a, "a.txt"), (b, "b.txt")],
    )
    result = run_product_replace_ingest(runtime, upload)
    assert result.corpus == "manuals"
    assert result.document_count == 2
    assert result.snapshot_id.startswith("snap_")
    runtime.shutdown()


# ---------------------------------------------------------------------------
# Complete product path + replace + read-during-ingest
# ---------------------------------------------------------------------------


def test_complete_product_path_replace_and_read_during_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 200

        first = _post_ingest(
            client,
            [
                ("corpus", b"manuals", None),
                ("files", b"Document A pump pressure is 42 psi.\n", "a.txt"),
                ("files", b"Document B valve torque is 18 Nm.\n", "b.txt"),
            ],
        )
        assert first.status_code == 200
        snap_n = first.json()["snapshot_id"]
        assert first.json()["document_count"] == 2

        docs = client.get("/v1/documents", params={"corpus": "manuals"})
        assert docs.status_code == 200
        docs_body = docs.json()
        assert docs_body["snapshot_id"] == snap_n
        names = sorted(d["source_name"] for d in docs_body["documents"])
        assert names == ["a.txt", "b.txt"]
        doc_a = next(d for d in docs_body["documents"] if d["source_name"] == "a.txt")
        one = client.get(
            f"/v1/documents/{doc_a['document_id']}",
            params={"corpus": "manuals"},
        )
        assert one.status_code == 200
        assert one.json()["document"]["document_id"] == doc_a["document_id"]

        _patch_execute_for_snapshot(
            monkeypatch,
            runtime,
            corpus="manuals",
            document_id=doc_a["document_id"],
        )
        q1 = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": "what is pump pressure?"},
        )
        assert q1.status_code == 200
        q1_body = q1.json()
        assert set(q1_body.keys()) == SUCCESS_KEYS
        assert q1_body["product_mode_id"] == "grounded_v1"
        assert q1_body["status"] == "answered"
        assert q1_body["answer"]
        assert q1_body["citations"]
        assert q1_body["snapshot_id"] == snap_n
        assert all(
            c["document_id"] == doc_a["document_id"] for c in q1_body["citations"]
        )

        tr = client.get(f"/v1/trace/{q1_body['trace_id']}")
        assert tr.status_code == 200
        tr_body = tr.json()
        assert tr_body["corpus"] == "manuals"
        assert tr_body["snapshot_id"] == snap_n
        assert tr_body["status"] == "answered"
        assert SENTINEL_API_KEY not in tr.text
        assert SENTINEL_HF not in tr.text

        # Hold N+1 after lease / mutation start, query must remain on N.
        hold = threading.Event()
        released = threading.Event()

        def after_lease(corpus: str, candidate_root: Path) -> None:
            del corpus, candidate_root
            hold.set()
            released.wait(timeout=10)

        runtime.product_ingest_hooks = ProductIngestHooks(after_lease_acquired=after_lease)
        mid_query: dict[str, Any] = {}

        def reader() -> None:
            hold.wait(timeout=10)
            op = None
            try:
                # In-process product query against the live runtime (avoids
                # TestClient thread-safety issues while still exercising app).
                op = runtime.operations.admit_query()
                result = run_product_query(
                    runtime,
                    corpus="manuals",
                    question="still on snapshot N?",
                    control=op,
                )
                mid_query["snapshot_id"] = result.snapshot_id
                mid_query["status"] = result.status
            except Exception as exc:  # noqa: BLE001
                mid_query["error"] = exc
            finally:
                if op is not None:
                    runtime.operations.release(op)
                released.set()

        thread = threading.Thread(target=reader)
        thread.start()
        second = _post_ingest(
            client,
            [
                ("corpus", b"manuals", None),
                ("files", b"Document B valve torque is 18 Nm.\n", "b.txt"),
                ("files", b"Document C filter interval is 250 hours.\n", "c.txt"),
            ],
        )
        thread.join(timeout=15)
        assert second.status_code == 200
        snap_n1 = second.json()["snapshot_id"]
        assert snap_n1 != snap_n
        assert "error" not in mid_query
        assert mid_query.get("snapshot_id") == snap_n

        docs2 = client.get("/v1/documents", params={"corpus": "manuals"}).json()
        assert docs2["snapshot_id"] == snap_n1
        names2 = sorted(d["source_name"] for d in docs2["documents"])
        assert names2 == ["b.txt", "c.txt"]
        assert all(d["source_name"] != "a.txt" for d in docs2["documents"])
        doc_c = next(d for d in docs2["documents"] if d["source_name"] == "c.txt")

        _patch_execute_for_snapshot(
            monkeypatch,
            runtime,
            corpus="manuals",
            document_id=doc_c["document_id"],
            answer="Filter interval is 250 hours.",
        )
        q2 = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": "what is the filter interval?"},
        )
        assert q2.status_code == 200
        assert q2.json()["snapshot_id"] == snap_n1
        assert all(
            c["document_id"] == doc_c["document_id"] for c in q2.json()["citations"]
        )


# ---------------------------------------------------------------------------
# OpenAPI + D08 matrix
# ---------------------------------------------------------------------------


def test_openapi_exact_product_path_set(tmp_path: Path) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        paths = set(client.get("/openapi.json").json().get("paths", {}))
    product_paths = {p for p in paths if p.startswith(("/health", "/v1/"))}
    assert product_paths == ALLOWED_OPENAPI_PATHS
    for forbidden in FORBIDDEN_OPENAPI_PATHS:
        assert forbidden not in paths


def test_d08_closeout_evidence_matrix_complete() -> None:
    assert set(D08_EVIDENCE) == set(ErrorCode)
    assert set(D08_EVIDENCE) == set(ERROR_CATALOG)
    for code, (http, retryable, evidence) in D08_EVIDENCE.items():
        assert ERROR_CATALOG[code].http_status == http
        assert ERROR_CATALOG[code].retryable is retryable
        assert evidence.strip()


def test_representative_d08_request_invalid_and_unknown(
    tmp_path: Path,
) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        bad = client.post(
            "/v1/ingest",
            content=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert bad.status_code == 422
        assert bad.json()["error"]["code"] == "request_invalid"
        assert bad.json()["retryable"] is False

        unknown = client.get("/v1/trace/tr_does_not_exist")
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "trace_unknown"


# ---------------------------------------------------------------------------
# Strict offline / secrets / overload
# ---------------------------------------------------------------------------


def test_strict_offline_missing_embedding_asset_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = {
        "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
        "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
        "OFFLINE_RAG_STRICT_OFFLINE": "true",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
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
    # Docling + tokenizer present; omit embedding model directory contents.
    _provision_assets(settings)
    settings.paths.embedding_artifacts.mkdir(parents=True, exist_ok=True)

    # Production factories attempt real embedder construction → fail closed.
    runtime = ApplicationRuntime(settings=settings)
    # Prevent accidental network by ensuring offline env is visible.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    runtime.start()
    assert runtime.is_ready is False
    assert runtime.failure_reason == "startup_failed"
    with pytest.raises(AppError) as exc:
        runtime.require_ready()
    assert exc.value.code is ErrorCode.RUNTIME_NOT_READY


def test_secret_non_leakage_in_health_errors_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _settings(tmp_path)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client, caplog.at_level(
        logging.INFO
    ):
        health = client.get("/health/ready")
        assert health.status_code == 200
        assert SENTINEL_API_KEY not in health.text
        assert SENTINEL_HF not in health.text

        bad = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": ""},
        )
        assert bad.status_code == 422
        assert SENTINEL_API_KEY not in bad.text
        assert SENTINEL_HF not in bad.text

        first = _post_ingest(
            client,
            [
                ("corpus", b"manuals", None),
                ("files", b"Secret nonleak fixture document.\n", "a.txt"),
            ],
        )
        assert first.status_code == 200
        doc_id = client.get("/v1/documents", params={"corpus": "manuals"}).json()[
            "documents"
        ][0]["document_id"]
        _patch_execute_for_snapshot(
            monkeypatch, runtime, corpus="manuals", document_id=doc_id
        )
        q = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": "secret marker question"},
        )
        assert q.status_code == 200
        assert SENTINEL_API_KEY not in q.text
        tr = client.get(f"/v1/trace/{q.json()['trace_id']}")
        assert SENTINEL_API_KEY not in tr.text
        assert SENTINEL_HF not in tr.text
        assert SENTINEL_API_KEY not in caplog.text
        assert SENTINEL_HF not in caplog.text


def test_query_overload_fail_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, max_concurrent_query=1)
    runtime = _runtime(settings)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        first = _post_ingest(
            client,
            [
                ("corpus", b"manuals", None),
                ("files", b"Overload fixture document.\n", "a.txt"),
            ],
        )
        assert first.status_code == 200
        doc_id = client.get("/v1/documents", params={"corpus": "manuals"}).json()[
            "documents"
        ][0]["document_id"]

        gate = threading.Event()
        entered = threading.Event()

        def _blocking(handle: Any, question: str, *, control: object | None = None):
            del question, control
            entered.set()
            gate.wait(timeout=10)
            binding = handle.binding
            return _canned_answered(
                doc_id,
                dense_index_id=binding.dense_index_id,
                lexical_index_id=binding.lexical_index_id,
                context_config_hash=binding.context_config_hash,
                fusion_config_hash=binding.fusion_config_hash,
                reranker_config_hash=binding.reranker_config_hash,
            )

        monkeypatch.setattr("offline_rag.app.query._execute_snapshot_query", _blocking)

        # Hold capacity via in-process admit + use case (TestClient is not
        # reliably concurrent across threads).
        def _hold() -> None:
            op = runtime.operations.admit_query()
            try:
                run_product_query(
                    runtime,
                    corpus="manuals",
                    question="hold the capacity slot",
                    control=op,
                )
            finally:
                runtime.operations.release(op)

        t = threading.Thread(target=_hold)
        t.start()
        assert entered.wait(timeout=5)
        overloaded = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": "should fail fast"},
        )
        assert overloaded.status_code == 503
        assert overloaded.json()["error"]["code"] == "service_overloaded"
        assert overloaded.json().get("trace_id") in {None, ""}
        gate.set()
        t.join(timeout=10)


def test_drain_rejects_new_work_while_live_remains(
    tmp_path: Path,
) -> None:
    runtime = _runtime(_settings(tmp_path))
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health/ready").status_code == 200
        runtime.begin_drain()
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["error"]["code"] == "runtime_not_ready"
        live = client.get("/health/live")
        assert live.status_code == 200
        rejected = client.post(
            "/v1/query",
            json={"corpus": "manuals", "question": "during drain"},
        )
        assert rejected.status_code == 503
        assert rejected.json()["error"]["code"] == "runtime_not_ready"


def test_cli_helpers_exported_for_inspection() -> None:
    # Keep a cheap smoke that product entrypoints remain importable.
    assert callable(cmd_ingest)
    assert callable(cmd_query)
    assert "run_product_replace_ingest" in inspect.getsource(cmd_ingest)
    assert "run_product_query" in inspect.getsource(cmd_query)
