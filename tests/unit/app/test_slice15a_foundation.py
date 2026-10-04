"""Phase 15A — app boundary, D08 catalog, Residual A settings, path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from offline_rag.app import (
    ERROR_CATALOG,
    AppError,
    ErrorCode,
    app_error_from_validation_errors,
    ensure_data_directories,
    error_response_from_app_error,
    http_status_for,
    project_validation_errors,
    required_data_directories,
    retryable_for,
    sanitize_error_details,
    validate_product_corpus_name,
)
from offline_rag.config import load_settings
from offline_rag.dense.provision import resolve_embedding_model_dir
from offline_rag.rerank.provision import resolve_reranker_model_dir

REPO_ROOT = Path(__file__).resolve().parents[3]

# Locked D08 HTTP mappings (request_cancelled has none).
_EXPECTED_HTTP: dict[ErrorCode, int | None] = {
    ErrorCode.REQUEST_INVALID: 422,
    ErrorCode.DOCUMENT_INVALID: 422,
    ErrorCode.DOCUMENT_UNKNOWN: 404,
    ErrorCode.CORPUS_UNKNOWN: 404,
    ErrorCode.CORPUS_NOT_READY: 409,
    ErrorCode.CORPUS_BUSY: 409,
    ErrorCode.SNAPSHOT_UNAVAILABLE: 409,
    ErrorCode.INGEST_FAILED: 500,
    ErrorCode.GENERATION_UNAVAILABLE: 502,
    ErrorCode.GENERATION_TIMEOUT: 504,
    ErrorCode.GENERATION_FAILED: 502,
    ErrorCode.RESPONSE_PARSE_ERROR: 502,
    ErrorCode.CITATION_INVALID: 502,
    ErrorCode.RUNTIME_NOT_READY: 503,
    ErrorCode.SERVICE_OVERLOADED: 503,
    ErrorCode.REQUEST_TIMEOUT: 504,
    ErrorCode.REQUEST_CANCELLED: None,
    ErrorCode.TRACE_UNKNOWN: 404,
    ErrorCode.INTERNAL_ERROR: 500,
}

_EXPECTED_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.REQUEST_INVALID: False,
    ErrorCode.DOCUMENT_INVALID: False,
    ErrorCode.DOCUMENT_UNKNOWN: False,
    ErrorCode.CORPUS_UNKNOWN: False,
    ErrorCode.CORPUS_NOT_READY: False,
    ErrorCode.CORPUS_BUSY: True,
    ErrorCode.SNAPSHOT_UNAVAILABLE: False,
    ErrorCode.INGEST_FAILED: False,
    ErrorCode.GENERATION_UNAVAILABLE: True,
    ErrorCode.GENERATION_TIMEOUT: True,
    ErrorCode.GENERATION_FAILED: False,
    ErrorCode.RESPONSE_PARSE_ERROR: False,
    ErrorCode.CITATION_INVALID: False,
    ErrorCode.RUNTIME_NOT_READY: True,
    ErrorCode.SERVICE_OVERLOADED: True,
    ErrorCode.REQUEST_TIMEOUT: True,
    ErrorCode.REQUEST_CANCELLED: True,
    ErrorCode.TRACE_UNKNOWN: False,
    ErrorCode.INTERNAL_ERROR: False,
}


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("manuals", True),
        ("default", True),
        ("A", True),
        ("a.b_c-1", True),
        ("x" * 64, True),
        ("", False),
        (" ", False),
        ("-bad", False),
        (".bad", False),
        ("bad/name", False),
        ("bad\\name", False),
        ("../x", False),
        ("x" * 65, False),
    ],
)
def test_product_corpus_name_grammar(name: str, ok: bool) -> None:
    if ok:
        assert validate_product_corpus_name(name) == name
    else:
        with pytest.raises(AppError) as exc_info:
            validate_product_corpus_name(name)
        assert exc_info.value.code is ErrorCode.REQUEST_INVALID
        assert exc_info.value.http_status == 422
        assert exc_info.value.retryable is False


def test_d08_catalog_complete_and_mapped() -> None:
    assert set(ERROR_CATALOG) == set(ErrorCode)
    assert set(ERROR_CATALOG) == set(_EXPECTED_HTTP)
    assert set(ERROR_CATALOG) == set(_EXPECTED_RETRYABLE)
    for code in ErrorCode:
        assert retryable_for(code) is _EXPECTED_RETRYABLE[code]
        assert http_status_for(code) == _EXPECTED_HTTP[code]
        assert ERROR_CATALOG[code].http_status == _EXPECTED_HTTP[code]
    assert http_status_for(ErrorCode.REQUEST_CANCELLED) is None
    assert ERROR_CATALOG[ErrorCode.REQUEST_CANCELLED].http_status is None


def test_error_response_envelope_safe() -> None:
    err = AppError(
        ErrorCode.CORPUS_BUSY,
        details={"corpus": "manuals"},
        trace_id="trace-1",
    )
    payload = error_response_from_app_error(err).model_dump(mode="json")
    assert payload == {
        "error": {"code": "corpus_busy", "message": err.message},
        "retryable": True,
        "trace_id": "trace-1",
        "details": {"corpus": "manuals"},
    }


@pytest.mark.parametrize(
    "secret_key",
    [
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
        "credential",
        "private_key",
        "API_KEY",
        "Authorization",
    ],
)
def test_app_error_details_drop_secret_bearing_keys(secret_key: str) -> None:
    err = AppError(
        ErrorCode.INTERNAL_ERROR,
        details={
            secret_key: "super-secret-value",
            "corpus": "manuals",
            "traceback": "should-also-drop",
        },
    )
    assert err.details == {"corpus": "manuals"}
    payload = error_response_from_app_error(err).model_dump(mode="json")
    text = str(payload)
    assert "super-secret-value" not in text
    assert secret_key.lower().replace("-", "_") not in str(payload.get("details"))
    assert payload["details"] == {"corpus": "manuals"}
    assert sanitize_error_details({secret_key: "x", "reason": "ok"}) == {"reason": "ok"}


def test_residual_a_defaults_without_env() -> None:
    settings = load_settings(yaml_paths=[], environ={})
    api = settings.api
    assert api.product_mode_id == "grounded_v1"
    assert api.max_files_per_ingest == 32
    assert api.max_bytes_per_document == 26_214_400
    assert api.max_total_upload_bytes == 104_857_600
    assert api.max_question_chars == 8_000
    assert api.query_deadline_seconds == 180
    assert api.ingest_deadline_seconds == 1_800
    assert api.max_concurrent_query == 1
    assert api.max_concurrent_ingest == 1
    assert api.admission_wait_seconds == 0
    assert api.shutdown_grace_seconds == 30
    assert api.http_host == "127.0.0.1"
    assert api.http_port == 8080
    assert api.allow_non_loopback is False
    assert api.trace_retention_days == 7
    assert api.trace_retention_max_count == 1_000
    assert settings.paths.raw_data == Path("data/raw")
    assert settings.paths.traces == Path("data/traces")
    assert settings.paths.staging == Path("data/staging")
    assert settings.paths.locks == Path("data/locks")


def test_residual_a_env_overrides_and_precedence(tmp_path: Path) -> None:
    yaml_path = tmp_path / "overlay.yaml"
    yaml_path.write_text(
        "api:\n  max_question_chars: 1000\n  http_port: 9000\n",
        encoding="utf-8",
    )
    settings = load_settings(
        yaml_paths=[yaml_path],
        environ={
            "OFFLINE_RAG_MAX_QUESTION_CHARS": "2000",
            "OFFLINE_RAG_HTTP_PORT": "8081",
            "OFFLINE_RAG_ALLOW_NON_LOOPBACK": "true",
            "OFFLINE_RAG_MAX_CONCURRENT_QUERY": "1",
            "OFFLINE_RAG_TRACE_RETENTION_DAYS": "3",
        },
        overrides={"api": {"max_question_chars": 3000}},
    )
    assert settings.api.max_question_chars == 3000  # overrides win
    assert settings.api.http_port == 8081  # env over yaml
    assert settings.api.allow_non_loopback is True
    assert settings.api.trace_retention_days == 3


def test_data_dir_resolves_frozen_layout() -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_DATA_DIR": "/data"},
    )
    root = Path("/data")
    assert settings.paths.raw_data == root / "raw"
    assert settings.paths.qdrant_storage == root / "qdrant"
    assert settings.paths.corpora == root / "corpora"
    assert settings.paths.manifests == root / "manifests"
    assert settings.paths.processed == root / "processed"
    assert settings.paths.chunks == root / "chunks"
    assert settings.paths.chunk_manifests == root / "chunk-manifests"
    assert settings.paths.embeddings == root / "embeddings"
    assert settings.paths.index_manifests == root / "index-manifests"
    assert settings.paths.lexical_indexes == root / "lexical-indexes"
    assert settings.paths.lexical_index_manifests == root / "lexical-index-manifests"
    assert settings.paths.traces == root / "traces"
    assert settings.paths.staging == root / "staging"
    assert settings.paths.locks == root / "locks"
    assert settings.paths.logs == root / "logs"
    assert settings.paths.eval_results == root / "eval" / "results"


def test_models_dir_rebases_provisioned_assets() -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_MODELS_DIR": "/models"},
    )
    root = Path("/models")
    assert settings.paths.retrieval_models == root
    assert settings.paths.docling_artifacts == root / "docling"
    assert settings.paths.tokenizer_artifacts == root / "tokenizers" / "tiktoken"
    assert settings.paths.embedding_artifacts == root / "embeddings"
    assert settings.paths.reranker_artifacts == root / "rerankers"


def test_models_dir_rebases_effective_runtime_model_paths() -> None:
    """MODELS_DIR must control paths used by embedder/reranker resolvers."""
    settings = load_settings(
        yaml_paths=[REPO_ROOT / "config" / "base.yaml"],
        environ={"OFFLINE_RAG_MODELS_DIR": "/models"},
    )
    root = Path("/models")
    assert settings.paths.embedding_artifacts == root / "embeddings"
    assert settings.paths.reranker_artifacts == root / "rerankers"
    assert settings.dense.model_path == root / "embeddings" / "qwen3-embedding-0.6b"
    assert settings.reranker.model.model_path == root / "rerankers" / "bge-reranker-v2-m3"

    embedding_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=settings.dense.model_path,
    )
    reranker_dir = resolve_reranker_model_dir(
        reranker_artifacts_root=settings.paths.reranker_artifacts,
        model_path=settings.reranker.model.model_path,
    )
    assert embedding_dir == (root / "embeddings" / "qwen3-embedding-0.6b").resolve()
    assert reranker_dir == (root / "rerankers" / "bge-reranker-v2-m3").resolve()
    assert embedding_dir.is_relative_to(root.resolve())
    assert reranker_dir.is_relative_to(root.resolve())


def test_models_dir_runtime_path_respects_explicit_overrides() -> None:
    settings = load_settings(
        yaml_paths=[REPO_ROOT / "config" / "base.yaml"],
        environ={"OFFLINE_RAG_MODELS_DIR": "/models"},
        overrides={"dense": {"model_path": "/custom/embed"}},
    )
    assert settings.dense.model_path == Path("/custom/embed")
    assert settings.reranker.model.model_path == Path("/models/rerankers/bge-reranker-v2-m3")


def test_api_excluded_from_canonical_dict() -> None:
    settings = load_settings(yaml_paths=[], environ={})
    canonical = settings.to_canonical_dict()
    assert "api" not in canonical
    assert "paths" in canonical


def test_validation_projection_allowlisted_and_no_input_echo() -> None:
    errors = [
        {
            "loc": ("body", "api_key"),
            "msg": "Field required",
            "type": "missing",
            "input": "sk-super-secret",
        },
        {
            "loc": ("body", "question"),
            "msg": "ensure this value has at most 8000 characters",
            "type": "string_too_long",
            "input": "x" * 20,
        },
    ]
    projected = project_validation_errors(errors)
    assert "input" not in str(projected)
    assert "sk-super-secret" not in str(projected)
    assert projected["fields"][0]["msg"] == "Invalid value"
    assert projected["fields"][0]["loc"] == ["body", "api_key"]
    assert projected["fields"][1]["loc"] == ["body", "question"]


def test_validation_translator_request_invalid_envelope() -> None:
    class _Probe(BaseModel):
        model_config = ConfigDict(extra="forbid")

        corpus: str
        question: str

    with pytest.raises(ValidationError) as exc_info:
        _Probe.model_validate(
            {"corpus": "manuals", "question": "q", "temperature": 0.8}
        )
    app_error = app_error_from_validation_errors(exc_info.value.errors())
    assert app_error.code is ErrorCode.REQUEST_INVALID
    assert app_error.http_status == 422
    assert app_error.retryable is False
    response = error_response_from_app_error(app_error)
    dumped = response.model_dump(mode="json")
    assert dumped["error"]["code"] == "request_invalid"
    assert dumped["retryable"] is False
    assert dumped["error"]["message"] == "Request validation failed"
    assert "fields" in dumped["details"]
    assert "0.8" not in str(dumped)


def test_ensure_data_directories_is_startup_owned(tmp_path: Path) -> None:
    settings = load_settings(
        yaml_paths=[],
        environ={"OFFLINE_RAG_DATA_DIR": str(tmp_path / "data")},
    )
    required = required_data_directories(settings)
    assert settings.paths.raw_data in required
    assert settings.paths.locks in required
    assert settings.paths.traces in required
    for path in required:
        assert not path.exists()
    ensure_data_directories(settings)
    for path in required:
        assert path.is_dir()
    # Optional logs/eval are not required startup roots.
    assert settings.paths.logs not in required
    assert settings.paths.eval_results not in required
