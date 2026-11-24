"""Stage 2 ASGI server with isolated synthetic and native diagnostic modes."""

from __future__ import annotations

import argparse
import contextvars
import hashlib
import json
import math
import os
import resource
import shutil
import sys
import threading
import time
import traceback
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import torch
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from stage2_identity import Stage2IdentityMiddleware
from stage2_settings import configure_fixture_generation

from offline_rag.api.app import create_app
from offline_rag.app.conversation.traces import ConversationTraceStore
from offline_rag.app.runtime import (
    ApplicationRuntime,
    ProcessResources,
    ResourceFactories,
    default_resource_factories,
)
from offline_rag.app.traces import ProductTraceStore
from offline_rag.config import load_settings
from offline_rag.core.ids import CHUNK_ID_ASC_TIE_BREAK
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.qdrant_local import QdrantLocalBackend
from offline_rag.generation.fake import FakeGenerator
from offline_rag.ingestion.docling_artifacts import write_provisioning_manifest
from offline_rag.rerank.cross_encoder import CrossEncoderReranker

EVENTS = Path("/stage2-journal/events.jsonl")
CONTROL = Path("/stage2-control")
DIAGNOSTIC_IMAGE_DIGEST = (
    "sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee"
)
_event_lock = threading.Lock()
_ordinal = contextvars.ContextVar("stage2_ordinal", default=None)
_operation_ordinals: dict[str, int] = {}
_operation_lock = threading.Lock()
_runtime: ApplicationRuntime | None = None
_native_model_verified = False
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


def process_measurement() -> dict[str, int]:
    """Return Linux process CPU and resident-memory measurements."""
    pages = int(Path("/proc/self/statm").read_text().split()[1])
    page_size_kib = os.sysconf("SC_PAGE_SIZE") // 1024
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "process_cpu_ns": time.process_time_ns(),
        "process_rss_kib": pages * page_size_kib,
        "process_peak_rss_kib": int(usage.ru_maxrss),
    }


def process_measurement_delta(start: dict[str, int]) -> dict[str, float | int]:
    """Project request-local process CPU time and current/peak RSS."""
    end = process_measurement()
    return {
        "process_cpu_ms": (end["process_cpu_ns"] - start["process_cpu_ns"]) / 1_000_000,
        "process_rss_start_kib": start["process_rss_kib"],
        "process_rss_kib": end["process_rss_kib"],
        "process_peak_rss_kib": end["process_peak_rss_kib"],
    }


def exception_diagnostics(exc: BaseException) -> dict[str, object]:
    """Capture exception types and traceback frames without messages or locals."""
    chain: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    relation = "outer"
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        frames = traceback.extract_tb(current.__traceback__)
        chain.append(
            {
                "relation": relation,
                "exception_type": type(current).__name__,
                "frames": [
                    {
                        "file": Path(frame.filename).name,
                        "line": frame.lineno,
                        "function": frame.name,
                    }
                    for frame in frames[-32:]
                ],
            }
        )
        if current.__cause__ is not None:
            current = current.__cause__
            relation = "cause"
        elif current.__context__ is not None and not current.__suppress_context__:
            current = current.__context__
            relation = "context"
        else:
            current = None
    return {"exception_chain": chain}


def failure_trace_projection(trace) -> dict[str, object]:
    """Return only bounded failure and timing fields from a product trace."""
    failure = trace.internal_failure
    execution = trace.execution
    return {
        "trace_id": trace.trace_id,
        "error_code": trace.error_code,
        "failure": (
            None
            if failure is None
            else {
                "stage": failure.stage,
                "failure_class": failure.failure_class,
                "exception_type": failure.exception_type,
                "causal_exception_types": failure.causal_exception_types,
            }
        ),
        "execution": {
            "generator_invoked": execution.generator_invoked,
            "attempt_count": execution.attempt_count,
            "context_latency_ms": execution.context_latency_ms,
            "generation_latency_ms": execution.generation_latency_ms,
            "total_latency_ms": execution.total_latency_ms,
            "citation_count": execution.citation_count,
        },
    }


def latency_projection(value: object) -> dict[str, object]:
    """Keep only finite numeric values in nested stage-latency metadata."""
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            nested = latency_projection(item)
            if nested:
                result[str(key)] = nested
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            if math.isfinite(float(item)):
                result[str(key)] = item
    return result


def observe_fixture_generation(request, respond) -> str:
    """Run the deterministic provider fixture and persist bounded timing."""
    ordinal = _ordinal.get()
    wall_start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    event("synthetic_generator_invoked", ordinal)
    try:
        response = respond(request)
    except BaseException as exc:
        event(
            "synthetic_generator_failed",
            ordinal,
            exception=type(exc).__name__,
            elapsed_ms=(time.perf_counter_ns() - wall_start) / 1_000_000,
            process_cpu_ms=(time.process_time_ns() - cpu_start) / 1_000_000,
        )
        raise
    event(
        "synthetic_generator_returned",
        ordinal,
        elapsed_ms=(time.perf_counter_ns() - wall_start) / 1_000_000,
        process_cpu_ms=(time.process_time_ns() - cpu_start) / 1_000_000,
    )
    return response


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
        except UnicodeDecodeError:
            ordinal = -1
        except ValueError:
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
                event(
                    "http_handler_raised",
                    ordinal,
                    exception=type(exc).__name__,
                    **exception_diagnostics(exc),
                    **process_measurement(),
                )
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

    settings = configure_fixture_generation(settings)
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
    return settings.model_copy(update={"reranker": reranker, "api": api})


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


def install_observers(app, runtime, counters, *, native_mode=False, strategy=None):
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
        local_deadline_override_s = (
            2 if not native_mode and control.get("case") == "deadline" else None
        )
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
            worker_measurement = process_measurement()
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
                trace_summary = None
                if trace_id:
                    try:
                        trace = ProductTraceStore(runtime.settings).get(trace_id)
                        if trace is not None:
                            trace_summary = failure_trace_projection(trace)
                    except Exception as trace_exc:  # noqa: BLE001
                        # Diagnostics must not mask the worker's original error.
                        trace_summary = {"read_error_type": type(trace_exc).__name__}
                event(
                    "worker_failed",
                    ordinal,
                    operation_id=operation.op_id,
                    exception=type(exc).__name__,
                    error_code=error_code,
                    reason=detail_reason,
                    trace_id=trace_id,
                    query_trace_present=(trace_summary is not None),
                    failure_trace=trace_summary,
                    **exception_diagnostics(exc),
                    **process_measurement_delta(worker_measurement),
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
                    **process_measurement_delta(worker_measurement),
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
            if native_mode and response.query_trace_id:
                trace = ProductTraceStore(runtime.settings).get(response.query_trace_id)
                if trace is not None:
                    observe_native_citations(response, trace, ordinal=ordinal)
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

    def diagnostic_identity():
        if native_mode:
            return native_identity(runtime.settings, strategy)
        return {
            "mode": "synthetic",
            "strategy": strategy,
            "source_revision": "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
        }

    app.add_middleware(
        Stage2IdentityMiddleware,
        identity_provider=diagnostic_identity,
    )
    if native_mode:
        install_native_ranking_observer()
        install_native_context_observer()

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


def load_native_bindings(path: Path) -> dict[str, dict[str, object]]:
    """Load only preflight-produced identities for existing workspaces."""
    from native_contract import validate_bindings

    return validate_bindings(
        json.loads(path.read_text(encoding="utf-8")),
        inputs=Path("/review/inputs"),
    )


def validate_native_settings(settings, strategy: str) -> None:
    """Fail closed unless native execution matches the frozen Stage 2 profile."""
    from offline_rag.dense.st_onnx_runtime import (
        FROZEN_ORT_INTER_OP_THREADS,
        FROZEN_ORT_INTRA_OP_THREADS,
    )

    rrk = settings.reranker
    api = settings.api
    embedding = settings.indexing.embedding
    if (
        rrk.enabled is not True
        or rrk.input_k != 30
        or rrk.batch_size != 16
        or rrk.max_length != 1024
        or rrk.input_construction != "plain-pair-v1"
        or rrk.sequence_contract != "seq-trunc-1024-passage-right-v1"
        or rrk.device != "auto"
        or rrk.score_transform != "raw-logit-v1"
        or rrk.tie_break != CHUNK_ID_ASC_TIE_BREAK
        or rrk.output_k != 10
        or rrk.model.model_id != "BAAI/bge-reranker-v2-m3"
        or rrk.model.revision != "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
        or rrk.model.local_files_only is not True
        or rrk.model.trust_remote_code is not False
        or rrk.batching_strategy != strategy
    ):
        raise RuntimeError("native reranker configuration differs from manifest")
    if (
        embedding.model_id != "Qwen/Qwen3-Embedding-0.6B"
        or embedding.revision != "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
        or embedding.dimension != 1024
        or embedding.device != "auto"
        or embedding.precision != "native"
        or settings.dense.enabled is not True
        or settings.project.strict_offline is not True
        or settings.deployment.qdrant_mode != "local"
        or api.max_concurrent_query != 1
        or api.query_deadline_seconds != 180
        or api.shutdown_grace_seconds != 30
    ):
        raise RuntimeError("native application execution settings differ")
    if (FROZEN_ORT_INTRA_OP_THREADS, FROZEN_ORT_INTER_OP_THREADS) != (8, 1):
        raise RuntimeError("frozen ONNX Runtime thread policy differs")
    if (torch.get_num_threads(), torch.get_num_interop_threads()) != (2, 2):
        raise RuntimeError("native Torch thread policy differs")
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 4:
        raise RuntimeError("native CPU execution environment differs")
    from native_contract import load_manifest, verify_config_file

    manifest = load_manifest(Path("/review/inputs"))
    verify_config_file(
        manifest,
        Path(os.environ.get("OFFLINE_RAG_CONFIG", "")),
    )
    if (
        manifest.get("schema") != "seneca-stage2-native-settings-v1"
        or manifest.get("application_source_commit")
        != "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e"
        or manifest.get("diagnostic_image_digest") != DIAGNOSTIC_IMAGE_DIGEST
        or manifest.get("scientific_settings_hash")
        != "5dce337dc1875b2aa615d62ee771a0ae384559c2da14be384e067ded035f5417"
        or hashlib.sha256(
            Path("/review/inputs/workloads-rich2.json").read_bytes()
        ).hexdigest()
        != manifest.get("workloads_file_sha256")
        or hashlib.sha256(
            Path("/review/inputs/stage1-bindings.json").read_bytes()
        ).hexdigest()
        != manifest.get("stage1_binding_file_sha256")
        or manifest.get("budget", {}).get("total_submissions") != 36
    ):
        raise RuntimeError("native settings manifest content differs")


def native_identity(settings, strategy: str) -> dict[str, object]:
    from offline_rag.dense.st_onnx_runtime import (
        FROZEN_ORT_INTER_OP_THREADS,
        FROZEN_ORT_INTRA_OP_THREADS,
    )

    availability = _runtime.embedding_availability if _runtime is not None else None
    reranker = (
        None
        if _runtime is None or _runtime.resources is None
        else _runtime.resources.reranker
    )
    embedder = (
        None
        if _runtime is None or _runtime.resources is None
        else _runtime.resources.embedder
    )
    profile = None if embedder is None else getattr(embedder, "profile", None)
    return {
        "mode": "native",
        "source_revision": "1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
        "strategy": strategy,
        "reranker_model_id": settings.reranker.model.model_id,
        "reranker_revision": settings.reranker.model.revision,
        "reranker_input_k": settings.reranker.input_k,
        "reranker_max_length": settings.reranker.max_length,
        "reranker_device_policy": settings.reranker.device,
        "reranker_resolved_device": None if reranker is None else reranker.device,
        "reranker_precision": "fp32",
        "reranker_score_transform": settings.reranker.score_transform,
        "embedding_model_id": settings.indexing.embedding.model_id,
        "embedding_revision": settings.indexing.embedding.revision,
        "embedding_device_policy": settings.indexing.embedding.device,
        "embedding_profile_id": (
            None if availability is None else availability.selected_profile_id
        ),
        "embedding_representation_id": (
            None if availability is None else availability.selected_representation_id
        ),
        "embedding_backend_family": None if profile is None else profile.backend_family,
        "embedding_resolved_device": None if profile is None else profile.device,
        "embedding_resolved_precision": None if profile is None else profile.precision,
        "embedding_provider": None if profile is None else profile.provider,
        "ort_intra": FROZEN_ORT_INTRA_OP_THREADS,
        "ort_inter": FROZEN_ORT_INTER_OP_THREADS,
        "configured_query_deadline_s": settings.api.query_deadline_seconds,
        "configured_shutdown_grace_s": settings.api.shutdown_grace_seconds,
        "effective_cpus": len(os.sched_getaffinity(0)),
        "torch_intra": torch.get_num_threads(),
        "torch_inter": torch.get_num_interop_threads(),
        "provider_fixture": True,
        "external_network": False,
        "runtime_ready": _runtime is not None and _runtime.is_ready,
    }


def native_resource_factories() -> ResourceFactories:
    """Use production embedding/reranking with only the fixture generator."""
    defaults = default_resource_factories()
    sys.path.insert(0, "/review/inputs")
    provider_path = Path("/review/inputs/provider_fixture.py")
    if hashlib.sha256(provider_path.read_bytes()).hexdigest() != (
        "07f3e9daaeffc2d46e0cd421fd57487fa8603020ff1d3271d923c94aae7ad3a0"
    ):
        raise RuntimeError("native deterministic provider fixture identity differs")
    from provider_fixture import respond

    def fixture_generator(_settings):
        return FakeGenerator(
            response_fn=lambda request: observe_fixture_generation(request, respond)
        )

    return replace(defaults, generator_client=fixture_generator)


def install_native_scorer_observer(counters: dict[str, int]) -> None:
    """Observe real BGE calls and barriers without changing tensors or scores."""
    original = CrossEncoderReranker.score_pairs

    def observed_score_pairs(scorer, pairs):
        global _native_model_verified
        ordinal = _ordinal.get()
        scorer_wall_start = time.perf_counter_ns()
        scorer_cpu_start = time.process_time_ns()
        counters["native_scorer_calls"] = counters.get("native_scorer_calls", 0) + 1
        counters["native_candidate_pairs"] = len(pairs)
        event("scorer_entered", ordinal, pair_count=len(pairs), mode="native")
        _tokenizer, model = scorer._load()
        import torch

        if not _native_model_verified:
            floating_tensors = [
                tensor
                for tensor in (*model.parameters(), *model.buffers())
                if tensor.is_floating_point()
            ]
            if not floating_tensors or any(
                tensor.dtype != torch.float32 or tensor.device.type != "cpu"
                for tensor in floating_tensors
            ):
                raise RuntimeError("native BGE tensors are not CPU FP32")
            _native_model_verified = True
        control = current_control(ordinal)
        forward_starts: list[tuple[int, int]] = []

        def before(_module, _args, kwargs):
            marker = EVENTS.parent / f"{ordinal}.forward_entered"
            if control.get("hold") == "forward" and not marker.exists():
                marker.touch(exist_ok=False)
                event(
                    "forward_entered",
                    ordinal,
                    shape=list(kwargs["input_ids"].shape),
                    mode="native",
                    query_capacity_held=(
                        _runtime.operations.query_capacity.held
                        if _runtime is not None
                        else None
                    ),
                )
                deadline = time.monotonic() + 180
                release = EVENTS.parent / f"{ordinal}.release"
                while not release.exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("native forward barrier expired")
                    time.sleep(0.01)
                event("forward_released", ordinal)
            forward_starts.append((time.perf_counter_ns(), time.process_time_ns()))
            shape = list(kwargs["input_ids"].shape)
            event("forward_started", ordinal, shape=shape, mode="native")

        def after(_module, _args, output):
            if not forward_starts:
                return
            wall_start, cpu_start = forward_starts.pop()
            elapsed_ms = (time.perf_counter_ns() - wall_start) / 1_000_000
            logits = getattr(output, "logits", None)
            process = process_measurement()
            event(
                "forward_returned",
                ordinal,
                elapsed_ms=elapsed_ms,
                process_cpu_ms=(time.process_time_ns() - cpu_start) / 1_000_000,
                process_rss_kib=process["process_rss_kib"],
                process_peak_rss_kib=process["process_peak_rss_kib"],
                logits_shape=(list(logits.shape) if logits is not None else None),
                mode="native",
            )

        pre_hook = model.register_forward_pre_hook(before, with_kwargs=True)
        post_hook = model.register_forward_hook(after, always_call=True)
        try:
            result = original(scorer, pairs)
        except BaseException as exc:
            event(
                "scorer_failed",
                ordinal,
                exception=type(exc).__name__,
                scorer_wall_ms=(time.perf_counter_ns() - scorer_wall_start) / 1_000_000,
                scorer_cpu_ms=(time.process_time_ns() - scorer_cpu_start) / 1_000_000,
                mode="native",
            )
            raise
        else:
            event(
                "native_scores",
                ordinal,
                candidate_order_sha256=hash_json([pair.chunk_id for pair in pairs]),
                score_associations=[
                    {
                        "candidate_id_sha256": hashlib.sha256(
                            pair.chunk_id.encode("utf-8")
                        ).hexdigest(),
                        "pair_input_sha256": hashlib.sha256(
                            (pair.query_text + "\0" + pair.passage_text).encode("utf-8")
                        ).hexdigest(),
                        "raw_logit": float(score),
                    }
                    for pair, score in zip(pairs, result, strict=True)
                ],
                score_count=len(result),
            )
            event(
                "scorer_returned",
                ordinal,
                score_count=len(result),
                scorer_wall_ms=(time.perf_counter_ns() - scorer_wall_start) / 1_000_000,
                scorer_cpu_ms=(time.process_time_ns() - scorer_cpu_start) / 1_000_000,
                mode="native",
            )
            return result
        finally:
            pre_hook.remove()
            post_hook.remove()

    CrossEncoderReranker.score_pairs = observed_score_pairs


def hash_json(value) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def observe_native_ranking(ordered, *, ordinal: int | None = None) -> None:
    """Persist candidate identity from canonical ``(candidate, score)`` pairs."""
    candidates = [candidate for candidate, _score in ordered]
    event(
        "native_ranked_candidates",
        ordinal,
        candidate_count=len(candidates),
        ranked_candidate_ids_sha256=hash_json(
            [candidate.chunk_id for candidate in candidates]
        ),
        ranked_candidate_order=[
            hashlib.sha256(candidate.chunk_id.encode("utf-8")).hexdigest()
            for candidate in candidates
        ],
        tie_break=CHUNK_ID_ASC_TIE_BREAK,
        mode="native",
    )


def install_native_ranking_observer() -> None:
    """Observe the canonical tuple-valued reranker sort boundary."""
    from offline_rag.rerank import retrieve as rerank_retrieve

    original_sort_scored = rerank_retrieve._sort_scored

    def observed_sort_scored(pool, scores):
        ordered = original_sort_scored(pool, scores)
        if len(ordered) != len(pool):
            raise RuntimeError("native reranker ranking lost a candidate")
        observe_native_ranking(ordered, ordinal=_ordinal.get())
        return ordered

    rerank_retrieve._sort_scored = observed_sort_scored


def observe_native_context(result, *, ordinal: int | None = None) -> None:
    """Persist context identity and canonical nested latency metadata."""
    event(
        "native_context",
        ordinal,
        anchor_ids_sha256=hash_json([item.chunk_id for item in result.anchors]),
        anchor_order=[
            hashlib.sha256(str(item.chunk_id).encode("utf-8")).hexdigest()
            for item in result.anchors
        ],
        evidence_unit_ids_sha256=hash_json(
            [item.evidence_unit_id for item in result.evidence_units]
        ),
        context_sha256=hashlib.sha256(
            result.assembled_text.encode("utf-8")
        ).hexdigest(),
        context_token_count=result.context_token_count,
        evidence_unit_count=len(result.evidence_units),
        reranker_execution=result.metadata.get("reranker_execution"),
        latency_ms=latency_projection(result.metadata.get("latency_ms")),
    )


def install_native_context_observer() -> None:
    """Observe canonical context results without altering assembly behavior."""
    from offline_rag.context.assemble import HybridRerankContextAssembler

    original_assemble = HybridRerankContextAssembler.assemble

    def observed_assemble(assembler, *args, **kwargs):
        result = original_assemble(assembler, *args, **kwargs)
        observe_native_context(result, ordinal=_ordinal.get())
        return result

    HybridRerankContextAssembler.assemble = observed_assemble


def observe_native_citations(response, trace, *, ordinal: int | None = None) -> None:
    """Persist citation identity from the canonical product trace."""
    chunk_ids = trace.execution.citation_chunk_ids
    evidence_unit_ids = trace.execution.citation_evidence_unit_ids
    if not chunk_ids or not evidence_unit_ids:
        raise RuntimeError("native provider fixture produced no citations")
    event(
        "native_citations",
        ordinal,
        query_trace_id=response.query_trace_id,
        citation_chunk_ids_sha256=hash_json(chunk_ids),
        citation_evidence_unit_ids_sha256=hash_json(evidence_unit_ids),
        citation_chunk_count=len(chunk_ids),
        citation_evidence_unit_count=len(evidence_unit_ids),
        context_latency_ms=trace.execution.context_latency_ms,
        generation_latency_ms=trace.execution.generation_latency_ms,
        total_latency_ms=trace.execution.total_latency_ms,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("synthetic", "native"), default="synthetic")
    parser.add_argument(
        "--strategy", choices=("consecutive", "length_sorted_8"), required=True
    )
    parser.add_argument("--native-bindings", type=Path)
    options = parser.parse_args()
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 4:
        raise RuntimeError("Stage 2 container must be CPU-only with four CPUs")
    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    counters: dict[str, int] = {}
    from offline_rag.api.app import create_app as make_app

    if options.mode == "synthetic":
        if options.native_bindings is not None:
            raise ValueError("synthetic mode does not accept native bindings")
        work_root = Path("/stage2-work")
        settings = settings_for(work_root, options.strategy)
        factories = resource_factories(options.strategy, counters)
        bindings_path = work_root / "bindings.json"
        if bindings_path.is_file():
            bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
        else:
            # The synthetic rehearsal seeds disposable workspaces through the
            # application APIs. Native mode never enters this branch.
            bindings = seed_workspaces(settings, factories)
            bindings_path.write_text(
                json.dumps(bindings, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
    else:
        if options.native_bindings is None:
            raise ValueError("native mode requires verified native bindings")
        if not options.native_bindings.is_file():
            raise FileNotFoundError("native binding artifact is missing")
        if (
            os.environ.get("HF_HUB_OFFLINE") != "1"
            or os.environ.get("TRANSFORMERS_OFFLINE") != "1"
        ):
            raise RuntimeError("native mode requires offline model loading")
        if not Path("/data").is_dir() or not Path("/models").is_dir():
            raise RuntimeError("native mode requires /data and /models mounts")
        if not os.statvfs("/models").f_flag & os.ST_RDONLY:
            raise RuntimeError("native model mount must be read-only")
        settings = configure_fixture_generation(load_settings())
        settings = settings.model_copy(
            update={
                "reranker": settings.reranker.model_copy(
                    update={"batching_strategy": options.strategy}
                )
            }
        )
        validate_native_settings(settings, options.strategy)
        bindings = load_native_bindings(options.native_bindings)
        factories = native_resource_factories()
        install_native_scorer_observer(counters)

    (EVENTS.parent / "bindings.json").write_text(
        json.dumps(bindings, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    runtime = ApplicationRuntime(settings=settings, factories=factories)
    global _runtime
    _runtime = runtime
    app = make_app(runtime=runtime)
    install_observers(
        app,
        runtime,
        counters,
        native_mode=options.mode == "native",
        strategy=options.strategy,
    )
    expected_shutdown_grace = 30 if options.mode == "native" else 1
    if settings.api.shutdown_grace_seconds != expected_shutdown_grace:
        raise RuntimeError("unexpected Stage 2 shutdown grace")
    event(
        "server_ready_identity",
        None,
        source_revision="1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e",
        mode=options.mode,
        strategy=options.strategy,
        local_deadline_fixture_seconds=2 if options.mode == "synthetic" else None,
        configured_deadline_s=settings.api.query_deadline_seconds,
        shutdown_grace_s=settings.api.shutdown_grace_seconds,
        effective_cpus=len(os.sched_getaffinity(0)),
        torch_intra=torch.get_num_threads(),
        torch_inter=torch.get_num_interop_threads(),
        provider_calls=0,
        synthetic_inference=options.mode == "synthetic",
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        timeout_graceful_shutdown=expected_shutdown_grace,
        log_level="warning",
    )
    event("server_exit", None, counters=counters)


if __name__ == "__main__":
    main()
