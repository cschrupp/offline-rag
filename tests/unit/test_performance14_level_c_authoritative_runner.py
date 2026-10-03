"""Unit tests for authoritative Level-C campaign runner (no real network)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import offline_rag.evaluation.performance_14.run_authoritative_14_level_c as runner_mod
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkObservationV1,
    PerformanceLevelCAttemptV1,
    PerformanceLevelCStageDispositionV1,
    PerformanceMachineProfileV1,
    PerformancePreflightRecordV1,
)
from offline_rag.evaluation.performance_14.level_c import (
    LevelCTimeline,
    PassiveLevelCGenerator,
    build_generation_telemetry,
)
from offline_rag.evaluation.performance_14.paths import allocate_authoritative_run_dir
from offline_rag.evaluation.performance_14.preflight_14_level_c import (
    LOCKED_CTXCFG_LEVEL_C,
    LOCKED_GENCFG_LEVEL_C,
    LOCKED_PERFCFG_LEVEL_C,
    LOCKED_PERFSUITE_LEVEL_C,
    LevelCPreflightContext,
    collect_runtime_api_key_secrets,
    load_level_c_runtime_settings,
)
from offline_rag.evaluation.performance_14.run_authoritative_14_level_c import (
    EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C,
    LevelCRuntimeBundle,
    run_authoritative_14_level_c,
)
from offline_rag.evaluation.performance_14.suite_14_level_c import (
    EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
    GENERATION_MODEL_LEVEL_C,
    GENERATOR_PIN_STRENGTH_LEVEL_C,
    QUERY_IDS_LEVEL_C,
    context_config_hash_level_c,
    effective_config_id_level_c,
    generation_config_hash_level_c,
    load_frozen_suite_artifact_level_c,
)
from offline_rag.generation.openai_compatible import normalize_endpoint
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_API_KEY = "test-level-c-runner-secret-key-do-not-leak-zzzz9999"
SECRET_AUTHORING = "test-authoring-secret-api-key-aaaa1111"
SECRET_RECOVERY = "test-recovery-secret-api-key-bbbb2222"
SECRET_JUDGE = "test-judge-secret-api-key-cccc3333"
ALL_SECRETS = (SECRET_API_KEY, SECRET_AUTHORING, SECRET_RECOVERY, SECRET_JUDGE)

Q1, Q2, Q3, Q4, Q5 = QUERY_IDS_LEVEL_C


def _disp(
    status: str, reason: str | None = None
) -> PerformanceLevelCStageDispositionV1:
    return PerformanceLevelCStageDispositionV1(status=status, reason=reason)  # type: ignore[arg-type]


def _obs(
    stage_id: str,
    status: str,
    *,
    duration: float | None = 0.1,
    is_warmup: bool = False,
    failure_reason: str | None = None,
    exclusion_reason: str | None = None,
) -> PerformanceBenchmarkObservationV1:
    return PerformanceBenchmarkObservationV1(
        observation_status=status,  # type: ignore[arg-type]
        stage_id=stage_id,
        duration_seconds=duration,
        is_warmup=is_warmup,
        failure_reason=failure_reason,
        exclusion_reason=exclusion_reason,
    )


def _full_dispositions(**overrides: PerformanceLevelCStageDispositionV1):
    base = {
        "context_assembly": _disp("valid"),
        "generation": _disp("valid"),
        "citation_validation": _disp("valid"),
        "end_to_end": _disp("valid"),
    }
    base.update(overrides)
    return base


def _answered_attempt(
    *,
    subject_identity: str,
    attempt_index: int,
    is_warmup: bool,
    duration: float = 0.2,
) -> PerformanceLevelCAttemptV1:
    return PerformanceLevelCAttemptV1(
        attempt_index=attempt_index,
        is_warmup=is_warmup,
        subject_identity=subject_identity,
        terminal_status="answered",
        generator_invoked=True,
        stage_dispositions=_full_dispositions(),
        context_assembly_observation=_obs(
            "context_assembly", "valid", duration=duration, is_warmup=is_warmup
        ),
        generation_observation=_obs(
            "generation", "valid", duration=duration, is_warmup=is_warmup
        ),
        citation_validation_observation=_obs(
            "citation_validation", "valid", duration=duration, is_warmup=is_warmup
        ),
        end_to_end_observation=_obs(
            "end_to_end", "valid", duration=duration * 4, is_warmup=is_warmup
        ),
        generation_telemetry=build_generation_telemetry(
            generator_invoked=True, usage={"completion_tokens": 7}
        ),
    )


def _attempt_with_terminal(
    *,
    subject_identity: str,
    attempt_index: int,
    is_warmup: bool,
    terminal: str,
) -> PerformanceLevelCAttemptV1:
    if terminal == "answered":
        return _answered_attempt(
            subject_identity=subject_identity,
            attempt_index=attempt_index,
            is_warmup=is_warmup,
        )
    if terminal == "generation_failed":
        return PerformanceLevelCAttemptV1(
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            subject_identity=subject_identity,
            terminal_status="generation_failed",
            generation_failure_reason="timeout",
            generator_invoked=True,
            stage_dispositions=_full_dispositions(
                generation=_disp("failed", "timeout"),
                citation_validation=_disp(
                    "not_applicable", "no_raw_generation_response"
                ),
            ),
            context_assembly_observation=_obs(
                "context_assembly", "valid", duration=0.1, is_warmup=is_warmup
            ),
            generation_observation=_obs(
                "generation",
                "failed",
                duration=0.2,
                is_warmup=is_warmup,
                failure_reason="timeout",
            ),
            citation_validation_observation=None,
            end_to_end_observation=_obs(
                "end_to_end", "valid", duration=1.0, is_warmup=is_warmup
            ),
            generation_telemetry=build_generation_telemetry(generator_invoked=True),
        )
    if terminal == "citation_invalid":
        return PerformanceLevelCAttemptV1(
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            subject_identity=subject_identity,
            terminal_status="citation_invalid",
            generator_invoked=True,
            stage_dispositions=_full_dispositions(
                citation_validation=_disp("failed", "citation_invalid"),
            ),
            context_assembly_observation=_obs(
                "context_assembly", "valid", duration=0.1, is_warmup=is_warmup
            ),
            generation_observation=_obs(
                "generation", "valid", duration=0.2, is_warmup=is_warmup
            ),
            citation_validation_observation=_obs(
                "citation_validation",
                "failed",
                duration=0.05,
                is_warmup=is_warmup,
                failure_reason="citation_invalid",
            ),
            end_to_end_observation=_obs(
                "end_to_end", "valid", duration=1.0, is_warmup=is_warmup
            ),
            generation_telemetry=build_generation_telemetry(
                generator_invoked=True, usage={"completion_tokens": 3}
            ),
        )
    if terminal == "insufficient_evidence":
        return PerformanceLevelCAttemptV1(
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            subject_identity=subject_identity,
            terminal_status="insufficient_evidence",
            abstention_reason="empty_context",
            generator_invoked=False,
            stage_dispositions={
                "context_assembly": _disp(
                    "not_applicable", "generator_request_not_finalized"
                ),
                "generation": _disp("not_applicable", "generator_not_invoked"),
                "citation_validation": _disp(
                    "not_applicable", "no_raw_generation_response"
                ),
                "end_to_end": _disp("valid"),
            },
            context_assembly_observation=None,
            generation_observation=None,
            citation_validation_observation=None,
            end_to_end_observation=_obs(
                "end_to_end", "valid", duration=0.5, is_warmup=is_warmup
            ),
            generation_telemetry=build_generation_telemetry(generator_invoked=False),
        )
    if terminal == "model_abstain":
        return PerformanceLevelCAttemptV1(
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            subject_identity=subject_identity,
            terminal_status="model_abstain",
            abstention_reason="model_abstain",
            generator_invoked=True,
            stage_dispositions=_full_dispositions(
                citation_validation=_disp(
                    "not_applicable", "model_abstain_no_citation_validation"
                ),
            ),
            context_assembly_observation=_obs(
                "context_assembly", "valid", duration=0.1, is_warmup=is_warmup
            ),
            generation_observation=_obs(
                "generation", "valid", duration=0.2, is_warmup=is_warmup
            ),
            citation_validation_observation=None,
            end_to_end_observation=_obs(
                "end_to_end", "valid", duration=1.0, is_warmup=is_warmup
            ),
            generation_telemetry=build_generation_telemetry(
                generator_invoked=True, usage={"completion_tokens": 2}
            ),
        )
    if terminal == "orchestration_failed":
        return PerformanceLevelCAttemptV1(
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            subject_identity=subject_identity,
            terminal_status="orchestration_failed",
            generation_failure_reason="GroundedAnswerError: boom",
            generator_invoked=False,
            stage_dispositions={
                "context_assembly": _disp("not_applicable", "orchestration_failed"),
                "generation": _disp("not_applicable", "orchestration_failed"),
                "citation_validation": _disp(
                    "not_applicable", "orchestration_failed"
                ),
                "end_to_end": _disp("failed", "GroundedAnswerError: boom"),
            },
            context_assembly_observation=None,
            generation_observation=None,
            citation_validation_observation=None,
            end_to_end_observation=_obs(
                "end_to_end",
                "failed",
                duration=None,
                is_warmup=is_warmup,
                failure_reason="GroundedAnswerError: boom",
            ),
            generation_telemetry=build_generation_telemetry(generator_invoked=False),
        )
    raise AssertionError(f"unknown terminal {terminal}")


def _machine_profile() -> PerformanceMachineProfileV1:
    return PerformanceMachineProfileV1(
        os_name="Linux",
        os_version="test",
        architecture="x86_64",
        cpu_model="test-cpu",
        physical_cores=4,
        logical_cores=8,
        system_ram_bytes=16 * 1024**3,
        python_version="3.12.0",
        offline_rag_commit_sha="a" * 40,
    )


def _preflight_record(
    *,
    status: str = "passed",
    telemetry_vram: str = "unavailable",
) -> PerformancePreflightRecordV1:
    return PerformancePreflightRecordV1(
        preflight_status=status,  # type: ignore[arg-type]
        working_tree_state="clean",
        disk_capacity_sufficient=True,
        disk_free_bytes=10**12,
        telemetry_ram="available",
        telemetry_vram=telemetry_vram,  # type: ignore[arg-type]
        checks=[],
        failing_check=None if status == "passed" else "provider_probe",
        executing_sha="b" * 40,
        machine_profile_id="perfhost_" + ("c" * 64),
        suite_id=LOCKED_PERFSUITE_LEVEL_C,
    )


def _fake_preflight(
    *,
    repo_root: Path,
    execution_ready: bool = True,
    provider_probe_performed: bool = True,
    provider_probe_ok: bool | None = True,
    preflight_status: str = "passed",
    api_key_in_settings: bool = False,
    telemetry_vram: str = "unavailable",
) -> LevelCPreflightContext:
    settings = AppSettings().model_copy(
        update={
            "generation": AppSettings().generation.model_copy(
                update={
                    "enabled": True,
                    "model": GENERATION_MODEL_LEVEL_C,
                    "approved_models": [GENERATION_MODEL_LEVEL_C],
                    "base_url": EXPECTED_GENERATION_ENDPOINT_LEVEL_C,
                    "approved_endpoints": [EXPECTED_GENERATION_ENDPOINT_LEVEL_C],
                    "timeout_seconds": 300,
                    "api_key": SECRET_API_KEY if api_key_in_settings else None,
                }
            )
        }
    )
    profile = _machine_profile()
    return LevelCPreflightContext(
        repo_root=repo_root,
        executing_sha="b" * 40,
        suite_id=LOCKED_PERFSUITE_LEVEL_C,
        scientific_config_id=LOCKED_PERFCFG_LEVEL_C,
        generation_config_id=LOCKED_GENCFG_LEVEL_C,
        context_config_id=LOCKED_CTXCFG_LEVEL_C,
        freeze_authority="f3ff6de00d90ebae24639d1569ef0f91b25b3c65",
        instrumentation_authority="d25f5f85bd20aff18873dfd26fc8926da9a6dade",
        machine_profile=profile,
        machine_profile_id="perfhost_" + ("c" * 64),
        results_parent=repo_root / "eval" / "results" / "performance_14",
        runtime_settings=settings,
        api_key_configured=True,
        provider_probe_performed=provider_probe_performed,
        provider_probe_ok=provider_probe_ok,
        execution_ready=execution_ready,
        preflight_record=_preflight_record(
            status=preflight_status, telemetry_vram=telemetry_vram
        ),
    )


class _Closeable:
    def __init__(self, *, raise_on_close: Exception | None = None) -> None:
        self.close_calls = 0
        self.raise_on_close = raise_on_close

    def close(self) -> None:
        self.close_calls += 1
        if self.raise_on_close is not None:
            raise self.raise_on_close


def _fake_runtime(
    *,
    query_by_id: dict[str, str] | None = None,
    generator_close_error: Exception | None = None,
    retriever_close_error: Exception | None = None,
) -> tuple[LevelCRuntimeBundle, _Closeable, _Closeable]:
    retriever = _Closeable(raise_on_close=retriever_close_error)
    generator = _Closeable(raise_on_close=generator_close_error)
    timeline = LevelCTimeline()
    orch = MagicMock(spec=GroundedAnswerOrchestrator)
    gen_proxy = MagicMock(spec=PassiveLevelCGenerator)
    gen_proxy.last_response = None
    gen_proxy.time_to_error_seconds = None
    bundle = LevelCRuntimeBundle(
        settings=AppSettings(),
        retriever=retriever,  # type: ignore[arg-type]
        generator=generator,  # type: ignore[arg-type]
        query_by_id=query_by_id
        or {qid: f"query text for {qid}" for qid in QUERY_IDS_LEVEL_C},
        orchestrator=orch,
        timeline=timeline,
        generator_proxy=gen_proxy,
    )
    return bundle, retriever, generator


def _inject_all_runtime_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure collect_runtime_api_key_secrets sees all four API-key fields."""
    original = load_level_c_runtime_settings

    def _load(*args: Any, **kwargs: Any) -> AppSettings:
        loaded = original(*args, **kwargs)
        return loaded.model_copy(
            update={
                "generation": loaded.generation.model_copy(
                    update={"api_key": SECRET_API_KEY}
                ),
                "authoring": loaded.authoring.model_copy(
                    update={"api_key": SECRET_AUTHORING}
                ),
                "retrieval_recovery": loaded.retrieval_recovery.model_copy(
                    update={
                        "rewriter": loaded.retrieval_recovery.rewriter.model_copy(
                            update={"api_key": SECRET_RECOVERY}
                        )
                    }
                ),
                "evaluation": loaded.evaluation.model_copy(
                    update={
                        "generation_semantic_judge": (
                            loaded.evaluation.generation_semantic_judge.model_copy(
                                update={"api_key": SECRET_JUDGE}
                            )
                        )
                    }
                ),
            }
        )

    monkeypatch.setattr(runner_mod, "load_level_c_runtime_settings", _load)


def _tracking_attempt_fn(
    *,
    log: list[tuple[str, bool, int]],
    orchestrator_ids: list[int] | None = None,
    terminals: dict[tuple[str, bool, int], str] | None = None,
    fail_structural_at: int | None = None,
    structural_message: str | None = None,
    unsafe_secret_attempt_at: int | None = None,
    generator_invocations: list[int] | None = None,
):
    call_count = {"n": 0}

    def _fn(**kwargs: Any) -> PerformanceLevelCAttemptV1:
        call_count["n"] += 1
        subject = kwargs["subject_identity"]
        is_warmup = kwargs["is_warmup"]
        attempt_index = kwargs["attempt_index"]
        log.append((subject, is_warmup, attempt_index))
        if orchestrator_ids is not None:
            orchestrator_ids.append(id(kwargs["orchestrator"]))
        if generator_invocations is not None:
            # Count every scheduled attempt as one generator-facing invocation slot
            # for the max-30 invariant (fake path; no real HTTP).
            generator_invocations.append(1)
        if fail_structural_at is not None and call_count["n"] == fail_structural_at:
            raise RuntimeError(
                structural_message or "injected structural harness failure"
            )
        if (
            unsafe_secret_attempt_at is not None
            and call_count["n"] == unsafe_secret_attempt_at
        ):
            attempt = _answered_attempt(
                subject_identity=subject,
                attempt_index=attempt_index,
                is_warmup=is_warmup,
            )
            return attempt.model_copy(
                update={
                    "terminal_status": "generation_failed",
                    "generation_failure_reason": (
                        f"provider leaked {SECRET_API_KEY} in diagnostics"
                    ),
                    "generator_invoked": True,
                    "stage_dispositions": _full_dispositions(
                        generation=_disp("failed", "timeout"),
                        citation_validation=_disp(
                            "not_applicable", "no_raw_generation_response"
                        ),
                    ),
                    "generation_observation": _obs(
                        "generation",
                        "failed",
                        duration=0.2,
                        is_warmup=is_warmup,
                        failure_reason="timeout",
                    ),
                    "citation_validation_observation": None,
                }
            )
        terminal = "answered"
        if terminals is not None:
            terminal = terminals.get((subject, is_warmup, attempt_index), "answered")
        return _attempt_with_terminal(
            subject_identity=subject,
            attempt_index=attempt_index,
            is_warmup=is_warmup,
            terminal=terminal,
        )

    return _fn


def _patch_allocate_to_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Confine authoritative run dirs to tmp (never real eval/results)."""
    results_root = tmp_path / "eval" / "results" / "performance_14"
    results_root.mkdir(parents=True, exist_ok=True)
    existing: set[Path] = set()

    def _allocate(
        *,
        suite_id: str,
        run_id: str,
        repo_root: Path | None = None,
    ) -> Path:
        del repo_root
        target = (results_root / suite_id / run_id).resolve()
        if target in existing or target.exists():
            raise Performance14Error(
                f"authoritative run directory already exists (immutable): {target}"
            )
        existing.add(target)
        return target

    monkeypatch.setattr(runner_mod, "allocate_authoritative_run_dir", _allocate)
    return results_root


def _run_fake_campaign(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    attempt_log: list[tuple[str, bool, int]] | None = None,
    orchestrator_ids: list[int] | None = None,
    terminals: dict[tuple[str, bool, int], str] | None = None,
    fail_structural_at: int | None = None,
    structural_message: str | None = None,
    unsafe_secret_attempt_at: int | None = None,
    generator_invocations: list[int] | None = None,
    preflight_fn=None,
    raise_on_preflight: Exception | None = None,
    telemetry_vram: str = "unavailable",
    environ: dict[str, str] | None = None,
    dotenv_path: Path | None = None,
    inject_secrets: bool = False,
    generator_close_error: Exception | None = None,
    retriever_close_error: Exception | None = None,
    factory_envs: list[dict[str, str]] | None = None,
):
    _patch_allocate_to_tmp(monkeypatch, tmp_path)
    if inject_secrets:
        _inject_all_runtime_secrets(monkeypatch)
    bundle, retriever, generator = _fake_runtime(
        generator_close_error=generator_close_error,
        retriever_close_error=retriever_close_error,
    )
    orch_id = id(bundle.orchestrator)
    log = attempt_log if attempt_log is not None else []
    orch_ids = orchestrator_ids if orchestrator_ids is not None else []
    attempt_fn = _tracking_attempt_fn(
        log=log,
        orchestrator_ids=orch_ids,
        terminals=terminals,
        fail_structural_at=fail_structural_at,
        structural_message=structural_message,
        unsafe_secret_attempt_at=unsafe_secret_attempt_at,
        generator_invocations=generator_invocations,
    )
    preflight_calls: list[dict[str, Any]] = []

    def _pf(**kwargs: Any) -> LevelCPreflightContext:
        preflight_calls.append(dict(kwargs))
        if raise_on_preflight is not None:
            raise raise_on_preflight
        if preflight_fn is not None:
            return preflight_fn(**kwargs)
        return _fake_preflight(repo_root=REPO_ROOT, telemetry_vram=telemetry_vram)

    runtime_builds: list[int] = []
    factory_env_log = factory_envs if factory_envs is not None else []

    def _factory(**kwargs: Any) -> LevelCRuntimeBundle:
        runtime_builds.append(1)
        factory_env_log.append(dict(kwargs["runtime_env"]))
        return bundle

    result = run_authoritative_14_level_c(
        confirm_execution_authorization=True,
        repo_root=REPO_ROOT,
        environ=environ if environ is not None else {},
        dotenv_path=dotenv_path if dotenv_path is not None else (tmp_path / "missing.env"),
        preflight_fn=_pf,
        runtime_factory=_factory,
        attempt_fn=attempt_fn,
    )
    return (
        result,
        log,
        preflight_calls,
        runtime_builds,
        retriever,
        generator,
        orch_id,
        orch_ids,
        factory_env_log,
    )


# ---------------------------------------------------------------------------
# 1. Authorization latch
# ---------------------------------------------------------------------------


def test_false_authorization_latch_fails_before_side_effects(tmp_path: Path) -> None:
    preflight_called = {"n": 0}
    runtime_called = {"n": 0}
    attempt_called = {"n": 0}

    def _pf(**kwargs: Any) -> LevelCPreflightContext:
        preflight_called["n"] += 1
        raise AssertionError("preflight must not run")

    def _factory(**kwargs: Any) -> LevelCRuntimeBundle:
        runtime_called["n"] += 1
        raise AssertionError("runtime must not build")

    def _attempt(**kwargs: Any) -> PerformanceLevelCAttemptV1:
        attempt_called["n"] += 1
        raise AssertionError("attempt must not run")

    with pytest.raises(
        Performance14Error, match=EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C
    ):
        run_authoritative_14_level_c(
            confirm_execution_authorization=False,
            repo_root=tmp_path,
            preflight_fn=_pf,
            runtime_factory=_factory,
            attempt_fn=_attempt,
        )
    assert preflight_called["n"] == 0
    assert runtime_called["n"] == 0
    assert attempt_called["n"] == 0
    results_root = tmp_path / "eval" / "results" / "performance_14"
    if results_root.exists():
        assert list(results_root.rglob("perfrun_*")) == []


# ---------------------------------------------------------------------------
# 2 / 23. Frozen scientific identities
# ---------------------------------------------------------------------------


def test_frozen_suite_perfcfg_gencfg_ctxcfg_unchanged() -> None:
    frozen = load_frozen_suite_artifact_level_c(repo_root=REPO_ROOT)
    assert frozen.suite_identity_hash == LOCKED_PERFSUITE_LEVEL_C
    assert frozen.effective_config_id == LOCKED_PERFCFG_LEVEL_C
    assert frozen.generation_config_hash == LOCKED_GENCFG_LEVEL_C
    assert frozen.context_config_hash == LOCKED_CTXCFG_LEVEL_C
    assert effective_config_id_level_c(repo_root=REPO_ROOT) == LOCKED_PERFCFG_LEVEL_C
    assert generation_config_hash_level_c() == LOCKED_GENCFG_LEVEL_C
    assert context_config_hash_level_c(repo_root=REPO_ROOT) == LOCKED_CTXCFG_LEVEL_C
    assert QUERY_IDS_LEVEL_C == (
        "draft_08f83eaef198495d92ff557eda974bf4",
        "draft_127ac342012d47fc9720a0c13a577550",
        "draft_2083433ad52e4e00ad4214d3fec27464",
        "draft_29389bdab2f84345b596e45fcf2e2bcc",
        "draft_296be0251d6f4ad2baadedfb506eba4b",
    )


# ---------------------------------------------------------------------------
# 3–5. Execution-time preflight
# ---------------------------------------------------------------------------


def test_execution_time_preflight_required_with_provider_probe_require(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _log, preflight_calls, runtime_builds, *_ = _run_fake_campaign(
        tmp_path, monkeypatch
    )
    assert len(preflight_calls) == 1
    assert preflight_calls[0]["provider_probe"] == "require"
    assert result.run_status == "completed"
    assert runtime_builds == [1]


def test_preflight_failure_causes_zero_query_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_allocate_to_tmp(monkeypatch, tmp_path)
    record = _preflight_record(status="failed")
    exc = Performance14Error("provider probe failed")
    exc.preflight_record = record  # type: ignore[attr-defined]
    exc.preflight_partial = None  # type: ignore[attr-defined]

    attempt_log: list[tuple[str, bool, int]] = []
    runtime_builds: list[int] = []

    def _pf(**kwargs: Any) -> LevelCPreflightContext:
        raise exc

    def _factory(**kwargs: Any) -> LevelCRuntimeBundle:
        runtime_builds.append(1)
        raise AssertionError("runtime must not build after failed preflight")

    def _attempt(**kwargs: Any) -> PerformanceLevelCAttemptV1:
        attempt_log.append(("x", False, 0))
        raise AssertionError("attempts must not run")

    result = run_authoritative_14_level_c(
        confirm_execution_authorization=True,
        repo_root=REPO_ROOT,
        environ={},
        dotenv_path=tmp_path / "missing.env",
        preflight_fn=_pf,
        runtime_factory=_factory,
        attempt_fn=_attempt,
    )
    assert result.run_status == "failed_preflight"
    assert attempt_log == []
    assert runtime_builds == []
    assert result.cases == []
    assert (result.output_dir / "preflight.json").is_file()
    assert not (result.output_dir / "cases").exists() or list(
        (result.output_dir / "cases").iterdir()
    ) == []


def test_not_execution_ready_persists_failed_preflight_zero_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _pf(**kwargs: Any) -> LevelCPreflightContext:
        return _fake_preflight(
            repo_root=kwargs["repo_root"],
            execution_ready=False,
            provider_probe_performed=True,
            provider_probe_ok=True,
        )

    result, log, *_rest = _run_fake_campaign(
        tmp_path, monkeypatch, preflight_fn=_pf
    )
    assert result.run_status == "failed_preflight"
    assert log == []
    assert result.cases == []


# ---------------------------------------------------------------------------
# 6–17. Persistent orchestrator + frozen schedule
# ---------------------------------------------------------------------------


def test_one_persistent_orchestrator_and_frozen_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log: list[tuple[str, bool, int]] = []
    gens: list[int] = []
    orch_ids: list[int] = []
    result, log, _pf, runtime_builds, _retriever, _generator, orch_id, orch_ids, _ = (
        _run_fake_campaign(
            tmp_path,
            monkeypatch,
            attempt_log=log,
            orchestrator_ids=orch_ids,
            generator_invocations=gens,
        )
    )
    assert result.run_status == "completed"
    assert runtime_builds == [1]
    assert len(log) == 30
    warmups = [entry for entry in log if entry[1] is True]
    measured = [entry for entry in log if entry[1] is False]
    assert len(warmups) == 5
    assert len(measured) == 25
    assert [entry[0] for entry in warmups] == list(QUERY_IDS_LEVEL_C)
    assert all(entry[2] == 0 for entry in warmups)
    # All warm-ups precede all measurements.
    first_measured_idx = next(i for i, e in enumerate(log) if e[1] is False)
    assert all(e[1] is True for e in log[:first_measured_idx])
    assert all(e[1] is False for e in log[first_measured_idx:])
    # Measured order: five q1→q5 rounds.
    expected_measured = [
        (qid, False, round_idx)
        for round_idx in range(5)
        for qid in QUERY_IDS_LEVEL_C
    ]
    assert measured == expected_measured
    assert all(entry[2] in {0, 1, 2, 3, 4} for entry in measured)
    assert len(result.cases) == 5
    for case in result.cases:
        assert len(case.level_c_attempts) == 6
        wu = [a for a in case.level_c_attempts if a.is_warmup]
        md = [a for a in case.level_c_attempts if not a.is_warmup]
        assert len(wu) == 1 and wu[0].attempt_index == 0
        assert sorted(a.attempt_index for a in md) == [0, 1, 2, 3, 4]
    assert sum(len(c.level_c_attempts) for c in result.cases) == 30
    assert len(gens) <= 30
    assert len(gens) == 30  # no hidden 31st preparation generation
    assert len(orch_ids) == 30
    assert len(set(orch_ids)) == 1
    assert orch_ids[0] == orch_id


# ---------------------------------------------------------------------------
# 18–22. Representable terminal outcomes continue the schedule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "terminal",
    [
        "generation_failed",
        "citation_invalid",
        "insufficient_evidence",
        "model_abstain",
        "orchestration_failed",
    ],
)
def test_representable_terminal_recorded_and_schedule_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, terminal: str
) -> None:
    terminals = {(Q3, False, 2): terminal}
    result, log, *_ = _run_fake_campaign(
        tmp_path, monkeypatch, terminals=terminals
    )
    assert result.run_status == "completed"
    assert len(log) == 30
    found = None
    for case in result.cases:
        if case.subject_identity == Q3:
            for attempt in case.level_c_attempts:
                if not attempt.is_warmup and attempt.attempt_index == 2:
                    found = attempt
    assert found is not None
    assert found.terminal_status == terminal


# ---------------------------------------------------------------------------
# 23–26. Structural failure + resource close
# ---------------------------------------------------------------------------


def test_harness_structural_failure_produces_failed_run_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, log, _pf, _rb, retriever, generator, *_rest = _run_fake_campaign(
        tmp_path, monkeypatch, fail_structural_at=8
    )
    assert result.run_status == "failed_during_execution"
    assert result.error is not None
    assert "structural harness failure" in result.error
    # 7 successful attempts preserved before structural failure on 8th.
    preserved = sum(len(c.level_c_attempts) for c in result.cases)
    assert preserved == 7
    assert len(log) == 8  # failure raised during 8th call after append
    assert retriever.close_calls == 1
    assert generator.close_calls == 1


def test_resources_close_exactly_once_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _log, _pf, _rb, retriever, generator, *_rest = _run_fake_campaign(
        tmp_path, monkeypatch
    )
    assert result.run_status == "completed"
    assert retriever.close_calls == 1
    assert generator.close_calls == 1


# ---------------------------------------------------------------------------
# 27–29. Aggregate semantics
# ---------------------------------------------------------------------------


def test_authoritative_aggregate_uses_level_c_stages_and_warmup_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(tmp_path, monkeypatch)
    agg = result.aggregate
    assert agg.benchmark_level == "C"
    assert agg.diagnostic_only is False
    assert agg.authoritative is True
    assert agg.evidence_class == "AUTHORITATIVE"
    stage_ids = {item.stage_or_path for item in agg.by_stage_or_path}
    assert stage_ids == {
        "context_assembly",
        "generation",
        "citation_validation",
        "end_to_end",
    }
    e2e = next(
        item for item in agg.by_stage_or_path if item.stage_or_path == "end_to_end"
    )
    assert e2e.stats.warmup_count == 5
    assert e2e.stats.n == 25
    assert e2e.stats.valid_count == 25
    assert e2e.stats.failure_count == 0
    assert agg.overall is not None
    assert agg.overall.n == 25
    assert agg.overall.warmup_count == 5


def test_failed_na_excluded_accounting_remains_correct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    terminals = {
        (Q1, False, 0): "generation_failed",
        (Q2, False, 0): "insufficient_evidence",
    }
    result, *_ = _run_fake_campaign(tmp_path, monkeypatch, terminals=terminals)
    gen = next(
        item for item in result.aggregate.by_stage_or_path if item.stage_or_path == "generation"
    )
    # 25 measured: 1 failed (generation_failed), 1 N/A (insufficient_evidence),
    # rest valid answered (23) — wait Q2 insufficient has generation N/A.
    assert gen.stats.failure_count == 1
    assert gen.stats.not_applicable_count == 1
    assert gen.stats.valid_count == 23
    assert gen.stats.warmup_count == 5


# ---------------------------------------------------------------------------
# 30–37. Manifest provenance + secret hygiene
# ---------------------------------------------------------------------------


def test_manifest_provenance_and_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(tmp_path, monkeypatch)
    env = result.manifest.environment
    assert result.manifest.model_ids["generator"] == GENERATION_MODEL_LEVEL_C
    assert env["generator_pin_class"] == GENERATOR_PIN_STRENGTH_LEVEL_C
    assert env["generator_endpoint"] == normalize_endpoint(
        EXPECTED_GENERATION_ENDPOINT_LEVEL_C
    )
    assert env["generator_timeout_seconds"] == "300"
    assert env["generation_streaming"] == "false"
    assert env["retrieval_recovery"] == "false"
    assert env["evidence_class"] == "AUTHORITATIVE"
    assert env["execution_authorization"] == EXECUTION_AUTHORIZATION_STATEMENT_LEVEL_C
    assert env["gencfg"] == LOCKED_GENCFG_LEVEL_C
    assert env["ctxcfg"] == LOCKED_CTXCFG_LEVEL_C
    assert env["provider_readiness_probe"] == "passed"
    assert "weight" not in json.dumps(result.manifest.model_dump(mode="json")).lower()
    blobs = [
        json.dumps(result.manifest.model_dump(mode="json")),
        json.dumps(result.aggregate.model_dump(mode="json")),
        (result.output_dir / "report.md").read_text(encoding="utf-8"),
        repr(result),
    ]
    for case in result.cases:
        blobs.append(json.dumps(case.model_dump(mode="json")))
    for blob in blobs:
        assert SECRET_API_KEY not in blob


# ---------------------------------------------------------------------------
# 38–41. Immutable persistence
# ---------------------------------------------------------------------------


def test_immutable_allocation_and_artifact_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(tmp_path, monkeypatch)
    assert result.output_dir.name.startswith("perfrun_")
    assert (result.output_dir / "run_manifest.json").is_file()
    assert (result.output_dir / "aggregate.json").is_file()
    assert (result.output_dir / "preflight.json").is_file()
    assert (result.output_dir / "report.md").is_file()
    case_files = sorted((result.output_dir / "cases").glob("*.json"))
    assert len(case_files) == 5
    # Patched allocator refuses overwrite; also prove production allocator does.
    with pytest.raises(Performance14Error, match="already exists"):
        runner_mod.allocate_authoritative_run_dir(
            suite_id=result.suite_id,
            run_id=result.run_id,
            repo_root=REPO_ROOT,
        )
    # Production path allocator against a fabricated existing dir under tmp layout.
    synthetic_repo = tmp_path / "synth_repo"
    suite_dir = (
        synthetic_repo
        / "eval"
        / "results"
        / "performance_14"
        / result.suite_id
        / result.run_id
    )
    suite_dir.mkdir(parents=True)
    with pytest.raises(Performance14Error, match="already exists"):
        allocate_authoritative_run_dir(
            suite_id=result.suite_id,
            run_id=result.run_id,
            repo_root=synthetic_repo,
        )


def test_aggregate_and_report_deterministic_from_fake_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r1, *_ = _run_fake_campaign(tmp_path / "a", monkeypatch)
    # Re-bind allocator for second campaign under a distinct tmp tree.
    r2, *_ = _run_fake_campaign(tmp_path / "b", monkeypatch)
    assert r1.aggregate.overall.model_dump() == r2.aggregate.overall.model_dump()
    assert r1.aggregate.by_stage_or_path == r2.aggregate.by_stage_or_path
    # Report presentation differs by run_id; stage section shape is stable.
    assert "## Level-C stages" in (r1.output_dir / "report.md").read_text(
        encoding="utf-8"
    )
    assert "TTFT: `UNEVALUABLE`" in (r1.output_dir / "report.md").read_text(
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 42. No real network in tests (hooks only)
# ---------------------------------------------------------------------------


def test_no_real_network_hooks_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If production preflight/runtime were used, this would touch provider/indexes.
    # Injected hooks prove the unit path never reaches those surfaces.
    result, log, preflight_calls, runtime_builds, *_ = _run_fake_campaign(
        tmp_path, monkeypatch
    )
    assert preflight_calls and runtime_builds == [1]
    assert len(log) == 30
    assert result.authoritative is True
    assert result.diagnostic_only is False


# ---------------------------------------------------------------------------
# F-LC-R1 — runner-level secret hygiene
# ---------------------------------------------------------------------------


def _assert_no_secrets_in_result(result) -> None:
    blobs = [
        json.dumps(result.manifest.model_dump(mode="json")),
        json.dumps(result.aggregate.model_dump(mode="json")),
        (result.output_dir / "report.md").read_text(encoding="utf-8"),
        result.error or "",
        repr(result),
    ]
    if result.preflight is not None:
        blobs.append(json.dumps(result.preflight.model_dump(mode="json")))
    for case in result.cases:
        blobs.append(json.dumps(case.model_dump(mode="json")))
    for blob in blobs:
        for secret in ALL_SECRETS:
            assert secret not in blob


def test_structural_exception_with_generation_api_key_is_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        inject_secrets=True,
        fail_structural_at=3,
        structural_message=f"provider exploded with {SECRET_API_KEY}",
    )
    assert result.run_status == "failed_during_execution"
    assert result.error is not None
    assert SECRET_API_KEY not in result.error
    assert "<redacted>" in result.error
    report = (result.output_dir / "report.md").read_text(encoding="utf-8")
    assert SECRET_API_KEY not in report
    _assert_no_secrets_in_result(result)


def test_unsafe_secret_bearing_attempt_rejected_before_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        inject_secrets=True,
        unsafe_secret_attempt_at=4,
    )
    assert result.run_status == "failed_during_execution"
    assert result.error is not None
    assert "refusing to persist unsafe attempt" in result.error
    preserved = sum(len(c.level_c_attempts) for c in result.cases)
    assert preserved == 3
    _assert_no_secrets_in_result(result)


def test_authoring_recovery_judge_api_keys_are_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Prove collector sees all four secrets under the runner load path.
    _inject_all_runtime_secrets(monkeypatch)
    settings = runner_mod.load_level_c_runtime_settings(
        REPO_ROOT, runtime_env={}, dotenv_path=tmp_path / "missing.env"
    )
    assert collect_runtime_api_key_secrets(settings) == ALL_SECRETS

    result, *_ = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        inject_secrets=True,
        fail_structural_at=2,
        structural_message=(
            f"multi-secret boom {SECRET_AUTHORING} {SECRET_RECOVERY} {SECRET_JUDGE}"
        ),
    )
    assert result.error is not None
    for secret in (SECRET_AUTHORING, SECRET_RECOVERY, SECRET_JUDGE):
        assert secret not in result.error
    report = (result.output_dir / "report.md").read_text(encoding="utf-8")
    for secret in ALL_SECRETS:
        assert secret not in report
    _assert_no_secrets_in_result(result)


# ---------------------------------------------------------------------------
# F-LC-R2 — single captured runtime environment
# ---------------------------------------------------------------------------


def test_preflight_uses_captured_env_without_rereading_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("# initially no timeout pin\n", encoding="utf-8")
    factory_envs: list[dict[str, str]] = []

    def _pf(**kwargs: Any) -> LevelCPreflightContext:
        # Mutate .env after runner capture; re-read would pick this up.
        dotenv.write_text("OFFLINE_RAG_LLM_TIMEOUT_SECONDS=300\n", encoding="utf-8")
        assert kwargs["dotenv_path"] == Path(os.devnull)
        assert "OFFLINE_RAG_LLM_TIMEOUT_SECONDS" not in kwargs["environ"]
        return _fake_preflight(repo_root=REPO_ROOT)

    result, _log, preflight_calls, _rb, *_rest = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        preflight_fn=_pf,
        dotenv_path=dotenv,
        environ={},
        factory_envs=factory_envs,
    )
    assert result.run_status == "completed"
    assert len(preflight_calls) == 1
    assert preflight_calls[0]["dotenv_path"] == Path(os.devnull)
    assert "OFFLINE_RAG_LLM_TIMEOUT_SECONDS" not in preflight_calls[0]["environ"]
    assert len(factory_envs) == 1
    assert factory_envs[0] == preflight_calls[0]["environ"]
    assert "OFFLINE_RAG_LLM_TIMEOUT_SECONDS=300" in dotenv.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# F-LC-R3 — VRAM availability propagation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("vram", ["unavailable", "available"])
def test_vram_availability_propagates_from_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vram: str
) -> None:
    result, *_ = _run_fake_campaign(tmp_path, monkeypatch, telemetry_vram=vram)
    assert result.aggregate.vram_availability == vram
    assert result.preflight is not None
    assert result.preflight.telemetry_vram == vram


# ---------------------------------------------------------------------------
# F-LC-R4 — close failures must not destroy terminal evidence
# ---------------------------------------------------------------------------


def test_generator_close_failure_still_closes_retriever_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _log, _pf, _rb, retriever, generator, *_rest = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        generator_close_error=RuntimeError(f"close leaked {SECRET_API_KEY}"),
        inject_secrets=True,
    )
    assert result.run_status == "failed_during_execution"
    assert generator.close_calls == 1
    assert retriever.close_calls == 1
    assert len(result.cases) == 5
    assert sum(len(c.level_c_attempts) for c in result.cases) == 30
    assert (result.output_dir / "aggregate.json").is_file()
    assert (result.output_dir / "report.md").is_file()
    assert result.error is not None
    assert "resource_close_failure" in result.error
    assert SECRET_API_KEY not in result.error
    assert "<redacted>" in result.error


def test_retriever_close_failure_seals_failed_during_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, _log, _pf, _rb, retriever, generator, *_rest = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        retriever_close_error=RuntimeError("retriever close boom"),
    )
    assert result.run_status == "failed_during_execution"
    assert generator.close_calls == 1
    assert retriever.close_calls == 1
    assert sum(len(c.level_c_attempts) for c in result.cases) == 30
    assert result.error is not None
    assert "resource_close_failure" in result.error
    assert (result.output_dir / "cases").is_dir()


def test_close_error_does_not_replace_campaign_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, *_ = _run_fake_campaign(
        tmp_path,
        monkeypatch,
        fail_structural_at=5,
        structural_message="original campaign structural failure",
        generator_close_error=RuntimeError("close secondary failure"),
    )
    assert result.run_status == "failed_during_execution"
    assert result.error is not None
    assert "original campaign structural failure" in result.error
    assert "resource_close_failure" in result.error
    assert "close secondary failure" in result.error
    assert sum(len(c.level_c_attempts) for c in result.cases) == 4
