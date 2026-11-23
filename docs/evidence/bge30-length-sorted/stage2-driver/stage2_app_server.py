"""Disposable Stage 2 ASGI server using the integrated app and synthetic models."""

from __future__ import annotations

import argparse
import contextvars
import json
import os
import shutil
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import torch
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from offline_rag.api.app import create_app
from offline_rag.app.conversation.traces import ConversationTraceStore
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ProcessResources,
    ResourceFactories,
)
from offline_rag.app.traces import ProductTraceStore
from offline_rag.config import load_settings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.cross_encoder import CrossEncoderReranker

EVENTS = Path("/stage2-journal/events.jsonl")
CONTROL = Path("/stage2-control")
_event_lock = threading.Lock()
_ordinal = contextvars.ContextVar("stage2_ordinal", default=None)
_operation_ordinals: dict[str, int] = {}
_operation_lock = threading.Lock()
_runtime: ApplicationRuntime | None = None
_held_preflights: list[object] = []
_held_query_slots: list[object] = []
_held_lock = threading.Lock()


def event(kind: str, ordinal: int | None = None, **values: object) -> None:
    row = {
        "event": kind,
        "ordinal": ordinal if ordinal is not None else _ordinal.get(),
        "monotonic_ns": time.monotonic_ns(),
        **values,
    }
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
    with _event_lock:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())


class Stage2RequestObserver:
    """Pure ASGI observer; preserves the application's original receive path."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        raw = headers.get(b"x-stage2-ordinal")
        try:
            ordinal = None if raw is None else int(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            ordinal = -1
        token = _ordinal.set(ordinal)
        response_status = None
        if ordinal is not None:
            event(
                "http_received",
                ordinal,
                method=scope.get("method"),
                path=scope.get("path"),
            )

        async def observe_send(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
                if ordinal is not None:
                    event("http_response", ordinal, status=response_status)
            await send(message)

        try:
            await self.app(scope, receive, observe_send)
        except BaseException as exc:
            if ordinal is not None:
                event("http_handler_raised", ordinal, exception=type(exc).__name__)
            raise
        finally:
            _ordinal.reset(token)


def operation_ordinal(operation_id: str) -> int | None:
    with _operation_lock:
        return _operation_ordinals.get(operation_id)


def record_operation(operation_id: str, ordinal: int) -> None:
    with _operation_lock:
        if operation_id in _operation_ordinals:
            raise RuntimeError("duplicate operation identity")
        _operation_ordinals[operation_id] = ordinal


def current_control(ordinal: int | None) -> dict[str, object]:
    if ordinal is None:
        return {}
    path = CONTROL / f"{ordinal}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class TinyTokenizer:
    """Deterministic pair tokenizer for route/lifecycle rehearsal only."""

    @staticmethod
    def encode(text: str, *, add_special_tokens: bool) -> list[int]:
        tokens = [3 + (ord(char) % 251) for char in text]
        return [1, *tokens, 2] if add_special_tokens else tokens

    def num_special_tokens_to_add(self, *, pair: bool) -> int:
        return 3 if pair else 2

    def __call__(
        self,
        *,
        text: list[str],
        text_pair: list[str],
        max_length: int,
        truncation: str,
        padding: bool,
        return_tensors: str | None = None,
        return_attention_mask: bool = True,
    ) -> dict[str, object]:
        assert truncation == "only_second"
        rows: list[list[int]] = []
        for query, passage in zip(text, text_pair, strict=True):
            query_ids = self.encode(query, add_special_tokens=False)
            passage_room = max(0, max_length - len(query_ids) - 3)
            passage_ids = self.encode(passage, add_special_tokens=False)[:passage_room]
            rows.append([1, *query_ids, 2, *passage_ids, 2])
        width = max(len(row) for row in rows)
        padded = [row + [0] * (width - len(row)) for row in rows]
        masks = [[int(token != 0) for token in row] for row in padded]
        if not padding:
            result: dict[str, object] = {"input_ids": rows}
            if return_attention_mask:
                result["attention_mask"] = [[1] * len(row) for row in rows]
            return result
        if return_tensors != "pt":
            raise ValueError("synthetic tokenizer expects tensor batching")
        result = {"input_ids": torch.tensor(padded, dtype=torch.long)}
        if return_attention_mask:
            result["attention_mask"] = torch.tensor(masks, dtype=torch.long)
        return result


class SyntheticForward(torch.nn.Module):
    """Tiny deterministic Torch forward; it never replaces production code."""

    def forward(self, *, input_ids: torch.Tensor, attention_mask: torch.Tensor):
        ordinal = _ordinal.get()
        control = current_control(ordinal)
        marker = EVENTS.parent / f"{ordinal}.forward_entered"
        if control.get("hold") == "forward" and not marker.exists():
            marker.touch(exist_ok=False)
            event(
                "forward_entered",
                ordinal,
                shape=list(input_ids.shape),
                strategy=control.get("strategy"),
                active_count=(
                    _runtime.operations.active_count() if _runtime is not None else None
                ),
                query_capacity_held=(
                    _runtime.operations.query_capacity.held
                    if _runtime is not None
                    else None
                ),
            )
            deadline = time.monotonic() + 30
            while not (EVENTS.parent / f"{ordinal}.release").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("synthetic forward barrier expired")
                time.sleep(0.01)
            event("forward_released", ordinal)
        masked = input_ids * attention_mask
        # Deliberately stable, non-semantic score to exercise real scorer
        # association/batching with deterministic synthetic inference.
        values = masked.sum(dim=1).to(dtype=torch.float32) / 1000.0
        return SimpleNamespace(logits=values.reshape(-1, 1))


def build_scorer(strategy: str, *, counters: dict[str, int]) -> CrossEncoderReranker:
    scorer = object.__new__(CrossEncoderReranker)
    scorer.model_path = Path("/stage2-synthetic/no-model-assets")
    scorer.model_id = "stage2/synthetic-only"
    scorer.model_revision = "synthetic-fixture-v1"
    scorer.adapter_contract = "stage2-synthetic-contract"
    scorer.max_length = 1024
    scorer.sequence_contract = "seq_trunc_1024_passage_right"
    scorer.score_transform = "raw_logit_v1"
    scorer.device = "cpu"
    scorer.batch_size = 16
    scorer.batching_strategy = strategy
    scorer.local_files_only = True
    scorer.trust_remote_code = False
    scorer._load_lock = threading.Lock()
    scorer._tokenizer_lock = threading.Lock()
    model = SyntheticForward()
    model.eval()
    scorer._loaded = (TinyTokenizer(), model)

    original = CrossEncoderReranker.score_pairs

    def counted_score_pairs(self, pairs):
        counters["scorer_calls"] = counters.get("scorer_calls", 0) + 1
        counters["candidate_pairs"] = len(pairs)
        event(
            "scorer_entered",
            _ordinal.get(),
            pair_count=len(pairs),
            strategy=strategy,
        )
        try:
            result = original(self, pairs)
        except BaseException as exc:
            event(
                "scorer_failed",
                _ordinal.get(),
                exception=type(exc).__name__,
            )
            raise
        event("scorer_returned", _ordinal.get(), score_count=len(result))
        return result

    scorer.score_pairs = counted_score_pairs.__get__(scorer, CrossEncoderReranker)
    scorer._stage2_counters = counters
    return scorer


def settings_for(work_root: Path, strategy: str):
    settings = load_settings(
        yaml_paths=[Path(os.environ["OFFLINE_RAG_CONFIG"])],
        environ={
            "OFFLINE_RAG_DATA_DIR": str(work_root / "data"),
            "OFFLINE_RAG_MODELS_DIR": str(work_root / "models"),
            "OFFLINE_RAG_STRICT_OFFLINE": "true",
        },
    )
    settings.paths.docling_artifacts.mkdir(parents=True, exist_ok=True)
    (settings.paths.docling_artifacts / "placeholder.bin").write_bytes(b"stage2")
    write_provisioning_manifest(
        settings.paths.docling_artifacts, docling_version="stage2-synthetic"
    )
    tokenizer_source = Path("/review/inputs/tiktoken")
    if not (tokenizer_source / "offline-rag-tokenizer.json").is_file():
        raise RuntimeError("mounted tiktoken input is incomplete")
    settings.paths.tokenizer_artifacts.parent.mkdir(parents=True, exist_ok=True)
    if settings.paths.tokenizer_artifacts.exists():
        shutil.rmtree(settings.paths.tokenizer_artifacts)
    shutil.copytree(tokenizer_source, settings.paths.tokenizer_artifacts)

    generation = settings.generation.model_copy(
        update={
            "enabled": True,
            "base_url": "http://127.0.0.1:9/v1",
            "model": "stage2-synthetic-provider",
            "approved_endpoints": ["http://127.0.0.1:9/v1"],
            "approved_models": ["stage2-synthetic-provider"],
            "api_key": None,
        }
    )
    reranker = settings.reranker.model_copy(
        update={
            "batching_strategy": strategy,
        }
    )
    api = settings.api.model_copy(
        update={
            "max_concurrent_query": 1,
            "query_deadline_seconds": 180,
            "shutdown_grace_seconds": 1,
        }
    )
    return settings.model_copy(
        update={"generation": generation, "reranker": reranker, "api": api}
    )


def resource_factories(strategy: str, counters: dict[str, int]) -> ResourceFactories:
    def generator(_settings):
        def respond(request):
            counters["generator_calls"] = counters.get("generator_calls", 0) + 1
            event("synthetic_generator_invoked", _ordinal.get())
            prompt = "\n".join(message.content for message in request.messages)
            import re

            handles = re.findall(r"\[EVIDENCE (E[1-9][0-9]*)\]", prompt)
            if not handles:
                raise RuntimeError("synthetic fixture received no evidence handles")
            return json.dumps(
                {
                    "abstain": False,
                    "blocks": [
                        {
                            "text": "Synthetic Stage 2 route response.",
                            "evidence_handles": [handles[0]],
                        }
                    ],
                    "abstention_reason": None,
                }
            )

        return FakeGenerator(response_fn=respond)

    return ResourceFactories(
        embedder=lambda _settings: FakeEmbedder(dimension=8, normalize=True),
        reranker=lambda _settings: build_scorer(strategy, counters=counters),
        generator_client=generator,
        qdrant=lambda s: QdrantLocalBackend(s.paths.qdrant_storage),
    )


def seed_workspaces(settings, factories) -> dict[str, dict[str, object]]:

    runtime = ApplicationRuntime(settings=settings, factories=factories)
    app = create_app(runtime=runtime)
    result: dict[str, dict[str, object]] = {}
    with TestClient(app, raise_server_exceptions=True) as client:
        for workload, count in (("Recipes", 30), ("Rich", 10)):
            created = client.post(
                "/v1/workspaces",
                json={"title": f"Stage 2 {workload}", "description": "synthetic"},
                headers={"Idempotency-Key": f"stage2-{workload.lower()}-create"},
            )
            if created.status_code != 201:
                raise RuntimeError(
                    "synthetic workspace creation failed: "
                    f"{created.status_code} {created.text[:1000]}"
                )
            workspace_id = created.json()["workspace_id"]
            files = []
            for index in range(count):
                body = (
                    f"STAGE2 SYNTHETIC {workload} item {index:02d}. "
                    "Baked preparation and incident decision concepts are included "
                    "as deterministic test content. "
                    f"Unique token marker {workload.lower()}-{index:02d}.\n"
                ).encode()
                files.append(
                    (
                        "files",
                        (f"item-{index:02d}.txt", body, "text/plain"),
                    )
                )
            added = client.post(
                f"/v1/workspaces/{workspace_id}/sources",
                headers={
                    "Idempotency-Key": f"stage2-{workload.lower()}-sources",
                    "If-Match": '"1"',
                },
                files=files,
                timeout=120,
            )
            if added.status_code != 202:
                raise RuntimeError("synthetic source ingestion did not start")
            operation_id = added.json()["operation_id"]
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                status = client.get(f"/v1/operations/{operation_id}").json()
                if status["status"] in {"succeeded", "failed", "interrupted"}:
                    break
                time.sleep(0.025)
            else:
                raise TimeoutError("synthetic source ingestion timed out")
            if status["status"] != "succeeded":
                raise RuntimeError("synthetic source ingestion failed")
            sources = client.get(f"/v1/workspaces/{workspace_id}/sources").json()[
                "sources"
            ]
            if len(sources) != count:
                raise RuntimeError("synthetic workspace source count mismatch")
            result[workload] = {
                "workspace_id": workspace_id,
                "source_ids": sorted(row["source_id"] for row in sources),
                "revision": 2,
                "source_count": len(sources),
            }
    return result


def install_observers(app, runtime, counters):
    from offline_rag.api import workspaces as workspaces_api
    from offline_rag.app.errors import AppError
    from offline_rag.app.operations import OperationHandle, OperationRegistry

    originals = {
        "start": OperationRegistry.start_query_preflight,
        "promote": OperationRegistry.promote_query_preflight,
        "claim": OperationRegistry.claim_query_terminal,
        "release": OperationRegistry.release,
        "signal": OperationHandle.signal_cancel,
        "checkpoint": OperationHandle.checkpoint,
        "worker": workspaces_api.run_owned_worker,
        "execute": workspaces_api.execute_prepared_conversation_turn,
        "wait": ApplicationRuntime.wait_for_drain,
        "begin": ApplicationRuntime.begin_drain,
        "resources_close": ProcessResources.close,
    }

    def started(self):
        ordinal = _ordinal.get()
        try:
            handle = originals["start"](self)
        except AppError as exc:
            event(
                "preflight_rejected",
                ordinal,
                reason=(exc.details or {}).get("reason"),
                error_code=str(exc.code),
            )
            raise
        if ordinal is not None:
            record_operation(handle.op_id, ordinal)
            event("preflight_admitted", ordinal, operation_id=handle.op_id)
        return handle

    def promoted(self, handle):
        originals["promote"](self, handle)
        ordinal = operation_ordinal(handle.op_id)
        control = current_control(ordinal)
        local_deadline_override_s = 2 if control.get("case") == "deadline" else None
        if local_deadline_override_s is not None:
            # Only the explicit local deadline lifecycle case is accelerated.
            # All ordinary load requests retain the accepted 180-second value.
            handle.deadline_mono = time.monotonic() + local_deadline_override_s
            event(
                "diagnostic_deadline_override",
                ordinal,
                operation_id=handle.op_id,
                seconds=local_deadline_override_s,
            )
        event(
            "query_admitted",
            ordinal,
            operation_id=handle.op_id,
            active_count=self.active_count(),
            query_capacity_held=self.query_capacity.held,
            deadline_mono=handle.deadline_mono,
        )

    def claimed(self, handle):
        originals["claim"](self, handle)
        event(
            "terminal_claimed",
            operation_ordinal(handle.op_id),
            operation_id=handle.op_id,
            terminal_claimed=handle._terminal_claimed,
        )

    def released(self, handle):
        originals["release"](self, handle)
        if operation_ordinal(handle.op_id) is not None:
            event(
                "slot_released",
                operation_ordinal(handle.op_id),
                operation_id=handle.op_id,
                worker_returned=handle._released,
                active_count=self.active_count(),
                query_capacity_held=self.query_capacity.held,
                operation_released=(
                    handle._released and handle.op_id not in self._active
                ),
                global_query_capacity_empty=self.query_capacity.held == 0,
            )

    def signaled(handle, reason):
        originals["signal"](handle, reason)
        ordinal = operation_ordinal(handle.op_id)
        if ordinal is not None:
            event(
                "cancel_signaled",
                ordinal,
                operation_id=handle.op_id,
                reason=str(handle.cancel_reason),
                terminal_claimed=handle._terminal_claimed,
            )

    def checkpoint(handle, where=""):
        originals["checkpoint"](handle, where)
        ordinal = operation_ordinal(handle.op_id)
        control = current_control(ordinal)
        if (
            ordinal is not None
            and where == "pre_grounded"
            and control.get("hold") == "before_rerank"
        ):
            marker = EVENTS.parent / f"{ordinal}.checkpoint_entered"
            marker.touch(exist_ok=False)
            event(
                "checkpoint_hold_entered",
                ordinal,
                checkpoint=where,
                active_count=_runtime.operations.active_count(),
                preflight_count=len(_runtime.operations._query_preflights),
                query_capacity_held=_runtime.operations.query_capacity.held,
            )
            deadline = time.monotonic() + 30
            while not (EVENTS.parent / f"{ordinal}.release").exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("pre-rerank barrier expired")
                time.sleep(0.01)
            event("checkpoint_hold_released", ordinal, checkpoint=where)
            # Recheck the actual operation after transport cancellation.
            originals["checkpoint"](handle, where)

    async def owned_worker(**kwargs):
        operation = kwargs["operation"]
        ordinal = operation_ordinal(operation.op_id)
        original_worker = kwargs["worker"]
        request = kwargs.get("request")
        disconnect_polls = 0

        class ObservedRequest:
            def __getattr__(self, name):
                return getattr(request, name)

            async def is_disconnected(self):
                nonlocal disconnect_polls
                disconnected = await request.is_disconnected()
                disconnect_polls += 1
                if disconnect_polls <= 2 or disconnected:
                    event(
                        "request_disconnect_poll",
                        ordinal,
                        disconnected=bool(disconnected),
                        poll=disconnect_polls,
                    )
                if disconnected:
                    event("request_disconnect_observed", ordinal)
                return disconnected

        if request is not None:
            kwargs["request"] = ObservedRequest()

        def tracked_worker():
            token = _ordinal.set(ordinal)
            event("worker_started", ordinal, operation_id=operation.op_id)
            try:
                value = original_worker()
            except BaseException as exc:
                details = getattr(exc, "details", None) or {}
                detail_reason = (
                    details.get("reason")
                    if hasattr(details, "get")
                    else getattr(details, "reason", None)
                )
                error_code = str(getattr(exc, "code", ""))
                if detail_reason is None and error_code == "request_timeout":
                    # The canonical workspace query deadline maps to this
                    # error code in OperationHandle.checkpoint().
                    detail_reason = "query_deadline_exceeded"
                trace_id = getattr(exc, "trace_id", None)
                event(
                    "worker_failed",
                    ordinal,
                    operation_id=operation.op_id,
                    exception=type(exc).__name__,
                    error_code=error_code,
                    reason=detail_reason,
                    trace_id=trace_id,
                    query_trace_present=(
                        ProductTraceStore(runtime.settings).get(trace_id) is not None
                        if trace_id
                        else False
                    ),
                )
                raise
            else:
                query_trace_id = value.get("query_trace_id")
                conversation_trace_id = value.get("conversation_trace_id")
                event(
                    "worker_returned",
                    ordinal,
                    operation_id=operation.op_id,
                    conversation_trace_id=conversation_trace_id,
                    query_trace_id=query_trace_id,
                    result_status=value.get("status"),
                    query_trace_present=(
                        ProductTraceStore(runtime.settings).get(query_trace_id)
                        is not None
                        if query_trace_id
                        else False
                    ),
                    conversation_trace_present=(
                        ConversationTraceStore(runtime.settings).get(
                            conversation_trace_id
                        )
                        is not None
                        if conversation_trace_id
                        else False
                    ),
                )
                return value
            finally:
                _ordinal.reset(token)

        kwargs["worker"] = tracked_worker
        return await originals["worker"](**kwargs)

    def executed(*args, **kwargs):
        response = originals["execute"](*args, **kwargs)
        control = kwargs.get("control")
        ordinal = None if control is None else operation_ordinal(control.op_id)
        if ordinal is not None:
            event(
                "turn_result",
                ordinal,
                conversation_trace_id=response.conversation_trace_id,
                query_trace_id=response.query_trace_id,
                status=response.status,
            )
        return response

    def begin_drain(self):
        originals["begin"](self)
        event(
            "drain_started",
            None,
            active_count=self.operations.active_count(),
            query_capacity_held=self.operations.query_capacity.held,
        )

    def wait_for_drain(self, timeout_seconds=None):
        idle = originals["wait"](self, timeout_seconds)
        if not idle:
            event(
                "drain_grace_exhausted",
                None,
                active_count=self.operations.active_count(),
                query_capacity_held=self.operations.query_capacity.held,
                resources_open=self.resources is not None,
            )
        return idle

    def resources_close(self):
        active = runtime.operations.active_count()
        held = runtime.operations.query_capacity.held
        if active or held:
            event(
                "resource_close_while_owned",
                None,
                active_count=active,
                query_capacity_held=held,
            )
            raise RuntimeError("runtime attempted to close under an active worker")
        originals["resources_close"](self)
        event("resources_closed", None, active_count=active, query_capacity_held=held)

    OperationRegistry.start_query_preflight = started
    OperationRegistry.promote_query_preflight = promoted
    OperationRegistry.claim_query_terminal = claimed
    OperationRegistry.release = released
    OperationHandle.signal_cancel = signaled
    OperationHandle.checkpoint = checkpoint
    workspaces_api.run_owned_worker = owned_worker
    workspaces_api.execute_prepared_conversation_turn = executed
    ApplicationRuntime.begin_drain = begin_drain
    ApplicationRuntime.wait_for_drain = wait_for_drain
    ProcessResources.close = resources_close

    app.add_middleware(Stage2RequestObserver)

    @app.post("/__stage2/drain")
    async def diagnostic_drain():
        event("diagnostic_drain_requested", None)
        await runtime.drain_async()
        event("runtime_stopped", None)
        return JSONResponse({"status": "stopped"})

    @app.post("/__stage2/hold-preflight")
    async def hold_preflight():
        handle = runtime.operations.start_query_preflight()
        with _held_lock:
            _held_preflights.append(handle)
        event("test_preflight_held", None, operation_id=handle.op_id)
        return JSONResponse({"held": True})

    @app.post("/__stage2/release-preflight")
    async def release_preflight():
        with _held_lock:
            handle = _held_preflights.pop()
        runtime.operations.release(handle)
        event("test_preflight_released", None, operation_id=handle.op_id)
        return JSONResponse({"released": True})

    @app.post("/__stage2/hold-query-slot")
    async def hold_query_slot():
        handle = runtime.operations.admit_query()
        with _held_lock:
            _held_query_slots.append(handle)
        event("test_query_slot_held", None, operation_id=handle.op_id)
        return JSONResponse({"held": True})

    @app.post("/__stage2/release-query-slot")
    async def release_query_slot():
        with _held_lock:
            handle = _held_query_slots.pop()
        runtime.operations.release(handle)
        event("test_query_slot_released", None, operation_id=handle.op_id)
        return JSONResponse({"released": True})

    return originals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy", choices=("consecutive", "length_sorted_8"), required=True
    )
    options = parser.parse_args()
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 4:
        raise RuntimeError("local Stage 2 container must be CPU-only with four CPUs")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    counters: dict[str, int] = {}
    work_root = Path("/stage2-work")
    settings = settings_for(work_root, options.strategy)
    factories = resource_factories(options.strategy, counters)

    # Seed disposable backing through the application HTTP APIs before the
    # measured server starts. The seed app and measured app never share an
    # open Qdrant handle.
    from offline_rag.api.app import create_app as make_app

    bindings_path = work_root / "bindings.json"
    if bindings_path.is_file():
        bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    else:
        bindings = seed_workspaces(settings, factories)
        bindings_path.write_text(
            json.dumps(bindings, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    (EVENTS.parent / "bindings.json").write_text(
        json.dumps(bindings, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    global _runtime
    _runtime = runtime
    app = make_app(runtime=runtime)
    install_observers(app, runtime, counters)
    event(
        "server_ready_identity",
        None,
        source_revision="1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
        strategy=options.strategy,
        local_deadline_fixture_seconds=2,
        configured_deadline_s=settings.api.query_deadline_seconds,
        shutdown_grace_s=settings.api.shutdown_grace_seconds,
        effective_cpus=len(os.sched_getaffinity(0)),
        torch_intra=torch.get_num_threads(),
        torch_inter=torch.get_num_interop_threads(),
        provider_calls=0,
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        timeout_graceful_shutdown=1,
        log_level="warning",
    )
    event("server_exit", None, counters=counters)


if __name__ == "__main__":
    main()
