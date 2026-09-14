"""Loopback-only stdlib HTTP review server (Slice 9E)."""

from __future__ import annotations

import json
import mimetypes
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

from offline_rag.config.models import AppSettings
from offline_rag.gold_authoring.models import GoldAuthoringRun
from offline_rag.gold_authoring.persist import load_authoring_run, write_authoring_run
from offline_rag.gold_authoring.review_models import ReviewError
from offline_rag.gold_authoring.review_ops import (
    accept_case,
    approve_edited_case,
    get_case,
    reject_case,
    reopen_case,
    set_human_grade,
    set_reviewed_category,
    set_reviewed_query,
    set_reviewed_tags,
)
from offline_rag.gold_authoring.review_view import (
    build_case_detail_payload,
    build_case_list_payload,
)

DEFAULT_REVIEW_HOST = "127.0.0.1"
DEFAULT_REVIEW_PORT = 8765

_T = TypeVar("_T")


class ReviewServerError(RuntimeError):
    """Review server configuration / bind error."""


class _ThreadingHTTPServerV6(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def normalize_review_host(host: str) -> str:
    value = (host or "").strip()
    if value == "localhost":
        return "127.0.0.1"
    if value in {"127.0.0.1", "::1"}:
        return value
    raise ReviewServerError(
        "Review server may bind only to loopback. "
        "Allowed hosts: 127.0.0.1, localhost, ::1."
    )


def canonical_origin(host: str, port: int) -> str:
    if host == "::1":
        return f"http://[::1]:{port}"
    return f"http://{host}:{port}"


def _static_resource(name: str) -> bytes:
    package = resources.files("offline_rag.gold_authoring.review_ui")
    target = package.joinpath(name)
    if not target.is_file():
        raise FileNotFoundError(name)
    return target.read_bytes()


class ReviewSession:
    """Process-local mutable review session for one --run artifact."""

    def __init__(
        self,
        *,
        settings: AppSettings,
        run_path: Path,
        host: str,
        port: int,
    ) -> None:
        self.settings = settings
        self.run_path = run_path.resolve()
        self.host = host
        self.port = port
        self.origin = canonical_origin(host, port)
        self._lock = threading.RLock()
        self.run: GoldAuthoringRun = load_authoring_run(self.run_path)

    def reload(self) -> GoldAuthoringRun:
        with self._lock:
            self.run = load_authoring_run(self.run_path)
            return self.run

    def mutate(
        self, mutator: Callable[[GoldAuthoringRun], GoldAuthoringRun]
    ) -> GoldAuthoringRun:
        updated, _ = self.mutate_with_result(mutator, lambda _run: None)
        return updated

    def mutate_with_result(
        self,
        mutator: Callable[[GoldAuthoringRun], GoldAuthoringRun],
        result_builder: Callable[[GoldAuthoringRun], _T],
    ) -> tuple[GoldAuthoringRun, _T]:
        """Apply a mutation only if the success-response builder also succeeds.

        Order under the session lock:

        1. load current ``--run``
        2. apply ``mutator`` → prospective run
        3. validate prospective run
        4. build response/view from the prospective run (may raise)
        5. only then atomically write and update session state

        If step 4 fails, the durable artifact is unchanged.
        """
        with self._lock:
            current = load_authoring_run(self.run_path)
            updated = mutator(current)
            # Validate by round-tripping through model dump/load semantics.
            GoldAuthoringRun.model_validate_json(updated.model_dump_json())
            result = result_builder(updated)
            write_authoring_run(self.run_path, updated)
            self.run = updated
            return updated, result


def _json_response(
    handler: BaseHTTPRequestHandler,
    *,
    status: int,
    payload: dict[str, Any],
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length <= 0:
        raise ReviewError("empty JSON body", code="invalid_json")
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewError(f"invalid JSON: {exc}", code="invalid_json") from exc
    if not isinstance(data, dict):
        raise ReviewError("JSON body must be an object", code="invalid_json")
    return data


def make_handler(session: ReviewSession) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Keep logs concise; avoid dumping private document bodies.
            return

        def _expected_hosts(self) -> set[str]:
            port = session.port
            hosts = {
                f"{session.host}:{port}",
                f"127.0.0.1:{port}",
                f"localhost:{port}",
            }
            if session.host == "::1":
                hosts.add(f"[::1]:{port}")
            return hosts

        def _validate_host(self) -> bool:
            host = (self.headers.get("Host") or "").strip()
            if host not in self._expected_hosts():
                _json_response(
                    self,
                    status=400,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "invalid_host",
                            "message": "unexpected Host header",
                        },
                    },
                )
                return False
            return True

        def _validate_mutation_headers(self) -> bool:
            if not self._validate_host():
                return False
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
            if content_type != "application/json":
                _json_response(
                    self,
                    status=415,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "unsupported_media_type",
                            "message": "mutations require Content-Type: application/json",
                        },
                    },
                )
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip() != session.origin:
                _json_response(
                    self,
                    status=403,
                    payload={
                        "ok": False,
                        "error": {
                            "code": "invalid_origin",
                            "message": "cross-origin mutations are not allowed",
                        },
                    },
                )
                return False
            return True

        def do_GET(self) -> None:
            if not self._validate_host():
                return
            parsed = urlparse(self.path)
            path = parsed.path

            if path in {"/", "/index.html"}:
                self._serve_static("index.html", "text/html; charset=utf-8")
                return
            if path == "/review.css":
                self._serve_static("review.css", "text/css; charset=utf-8")
                return
            if path == "/review.js":
                self._serve_static(
                    "review.js", "application/javascript; charset=utf-8"
                )
                return
            if path == "/api/run":
                run = session.reload()
                _json_response(
                    self,
                    status=200,
                    payload={
                        "ok": True,
                        "run": {
                            "authoring_run_id": run.authoring_run_id,
                            "chunk_set_id": run.chunk_set_id,
                            "corpus_name": run.corpus_name,
                            "case_count": len(run.cases),
                        },
                        "cases": build_case_list_payload(run),
                    },
                )
                return
            if path.startswith("/api/cases/"):
                draft_case_id = path[len("/api/cases/") :].strip("/")
                if not draft_case_id or "/" in draft_case_id:
                    _json_response(
                        self,
                        status=404,
                        payload={
                            "ok": False,
                            "error": {"code": "not_found", "message": "unknown route"},
                        },
                    )
                    return
                try:
                    run = session.reload()
                    case = get_case(run, draft_case_id)
                    detail = build_case_detail_payload(session.settings, run, case)
                except ReviewError as exc:
                    status = 404 if exc.code == "unknown_case" else 400
                    _json_response(
                        self,
                        status=status,
                        payload={
                            "ok": False,
                            "error": {"code": exc.code, "message": exc.message},
                        },
                    )
                    return
                except Exception as exc:  # noqa: BLE001
                    _json_response(
                        self,
                        status=400,
                        payload={
                            "ok": False,
                            "error": {
                                "code": "review_error",
                                "message": str(exc),
                            },
                        },
                    )
                    return
                _json_response(self, status=200, payload={"ok": True, "case": detail})
                return

            _json_response(
                self,
                status=404,
                payload={
                    "ok": False,
                    "error": {"code": "not_found", "message": "unknown route"},
                },
            )

        def do_POST(self) -> None:
            if not self._validate_mutation_headers():
                return
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = _read_json(self)
            except ReviewError as exc:
                _json_response(
                    self,
                    status=400,
                    payload={
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message},
                    },
                )
                return

            try:
                detail = self._dispatch_mutation(path, body)
            except ReviewError as exc:
                _json_response(
                    self,
                    status=400,
                    payload={
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message},
                    },
                )
                return
            except Exception as exc:  # noqa: BLE001
                _json_response(
                    self,
                    status=400,
                    payload={
                        "ok": False,
                        "error": {"code": "review_error", "message": str(exc)},
                    },
                )
                return

            _json_response(self, status=200, payload={"ok": True, "case": detail})

        def _dispatch_mutation(
            self, path: str, body: dict[str, Any]
        ) -> dict[str, Any]:
            prefix = "/api/cases/"
            if not path.startswith(prefix):
                raise ReviewError("unknown route", code="not_found")
            remainder = path[len(prefix) :]
            parts = [p for p in remainder.split("/") if p]
            if len(parts) != 2:
                raise ReviewError("unknown route", code="not_found")
            draft_case_id, action = parts

            def build_detail(run: GoldAuthoringRun) -> dict[str, Any]:
                case = get_case(run, draft_case_id)
                return build_case_detail_payload(session.settings, run, case)

            def commit(
                mutator: Callable[[GoldAuthoringRun], GoldAuthoringRun],
            ) -> dict[str, Any]:
                # Response/evidence validation is part of the pre-write transaction.
                _updated, detail = session.mutate_with_result(mutator, build_detail)
                return detail

            if action == "grade":
                if set(body.keys()) - {"chunk_id", "relevance"}:
                    raise ReviewError("unknown fields in grade payload", code="invalid_json")
                chunk_id = body.get("chunk_id")
                relevance = body.get("relevance")
                if not isinstance(chunk_id, str) or type(relevance) is not int:
                    raise ReviewError(
                        "grade requires chunk_id:string and relevance:int",
                        code="invalid_json",
                    )

                def mutate(run: GoldAuthoringRun) -> GoldAuthoringRun:
                    return set_human_grade(
                        run,
                        draft_case_id=draft_case_id,
                        chunk_id=chunk_id,
                        relevance=relevance,
                    )

                return commit(mutate)

            if action == "query":
                if set(body.keys()) - {"query"}:
                    raise ReviewError("unknown fields in query payload", code="invalid_json")
                query = body.get("query")
                if not isinstance(query, str):
                    raise ReviewError("query must be a string", code="invalid_json")

                def mutate(run: GoldAuthoringRun) -> GoldAuthoringRun:
                    return set_reviewed_query(
                        run, draft_case_id=draft_case_id, query=query
                    )

                return commit(mutate)

            if action == "category":
                if set(body.keys()) - {"category", "clear"}:
                    raise ReviewError(
                        "unknown fields in category payload", code="invalid_json"
                    )
                if not body:
                    raise ReviewError(
                        "category mutation requires explicit clear and/or category",
                        code="invalid_json",
                    )
                if "clear" in body and type(body["clear"]) is not bool:
                    raise ReviewError(
                        "clear must be a JSON boolean when present",
                        code="invalid_json",
                    )
                clear = bool(body["clear"]) if "clear" in body else False
                if "category" not in body and not clear:
                    raise ReviewError(
                        "category mutation requires category or clear=true",
                        code="invalid_json",
                    )
                category = body.get("category")
                if "category" in body and category is not None and not isinstance(
                    category, str
                ):
                    raise ReviewError(
                        "category must be string or null", code="invalid_json"
                    )

                def mutate(run: GoldAuthoringRun) -> GoldAuthoringRun:
                    return set_reviewed_category(
                        run,
                        draft_case_id=draft_case_id,
                        category=category if isinstance(category, str) else None,
                        clear=clear,
                    )

                return commit(mutate)

            if action == "tags":
                if set(body.keys()) - {"tags", "clear_override"}:
                    raise ReviewError(
                        "unknown fields in tags payload", code="invalid_json"
                    )
                if not body:
                    raise ReviewError(
                        "tags mutation requires tags and/or clear_override",
                        code="invalid_json",
                    )
                if "clear_override" in body and type(body["clear_override"]) is not bool:
                    raise ReviewError(
                        "clear_override must be a JSON boolean when present",
                        code="invalid_json",
                    )
                clear_override = (
                    bool(body["clear_override"]) if "clear_override" in body else False
                )
                tags = body.get("tags")
                if not clear_override:
                    if "tags" not in body:
                        raise ReviewError(
                            "tags must be present when clear_override is false",
                            code="invalid_json",
                        )
                    if not isinstance(tags, list):
                        raise ReviewError("tags must be a list", code="invalid_json")

                def mutate(run: GoldAuthoringRun) -> GoldAuthoringRun:
                    return set_reviewed_tags(
                        run,
                        draft_case_id=draft_case_id,
                        tags=tags if isinstance(tags, list) else None,
                        clear_override=clear_override,
                    )

                return commit(mutate)

            if action in {"accept", "approve-edited", "reject", "reopen"}:
                if body:
                    raise ReviewError(
                        f"{action} accepts an empty JSON object",
                        code="invalid_json",
                    )
                op = {
                    "accept": accept_case,
                    "approve-edited": approve_edited_case,
                    "reject": reject_case,
                    "reopen": reopen_case,
                }[action]

                def mutate(run: GoldAuthoringRun) -> GoldAuthoringRun:
                    return op(run, draft_case_id=draft_case_id)

                return commit(mutate)

            raise ReviewError("unknown route", code="not_found")

        def _serve_static(self, name: str, content_type: str) -> None:
            try:
                data = _static_resource(name)
            except FileNotFoundError:
                _json_response(
                    self,
                    status=404,
                    payload={
                        "ok": False,
                        "error": {"code": "not_found", "message": "asset missing"},
                    },
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return ReviewHandler


def create_review_server(
    *,
    settings: AppSettings,
    run_path: Path,
    host: str = DEFAULT_REVIEW_HOST,
    port: int = DEFAULT_REVIEW_PORT,
) -> tuple[ThreadingHTTPServer, ReviewSession, str]:
    bind_host = normalize_review_host(host)
    if not run_path.exists():
        raise ReviewServerError(f"authoring run not found: {run_path}")
    # Fail closed early on invalid artifact.
    load_authoring_run(run_path.resolve())
    session = ReviewSession(
        settings=settings,
        run_path=run_path,
        host=bind_host,
        port=port,
    )
    handler = make_handler(session)
    server_cls: type[ThreadingHTTPServer]
    if bind_host == "::1":
        server_cls = _ThreadingHTTPServerV6
    else:
        server_cls = ThreadingHTTPServer
    try:
        server = server_cls((bind_host, port), handler)
    except OSError as exc:
        raise ReviewServerError(
            f"failed to bind review server on {bind_host!r}: {exc}"
        ) from exc
    # Reflect ephemeral port assignment (port=0) into session origin checks.
    bound_port = int(server.server_address[1])
    session.host = bind_host
    session.port = bound_port
    session.origin = canonical_origin(bind_host, bound_port)
    url = f"{session.origin}/"
    return server, session, url


# Silence unused import warning for mimetypes if kept for future assets.
_ = mimetypes
