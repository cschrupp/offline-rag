"""Small same-origin browser adapter for the canonical product query."""

from __future__ import annotations

import html
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError

from offline_rag.api.query import (
    ProductQueryRequest,
    _execute_product_query_owned,
    _runtime,
)
from offline_rag.app.errors import AppError, ErrorCode, ErrorResponse
from offline_rag.app.query import MAX_QUESTION_CHARS, ProductQueryResponse
from offline_rag.app.validation import app_error_from_validation_errors

router = APIRouter(tags=["browser query"])

_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "base-uri 'none'; frame-ancestors 'none'"
)
_CITATION_FIELDS: tuple[tuple[str, str], ...] = (
    ("evidence_unit_id", "Evidence unit"),
    ("document_id", "Document"),
    ("source_chunk_id", "Source chunk"),
    ("kind", "Kind"),
    ("section_path", "Section"),
    ("page_start", "Page start"),
    ("page_end", "Page end"),
    ("line_start", "Line start"),
    ("line_end", "Line end"),
    ("clipped", "Clipped"),
)


@dataclass(slots=True)
class _PageState:
    state: Literal[
        "idle",
        "answered",
        "insufficient_evidence",
        "model_abstain",
        "error",
    ] = "idle"
    corpus: str = ""
    question: str = ""
    answer: str | None = None
    citations: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str | None = None
    snapshot_id: str | None = None
    product_mode_id: str | None = None
    error: ErrorResponse | None = None


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _html_response(content: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": _CSP,
        },
    )


def _invalid_form() -> AppError:
    return AppError(ErrorCode.REQUEST_INVALID)


async def _parse_form(request: Request, state: _PageState) -> ProductQueryRequest:
    try:
        form = await request.form()
    except Exception as exc:
        raise _invalid_form() from exc

    items = form.multi_items()
    values: dict[str, str] = {}
    for key, value in items:
        if key == "corpus" and isinstance(value, str):
            state.corpus = value[:512]
        elif key == "question" and isinstance(value, str):
            state.question = value[:MAX_QUESTION_CHARS]

    counts = Counter(key for key, _value in items)
    if counts != Counter({"corpus": 1, "question": 1}):
        raise _invalid_form()
    if any(not isinstance(value, str) for _key, value in items):
        raise _invalid_form()
    values = {key: value for key, value in items}
    try:
        return ProductQueryRequest.model_validate(values)
    except ValidationError as exc:
        raise app_error_from_validation_errors(exc.errors()) from exc


def _result_state(
    result: ProductQueryResponse, form: ProductQueryRequest
) -> _PageState:
    state = _PageState(
        corpus=result.corpus[:512],
        question=form.question,
        trace_id=result.trace_id,
        snapshot_id=result.snapshot_id,
        product_mode_id=result.product_mode_id,
    )
    if result.status == "answered":
        state.state = "answered"
        state.answer = result.answer
        state.citations = list(result.citations)
    elif result.status == "insufficient_evidence":
        state.state = "insufficient_evidence"
    elif result.status == "model_abstain":
        state.state = "model_abstain"
    else:
        raise AppError(ErrorCode.INTERNAL_ERROR)
    return state


def _display_citation_value(value: object) -> str:
    if isinstance(value, list) and all(isinstance(part, str) for part in value):
        return " / ".join(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (str, int)):
        return str(value)
    return ""


def _render_citations(citations: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for citation in citations:
        fields: list[str] = []
        for key, label in _CITATION_FIELDS:
            value = citation.get(key)
            text = _display_citation_value(value)
            if text == "":
                continue
            fields.append(f"<dt>{_escape(label)}</dt><dd>{_escape(text)}</dd>")
        rows.append(f"<li><dl>{''.join(fields)}</dl></li>")
    if not rows:
        return ""
    return (
        '<section aria-labelledby="citations-heading">'
        '<h3 id="citations-heading">Citations</h3>'
        f"<ol>{''.join(rows)}</ol></section>"
    )


def _render_error(error: ErrorResponse) -> str:
    trace = ""
    if error.trace_id is not None:
        trace = f"<dt>Trace ID</dt><dd><code>{_escape(error.trace_id)}</code></dd>"
    retryable = "Yes" if error.retryable else "No"
    return (
        '<section class="result error" aria-labelledby="result-heading" role="alert">'
        '<h2 id="result-heading">Query error</h2>'
        f"<p>{_escape(error.error.message)}</p>"
        "<dl><dt>Error code</dt>"
        f"<dd><code>{_escape(error.error.code.value)}</code></dd>"
        f"<dt>Retryable</dt><dd>{retryable}</dd>{trace}</dl></section>"
    )


def _render_result(state: _PageState) -> str:
    if state.state == "idle":
        return '<p id="query-help">Submit a question to query the selected corpus.</p>'
    if state.state == "error":
        assert state.error is not None
        return _render_error(state.error)

    provenance = [
        ("Corpus", state.corpus),
        ("Snapshot ID", state.snapshot_id),
        ("Trace ID", state.trace_id),
        ("Product mode", state.product_mode_id),
    ]
    provenance_html = "".join(
        f"<dt>{_escape(label)}</dt><dd><code>{_escape(value)}</code></dd>"
        for label, value in provenance
        if value is not None
    )
    details = f"<dl>{provenance_html}</dl>"

    if state.state == "answered":
        answer = "" if state.answer is None else _escape(state.answer)
        return (
            '<section class="result" aria-labelledby="result-heading" role="status">'
            '<h2 id="result-heading">Answer</h2>'
            f'<p class="answer">{answer}</p>'
            f"{_render_citations(state.citations)}{details}</section>"
        )
    if state.state == "insufficient_evidence":
        return (
            '<section class="result" aria-labelledby="result-heading" role="status">'
            '<h2 id="result-heading">Insufficient evidence</h2>'
            "<p>The published corpus did not provide enough evidence to answer.</p>"
            f"{details}</section>"
        )
    return (
        '<section class="result" aria-labelledby="result-heading" role="status">'
        '<h2 id="result-heading">Model abstained</h2>'
        "<p>The model declined to provide an answer.</p>"
        f"{details}</section>"
    )


def _render_page(state: _PageState) -> str:
    corpus = _escape(state.corpus)
    question = _escape(state.question)
    result = _render_result(state)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OfflineRAG query</title>
  <style>
    :root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
    body {{ max-width: 56rem; margin: 0 auto; padding: 2rem 1rem; line-height: 1.5; }}
    label {{ display: block; margin-top: 1rem; font-weight: 600; }}
    input, textarea, button {{ box-sizing: border-box; font: inherit; padding: .65rem; }}
    input, textarea {{ display: block; width: 100%; margin-top: .35rem; }}
    textarea {{ min-height: 9rem; }}
    button {{ margin-top: 1rem; cursor: pointer; }}
    :focus-visible {{ outline: 3px solid currentColor; outline-offset: 3px; }}
    .result {{ border: 1px solid currentColor; margin-top: 2rem; padding: 1rem; }}
    .answer {{ white-space: pre-wrap; }}
    dt {{ font-weight: 600; margin-top: .5rem; }}
    dd {{ overflow-wrap: anywhere; margin-left: 0; }}
  </style>
</head>
<body>
  <main>
    <h1>OfflineRAG query</h1>
    <form method="post" action="/ui/query">
      <label for="corpus">Corpus</label>
      <input id="corpus" name="corpus" type="text" required value="{corpus}">
      <label for="question">Question</label>
      <textarea id="question" name="question" required maxlength="{MAX_QUESTION_CHARS}">{question}</textarea>
      <button type="submit">Ask this corpus</button>
    </form>
    {result}
  </main>
</body>
</html>"""


@router.get("/ui", response_class=HTMLResponse)
async def query_page() -> HTMLResponse:
    """Render an idle query form without touching product runtime state."""
    return _html_response(_render_page(_PageState()))


@router.post("/ui/query", response_model=None)
async def submit_query(request: Request) -> HTMLResponse | Response:
    """Validate the exact browser form and call the owned product query path."""
    state = _PageState()
    try:
        form = await _parse_form(request, state)
        runtime = _runtime(request)
        result = await _execute_product_query_owned(
            request=request,
            runtime=runtime,
            corpus=form.corpus,
            question=form.question,
        )
        if isinstance(result, Response):
            return result
        return _html_response(_render_page(_result_state(result, form)))
    except AppError as exc:
        safe_error = (
            exc if exc.http_status is not None else AppError(ErrorCode.INTERNAL_ERROR)
        )
        state.state = "error"
        state.error = safe_error.to_error_response()
        return _html_response(
            _render_page(state),
            status_code=safe_error.http_status or 500,
        )
    except Exception:  # noqa: BLE001 - HTML boundary hides unexpected failures.
        safe_error = AppError(ErrorCode.INTERNAL_ERROR).to_error_response()
        state.state = "error"
        state.error = safe_error
        return _html_response(_render_page(state), status_code=500)
