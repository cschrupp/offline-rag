"""Unit tests for Slice 14C harness rework — semantic timing + quality coverage.

Does not execute an authoritative campaign.
"""

from __future__ import annotations

import pytest

from offline_rag.evaluation.gold import ChunkJudgment, GoldCase
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkCaseV1,
    PerformanceBenchmarkObservationV1,
    PerformanceCaseQualityV1,
    PerformancePathSampleV1,
    PerformanceResourceObservationV1,
)
from offline_rag.evaluation.performance_14.evidence_14c import (
    PATH_BASELINE_HYBRID_TOTAL,
    PATH_TREATMENT_HYBRID_COMPONENT,
    PATH_TREATMENT_RERANKER,
    PATH_TREATMENT_TOTAL,
    RESOURCE_SCOPE_RETRIEVAL_PATH,
    STAGE_END_TO_END_FORBIDDEN_FOR_14C,
    STAGE_FUSION,
    STAGE_RERANK,
    assert_not_end_to_end_stage,
    assert_paired_quality_coverage,
    assert_semantic_not_full_path,
    macro_quality_by_variant,
    path_latency_rollups,
    quality_from_ranking,
    resource_summary_by_variant,
    semantic_observations_from_hybrid_metadata,
    semantic_observations_from_hybrid_rerank_metadata,
)
from offline_rag.evaluation.performance_14.fixtures import (
    VARIANT_HYBRID,
    VARIANT_HYBRID_RERANK,
)
from offline_rag.evaluation.performance_14.suite_14c import (
    QUERY_IDS_14C,
    effective_config_id_14c,
)

LOCKED_PERFCFG = (
    "perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d"
)
LOCKED_PERFSUITE = (
    "perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba"
)


def _resource(
    *,
    rss: int = 1000,
    is_warmup: bool = False,
    stage_id: str = RESOURCE_SCOPE_RETRIEVAL_PATH,
) -> PerformanceResourceObservationV1:
    return PerformanceResourceObservationV1(
        stage_id=stage_id,
        ram_availability="available",
        ram_rss_bytes_before=rss,
        ram_rss_bytes_peak=None,
        vram_availability="unavailable",
        is_warmup=is_warmup,
        note="RSS sampled immediately before retrieval-path invocation",
    )


def test_scientific_ids_unchanged_by_evidence_module() -> None:
    assert effective_config_id_14c() == LOCKED_PERFCFG
    from offline_rag.evaluation.performance_14.suite_14c import build_suite_plan_14c

    plan = build_suite_plan_14c()
    assert plan.suite.suite_identity_hash == LOCKED_PERFSUITE


def test_assert_semantic_not_full_path_rejects_equal_durations() -> None:
    with pytest.raises(Performance14Error, match="equals total path"):
        assert_semantic_not_full_path(
            semantic_stage_id=STAGE_FUSION,
            semantic_duration=1.0,
            total_duration=1.0,
        )


def test_assert_semantic_not_full_path_accepts_strict_envelope() -> None:
    assert_semantic_not_full_path(
        semantic_stage_id=STAGE_FUSION,
        semantic_duration=0.05,
        total_duration=5.18,
    )
    assert_semantic_not_full_path(
        semantic_stage_id=STAGE_RERANK,
        semantic_duration=2.0,
        total_duration=13.06,
    )


def test_f002a_retrieval_path_total_is_not_end_to_end() -> None:
    """Property 1: retrieval-path totals must not use stage_id=end_to_end."""
    with pytest.raises(Performance14Error, match="must not use stage_id=end_to_end"):
        assert_not_end_to_end_stage(STAGE_END_TO_END_FORBIDDEN_FOR_14C)

    hybrid_meta = {
        "latency_seconds": {
            "dense": 2.0,
            "lexical": 2.5,
            "fusion": 0.05,
            "total": 4.6,
        }
    }
    observations, path_samples = semantic_observations_from_hybrid_metadata(
        hybrid_meta, is_warmup=False, resource=_resource()
    )
    assert all(obs.stage_id != "end_to_end" for obs in observations)
    assert {obs.stage_id for obs in observations} == {STAGE_FUSION}
    assert all(sample.path != "end_to_end" for sample in path_samples)
    assert {sample.path for sample in path_samples} == {PATH_BASELINE_HYBRID_TOTAL}

    rerank_meta = {
        "latency_seconds": {
            "hybrid": 4.6,
            "pair_build": 0.1,
            "rerank_infer": 7.0,
            "sort": 0.05,
            "rerank": 7.05,
            "total": 11.75,
        }
    }
    observations, path_samples = semantic_observations_from_hybrid_rerank_metadata(
        rerank_meta, is_warmup=False, resource=_resource(rss=2000)
    )
    assert all(obs.stage_id != "end_to_end" for obs in observations)
    assert {obs.stage_id for obs in observations} == {STAGE_RERANK}
    assert "end_to_end" not in {sample.path for sample in path_samples}


def test_hybrid_semantic_obs_are_not_full_path_wrap() -> None:
    metadata = {
        "latency_seconds": {
            "dense": 2.0,
            "lexical": 2.5,
            "fusion": 0.05,
            "total": 4.6,
        }
    }
    observations, path_samples = semantic_observations_from_hybrid_metadata(
        metadata, is_warmup=False, resource=_resource()
    )
    fusion = observations[0]
    total = path_samples[0]
    assert fusion.duration_seconds == pytest.approx(0.05)
    assert total.duration_seconds == pytest.approx(4.6)
    assert fusion.duration_seconds != total.duration_seconds


def test_rerank_semantic_obs_are_not_full_path_wrap() -> None:
    metadata = {
        "latency_seconds": {
            "hybrid": 4.6,
            "pair_build": 0.1,
            "rerank_infer": 7.0,
            "sort": 0.05,
            "rerank": 7.05,
            "total": 11.75,
        }
    }
    observations, path_samples = semantic_observations_from_hybrid_rerank_metadata(
        metadata, is_warmup=False, resource=_resource(rss=2000)
    )
    rerank = observations[0]
    by_path = {sample.path: sample for sample in path_samples}
    assert rerank.duration_seconds == pytest.approx(7.05)
    assert by_path[PATH_TREATMENT_TOTAL].duration_seconds == pytest.approx(11.75)
    assert rerank.duration_seconds != by_path[PATH_TREATMENT_TOTAL].duration_seconds


def test_refuse_integer_ms_only_metadata() -> None:
    with pytest.raises(Performance14Error, match="latency_seconds"):
        semantic_observations_from_hybrid_metadata(
            {"latency_ms": {"fusion": 50, "total": 5000}},
            is_warmup=False,
            resource=None,
        )


def test_quality_from_ranking_reuses_frozen_ir_semantics() -> None:
    gold = GoldCase(
        id="q1",
        query="what is torque",
        judgments=(
            ChunkJudgment(chunk_id="c_relevant", relevance=2),
            ChunkJudgment(chunk_id="c_other", relevance=1),
        ),
    )
    quality = quality_from_ranking(
        gold,
        ["c_relevant", "x", "y", "z", "c_other"],
        requested_depth=10,
    )
    assert isinstance(quality, PerformanceCaseQualityV1)
    assert quality.quality_eligible is True
    # Two positives; top-1 hits one → recall@1 = 0.5; hit@1 = 1.0; MRR = 1.0
    assert quality.recall_at_1 == pytest.approx(0.5)
    assert quality.hit_rate_at_1 == pytest.approx(1.0)
    assert quality.mrr == pytest.approx(1.0)
    assert quality.ndcg_at_1 is not None


def _eligible_quality() -> PerformanceCaseQualityV1:
    return PerformanceCaseQualityV1(
        quality_eligible=True,
        requested_depth=10,
        returned_count=10,
        recall_at_1=0.5,
        recall_at_5=1.0,
        recall_at_10=1.0,
        precision_at_1=1.0,
        precision_at_5=0.4,
        precision_at_10=0.2,
        hit_rate_at_1=1.0,
        hit_rate_at_5=1.0,
        hit_rate_at_10=1.0,
        mrr=1.0,
        ndcg_at_1=1.0,
        ndcg_at_5=0.9,
        ndcg_at_10=0.85,
    )


def _case(
    *,
    qid: str,
    variant: str,
    ranked: list[str] | None,
    quality: PerformanceCaseQualityV1 | None,
    rss_measured: int = 1000,
    rss_warmup: int | None = None,
    path_samples: list[PerformancePathSampleV1] | None = None,
    semantic_s: float = 0.1,
) -> PerformanceBenchmarkCaseV1:
    stage = STAGE_FUSION if variant == VARIANT_HYBRID else STAGE_RERANK
    measured = [
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id=stage,
            duration_seconds=semantic_s,
            is_warmup=False,
            resource=_resource(rss=rss_measured, is_warmup=False),
        )
    ]
    resources = [_resource(rss=rss_measured, is_warmup=False)]
    if rss_warmup is not None:
        resources.insert(0, _resource(rss=rss_warmup, is_warmup=True))
    if path_samples is None:
        if variant == VARIANT_HYBRID:
            path_samples = [
                PerformancePathSampleV1(
                    path=PATH_BASELINE_HYBRID_TOTAL,
                    duration_seconds=4.0,
                    is_warmup=False,
                )
            ]
        else:
            path_samples = [
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_HYBRID_COMPONENT,
                    duration_seconds=4.1,
                    is_warmup=False,
                ),
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_RERANKER,
                    duration_seconds=semantic_s,
                    is_warmup=False,
                ),
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_TOTAL,
                    duration_seconds=12.0,
                    is_warmup=False,
                ),
            ]
    return PerformanceBenchmarkCaseV1(
        case_id=f"perfcase_{qid}_{variant}",
        case_kind="retrieval_path",
        benchmark_level="B",
        stage_or_path=stage,
        subject_identity=qid,
        variant=variant,
        cold_warm="warm",
        measured_observations=measured,
        resource_samples=resources,
        ranked_chunk_ids=ranked,
        quality=quality,
        path_samples=path_samples,
    )


def test_assert_paired_quality_coverage_requires_22x2() -> None:
    quality = _eligible_quality()
    cases = []
    for qid in QUERY_IDS_14C:
        for variant in (VARIANT_HYBRID, VARIANT_HYBRID_RERANK):
            cases.append(
                _case(
                    qid=qid,
                    variant=variant,
                    ranked=[f"chunk_{qid}"],
                    quality=quality,
                )
            )
    assert len(cases) == 44
    assert_paired_quality_coverage(cases, expected_query_ids=QUERY_IDS_14C)


def test_assert_paired_quality_coverage_fails_when_cell_missing() -> None:
    quality = _eligible_quality()
    cases = [
        _case(
            qid=QUERY_IDS_14C[0],
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=quality,
        )
    ]
    with pytest.raises(Performance14Error, match="quality evidence incomplete"):
        assert_paired_quality_coverage(cases, expected_query_ids=QUERY_IDS_14C[:2])


def test_assert_paired_quality_coverage_fails_without_ranked_ids() -> None:
    cases = [
        _case(
            qid=QUERY_IDS_14C[0],
            variant=VARIANT_HYBRID,
            ranked=None,
            quality=_eligible_quality(),
        )
    ]
    with pytest.raises(Performance14Error, match="quality evidence missing"):
        assert_paired_quality_coverage(
            cases, expected_query_ids=[QUERY_IDS_14C[0]]
        )


def test_f002b_path_rollups_exclude_warmup_samples() -> None:
    """Property 2: warm-up path samples must not enter measured path stats."""
    cases = [
        _case(
            qid="qa",
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=_eligible_quality(),
            path_samples=[
                PerformancePathSampleV1(
                    path=PATH_BASELINE_HYBRID_TOTAL,
                    duration_seconds=99.0,
                    is_warmup=True,
                ),
                PerformancePathSampleV1(
                    path=PATH_BASELINE_HYBRID_TOTAL,
                    duration_seconds=4.0,
                    is_warmup=False,
                ),
            ],
        )
    ]
    by_path = {item.path: item for item in path_latency_rollups(cases)}
    stats = by_path[PATH_BASELINE_HYBRID_TOTAL].stats
    assert stats.n == 1
    assert stats.warmup_count == 1
    assert stats.p50 == pytest.approx(4.0)
    assert stats.p50 != pytest.approx(99.0)


def test_f002c_baseline_and_treatment_hybrid_paths_remain_separate() -> None:
    """Property 3: baseline hybrid total ≠ treatment hybrid component pool."""
    cases = [
        _case(
            qid="qa",
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=_eligible_quality(),
            path_samples=[
                PerformancePathSampleV1(
                    path=PATH_BASELINE_HYBRID_TOTAL,
                    duration_seconds=5.0,
                    is_warmup=False,
                )
            ],
        ),
        _case(
            qid="qa",
            variant=VARIANT_HYBRID_RERANK,
            ranked=["c2"],
            quality=_eligible_quality(),
            semantic_s=7.0,
            path_samples=[
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_HYBRID_COMPONENT,
                    duration_seconds=8.0,
                    is_warmup=False,
                ),
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_RERANKER,
                    duration_seconds=7.0,
                    is_warmup=False,
                ),
                PerformancePathSampleV1(
                    path=PATH_TREATMENT_TOTAL,
                    duration_seconds=16.0,
                    is_warmup=False,
                ),
            ],
        ),
    ]
    by_path = {item.path: item for item in path_latency_rollups(cases)}
    assert by_path[PATH_BASELINE_HYBRID_TOTAL].stats.p50 == pytest.approx(5.0)
    assert by_path[PATH_TREATMENT_HYBRID_COMPONENT].stats.p50 == pytest.approx(8.0)
    assert by_path[PATH_TREATMENT_RERANKER].stats.p50 == pytest.approx(7.0)
    assert by_path[PATH_TREATMENT_TOTAL].stats.p50 == pytest.approx(16.0)
    # No pooled hybrid_latency population exists.
    assert "hybrid_latency" not in by_path


def test_f003_ram_summary_excludes_warmup_samples() -> None:
    """Property 5: authoritative RAM summary uses measured samples only."""
    cases = [
        _case(
            qid="qa",
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=_eligible_quality(),
            rss_measured=2000,
            rss_warmup=999999,
        ),
        _case(
            qid="qa",
            variant=VARIANT_HYBRID_RERANK,
            ranked=["c2"],
            quality=_eligible_quality(),
            rss_measured=3000,
            rss_warmup=888888,
        ),
    ]
    by_var = {item.variant: item for item in resource_summary_by_variant(cases)}
    assert by_var[VARIANT_HYBRID].sample_count == 1
    assert by_var[VARIANT_HYBRID].ram_rss_bytes_p50 == 2000
    assert by_var[VARIANT_HYBRID].ram_rss_bytes_max == 2000
    assert by_var[VARIANT_HYBRID_RERANK].ram_rss_bytes_p50 == 3000


def test_f003_resource_scope_is_retrieval_path_not_semantic_stage() -> None:
    """Property 6: pre-retrieval RAM is path-scoped, not fusion/rerank."""
    sample = _resource(rss=1500, is_warmup=False)
    assert sample.stage_id == RESOURCE_SCOPE_RETRIEVAL_PATH
    assert sample.stage_id not in {STAGE_FUSION, STAGE_RERANK, "end_to_end"}
    assert sample.note is not None
    assert "retrieval-path" in sample.note


def test_macro_quality_and_resource_and_path_rollups() -> None:
    quality = _eligible_quality()
    cases = [
        _case(
            qid="qa",
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=quality,
            rss_measured=1000,
        ),
        _case(
            qid="qa",
            variant=VARIANT_HYBRID_RERANK,
            ranked=["c2"],
            quality=quality,
            rss_measured=2000,
            semantic_s=7.0,
        ),
    ]
    qualities = macro_quality_by_variant(cases)
    assert len(qualities) == 2
    assert qualities[0].mrr == pytest.approx(1.0)

    resources = resource_summary_by_variant(cases)
    by_var = {item.variant: item for item in resources}
    assert by_var[VARIANT_HYBRID].ram_rss_bytes_p50 == 1000

    paths = path_latency_rollups(cases)
    by_path = {item.path: item for item in paths}
    assert by_path[PATH_BASELINE_HYBRID_TOTAL].stats.p50 == pytest.approx(4.0)
    assert by_path[PATH_TREATMENT_TOTAL].stats.p50 == pytest.approx(12.0)


def test_f002d_rerank_semantic_includes_final_candidate_construction() -> None:
    """Property 4: rerank envelope ends when candidate list is available.

    Inspect production timing keys: ``rerank`` must be present and is distinct
    from infer+sort alone when construction work exists. We verify the
    retrieve implementation times the envelope past candidate construction.
    """
    import inspect

    from offline_rag.rerank import retrieve as rerank_mod

    source = inspect.getsource(rerank_mod.HybridRerankRetriever.retrieve)
    assert "t_rerank_envelope" in source
    assert "final HybridRerankCandidate list" in source or (
        "rerank_semantic_s = time.perf_counter() - t_rerank_envelope" in source
    )
    # Envelope starts at infer and stops after candidates are built — not
    # infer+sort arithmetic alone.
    assert "rerank_semantic_s = rerank_infer_s + sort_s" not in source


def test_authoritative_report_includes_quality_and_ram() -> None:
    from offline_rag.evaluation.performance_14.aggregate import build_run_aggregate
    from offline_rag.evaluation.performance_14.contracts import (
        PerformanceBenchmarkRunManifestV1,
    )
    from offline_rag.evaluation.performance_14.run_authoritative_14c import (
        _render_authoritative_report,
    )

    quality = _eligible_quality()
    cases = [
        _case(
            qid="qa",
            variant=VARIANT_HYBRID,
            ranked=["c1"],
            quality=quality,
            rss_measured=1500,
        ),
        _case(
            qid="qa",
            variant=VARIANT_HYBRID_RERANK,
            ranked=["c2"],
            quality=quality,
            rss_measured=2500,
            semantic_s=8.0,
        ),
    ]
    aggregate = build_run_aggregate(
        suite_id=LOCKED_PERFSUITE,
        run_id="perfrun_" + ("d" * 64),
        run_status="completed",
        benchmark_level="B",
        cases=cases,
        diagnostic_only=False,
        authoritative=True,
        evidence_class="AUTHORITATIVE",
        path_latency=path_latency_rollups(cases),
        quality_by_variant=macro_quality_by_variant(cases),
        resource_by_variant=resource_summary_by_variant(cases),
        vram_availability="unavailable",
    )
    # Variant totals come from path samples, not end_to_end observations.
    assert all(
        obs.stage_id != "end_to_end"
        for case in cases
        for obs in case.measured_observations
    )
    manifest = PerformanceBenchmarkRunManifestV1(
        suite_id=LOCKED_PERFSUITE,
        executing_sha="deadbeef",
        machine_profile_id="perfhost_test",
        config_id=LOCKED_PERFCFG,
        corpus_id="corpus_test",
        warmup_policy="warmup=2",
        repetition_counts={"measured": 10, "warmup": 2},
        start_timestamp="2026-01-01T00:00:00Z",
        environment={"dry_run": "false"},
        runtime_versions={"python": "3.12"},
        execution_mode="authoritative_14c_quality_vs_cost",
        run_nonce="abc",
        run_identity_hash="perfrun_" + ("d" * 64),
        run_status="completed",
    )
    report = _render_authoritative_report(
        run_id=manifest.run_identity_hash or "x",
        manifest=manifest,
        aggregate=aggregate,
        cases=cases,
    )
    assert "Quality by variant" in report
    assert "Recall@1/5/10" in report
    assert "Resource summary (RAM)" in report
    assert "VRAM: `unavailable`" in report
