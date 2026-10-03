"""Authoritative Slice 14 Level-C end-to-end warm campaign runner.

Requires explicit human authorization via
``confirm_execution_authorization=True``. Does not mutate the frozen suite
artifact's ``execution_authorized`` / ``authoritative_results_authorized``
gates; scientific ``perfsuite_`` / ``perfcfg_`` / ``gencfg_`` / ``ctxcfg_``
identities remain unchanged.

This module is the authoritative execution/persistence layer for the frozen
Level-C campaign. It does not authorize a campaign by its mere presence:
callers must pass the human latch, and real inference remains separately
authorized by human process.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import (
    BGE_RERANKER_MODEL_ID,
    QWEN3_EMBEDDING_MODEL_ID,
)
from offline_rag.evaluation.gold import load_gold_dataset
from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
from offline_rag.evaluation.performance_14.artifacts import write_run_artifacts
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceLevelCAttemptV1,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
    PerformanceRunAggregateV1,
    RunStatusV1,
    TelemetryAvailabilityV1,
)
from offline_rag.evaluation.performance_14.fixtures import stable_case_id
from offline_rag.evaluation.performance_14.identity import (
    compute_case_identity_hash,
    compute_run_identity_hash,
)
from offline_rag.evaluation.performance_14.level_c import (
    LevelCTimeline,
    PassiveLevelCGenerator,
    build_instrumented_orchestrator,
    derive_level_c_stage_stats,
    execute_level_c_attempt,
)
from offline_rag.evaluation.performance_14.paths import allocate_authoritative_run_dir
from offline_rag.evaluation.performance_14.preflight import (
    PreflightAccumulator,
    resolve_repo_root,
)
from offline_rag.evaluation.performance_14.preflight_14_level_c import (
    FREEZE_AUTHORITY_LEVEL_C,
    LOCKED_CTXCFG_LEVEL_C,
    LOCKED_GENCFG_LEVEL_C,
    LOCKED_PERFCFG_LEVEL_C,
    LOCKED_PERFSUITE_LEVEL_C,
    LevelCPreflightContext,
    build_level_c_runtime_environment,
    collect_runtime_api_key_secrets,
    load_level_c_hybrid_rerank_settings,
    load_level_c_runtime_settings,
    run_level_c_execution_preflight,
)
from offline_rag.evaluation.performance_14.preflight_14c import CORPUS_NAME_14C
from offline_rag.evaluation.performance_14.report import render_report_markdown
from offline_rag.evaluation.performance_14.suite_14_level_c import (
    EXECUTION_ORDER_CONTRACT_LEVEL_C,
    EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
    EXPECTED_TIMEOUT_SECONDS_LEVEL_C,
    GENERATION_MODEL_LEVEL_C,
    GENERATOR_PIN_STRENGTH_LEVEL_C,
    INSTRUMENTATION_AUTHORITY_LEVEL_C,
    MEASURED_REPETITIONS_LEVEL_C,
    QUERY_IDS_LEVEL_C,
    VARIANT_HYBRID_RERANK_CONTEXT_GENERATION,
    WARMUP_COUNT_LEVEL_C,
    build_suite_plan_level_c,
    case_specs_level_c,
    context_config_hash_level_c,
    effective_config_id_level_c,
    generation_config_hash_level_c,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    CORPUS_ID_14C,
    GOLD_RELATIVE_PATH_14C,
)
from offline_rag.generation.openai_compatible import (
    OpenAICompatibleGenerator,
    normalize_endpoint,
)
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.generation.protocol import Generator
from offline_rag.rerank.retrieve import HybridRerankRetriever

EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C = (
    "SLICE_14_LEVEL_C_AUTHORITATIVE_BENCHMARK_EXECUTION"
)

# Accepted Level-C preflight substrate commit (readiness layer authority).
PREFLIGHT_AUTHORITY_LEVEL_C = (
    "6327a9d018c252f339c342ddbc9e0c01fc998457"
)

# Empty dotenv source so preflight cannot re-interpret the real .env file.
_CAPTURED_ENV_DOTENV = Path(os.devnull)

LevelCPreflightFn = Callable[..., LevelCPreflightContext]
LevelCAttemptFn = Callable[..., PerformanceLevelCAttemptV1]


@dataclass
class AuthoritativeLevelCResult:
    run_id: str
    output_dir: Path
    run_status: RunStatusV1
    suite_id: str
    scientific_config_id: str
    manifest: PerformanceBenchmarkRunManifestV1
    aggregate: PerformanceRunAggregateV1
    cases: list[PerformanceBenchmarkCaseV1] = field(default_factory=list)
    preflight: PerformancePreflightRecordV1 | None = None
    run_label: str | None = None
    error: str | None = None
    diagnostic_only: bool = False
    authoritative: bool = True


@dataclass
class LevelCRuntimeBundle:
    """Persistent runtime objects for one authoritative Level-C campaign."""

    settings: AppSettings
    retriever: HybridRerankRetriever
    generator: Generator
    query_by_id: dict[str, str]
    orchestrator: GroundedAnswerOrchestrator
    timeline: LevelCTimeline
    generator_proxy: PassiveLevelCGenerator


LevelCRuntimeFactory = Callable[..., LevelCRuntimeBundle]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redact_runtime_secrets(
    text: str,
    *,
    secrets: Sequence[str],
) -> str:
    """Replace configured runtime API-key values with a redaction token."""
    redacted = text
    for secret in secrets:
        if secret and secret in redacted:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


def _format_exception(
    exc: BaseException,
    *,
    secrets: Sequence[str],
) -> str:
    return _redact_runtime_secrets(
        f"{type(exc).__name__}: {exc}",
        secrets=secrets,
    )


def _blob_contains_secret(blob: str, *, secrets: Sequence[str]) -> bool:
    return any(secret and secret in blob for secret in secrets)


def _assert_text_secret_free(
    text: str,
    *,
    secrets: Sequence[str],
    label: str,
) -> None:
    if _blob_contains_secret(text, secrets=secrets):
        raise Performance14Error(
            f"refusing to persist {label}: runtime API key material detected"
        )


def _assert_attempt_secret_free(
    attempt: PerformanceLevelCAttemptV1,
    *,
    secrets: Sequence[str],
) -> None:
    encoded = json.dumps(attempt.model_dump(mode="json"), sort_keys=True)
    if _blob_contains_secret(encoded, secrets=secrets):
        raise Performance14Error(
            "Level-C attempt evidence contained runtime API key material; "
            "refusing to persist unsafe attempt"
        )


def _assert_terminal_artifacts_secret_free(
    *,
    manifest: PerformanceBenchmarkRunManifestV1,
    aggregate: PerformanceRunAggregateV1,
    cases: Sequence[PerformanceBenchmarkCaseV1],
    report_markdown: str,
    preflight: PerformancePreflightRecordV1 | None,
    error: str | None,
    secrets: Sequence[str],
) -> None:
    if not secrets:
        return
    blobs = [
        ("manifest", json.dumps(manifest.model_dump(mode="json"), sort_keys=True)),
        ("aggregate", json.dumps(aggregate.model_dump(mode="json"), sort_keys=True)),
        ("report", report_markdown),
        ("error", error or ""),
    ]
    if preflight is not None:
        blobs.append(
            (
                "preflight",
                json.dumps(preflight.model_dump(mode="json"), sort_keys=True),
            )
        )
    for case in cases:
        blobs.append(
            (
                f"case:{case.case_id}",
                json.dumps(case.model_dump(mode="json"), sort_keys=True),
            )
        )
    for label, blob in blobs:
        _assert_text_secret_free(blob, secrets=secrets, label=label)


def _vram_availability_from_record(
    record: PerformancePreflightRecordV1 | None,
) -> TelemetryAvailabilityV1:
    if record is None or record.telemetry_vram is None:
        return "unavailable"
    return record.telemetry_vram


def _collect_runtime_secrets(
    repo_root: Path,
    *,
    runtime_env: Mapping[str, str],
) -> tuple[str, ...]:
    """Load settings transiently solely to collect API-key strings for redaction."""
    transient = load_level_c_runtime_settings(repo_root, runtime_env=runtime_env)
    return collect_runtime_api_key_secrets(transient)


def _build_query_map(repo_root: Path) -> dict[str, str]:
    loaded = load_gold_dataset(repo_root / GOLD_RELATIVE_PATH_14C)
    by_id = {case.id: case.query for case in loaded.cases}
    missing = [qid for qid in QUERY_IDS_LEVEL_C if qid not in by_id]
    if missing:
        raise Performance14Error(
            "frozen Level-C query ids missing from Gold population: "
            + ", ".join(missing)
        )
    return {qid: by_id[qid] for qid in QUERY_IDS_LEVEL_C}


def _assert_frozen_scientific_identities() -> None:
    plan = build_suite_plan_level_c()
    suite_id = plan.suite.suite_identity_hash
    if suite_id != LOCKED_PERFSUITE_LEVEL_C:
        raise Performance14Error(
            f"Level-C perfsuite_ drifted: expected {LOCKED_PERFSUITE_LEVEL_C}, "
            f"got {suite_id}"
        )
    scientific_config_id = effective_config_id_level_c()
    if scientific_config_id != LOCKED_PERFCFG_LEVEL_C:
        raise Performance14Error(
            f"Level-C perfcfg_ drifted: expected {LOCKED_PERFCFG_LEVEL_C}, "
            f"got {scientific_config_id}"
        )
    gencfg = generation_config_hash_level_c()
    if gencfg != LOCKED_GENCFG_LEVEL_C:
        raise Performance14Error(
            f"Level-C gencfg_ drifted: expected {LOCKED_GENCFG_LEVEL_C}, "
            f"got {gencfg}"
        )
    ctxcfg = context_config_hash_level_c()
    if ctxcfg != LOCKED_CTXCFG_LEVEL_C:
        raise Performance14Error(
            f"Level-C ctxcfg_ drifted: expected {LOCKED_CTXCFG_LEVEL_C}, "
            f"got {ctxcfg}"
        )


def _default_runtime_factory(
    *,
    repo_root: Path,
    runtime_env: Mapping[str, str],
) -> LevelCRuntimeBundle:
    secret_settings = load_level_c_runtime_settings(
        repo_root, runtime_env=runtime_env
    )
    rerank_settings = load_level_c_hybrid_rerank_settings(
        repo_root, runtime_env=runtime_env
    )
    # One persistent hybrid+rerank stack; HybridRerankRetriever owns HybridRetriever.
    retriever = HybridRerankRetriever(rerank_settings)
    generator = OpenAICompatibleGenerator(secret_settings)
    timeline = LevelCTimeline()
    orch, gen_proxy, _executor, _ret_delegate = build_instrumented_orchestrator(
        secret_settings,
        timeline=timeline,
        retriever=retriever,
        generator=generator,
    )
    return LevelCRuntimeBundle(
        settings=secret_settings,
        retriever=retriever,
        generator=generator,
        query_by_id=_build_query_map(repo_root),
        orchestrator=orch,
        timeline=timeline,
        generator_proxy=gen_proxy,
    )


def _close_runtime(
    bundle: LevelCRuntimeBundle | None,
    *,
    secrets: Sequence[str],
) -> list[str]:
    """Best-effort close of owned resources; never raises."""
    if bundle is None:
        return []
    close_errors: list[str] = []
    for label, owner in (
        ("generator", bundle.generator),
        ("retriever", bundle.retriever),
    ):
        close_fn = getattr(owner, "close", None)
        if not callable(close_fn):
            continue
        try:
            close_fn()
        except Exception as exc:  # noqa: BLE001 — close must not abort persistence
            close_errors.append(
                _redact_runtime_secrets(
                    f"{label}.close failed: {type(exc).__name__}: {exc}",
                    secrets=secrets,
                )
            )
    return close_errors


def _manifest_environment(
    *,
    preflight_status: str,
    provider_readiness: str,
    working_tree_state: str = "clean",
    failing_check: str | None = None,
) -> dict[str, str]:
    env: dict[str, str] = {
        "os": platform.system() or "unknown",
        "dry_run": "false",
        "evidence_class": "AUTHORITATIVE",
        "execution_authorization": EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C,
        "suite_freeze_authority": FREEZE_AUTHORITY_LEVEL_C,
        "level_c_instrumentation_authority": INSTRUMENTATION_AUTHORITY_LEVEL_C,
        "level_c_preflight_authority": PREFLIGHT_AUTHORITY_LEVEL_C,
        "gencfg": LOCKED_GENCFG_LEVEL_C,
        "ctxcfg": LOCKED_CTXCFG_LEVEL_C,
        "generator_pin_class": GENERATOR_PIN_STRENGTH_LEVEL_C,
        "generator_endpoint": normalize_endpoint(EXPECTED_GENERATION_ENDPOINT_LEVEL_C),
        "generator_timeout_seconds": str(EXPECTED_TIMEOUT_SECONDS_LEVEL_C),
        "generation_streaming": "false",
        "retrieval_recovery": "false",
        "provider_readiness_probe": provider_readiness,
        "preflight_status": preflight_status,
        "working_tree_state": working_tree_state,
        "execution_order_contract": EXECUTION_ORDER_CONTRACT_LEVEL_C,
        "harness_evidence": "level_c_attempt_traces_v1",
    }
    if failing_check:
        env["failing_check"] = failing_check
    return env


def _build_manifest(
    *,
    preflight: LevelCPreflightContext,
    run_nonce: str,
    run_label: str | None,
    scientific_config_id: str,
) -> PerformanceBenchmarkRunManifestV1:
    assert isinstance(preflight.machine_profile, PerformanceMachineProfileV1)
    plan = build_suite_plan_level_c()
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=preflight.suite_id,
        executing_sha=preflight.executing_sha,
        machine_profile_id=preflight.machine_profile_id,
        machine_profile=preflight.machine_profile,
        config_id=scientific_config_id,
        corpus_id=CORPUS_ID_14C,
        model_ids={
            "embedding": QWEN3_EMBEDDING_MODEL_ID,
            "reranker": BGE_RERANKER_MODEL_ID,
            "generator": GENERATION_MODEL_LEVEL_C,
        },
        warmup_policy=(
            f"warmup={plan.warmup_count};"
            f"order={EXECUTION_ORDER_CONTRACT_LEVEL_C}"
        ),
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=_manifest_environment(
            preflight_status=preflight.preflight_record.preflight_status,
            provider_readiness="passed",
            working_tree_state="clean",
        ),
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode="authoritative_14_level_c_e2e_warm",
        run_status=None,
        run_nonce=run_nonce,
        run_label=run_label,
    )
    return manifest.model_copy(
        update={"run_identity_hash": compute_run_identity_hash(manifest)}
    )


def _failed_preflight_manifest(
    *,
    suite_id: str,
    run_nonce: str,
    run_label: str | None,
    record: PerformancePreflightRecordV1,
    partial: PreflightAccumulator | None,
    scientific_config_id: str,
) -> PerformanceBenchmarkRunManifestV1:
    executing_sha = (
        (partial.executing_sha if partial is not None else None)
        or record.executing_sha
        or "unresolved"
    )
    machine_profile_id = (
        (partial.machine_profile_id if partial is not None else None)
        or record.machine_profile_id
        or "perfhost_unresolved"
    )
    machine_profile = partial.machine_profile if partial is not None else None
    plan = build_suite_plan_level_c()
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=suite_id,
        executing_sha=executing_sha,
        machine_profile_id=machine_profile_id,
        machine_profile=machine_profile,
        config_id=scientific_config_id,
        corpus_id=CORPUS_ID_14C,
        model_ids={
            "embedding": QWEN3_EMBEDDING_MODEL_ID,
            "reranker": BGE_RERANKER_MODEL_ID,
            "generator": GENERATION_MODEL_LEVEL_C,
        },
        warmup_policy=(
            f"warmup={plan.warmup_count};"
            f"order={EXECUTION_ORDER_CONTRACT_LEVEL_C}"
        ),
        repetition_counts={
            "measured": plan.measured_repetitions,
            "warmup": plan.warmup_count,
        },
        start_timestamp=_utc_now_iso(),
        environment=_manifest_environment(
            preflight_status="failed",
            provider_readiness="failed_or_not_passed",
            working_tree_state=record.working_tree_state,
            failing_check=record.failing_check,
        ),
        runtime_versions={"python": sys.version.split()[0]},
        execution_mode="authoritative_14_level_c_e2e_warm",
        run_status="failed_preflight",
        run_nonce=run_nonce,
        run_label=run_label,
    )
    return manifest.model_copy(
        update={"run_identity_hash": compute_run_identity_hash(manifest)}
    )


def _assert_execution_ready(preflight: LevelCPreflightContext) -> None:
    record = preflight.preflight_record
    if record.preflight_status != "passed":
        raise Performance14Error(
            "Level-C execution-time preflight did not pass: "
            f"preflight_status={record.preflight_status!r}"
        )
    if not preflight.provider_probe_performed:
        raise Performance14Error(
            "Level-C authoritative campaign requires provider_probe_performed=true"
        )
    if preflight.provider_probe_ok is not True:
        raise Performance14Error(
            "Level-C authoritative campaign requires provider_probe_ok=true"
        )
    if not preflight.execution_ready:
        raise Performance14Error(
            "Level-C authoritative campaign requires execution_ready=true"
        )


def _build_case_from_attempts(
    *,
    subject_identity: str,
    attempts: Sequence[PerformanceLevelCAttemptV1],
) -> PerformanceBenchmarkCaseV1:
    specs = {spec.subject_identity: spec for spec in case_specs_level_c()}
    spec = specs.get(subject_identity)
    if spec is None:
        raise Performance14Error(
            f"case membership mismatch: {subject_identity!r} not in frozen suite"
        )
    case_id = stable_case_id(spec)
    warmups = [a for a in attempts if a.is_warmup]
    measured = [a for a in attempts if not a.is_warmup]
    if (
        len(warmups) != WARMUP_COUNT_LEVEL_C
        or len(measured) != MEASURED_REPETITIONS_LEVEL_C
    ):
        case_status: str = "failed"
    else:
        case_status = "completed"
    resources = []
    for attempt in attempts:
        e2e = attempt.end_to_end_observation
        if e2e is not None and e2e.resource is not None:
            resources.append(e2e.resource)
    case = PerformanceBenchmarkCaseV1(
        case_id=case_id,
        case_kind=spec.case_kind,
        benchmark_level=spec.benchmark_level,
        stage_or_path=spec.stage_or_path,
        subject_identity=subject_identity,
        variant=VARIANT_HYBRID_RERANK_CONTEXT_GENERATION,
        cold_warm=spec.cold_warm,
        case_status=case_status,  # type: ignore[arg-type]
        warmup_count=len(warmups),
        warmup_observations=[],
        measured_observations=[],
        failures=[],
        resource_samples=resources,
        level_c_attempts=list(attempts),
    )
    derived = derive_level_c_stage_stats(list(attempts), "end_to_end")
    case_hash = compute_case_identity_hash(case)
    return case.model_copy(update={"derived": derived, "case_identity_hash": case_hash})


def _default_attempt_fn(
    *,
    orchestrator: GroundedAnswerOrchestrator,
    timeline: LevelCTimeline,
    generator_proxy: PassiveLevelCGenerator,
    query: str,
    subject_identity: str,
    attempt_index: int,
    is_warmup: bool,
) -> PerformanceLevelCAttemptV1:
    return execute_level_c_attempt(
        orchestrator,
        timeline,
        query=query,
        corpus_name=CORPUS_NAME_14C,
        subject_identity=subject_identity,
        attempt_index=attempt_index,
        is_warmup=is_warmup,
        generator_proxy=generator_proxy,
        capture_ram=True,
    )


@dataclass
class _ScheduleState:
    attempts_by_query: dict[str, list[PerformanceLevelCAttemptV1]] = field(
        default_factory=lambda: {qid: [] for qid in QUERY_IDS_LEVEL_C}
    )
    seen_keys: dict[str, set[tuple[bool, int]]] = field(
        default_factory=lambda: {qid: set() for qid in QUERY_IDS_LEVEL_C}
    )


def _record_scheduled_attempt(
    state: _ScheduleState,
    *,
    bundle: LevelCRuntimeBundle,
    attempt_fn: LevelCAttemptFn,
    query_id: str,
    is_warmup: bool,
    attempt_index: int,
    secrets: Sequence[str],
) -> None:
    query = bundle.query_by_id.get(query_id)
    if query is None:
        raise Performance14Error(
            f"frozen subject {query_id!r} missing from query map"
        )
    key = (is_warmup, attempt_index)
    if key in state.seen_keys[query_id]:
        raise Performance14Error(
            f"attempt-key collision for {query_id}: "
            f"is_warmup={is_warmup}, attempt_index={attempt_index}"
        )
    try:
        attempt = attempt_fn(
            orchestrator=bundle.orchestrator,
            timeline=bundle.timeline,
            generator_proxy=bundle.generator_proxy,
            query=query,
            subject_identity=query_id,
            attempt_index=attempt_index,
            is_warmup=is_warmup,
        )
    except Performance14Error as exc:
        raise Performance14Error(
            _redact_runtime_secrets(str(exc), secrets=secrets)
        ) from exc
    except Exception as exc:
        raise Performance14Error(
            _redact_runtime_secrets(
                "cannot construct validated PerformanceLevelCAttemptV1: "
                f"{type(exc).__name__}: {exc}",
                secrets=secrets,
            )
        ) from exc
    if not isinstance(attempt, PerformanceLevelCAttemptV1):
        raise Performance14Error(
            "cannot construct validated PerformanceLevelCAttemptV1: "
            f"got {type(attempt).__name__}"
        )
    if attempt.subject_identity != query_id:
        raise Performance14Error(
            "identity mismatch: attempt subject_identity "
            f"{attempt.subject_identity!r} != scheduled {query_id!r}"
        )
    if attempt.is_warmup != is_warmup or attempt.attempt_index != attempt_index:
        raise Performance14Error(
            "schedule invariant broken: attempt provenance "
            f"(is_warmup={attempt.is_warmup}, "
            f"attempt_index={attempt.attempt_index}) != "
            f"scheduled (is_warmup={is_warmup}, "
            f"attempt_index={attempt_index})"
        )
    # Refuse secret-bearing attempt evidence before it enters schedule state.
    _assert_attempt_secret_free(attempt, secrets=secrets)
    state.seen_keys[query_id].add(key)
    state.attempts_by_query[query_id].append(attempt)


def _cases_from_schedule_state(
    state: _ScheduleState,
) -> list[PerformanceBenchmarkCaseV1]:
    cases: list[PerformanceBenchmarkCaseV1] = []
    for query_id in QUERY_IDS_LEVEL_C:
        captured = state.attempts_by_query[query_id]
        if not captured:
            continue
        cases.append(
            _build_case_from_attempts(
                subject_identity=query_id,
                attempts=captured,
            )
        )
    return cases


def _run_frozen_schedule(
    *,
    bundle: LevelCRuntimeBundle,
    attempt_fn: LevelCAttemptFn,
    secrets: Sequence[str],
    state: _ScheduleState | None = None,
) -> list[PerformanceBenchmarkCaseV1]:
    """Execute warm-ups then measured round-robin; return five completed cases."""
    schedule = state if state is not None else _ScheduleState()

    # Warm-up phase: q1→q5, each attempt_index=0. No measured until all complete.
    for query_id in QUERY_IDS_LEVEL_C:
        _record_scheduled_attempt(
            schedule,
            bundle=bundle,
            attempt_fn=attempt_fn,
            query_id=query_id,
            is_warmup=True,
            attempt_index=0,
            secrets=secrets,
        )

    # Measured phase: five round-robin rounds q1→q5.
    for round_idx in range(MEASURED_REPETITIONS_LEVEL_C):
        for query_id in QUERY_IDS_LEVEL_C:
            _record_scheduled_attempt(
                schedule,
                bundle=bundle,
                attempt_fn=attempt_fn,
                query_id=query_id,
                is_warmup=False,
                attempt_index=round_idx,
                secrets=secrets,
            )

    return _cases_from_schedule_state(schedule)


def _persist_failed_preflight(
    *,
    suite_id: str,
    run_nonce: str,
    run_label: str | None,
    scientific_config_id: str,
    root: Path,
    record: PerformancePreflightRecordV1,
    partial: PreflightAccumulator | None,
    error: str,
    secrets: Sequence[str],
) -> AuthoritativeLevelCResult:
    sanitized_error = _redact_runtime_secrets(error, secrets=secrets)
    manifest = _failed_preflight_manifest(
        suite_id=suite_id,
        run_nonce=run_nonce,
        run_label=run_label,
        record=record,
        partial=partial,
        scientific_config_id=scientific_config_id,
    )
    run_id = manifest.run_identity_hash
    assert run_id is not None
    output_dir = allocate_authoritative_run_dir(
        suite_id=suite_id,
        run_id=run_id,
        repo_root=root,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    aggregate = build_run_aggregate(
        suite_id=suite_id,
        run_id=run_id,
        run_status="failed_preflight",
        benchmark_level="C",
        cases=[],
        diagnostic_only=False,
        authoritative=True,
        evidence_class="AUTHORITATIVE",
        vram_availability=_vram_availability_from_record(record),
    )
    report = render_report_markdown(
        run_id=run_id,
        manifest=manifest,
        aggregate=aggregate,
        cases=[],
        error=sanitized_error,
    )
    _assert_terminal_artifacts_secret_free(
        manifest=manifest,
        aggregate=aggregate,
        cases=[],
        report_markdown=report,
        preflight=record,
        error=sanitized_error,
        secrets=secrets,
    )
    write_run_artifacts(
        output_dir,
        manifest=manifest,
        aggregate=aggregate,
        cases=[],
        report_markdown=report,
        preflight=record,
    )
    return AuthoritativeLevelCResult(
        run_id=run_id,
        output_dir=output_dir,
        run_status="failed_preflight",
        suite_id=suite_id,
        scientific_config_id=scientific_config_id,
        manifest=manifest,
        aggregate=aggregate,
        cases=[],
        preflight=record,
        run_label=run_label,
        error=sanitized_error,
    )


def run_authoritative_14_level_c(
    *,
    confirm_execution_authorization: bool,
    run_label: str | None = None,
    repo_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
    preflight_fn: LevelCPreflightFn | None = None,
    runtime_factory: LevelCRuntimeFactory | None = None,
    attempt_fn: LevelCAttemptFn | None = None,
) -> AuthoritativeLevelCResult:
    """Execute the frozen Level-C suite and persist an authoritative terminal run.

    Refuses before any provider contact, inference, or output allocation when
    ``confirm_execution_authorization`` is False.
    """
    if not confirm_execution_authorization:
        raise Performance14Error(
            "refusing authoritative Level-C execution without "
            "confirm_execution_authorization=True "
            f"({EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C})"
        )

    _assert_frozen_scientific_identities()
    scientific_config_id = effective_config_id_level_c()
    suite_id = LOCKED_PERFSUITE_LEVEL_C
    run_nonce = uuid.uuid4().hex
    root = resolve_repo_root(repo_root)

    # Interpret .env exactly once; reuse the frozen mapping for preflight + runtime.
    runtime_env = build_level_c_runtime_environment(
        root, environ=environ, dotenv_path=dotenv_path
    )
    runtime_secrets = _collect_runtime_secrets(root, runtime_env=runtime_env)

    preflight_runner = preflight_fn or run_level_c_execution_preflight
    try:
        preflight = preflight_runner(
            repo_root=root,
            environ=runtime_env,
            # Prevent preflight from re-reading the real .env after capture.
            dotenv_path=_CAPTURED_ENV_DOTENV,
            provider_probe="require",
        )
    except Performance14Error as exc:
        record = getattr(exc, "preflight_record", None)
        partial = getattr(exc, "preflight_partial", None)
        if record is None:
            raise Performance14Error(
                _redact_runtime_secrets(str(exc), secrets=runtime_secrets)
            ) from exc
        return _persist_failed_preflight(
            suite_id=suite_id,
            run_nonce=run_nonce,
            run_label=run_label,
            scientific_config_id=scientific_config_id,
            root=root,
            record=record,
            partial=partial,
            error=str(exc),
            secrets=runtime_secrets,
        )

    try:
        _assert_execution_ready(preflight)
    except Performance14Error as exc:
        return _persist_failed_preflight(
            suite_id=suite_id,
            run_nonce=run_nonce,
            run_label=run_label,
            scientific_config_id=scientific_config_id,
            root=root,
            record=preflight.preflight_record,
            partial=None,
            error=str(exc),
            secrets=runtime_secrets,
        )

    if preflight.scientific_config_id != scientific_config_id:
        raise Performance14Error("preflight scientific_config_id diverged from lock")
    if preflight.suite_id != suite_id:
        raise Performance14Error("preflight suite_id diverged from lock")

    manifest = _build_manifest(
        preflight=preflight,
        run_nonce=run_nonce,
        run_label=run_label,
        scientific_config_id=scientific_config_id,
    )
    run_id = manifest.run_identity_hash
    assert run_id is not None
    output_dir = allocate_authoritative_run_dir(
        suite_id=suite_id,
        run_id=run_id,
        repo_root=root,
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    factory = runtime_factory or _default_runtime_factory
    execute = attempt_fn or _default_attempt_fn
    bundle: LevelCRuntimeBundle | None = None
    cases: list[PerformanceBenchmarkCaseV1] = []
    schedule_state = _ScheduleState()
    run_status: RunStatusV1 = "completed"
    error: str | None = None
    try:
        try:
            bundle = factory(repo_root=root, runtime_env=runtime_env)
        except Exception as exc:
            raise Performance14Error(
                _redact_runtime_secrets(
                    f"runtime_factory failed: {type(exc).__name__}: {exc}",
                    secrets=runtime_secrets,
                )
            ) from exc
        # No generation preparation request — lazy first-load belongs in warm-ups.
        cases = _run_frozen_schedule(
            bundle=bundle,
            attempt_fn=execute,
            secrets=runtime_secrets,
            state=schedule_state,
        )
        total_attempts = sum(len(case.level_c_attempts) for case in cases)
        if total_attempts != 30:
            raise Performance14Error(
                f"schedule invariant broken: expected 30 attempts, got {total_attempts}"
            )
        for case in cases:
            if len(case.level_c_attempts) != 6:
                raise Performance14Error(
                    f"case {case.case_id} expected 6 Level-C attempts; "
                    f"got {len(case.level_c_attempts)}"
                )
    except Exception as exc:  # noqa: BLE001 — preserve partial run
        run_status = "failed_during_execution"
        error = _format_exception(exc, secrets=runtime_secrets)
        cases = _cases_from_schedule_state(schedule_state)
    finally:
        close_errors = _close_runtime(bundle, secrets=runtime_secrets)
        if close_errors:
            run_status = "failed_during_execution"
            close_msg = "; ".join(close_errors)
            if error:
                error = f"{error}; resource_close_failure: {close_msg}"
            else:
                error = f"resource_close_failure: {close_msg}"

    sealed_manifest = manifest.model_copy(update={"run_status": run_status})
    aggregate = build_run_aggregate(
        suite_id=suite_id,
        run_id=run_id,
        run_status=run_status,
        benchmark_level="C",
        cases=cases,
        diagnostic_only=False,
        authoritative=True,
        evidence_class="AUTHORITATIVE",
        vram_availability=_vram_availability_from_record(preflight.preflight_record),
    )
    report = render_report_markdown(
        run_id=run_id,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        error=error,
    )
    _assert_terminal_artifacts_secret_free(
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        report_markdown=report,
        preflight=preflight.preflight_record,
        error=error,
        secrets=runtime_secrets,
    )
    write_run_artifacts(
        output_dir,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        report_markdown=report,
        preflight=preflight.preflight_record,
    )
    return AuthoritativeLevelCResult(
        run_id=run_id,
        output_dir=output_dir,
        run_status=run_status,
        suite_id=suite_id,
        scientific_config_id=scientific_config_id,
        manifest=sealed_manifest,
        aggregate=aggregate,
        cases=cases,
        preflight=preflight.preflight_record,
        run_label=run_label,
        error=error,
    )


def main(argv: list[str] | None = None) -> int:
    del argv  # reserved for future CLI flags
    result = run_authoritative_14_level_c(confirm_execution_authorization=True)
    print(
        f"status={result.run_status} run_id={result.run_id} output={result.output_dir}"
    )
    if result.error:
        print(f"error={result.error}")
    return 0 if result.run_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
