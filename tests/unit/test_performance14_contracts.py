"""Slice 14A unit tests — contracts, identity, stats, timing, resources, hooks."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from offline_rag.evaluation.performance_14 import (
    DEFAULT_INSTRUMENTER,
    DESIGN_AUTHORITY_SHA_14,
    SEMANTIC_STAGE_ENVELOPES_V1,
    PassiveStageInstrumenter,
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceBenchmarkRunManifestV1,
    PerformanceBenchmarkSuiteV1,
    PerformanceResourceObservationV1,
    capture_machine_profile_with_id,
    capture_resource_observation,
    compute_case_identity_hash,
    compute_config_identity_hash,
    compute_run_identity_hash,
    compute_suite_identity_hash,
    derive_latency_stats,
    linear_percentile,
    measure_stage,
    observe_stage,
    stage_envelope,
    timed_call,
    validate_stage_id,
)


def test_design_authority_pin() -> None:
    assert DESIGN_AUTHORITY_SHA_14.startswith("89a395ae")


def test_stage_envelopes_normative() -> None:
    assert stage_envelope("embed") == "embedding batch submitted → vectors returned"
    assert (
        stage_envelope("end_to_end")
        == "CLI/service query entry → accepted terminal result"
    )
    assert set(SEMANTIC_STAGE_ENVELOPES_V1) == {
        "document_load",
        "parse",
        "chunk",
        "embed",
        "dense_index_write",
        "lexical_index_write",
        "dense_retrieve",
        "lexical_retrieve",
        "fusion",
        "rerank",
        "context_assembly",
        "generation",
        "citation_validation",
        "end_to_end",
    }
    with pytest.raises(Performance14Error):
        validate_stage_id("not_a_stage")


def test_suite_identity_stable_and_excludes_results() -> None:
    suite = PerformanceBenchmarkSuiteV1(
        benchmark_level="B",
        population_identity="pop_test",
        variants=["hybrid", "hybrid_rerank"],
        case_ids=["c2", "c1"],
    )
    h1 = compute_suite_identity_hash(suite)
    h2 = compute_suite_identity_hash(suite)
    assert h1 == h2
    assert h1.startswith("perfsuite_")
    # Membership order must not affect identity (canonical sort).
    suite_reordered = PerformanceBenchmarkSuiteV1(
        benchmark_level="B",
        population_identity="pop_test",
        variants=["hybrid_rerank", "hybrid"],
        case_ids=["c1", "c2"],
    )
    assert compute_suite_identity_hash(suite_reordered) == h1


def test_case_identity_excludes_observations() -> None:
    base = PerformanceBenchmarkCaseV1(
        case_id="case_1",
        case_kind="pipeline_query",
        benchmark_level="B",
        stage_or_path="dense_retrieve",
        subject_identity="q_001",
        variant="hybrid",
        cold_warm="warm",
    )
    h1 = compute_case_identity_hash(base)
    with_obs = base.model_copy(
        update={
            "measured_observations": [
                PerformanceBenchmarkObservationV1(
                    observation_status="valid",
                    stage_id="dense_retrieve",
                    duration_seconds=0.01,
                )
            ]
        }
    )
    assert compute_case_identity_hash(with_obs) == h1
    assert h1.startswith("perfcase_")


def test_run_identity_requires_nonce_and_differs_on_nonce() -> None:
    shared = {
        "suite_id": "perfsuite_abc",
        "executing_sha": "deadbeef",
        "machine_profile_id": "perfhost_abc",
        "config_id": "perfcfg_abc",
        "corpus_id": "corpus_abc",
        "model_ids": {"embedding": "emb_v1"},
        "warmup_policy": "warmup=2",
        "repetition_counts": {"measured": 10},
        "start_timestamp": "2026-09-30T00:00:00Z",
        "environment": {"os": "linux"},
        "runtime_versions": {"python": "3.12"},
        "execution_mode": "warm",
    }
    m1 = PerformanceBenchmarkRunManifestV1(**shared, run_nonce="n1")
    m2 = PerformanceBenchmarkRunManifestV1(**shared, run_nonce="n2")
    with pytest.raises(ValueError, match="run_nonce"):
        compute_run_identity_hash(
            PerformanceBenchmarkRunManifestV1(**shared, run_nonce=None)
        )
    h1 = compute_run_identity_hash(m1)
    h2 = compute_run_identity_hash(m2)
    assert h1.startswith("perfrun_")
    assert h1 != h2


def test_run_identity_excludes_terminal_run_status() -> None:
    shared = {
        "suite_id": "perfsuite_abc",
        "executing_sha": "deadbeef",
        "machine_profile_id": "perfhost_abc",
        "config_id": "perfcfg_abc",
        "corpus_id": "corpus_abc",
        "model_ids": {"embedding": "emb_v1"},
        "warmup_policy": "warmup=2",
        "repetition_counts": {"measured": 10},
        "start_timestamp": "2026-09-30T00:00:00Z",
        "environment": {"os": "linux"},
        "runtime_versions": {"python": "3.12"},
        "execution_mode": "warm",
        "run_nonce": "stable-nonce",
    }
    base = PerformanceBenchmarkRunManifestV1(**shared, run_status=None)
    completed = PerformanceBenchmarkRunManifestV1(**shared, run_status="completed")
    failed = PerformanceBenchmarkRunManifestV1(
        **shared, run_status="failed_during_execution"
    )
    h0 = compute_run_identity_hash(base)
    assert h0 == compute_run_identity_hash(completed)
    assert h0 == compute_run_identity_hash(failed)


def test_config_identity_prefix() -> None:
    assert compute_config_identity_hash({"a": 1, "b": 2}).startswith("perfcfg_")
    assert compute_config_identity_hash({"b": 2, "a": 1}) == compute_config_identity_hash(
        {"a": 1, "b": 2}
    )


def test_canonical_json_fails_closed_on_unsupported_values() -> None:
    with pytest.raises(Performance14Error, match="unsupported identity value"):
        compute_config_identity_hash({"bad": {1, 2, 3}})

    class Weird:
        def __str__(self) -> str:
            return "nope"

    with pytest.raises(Performance14Error, match="unsupported identity value"):
        compute_config_identity_hash({"bad": Weird()})


def test_linear_percentile_semantics() -> None:
    samples = [1.0, 2.0, 3.0, 4.0]
    assert linear_percentile(samples, 0) == 1.0
    assert linear_percentile(samples, 100) == 4.0
    assert linear_percentile(samples, 50) == 2.5
    with pytest.raises(Performance14Error):
        linear_percentile([], 50)


def test_derive_latency_stats_separates_warmup_failures_exclusions() -> None:
    obs = [
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id="parse",
            duration_seconds=1.0,
            is_warmup=True,
        ),
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id="parse",
            duration_seconds=2.0,
        ),
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id="parse",
            duration_seconds=4.0,
        ),
        PerformanceBenchmarkObservationV1(
            observation_status="failed",
            stage_id="parse",
            failure_reason="timeout",
        ),
        PerformanceBenchmarkObservationV1(
            observation_status="excluded_instrumentation_error",
            stage_id="parse",
            exclusion_reason="clock_skew",
        ),
    ]
    stats = derive_latency_stats(obs)
    assert stats.valid_count == 2
    assert stats.n == 2
    assert stats.attempted_count == 4  # 2 valid + 1 fail + 1 exclusion
    assert stats.min == 2.0
    assert stats.max == 4.0
    assert stats.p50 == 3.0
    assert stats.failure_count == 1
    assert stats.instrumentation_exclusion_count == 1
    assert stats.warmup_count == 1


def test_resource_observation_never_infers_zero_when_unavailable() -> None:
    with pytest.raises(ValidationError):
        PerformanceResourceObservationV1(
            stage_id="embed",
            ram_availability="unavailable",
            ram_rss_bytes_before=0,
            vram_availability="unavailable",
        )
    sample = capture_resource_observation("embed")
    assert sample.vram_availability in {"unavailable", "unevaluable", "available"}
    if sample.vram_availability != "available":
        assert sample.vram_used_bytes_before is None
    if sample.ram_availability == "available":
        assert sample.ram_rss_bytes_before is not None
        assert sample.ram_rss_bytes_peak is None


def test_machine_profile_capture() -> None:
    profile, host_id = capture_machine_profile_with_id(
        offline_rag_commit_sha="89a395ae4df7aff23c2da2c8c44fd6fe405459a6"
    )
    assert profile.python_version
    assert profile.os_name
    assert profile.logical_cores is None or profile.logical_cores >= 1
    # Physical cores may be observed or unavailable; never invent a fake value.
    assert profile.physical_cores is None or profile.physical_cores >= 1
    assert host_id.startswith("perfhost_")


def test_physical_cores_from_topology_pairs() -> None:
    from offline_rag.evaluation.performance_14.machine import (
        _physical_cores_from_cpuinfo,
    )

    # Two sockets × two cores; SMT duplicates share (physical id, core id).
    cpuinfo = """\
processor	: 0
physical id	: 0
core id		: 0

processor	: 1
physical id	: 0
core id		: 0

processor	: 2
physical id	: 0
core id		: 1

processor	: 3
physical id	: 0
core id		: 1

processor	: 4
physical id	: 1
core id		: 0

processor	: 5
physical id	: 1
core id		: 0

processor	: 6
physical id	: 1
core id		: 1

processor	: 7
physical id	: 1
core id		: 1
"""
    assert _physical_cores_from_cpuinfo(cpuinfo) == 4


def test_physical_cores_cpu_cores_without_package_identity_is_unavailable() -> None:
    from offline_rag.evaluation.performance_14.machine import (
        _physical_cores_from_cpuinfo,
    )

    # "cpu cores" alone is cores-per-package; without package identity → None.
    cpuinfo = """\
processor	: 0
cpu cores	: 8
model name	: Example CPU

processor	: 1
cpu cores	: 8
model name	: Example CPU
"""
    assert _physical_cores_from_cpuinfo(cpuinfo) is None


def test_physical_cores_unreadable_topology_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from offline_rag.evaluation.performance_14 import machine as machine_mod

    monkeypatch.setattr(machine_mod.platform, "system", lambda: "Linux")
    real_open = open

    def _open_cpuinfo(path: object, *args: object, **kwargs: object) -> object:
        if str(path) == "/proc/cpuinfo":
            raise OSError("cpuinfo unavailable")
        return real_open(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("builtins.open", _open_cpuinfo)
    assert machine_mod._physical_cores() is None


def test_measure_stage_uses_monotonic_duration() -> None:
    with measure_stage("chunk") as result:
        time.sleep(0.01)
    assert result["duration_seconds"] >= 0.01


def test_timed_call_preserves_value_and_exception() -> None:
    value, sample = timed_call("fusion", lambda: 42)
    assert value == 42
    assert sample.stage_id == "fusion"
    assert sample.duration_seconds >= 0.0

    def boom() -> None:
        raise RuntimeError("preserve me")

    with pytest.raises(RuntimeError, match="preserve me"):
        timed_call("fusion", boom)


def test_passive_instrumenter_disabled_is_noop() -> None:
    DEFAULT_INSTRUMENTER.enabled = False
    DEFAULT_INSTRUMENTER.clear()
    assert observe_stage("rerank", lambda: "ok") == "ok"
    assert DEFAULT_INSTRUMENTER.samples == []

    enabled = PassiveStageInstrumenter(enabled=True)
    assert enabled.observe("rerank", lambda: "x") == "x"
    assert len(enabled.samples) == 1
    assert enabled.samples[0].stage_id == "rerank"
