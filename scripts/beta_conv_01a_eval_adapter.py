"""Evidence adapter for the canonical BETA-CONV-01A conversation route.

This module is preparation tooling. It never creates an application or
conversation executor; callers provide the application created by
``offline_rag.api.app.create_app`` and its ready runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Protocol, Self

import httpx

from offline_rag.app.conversation import turn as conversation_turn
from offline_rag.app.conversation.traces import ConversationTraceStore
from offline_rag.app.errors import ErrorCode
from offline_rag.app.query import MAX_QUESTION_CHARS
from offline_rag.app.traces import ProductTraceStore
from offline_rag.core.ids import CONVERSATION_CONTEXT_RESOLVER_V1, GROUNDED_ANSWER_V2

try:
    from offline_rag.app.conversation.planner import PLANNER_CONTRACT_ID
except ImportError:  # pragma: no cover - protects a mismatched checkout
    PLANNER_CONTRACT_ID = "seneca_conversation_task_plan_v1"

from offline_rag.app.conversation.transform import TRANSFORM_PROMPT_CONTRACT_ID

MAX_CASE_ID_CHARS = 128
_SAFE_REASON_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_request_sha256(request: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResponseClient(Protocol):
    def post(self, url: str, *, json: dict[str, Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class SourceAliasMap:
    """One-to-one aliases for the exact active synthetic source population."""

    alias_to_source_id: Mapping[str, str]
    source_id_to_alias: Mapping[str, str]
    sha256: str

    @classmethod
    def from_active_sources(
        cls,
        alias_to_display_name: Mapping[str, str],
        active_sources: Sequence[Mapping[str, Any]],
    ) -> SourceAliasMap:
        """Bind aliases to created source IDs and require exact population match."""
        if not alias_to_display_name:
            raise ValueError("source alias map must not be empty")
        if len(alias_to_display_name) != len(set(alias_to_display_name)):
            raise ValueError("source aliases must be unique")
        if any(
            not isinstance(alias, str)
            or not alias
            or not isinstance(display_name, str)
            or not display_name
            for alias, display_name in alias_to_display_name.items()
        ):
            raise ValueError(
                "source aliases and display names must be nonempty strings"
            )

        active_ids: list[str] = []
        active_by_name: dict[str, list[str]] = {}
        for source in active_sources:
            active_flag = source.get("active", True)
            if active_flag is False:
                continue
            if active_flag is not True:
                raise ValueError("active workspace source status is invalid")
            source_id = source.get("source_id")
            display_name = source.get("display_name")
            if (
                not isinstance(source_id, str)
                or not source_id
                or not isinstance(display_name, str)
                or not display_name
            ):
                raise ValueError("active workspace source identity is invalid")
            active_ids.append(source_id)
            active_by_name.setdefault(display_name, []).append(source_id)

        if len(active_ids) != len(set(active_ids)):
            raise ValueError("active workspace contains duplicate source IDs")

        alias_to_source_id: dict[str, str] = {}
        for alias, display_name in alias_to_display_name.items():
            matches = active_by_name.get(display_name, [])
            if len(matches) != 1:
                raise ValueError(
                    "source alias does not map to exactly one active source"
                )
            alias_to_source_id[alias] = matches[0]

        if len(set(alias_to_source_id.values())) != len(alias_to_source_id):
            raise ValueError("source aliases must map to distinct created source IDs")
        if set(alias_to_source_id.values()) != set(active_ids):
            raise ValueError("active workspace population differs from alias map")

        source_id_to_alias = {
            source_id: alias for alias, source_id in alias_to_source_id.items()
        }
        canonical = json.dumps(
            alias_to_source_id,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(alias_to_source_id, source_id_to_alias, digest)

    def translate_request_scope(self, aliases: object) -> list[str] | None:
        """Translate selected aliases; preserve null as all-active scope."""
        if aliases is None:
            return None
        if not isinstance(aliases, list) or not aliases:
            raise ValueError("source_ids must be null or a nonempty alias list")
        if any(not isinstance(alias, str) for alias in aliases):
            raise ValueError("source scope contains a non-string alias")
        if len(aliases) != len(set(aliases)):
            raise ValueError("source scope contains duplicate aliases")
        try:
            return [self.alias_to_source_id[alias] for alias in aliases]
        except KeyError as exc:
            raise ValueError("source scope contains an unknown alias") from exc

    def normalize_citations(self, citations: object) -> tuple[list[str], bool]:
        """Return stable aliases and whether every citation identity is known."""
        if not isinstance(citations, list):
            return [], False
        aliases: list[str] = []
        valid = True
        for citation in citations:
            if not isinstance(citation, dict):
                valid = False
                continue
            source_id = citation.get("source_id")
            alias = self.source_id_to_alias.get(source_id)
            if alias is None:
                valid = False
                continue
            aliases.append(alias)
        return aliases, valid


class _ObservedGenerator:
    def __init__(self, wrapped: Any, recorder: EvaluationInstrumentation) -> None:
        self._wrapped = wrapped
        self._recorder = recorder

    def generate(self, request: Any) -> Any:
        metadata = getattr(request, "metadata", None) or {}
        contract = metadata.get("prompt_contract")
        started = time.perf_counter()
        self._recorder.record_generator_call(contract)
        try:
            return self._wrapped.generate(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._recorder.record_generator_duration(contract, elapsed_ms)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class EvaluationInstrumentation(AbstractContextManager[Self]):
    """Count canonical executor calls without storing prompts or responses."""

    _install_lock = threading.Lock()

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._calls: Counter[str] = Counter()
        self._lock = threading.Lock()
        self._generator_original: Any = None
        self._query_original: Any = None
        self._transform_original: Any = None
        self._active = False
        self._latest_transform_options: dict[str, Any] | None = None
        self._latest_planner_elapsed_ms: float | None = None

    def __enter__(self) -> Self:
        if not self._install_lock.acquire(blocking=False):
            raise RuntimeError("evaluation instrumentation is already active")
        resources = getattr(self._runtime, "resources", None)
        if resources is None or resources.generator_client is None:
            self._install_lock.release()
            raise RuntimeError("ready runtime has no generation client")

        self._generator_original = resources.generator_client
        resources.generator_client = _ObservedGenerator(self._generator_original, self)

        self._query_original = conversation_turn.run_bound_snapshot_query

        def observe_query(*args: Any, **kwargs: Any) -> Any:
            self._increment("retrieval_calls")
            return self._query_original(*args, **kwargs)

        conversation_turn.run_bound_snapshot_query = observe_query
        self._transform_original = conversation_turn.transform_conversation_text

        def observe_transform(*args: Any, **kwargs: Any) -> Any:
            self._increment("transform_calls")
            self._record_transform_instruction(kwargs.get("instruction"))
            return self._transform_original(*args, **kwargs)

        conversation_turn.transform_conversation_text = observe_transform
        self._active = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self._active:
            return
        resources = getattr(self._runtime, "resources", None)
        if resources is not None:
            resources.generator_client = self._generator_original
        conversation_turn.run_bound_snapshot_query = self._query_original
        conversation_turn.transform_conversation_text = self._transform_original
        self._active = False
        self._install_lock.release()

    def snapshot_counts(self) -> dict[str, int]:
        with self._lock:
            return {key: self._calls[key] for key in _CALL_FIELDS}

    def transform_options(self) -> dict[str, Any] | None:
        with self._lock:
            return self._latest_transform_options

    def begin_request(self) -> None:
        """Clear per-request measurements before the canonical API call."""
        with self._lock:
            self._latest_transform_options = None
            self._latest_planner_elapsed_ms = None

    def planner_elapsed_ms(self) -> float | None:
        with self._lock:
            return self._latest_planner_elapsed_ms

    def record_generator_call(self, contract: object) -> None:
        if contract == PLANNER_CONTRACT_ID:
            self._increment("planner_calls")
        elif contract == CONVERSATION_CONTEXT_RESOLVER_V1:
            self._increment("resolver_calls")
        elif contract == GROUNDED_ANSWER_V2:
            self._increment("answer_generation_calls")
        elif contract == TRANSFORM_PROMPT_CONTRACT_ID:
            # Count only calls that reach the existing transform executor.
            pass

    def record_generator_duration(self, contract: object, elapsed_ms: float) -> None:
        if contract != PLANNER_CONTRACT_ID:
            return
        with self._lock:
            self._latest_planner_elapsed_ms = elapsed_ms

    def _record_transform_instruction(self, instruction: object) -> None:
        options = _options_from_instruction(instruction)
        with self._lock:
            self._latest_transform_options = options

    def _increment(self, name: str) -> None:
        with self._lock:
            self._calls[name] += 1


_CALL_FIELDS = (
    "planner_calls",
    "resolver_calls",
    "retrieval_calls",
    "answer_generation_calls",
    "transform_calls",
)


def _options_from_instruction(instruction: object) -> dict[str, Any] | None:
    """Normalize the exact sealed transform instruction passed to execution."""
    if not isinstance(instruction, str):
        return None
    values: dict[str, Any] = {
        "bullet_count": None,
        "audience": None,
        "target_language": None,
    }
    summarize = re.fullmatch(r"summarize(?: in ([1-9]|1[0-2]) bullets)?", instruction)
    if summarize:
        values["bullet_count"] = (
            int(summarize.group(1)) if summarize.group(1) is not None else None
        )
        return values
    edit = re.fullmatch(r"(rewrite|simplify)(?: for (.{1,60}))?", instruction)
    if edit:
        values["audience"] = edit.group(2)
        return values
    translation = re.fullmatch(r"translate into (.{1,40})", instruction)
    if translation:
        values["target_language"] = translation.group(1)
        return values
    if instruction in {"rewrite", "simplify"}:
        return values
    return None


def _safe_reason(value: object) -> str | None:
    if isinstance(value, str) and _SAFE_REASON_RE.fullmatch(value):
        return value
    return None


def _operation_from_trace(trace: Any, response_kind: object) -> str | None:
    planner_operation = getattr(trace, "planner_operation", None)
    if planner_operation == "grounded_query":
        return "grounded_query"
    if planner_operation == "transform_text":
        return "transform_text"
    if planner_operation == "unsupported_operation":
        return "unsupported_operation"
    if planner_operation == "clarify":
        return "clarify"
    if response_kind == "grounded_answer":
        return "grounded_query"
    if response_kind == "conversation_transform":
        return "transform_text"
    if response_kind == "clarification":
        return "clarify"
    return None


def _citation_ids_from_query_trace(query_trace: Any) -> set[str]:
    execution = getattr(query_trace, "execution", None)
    ids = getattr(execution, "citation_evidence_unit_ids", None)
    return set(ids) if isinstance(ids, list) else set()


def _empty_observation(
    *,
    case_id: str,
    arm: str,
    repeat: int,
    phase: str,
    elapsed_ms: float,
    terminal_state: str,
    reason_code: str | None,
    counts: Mapping[str, int],
    planner_elapsed_ms: float | None,
    planner_validation: str | None = None,
    adapter_error_category: str | None = None,
    source_alias_mapping_sha256: str | None = None,
    request_sha256: str | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "request_sha256": request_sha256,
        "arm": arm,
        "repeat": repeat,
        "terminal_state": terminal_state,
        "response_status": None,
        "measurement_phase": phase,
        "elapsed_ms": elapsed_ms,
        "planner_elapsed_ms": planner_elapsed_ms,
        "observed_operation": None,
        "planner_validation": planner_validation
        or ("unavailable" if counts.get("planner_calls", 0) else None),
        "reason_code": reason_code,
        "citation_source_ids": [],
        "citations_valid": False,
        "snapshot_consistent": None,
        "source_scope_consistent": None,
        "query_trace_present": False,
        "query_trace_link_consistent": None,
        "target_kind": None,
        "target_role": None,
        "target_ordinal": None,
        "target_sha256": None,
        "target_char_count": None,
        "transform_kind": None,
        "options": None,
        "planner_calls": counts.get("planner_calls", 0),
        "resolver_calls": counts.get("resolver_calls", 0),
        "retrieval_calls": counts.get("retrieval_calls", 0),
        "answer_generation_calls": counts.get("answer_generation_calls", 0),
        "transform_calls": counts.get("transform_calls", 0),
        "retry_count": 0,
        "adapter_error_category": adapter_error_category,
        "source_alias_mapping_sha256": source_alias_mapping_sha256,
    }


class ConversationApiEvidenceAdapter:
    """Call and normalize the one canonical conversation HTTP endpoint."""

    def __init__(
        self,
        *,
        client: ResponseClient,
        runtime: Any,
        workspace_id: str,
        source_aliases: SourceAliasMap,
        instrumentation: EvaluationInstrumentation,
    ) -> None:
        if not workspace_id:
            raise ValueError("workspace_id is required")
        configured_arm = getattr(
            getattr(getattr(runtime, "settings", None), "conversation", None),
            "router_mode",
            None,
        )
        if configured_arm not in {"legacy", "planner"}:
            raise ValueError("runtime router mode is unavailable")
        self._client = client
        self._runtime = runtime
        self._configured_arm = configured_arm
        self._workspace_id = workspace_id
        self._source_aliases = source_aliases
        self._instrumentation = instrumentation
        self._lock = threading.Lock()

    def execute(
        self,
        case: Mapping[str, Any],
        *,
        arm: str,
        repeat: int,
        measurement_phase: str,
        timeout: float,
    ) -> dict[str, Any]:
        """Run one scheduled request; retain API, timeout, and transport errors."""
        case_id = case.get("case_id")
        request = case.get("request")
        if (
            not isinstance(case_id, str)
            or not case_id
            or len(case_id) > MAX_CASE_ID_CHARS
            or arm not in {"legacy", "planner"}
            or isinstance(repeat, bool)
            or not isinstance(repeat, int)
            or repeat < 1
            or measurement_phase not in {"cold_start", "warm_interactive"}
            or isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or not isinstance(request, Mapping)
        ):
            raise ValueError("scheduled evaluation request identity is invalid")
        if arm != self._configured_arm:
            raise ValueError("scheduled arm does not match application router mode")
        question = request.get("question")
        prior_turns = request.get("prior_turns", [])
        request_sha256 = case.get("request_sha256")
        if (
            not isinstance(question, str)
            or not question.strip()
            or len(question.strip()) > MAX_QUESTION_CHARS
            or not isinstance(prior_turns, list)
            or not isinstance(request_sha256, str)
            or not _SHA256_RE.fullmatch(request_sha256)
        ):
            raise ValueError("evaluation request does not match conversation schema")
        try:
            actual_request_sha256 = _canonical_request_sha256(request)
        except (TypeError, ValueError) as exc:
            raise ValueError("evaluation request is not canonical JSON data") from exc
        if request_sha256 != actual_request_sha256:
            raise ValueError("evaluation request hash does not match dataset record")
        translated_scope = self._source_aliases.translate_request_scope(
            request.get("source_ids")
        )
        body = {
            "question": question,
            "prior_turns": prior_turns,
            "source_ids": translated_scope,
        }

        with self._lock:
            before = self._instrumentation.snapshot_counts()
            self._instrumentation.begin_request()
            started = time.perf_counter()
            try:
                response = self._client.post(
                    f"/v1/workspaces/{self._workspace_id}/conversation/turn",
                    json=body,
                    timeout=timeout,
                )
            except httpx.TimeoutException:
                elapsed_ms = (time.perf_counter() - started) * 1000
                return _empty_observation(
                    case_id=case_id,
                    arm=arm,
                    repeat=repeat,
                    phase=measurement_phase,
                    elapsed_ms=elapsed_ms,
                    terminal_state="timeout",
                    reason_code="request_timeout",
                    counts=_count_delta(
                        before, self._instrumentation.snapshot_counts()
                    ),
                    planner_elapsed_ms=self._instrumentation.planner_elapsed_ms(),
                    source_alias_mapping_sha256=self._source_aliases.sha256,
                    request_sha256=request_sha256,
                )
            except httpx.HTTPError:
                elapsed_ms = (time.perf_counter() - started) * 1000
                return _empty_observation(
                    case_id=case_id,
                    arm=arm,
                    repeat=repeat,
                    phase=measurement_phase,
                    elapsed_ms=elapsed_ms,
                    terminal_state="error",
                    reason_code="transport_error",
                    counts=_count_delta(
                        before, self._instrumentation.snapshot_counts()
                    ),
                    adapter_error_category="transport_error",
                    source_alias_mapping_sha256=self._source_aliases.sha256,
                    planner_elapsed_ms=self._instrumentation.planner_elapsed_ms(),
                    request_sha256=request_sha256,
                )
            elapsed_ms = (time.perf_counter() - started) * 1000
            counts = _count_delta(before, self._instrumentation.snapshot_counts())

            if response.status_code < 200 or response.status_code >= 300:
                error_code = None
                try:
                    error_code = response.json().get("error", {}).get("code")
                except ValueError, AttributeError:
                    pass
                known_codes = {code.value for code in ErrorCode}
                safe_code = error_code if error_code in known_codes else "api_error"
                return _empty_observation(
                    case_id=case_id,
                    arm=arm,
                    repeat=repeat,
                    phase=measurement_phase,
                    elapsed_ms=elapsed_ms,
                    terminal_state=(
                        "cancelled"
                        if safe_code == ErrorCode.REQUEST_CANCELLED.value
                        else "error"
                    ),
                    reason_code=safe_code,
                    counts=counts,
                    planner_elapsed_ms=self._instrumentation.planner_elapsed_ms(),
                    planner_validation=(
                        "unavailable" if counts["planner_calls"] else None
                    ),
                    source_alias_mapping_sha256=self._source_aliases.sha256,
                    request_sha256=request_sha256,
                )

            try:
                payload = response.json()
            except ValueError:
                return _empty_observation(
                    case_id=case_id,
                    arm=arm,
                    repeat=repeat,
                    phase=measurement_phase,
                    elapsed_ms=elapsed_ms,
                    terminal_state="error",
                    reason_code="invalid_api_response",
                    counts=counts,
                    planner_elapsed_ms=self._instrumentation.planner_elapsed_ms(),
                    adapter_error_category="invalid_api_response",
                    source_alias_mapping_sha256=self._source_aliases.sha256,
                    request_sha256=request_sha256,
                )

            return self._normalize_response(
                case_id=case_id,
                arm=arm,
                repeat=repeat,
                phase=measurement_phase,
                elapsed_ms=elapsed_ms,
                payload=payload,
                counts=counts,
                expected_live_scope=translated_scope,
                measured_planner_elapsed_ms=self._instrumentation.planner_elapsed_ms(),
                expected_request_sha256=request_sha256,
            )

    def _normalize_response(
        self,
        *,
        case_id: str,
        arm: str,
        repeat: int,
        phase: str,
        elapsed_ms: float,
        payload: object,
        counts: Mapping[str, int],
        expected_live_scope: list[str] | None,
        measured_planner_elapsed_ms: float | None,
        expected_request_sha256: str,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return _empty_observation(
                case_id=case_id,
                arm=arm,
                repeat=repeat,
                phase=phase,
                elapsed_ms=elapsed_ms,
                terminal_state="error",
                reason_code="invalid_api_response",
                counts=counts,
                planner_elapsed_ms=measured_planner_elapsed_ms,
                adapter_error_category="invalid_api_response",
                source_alias_mapping_sha256=self._source_aliases.sha256,
                request_sha256=expected_request_sha256,
            )

        conversation_trace_id = payload.get("conversation_trace_id")
        conversation_trace = None
        if isinstance(conversation_trace_id, str):
            try:
                conversation_trace = ConversationTraceStore(self._runtime.settings).get(
                    conversation_trace_id
                )
            except OSError, ValueError:
                conversation_trace = None
        query_trace_id = payload.get("query_trace_id")
        query_trace = None
        if isinstance(query_trace_id, str):
            try:
                query_trace = ProductTraceStore(self._runtime.settings).get(
                    query_trace_id
                )
            except OSError, ValueError:
                query_trace = None

        adapter_error_category = None
        citations, citation_ids_valid = self._source_aliases.normalize_citations(
            payload.get("citations")
        )
        query_evidence_ids = _citation_ids_from_query_trace(query_trace)
        raw_citations = payload.get("citations")
        if not isinstance(raw_citations, list):
            citation_ids_valid = False
            raw_citations = []
        evidence_refs_valid = all(
            isinstance(citation, dict)
            and isinstance(citation.get("evidence_unit_id"), str)
            and citation.get("evidence_unit_id") in query_evidence_ids
            for citation in raw_citations
        )
        citations_valid = citation_ids_valid and evidence_refs_valid
        if not citation_ids_valid:
            adapter_error_category = "unknown_citation_source"
        elif not evidence_refs_valid:
            adapter_error_category = "citation_trace_mismatch"

        snapshot_id = payload.get("snapshot_id")
        query_trace_link_consistent = bool(
            conversation_trace is not None
            and getattr(conversation_trace, "query_trace_id", None) == query_trace_id
        )
        if not query_trace_link_consistent:
            adapter_error_category = (
                adapter_error_category or "query_trace_link_mismatch"
            )
        snapshot_consistent = bool(
            conversation_trace is not None
            and conversation_trace.snapshot_id == snapshot_id
            and (query_trace is None or query_trace.snapshot_id == snapshot_id)
        )
        traced_scope = (
            getattr(conversation_trace, "source_scope", None)
            if conversation_trace is not None
            else None
        )
        expected_scope_set = (
            set(self._source_aliases.alias_to_source_id.values())
            if expected_live_scope is None
            else set(expected_live_scope)
        )
        traced_scope_ids = getattr(traced_scope, "source_ids", None)
        source_scope_consistent = bool(
            traced_scope is not None
            and isinstance(traced_scope_ids, list)
            and len(traced_scope_ids) == len(set(traced_scope_ids))
            and (
                (expected_live_scope is None and traced_scope.mode == "all_active")
                or (expected_live_scope is not None and traced_scope.mode == "selected")
            )
            and set(traced_scope_ids) == expected_scope_set
        )
        if not source_scope_consistent:
            adapter_error_category = adapter_error_category or "source_scope_mismatch"
        query_trace_present = bool(
            isinstance(query_trace_id, str) and query_trace is not None
        )
        if query_trace_id is not None and not query_trace_present:
            adapter_error_category = adapter_error_category or "query_trace_missing"
        if conversation_trace is None:
            adapter_error_category = (
                adapter_error_category or "conversation_trace_missing"
            )

        status = payload.get("status")
        if status not in {
            "answered",
            "insufficient_evidence",
            "model_abstain",
            "clarification_required",
            "transformed",
        }:
            return _empty_observation(
                case_id=case_id,
                arm=arm,
                repeat=repeat,
                phase=phase,
                elapsed_ms=elapsed_ms,
                terminal_state="error",
                reason_code="invalid_api_response",
                counts=counts,
                planner_elapsed_ms=measured_planner_elapsed_ms,
                adapter_error_category="invalid_api_response",
                source_alias_mapping_sha256=self._source_aliases.sha256,
                request_sha256=expected_request_sha256,
            )

        planner_elapsed_ms = getattr(conversation_trace, "planner_duration_ms", None)
        if planner_elapsed_ms is None:
            planner_elapsed_ms = measured_planner_elapsed_ms
        reason = _safe_reason(
            getattr(conversation_trace, "planner_reason_code", None)
            or payload.get("guidance_code")
            or payload.get("abstention_reason")
        )
        transform_source_kind = getattr(
            conversation_trace, "transform_source_kind", None
        )
        target_kind = (
            "current_message_span"
            if transform_source_kind == "current_message"
            else "prior_turn"
            if transform_source_kind in {"prior_user_turn", "prior_assistant_turn"}
            else None
        )
        options = (
            self._instrumentation.transform_options()
            if status == "transformed"
            else None
        )
        if status == "transformed" and options is None:
            adapter_error_category = (
                adapter_error_category or "transform_options_unobserved"
            )

        return {
            "case_id": case_id,
            "request_sha256": expected_request_sha256,
            "arm": arm,
            "repeat": repeat,
            "terminal_state": "response",
            "response_status": status,
            "measurement_phase": phase,
            "elapsed_ms": elapsed_ms,
            "planner_elapsed_ms": planner_elapsed_ms,
            "observed_operation": _operation_from_trace(
                conversation_trace, payload.get("response_kind")
            ),
            "planner_validation": getattr(
                conversation_trace,
                "planner_validation",
                "unavailable" if counts.get("planner_calls", 0) else None,
            )
            or ("unavailable" if counts.get("planner_calls", 0) else None),
            "reason_code": reason,
            "citation_source_ids": citations,
            "citations_valid": citations_valid,
            "snapshot_consistent": snapshot_consistent,
            "source_scope_consistent": source_scope_consistent,
            "query_trace_present": query_trace_present,
            "query_trace_link_consistent": query_trace_link_consistent,
            "target_kind": target_kind,
            "target_role": getattr(conversation_trace, "transform_source_role", None),
            "target_ordinal": getattr(
                conversation_trace, "transform_source_turn_ordinal", None
            ),
            "target_sha256": getattr(
                conversation_trace, "transform_target_sha256", None
            ),
            "target_char_count": getattr(
                conversation_trace, "transform_target_char_count", None
            ),
            "transform_kind": getattr(conversation_trace, "transform_operation", None),
            "options": options,
            "planner_calls": counts.get("planner_calls", 0),
            "resolver_calls": counts.get("resolver_calls", 0),
            "retrieval_calls": counts.get("retrieval_calls", 0),
            "answer_generation_calls": counts.get("answer_generation_calls", 0),
            "transform_calls": counts.get("transform_calls", 0),
            "retry_count": 0,
            "source_alias_mapping_sha256": self._source_aliases.sha256,
            "adapter_error_category": adapter_error_category,
        }


def _count_delta(before: Mapping[str, int], after: Mapping[str, int]) -> dict[str, int]:
    return {key: max(0, after.get(key, 0) - before.get(key, 0)) for key in _CALL_FIELDS}
