"""Slice 16A server-rendered query adapter contract."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from offline_rag.api import query as query_api
from offline_rag.api.app import create_app
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.query import MAX_QUESTION_CHARS, ProductQueryResponse
from offline_rag.app.runtime import ApplicationRuntime
from offline_rag.config import load_settings

BASELINE_SHA = "c72215186524c9937de789adb1cf2056be13ea23"


@pytest.fixture
def ui_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ApplicationRuntime]]:
    settings = load_settings(
        yaml_paths=[],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(tmp_path / "data"),
            "OFFLINE_RAG_MODELS_DIR": str(tmp_path / "models"),
            "OFFLINE_RAG_STRICT_OFFLINE": "false",
        },
    )
    runtime = ApplicationRuntime(settings=settings)
    monkeypatch.setattr(runtime, "start", lambda: None)

    async def _drain() -> None:
        return None

    monkeypatch.setattr(runtime, "drain_async", _drain)
    monkeypatch.setattr(runtime, "require_ready", lambda: None)
    app = create_app(runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, runtime


def _response(
    *,
    status: str = "answered",
    answer: str | None = "A grounded answer.",
    citations: list[dict[str, Any]] | None = None,
) -> ProductQueryResponse:
    return ProductQueryResponse(
        corpus="engineering",
        snapshot_id="snapshot_123",
        product_mode_id="grounded_v1",
        trace_id="trace_123",
        status=status,  # type: ignore[arg-type]
        answer=answer,
        citations=list(citations or []),
    )


def _patch_product_query(
    monkeypatch: pytest.MonkeyPatch,
    result: ProductQueryResponse | Exception,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def _run(
        runtime: ApplicationRuntime,
        *,
        corpus: str,
        question: str,
        control: object | None = None,
    ) -> ProductQueryResponse:
        calls.append(
            {
                "runtime": runtime,
                "corpus": corpus,
                "question": question,
                "control": control,
            }
        )
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(query_api, "run_product_query", _run)
    return calls


def _assert_security_headers(response: Any) -> None:
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )


def _post_form(client: TestClient, fields: list[tuple[str, str]]) -> Any:
    return client.post(
        "/ui/query",
        content=urlencode(fields),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def test_get_ui_is_idle_safe_and_has_accessible_form(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    calls = _patch_product_query(monkeypatch, _response())

    response = client.get("/ui")

    assert response.status_code == 200
    _assert_security_headers(response)
    assert '<form method="post" action="/ui/query">' in response.text
    assert '<label for="corpus">Corpus</label>' in response.text
    assert '<input id="corpus" name="corpus"' in response.text
    assert '<label for="question">Question</label>' in response.text
    assert '<textarea id="question" name="question"' in response.text
    assert 'type="submit">Ask this corpus</button>' in response.text
    assert "Submit a question" in response.text
    assert calls == []
    assert runtime.operations.active_count() == 0


def test_ui_uses_canonical_query_seam_and_renders_answer_citations_and_provenance(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    result = _response(
        answer='Answer says <script>alert("x")</script>',
        citations=[
            {
                "evidence_unit_id": "eu_1",
                "document_id": 'doc"><img src=x onerror=alert(1)>',
                "source_chunk_id": "chunk_1",
                "kind": "child",
                "section_path": ["Methods", "Pressure"],
                "page_start": 3,
                "page_end": 4,
                "line_start": None,
                "line_end": None,
                "clipped": False,
                "internal_trace": "do-not-render",
            }
        ],
    )
    calls = _patch_product_query(monkeypatch, result)

    response = _post_form(
        client,
        [("corpus", "engineering"), ("question", "  how is pressure measured?  ")],
    )

    assert response.status_code == 200
    _assert_security_headers(response)
    assert len(calls) == 1
    assert calls[0]["runtime"] is runtime
    assert calls[0]["corpus"] == "engineering"
    assert calls[0]["question"] == "how is pressure measured?"
    assert calls[0]["control"] is not None
    assert (
        "Answer says &lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in response.text
    )
    assert "eu_1" in response.text
    assert "Methods / Pressure" in response.text
    assert "snapshot_123" in response.text
    assert "trace_123" in response.text
    assert "grounded_v1" in response.text
    assert "do-not-render" not in response.text
    assert '<script>alert("x")</script>' not in response.text
    assert "<img src=x onerror=alert(1)>" not in response.text
    assert runtime.operations.active_count() == 0


@pytest.mark.parametrize(
    ("status", "heading", "forbidden"),
    [
        ("insufficient_evidence", "Insufficient evidence", "Model abstained"),
        ("model_abstain", "Model abstained", "Insufficient evidence"),
    ],
)
def test_abstention_states_are_distinct_and_do_not_fabricate_answers(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    heading: str,
    forbidden: str,
) -> None:
    client, _runtime = ui_client
    _patch_product_query(
        monkeypatch,
        _response(status=status, answer=None, citations=[]),
    )

    response = _post_form(
        client, [("corpus", "engineering"), ("question", "what is known?")]
    )

    assert response.status_code == 200
    assert f'<h2 id="result-heading">{heading}</h2>' in response.text
    assert forbidden not in response.text
    assert "A grounded answer." not in response.text
    assert "Citations" not in response.text
    assert "snapshot_123" in response.text
    assert "trace_123" in response.text


@pytest.mark.parametrize(
    "fields",
    [
        [("question", "question")],
        [("corpus", "engineering")],
        [("corpus", "engineering"), ("question", "")],
        [("corpus", "engineering"), ("question", "   ")],
        [("corpus", ""), ("question", "question")],
        [("corpus", "engineering"), ("question", "q" * (MAX_QUESTION_CHARS + 1))],
        [
            ("corpus", "engineering"),
            ("question", "question"),
            ("extra", "unexpected"),
        ],
        [
            ("corpus", "engineering"),
            ("corpus", "other"),
            ("question", "question"),
        ],
        [
            ("corpus", "engineering"),
            ("question", "question"),
            ("question", "second question"),
        ],
    ],
)
def test_form_contract_rejects_invalid_duplicate_and_unexpected_fields(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
    fields: list[tuple[str, str]],
) -> None:
    client, runtime = ui_client
    calls = _patch_product_query(monkeypatch, _response())

    response = _post_form(client, fields)

    assert response.status_code == 422
    _assert_security_headers(response)
    assert "request_invalid" in response.text
    assert calls == []
    assert runtime.operations.active_count() == 0


def test_product_validation_error_preserves_status_and_safe_projection(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    calls = _patch_product_query(
        monkeypatch,
        AppError(
            ErrorCode.REQUEST_INVALID,
            message="Invalid corpus name",
            trace_id="trace_invalid",
        ),
    )

    response = _post_form(client, [("corpus", "bad corpus"), ("question", "question")])

    assert response.status_code == 422
    _assert_security_headers(response)
    assert "request_invalid" in response.text
    assert "Invalid corpus name" in response.text
    assert "trace_invalid" in response.text
    assert calls
    assert runtime.operations.active_count() == 0


def test_app_error_is_rendered_safely_and_releases_operation(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    attack = '"><img src=x onerror=alert(1)>'
    calls = _patch_product_query(
        monkeypatch,
        AppError(
            ErrorCode.GENERATION_UNAVAILABLE,
            message=attack,
            trace_id=attack,
        ),
    )

    response = _post_form(client, [("corpus", "engineering"), ("question", "question")])

    assert response.status_code == 502
    _assert_security_headers(response)
    assert "generation_unavailable" in response.text
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in response.text
    assert attack not in response.text
    assert calls
    assert runtime.operations.active_count() == 0


def test_unexpected_query_failure_is_safe_internal_error_and_releases_operation(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    _patch_product_query(
        monkeypatch,
        RuntimeError("provider secret=/private/path token=unsafe"),
    )

    response = _post_form(client, [("corpus", "engineering"), ("question", "question")])

    assert response.status_code == 500
    _assert_security_headers(response)
    assert "internal_error" in response.text
    assert "provider secret" not in response.text
    assert "/private/path" not in response.text
    assert "token=unsafe" not in response.text
    assert runtime.operations.active_count() == 0


def test_question_xss_is_escaped_in_repopulated_form(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _runtime = ui_client
    _patch_product_query(monkeypatch, _response())
    question = '</textarea><script>alert("question")</script>'

    response = _post_form(client, [("corpus", "engineering"), ("question", question)])

    assert response.status_code == 200
    assert '<script>alert("question")</script>' not in response.text
    assert (
        "&lt;/textarea&gt;&lt;script&gt;alert(&quot;question&quot;)&lt;/script&gt;"
        in response.text
    )


def test_v1_query_json_contract_remains_unchanged(
    ui_client: tuple[TestClient, ApplicationRuntime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime = ui_client
    _patch_product_query(monkeypatch, _response())

    response = client.post(
        "/v1/query",
        json={"corpus": "engineering", "question": "question"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "corpus": "engineering",
        "snapshot_id": "snapshot_123",
        "product_mode_id": "grounded_v1",
        "trace_id": "trace_123",
        "status": "answered",
        "answer": "A grounded answer.",
        "citations": [],
    }
    extra = client.post(
        "/v1/query",
        json={"corpus": "engineering", "question": "question", "extra": 1},
    )
    assert extra.status_code == 422
    assert extra.json()["error"]["code"] == "request_invalid"
    assert runtime.operations.active_count() == 0


def test_dependency_and_frontend_toolchain_boundary_is_unchanged() -> None:
    baseline_pyproject = subprocess.check_output(
        ["git", "show", f"{BASELINE_SHA}:pyproject.toml"], text=False
    )
    assert Path("pyproject.toml").read_bytes() == baseline_pyproject
    assert not Path("package.json").exists()
    assert not Path("package-lock.json").exists()
    assert not Path("yarn.lock").exists()
    assert not Path("pnpm-lock.yaml").exists()
    ui_source = Path("src/offline_rag/api/ui.py").read_text(encoding="utf-8")
    assert "https://" not in ui_source
    assert "http://" not in ui_source
