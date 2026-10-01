"""Quality evidence, semantic timing decomposition, and resource rollups for 14C.

Preserves frozen ``perfsuite_`` / ``perfcfg_``. Does not execute campaigns.

Retrieval-path totals are ``PerformancePathSampleV1`` records — never the locked
Level-C ``end_to_end`` semantic stage.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from offline_rag.evaluation.gold import GoldCase
from offline_rag.evaluation.metrics import macro_average, score_ranking
from offline_rag.evaluation.performance_14.contracts import (
    Performance14Error,
    PerformanceBenchmarkObservationV1,
    PerformanceCaseQualityV1,
    PerformancePathLatencyV1,
    PerformancePathSampleV1,
    PerformanceResourceObservationV1,
    PerformanceVariantQualityV1,
    PerformanceVariantResourceV1,
)
from offline_rag.evaluation.performance_14.fixtures import (
    VARIANT_HYBRID,
    VARIANT_HYBRID_RERANK,
)
from offline_rag.evaluation.performance_14.statistics import (
    derive_latency_stats,
    linear_percentile,
)
from offline_rag.evaluation.performance_14.timing import validate_stage_id

# Locked semantic envelopes (docs/milestone7_performance_ui.md §8.2).
STAGE_FUSION = "fusion"
STAGE_RERANK = "rerank"
# Locked Level-C stage — must never be used for Level-B retrieval-path totals.
STAGE_END_TO_END_FORBIDDEN_FOR_14C = "end_to_end"

# Retrieval-path sample identities (not semantic stage_ids).
PATH_BASELINE_HYBRID_TOTAL = "baseline_hybrid_total_retrieval_path"
PATH_TREATMENT_HYBRID_COMPONENT = "treatment_hybrid_component"
PATH_TREATMENT_RERANKER = "treatment_reranker_latency"
PATH_TREATMENT_TOTAL = "treatment_total_retrieval_path"

RESOURCE_SCOPE_RETRIEVAL_PATH = "retrieval_path"
RESOURCE_NOTE_PRE_PATH = (
    "RSS sampled immediately before retrieval-path invocation; "
    "not a semantic fusion/rerank stage boundary"
)

VARIANT_TOTAL_PATH = {
    VARIANT_HYBRID: PATH_BASELINE_HYBRID_TOTAL,
    VARIANT_HYBRID_RERANK: PATH_TREATMENT_TOTAL,
}


def quality_from_ranking(
    case: GoldCase,
    ranked_chunk_ids: Sequence[str],
    *,
    requested_depth: int,
) -> PerformanceCaseQualityV1:
    """Reuse accepted Slice-9 IR semantics for one frozen Gold case."""
    score = score_ranking(
        case,
        list(ranked_chunk_ids),
        requested_depth=requested_depth,
        hit_rate_30_applicable=requested_depth >= 30,
    )
    return PerformanceCaseQualityV1(
        quality_eligible=score.quality_eligible,
        requested_depth=score.requested_depth,
        returned_count=score.returned_count,
        recall_at_1=score.recall.get(1),
        recall_at_5=score.recall.get(5),
        recall_at_10=score.recall.get(10),
        precision_at_1=score.precision.get(1),
        precision_at_5=score.precision.get(5),
        precision_at_10=score.precision.get(10),
        hit_rate_at_1=score.hit_rate.get(1),
        hit_rate_at_5=score.hit_rate.get(5),
        hit_rate_at_10=score.hit_rate.get(10),
        mrr=score.mrr,
        ndcg_at_1=score.ndcg.get(1),
        ndcg_at_5=score.ndcg.get(5),
        ndcg_at_10=score.ndcg.get(10),
    )


def _require_latency_seconds(metadata: Mapping[str, Any]) -> dict[str, Any]:
    raw = metadata.get("latency_seconds")
    if not isinstance(raw, dict) or not raw:
        raise Performance14Error(
            "retrieve metadata missing latency_seconds; refuse integer-ms-only timing"
        )
    return raw


def assert_not_end_to_end_stage(stage_id: str) -> None:
    """Fail closed if Level-B retrieval evidence uses the Level-C end_to_end id."""
    if stage_id == STAGE_END_TO_END_FORBIDDEN_FOR_14C:
        raise Performance14Error(
            "14C retrieval-path evidence must not use stage_id=end_to_end; "
            "end_to_end is reserved for Level-C CLI/service→terminal envelopes"
        )


def assert_semantic_not_full_path(
    *,
    semantic_stage_id: str,
    semantic_duration: float,
    total_duration: float,
) -> None:
    """Fail closed if a semantic stage duration equals the full-path duration."""
    validate_stage_id(semantic_stage_id)
    assert_not_end_to_end_stage(semantic_stage_id)
    if semantic_stage_id not in {STAGE_FUSION, STAGE_RERANK}:
        raise Performance14Error(
            f"assert_semantic_not_full_path only applies to fusion/rerank; "
            f"got {semantic_stage_id!r}"
        )
    if total_duration <= 0:
        raise Performance14Error("total_duration must be positive for envelope proof")
    if semantic_duration <= 0:
        raise Performance14Error(
            "semantic_duration must be positive for envelope proof"
        )
    if abs(semantic_duration - total_duration) < 1e-12:
        raise Performance14Error(
            f"{semantic_stage_id} duration equals total path duration; "
            "semantic envelope must not wrap the full retrieve() call"
        )
    if semantic_duration > total_duration + 1e-9:
        raise Performance14Error(
            f"{semantic_stage_id} duration exceeds total path duration"
        )


def _path_sample(
    path: str,
    duration_seconds: float,
    *,
    is_warmup: bool,
) -> PerformancePathSampleV1:
    assert_not_end_to_end_stage(path)
    return PerformancePathSampleV1(
        path=path,
        duration_seconds=float(duration_seconds),
        is_warmup=is_warmup,
        observation_status="valid",
    )


def semantic_observations_from_hybrid_metadata(
    metadata: Mapping[str, Any],
    *,
    is_warmup: bool,
    resource: PerformanceResourceObservationV1 | None,
) -> tuple[list[PerformanceBenchmarkObservationV1], list[PerformancePathSampleV1]]:
    """Emit fusion semantic obs + baseline hybrid total path sample."""
    latency = _require_latency_seconds(metadata)
    fusion_s = float(latency["fusion"])
    total_s = float(latency["total"])
    assert_semantic_not_full_path(
        semantic_stage_id=STAGE_FUSION,
        semantic_duration=fusion_s,
        total_duration=total_s,
    )
    observations = [
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id=STAGE_FUSION,
            duration_seconds=fusion_s,
            is_warmup=is_warmup,
            resource=resource,
        )
    ]
    path_samples = [
        _path_sample(PATH_BASELINE_HYBRID_TOTAL, total_s, is_warmup=is_warmup)
    ]
    return observations, path_samples


def semantic_observations_from_hybrid_rerank_metadata(
    metadata: Mapping[str, Any],
    *,
    is_warmup: bool,
    resource: PerformanceResourceObservationV1 | None,
) -> tuple[list[PerformanceBenchmarkObservationV1], list[PerformancePathSampleV1]]:
    """Emit rerank semantic obs + separate treatment path samples.

    Path samples keep warm-up identity. Hybrid component (input_k pool) is
    never pooled with baseline hybrid total.
    """
    latency = _require_latency_seconds(metadata)
    rerank_s = float(latency["rerank"])
    total_s = float(latency["total"])
    hybrid_s = float(latency["hybrid"])
    assert_semantic_not_full_path(
        semantic_stage_id=STAGE_RERANK,
        semantic_duration=rerank_s,
        total_duration=total_s,
    )
    observations = [
        PerformanceBenchmarkObservationV1(
            observation_status="valid",
            stage_id=STAGE_RERANK,
            duration_seconds=rerank_s,
            is_warmup=is_warmup,
            resource=resource,
        )
    ]
    path_samples = [
        _path_sample(
            PATH_TREATMENT_HYBRID_COMPONENT, hybrid_s, is_warmup=is_warmup
        ),
        _path_sample(PATH_TREATMENT_RERANKER, rerank_s, is_warmup=is_warmup),
        _path_sample(PATH_TREATMENT_TOTAL, total_s, is_warmup=is_warmup),
    ]
    return observations, path_samples


def macro_quality_by_variant(
    cases: Sequence[Any],
) -> list[PerformanceVariantQualityV1]:
    """Macro-average case quality metrics per variant (eligible cases only)."""
    by_variant: dict[str, list[PerformanceCaseQualityV1]] = defaultdict(list)
    for case in cases:
        quality = getattr(case, "quality", None)
        if quality is None:
            continue
        by_variant[str(case.variant)].append(quality)

    out: list[PerformanceVariantQualityV1] = []
    for variant in sorted(by_variant):
        qualities = by_variant[variant]
        eligible = [q for q in qualities if q.quality_eligible]
        metrics = {
            attr: macro_average([getattr(q, attr) for q in eligible])
            for attr in (
                "recall_at_1",
                "recall_at_5",
                "recall_at_10",
                "precision_at_1",
                "precision_at_5",
                "precision_at_10",
                "hit_rate_at_1",
                "hit_rate_at_5",
                "hit_rate_at_10",
                "mrr",
                "ndcg_at_1",
                "ndcg_at_5",
                "ndcg_at_10",
            )
        }
        recall_1, n = metrics["recall_at_1"]
        out.append(
            PerformanceVariantQualityV1(
                variant=variant,
                eligible_case_count=n,
                recall_at_1=recall_1,
                recall_at_5=metrics["recall_at_5"][0],
                recall_at_10=metrics["recall_at_10"][0],
                precision_at_1=metrics["precision_at_1"][0],
                precision_at_5=metrics["precision_at_5"][0],
                precision_at_10=metrics["precision_at_10"][0],
                hit_rate_at_1=metrics["hit_rate_at_1"][0],
                hit_rate_at_5=metrics["hit_rate_at_5"][0],
                hit_rate_at_10=metrics["hit_rate_at_10"][0],
                mrr=metrics["mrr"][0],
                ndcg_at_1=metrics["ndcg_at_1"][0],
                ndcg_at_5=metrics["ndcg_at_5"][0],
                ndcg_at_10=metrics["ndcg_at_10"][0],
            )
        )
    return out


def resource_summary_by_variant(
    cases: Sequence[Any],
) -> list[PerformanceVariantResourceV1]:
    """Deterministic RSS summary from measured (non-warm-up) resource samples."""
    by_variant: dict[str, list[int]] = defaultdict(list)
    for case in cases:
        for sample in getattr(case, "resource_samples", []) or []:
            if sample is None:
                continue
            if getattr(sample, "is_warmup", False):
                continue
            if sample.ram_availability != "available":
                continue
            rss = sample.ram_rss_bytes_before
            if rss is None:
                rss = sample.ram_rss_bytes_peak
            if rss is None:
                continue
            by_variant[str(case.variant)].append(int(rss))

    out: list[PerformanceVariantResourceV1] = []
    for variant in (VARIANT_HYBRID, VARIANT_HYBRID_RERANK):
        values = sorted(by_variant.get(variant, []))
        if not values:
            out.append(
                PerformanceVariantResourceV1(
                    variant=variant,
                    ram_availability="unavailable",
                    sample_count=0,
                )
            )
            continue
        floats = [float(v) for v in values]
        out.append(
            PerformanceVariantResourceV1(
                variant=variant,
                ram_availability="available",
                sample_count=len(values),
                ram_rss_bytes_min=values[0],
                ram_rss_bytes_p50=round(linear_percentile(floats, 0.50)),
                ram_rss_bytes_p95=round(linear_percentile(floats, 0.95)),
                ram_rss_bytes_max=values[-1],
            )
        )
    return out


def path_samples_to_observations(
    samples: Sequence[PerformancePathSampleV1],
) -> list[PerformanceBenchmarkObservationV1]:
    """Adapt path samples for ``derive_latency_stats`` (preserves is_warmup)."""
    out: list[PerformanceBenchmarkObservationV1] = []
    for sample in samples:
        assert_not_end_to_end_stage(sample.path)
        out.append(
            PerformanceBenchmarkObservationV1(
                observation_status=sample.observation_status,
                # Carrier field for derive_latency_stats only; authoritative path
                # identity is PerformancePathSampleV1.path / PathLatencyV1.path.
                stage_id=sample.path,
                duration_seconds=float(sample.duration_seconds),
                is_warmup=bool(sample.is_warmup),
            )
        )
    return out


def path_latency_rollups(cases: Sequence[Any]) -> list[PerformancePathLatencyV1]:
    """Roll separate baseline/treatment path populations (warm-ups excluded)."""
    by_path: dict[str, list[PerformancePathSampleV1]] = defaultdict(list)
    for case in cases:
        for sample in getattr(case, "path_samples", []) or []:
            by_path[str(sample.path)].append(sample)

    ordered_paths = (
        PATH_BASELINE_HYBRID_TOTAL,
        PATH_TREATMENT_HYBRID_COMPONENT,
        PATH_TREATMENT_RERANKER,
        PATH_TREATMENT_TOTAL,
    )
    return [
        PerformancePathLatencyV1(
            path=path,
            stats=derive_latency_stats(
                path_samples_to_observations(by_path.get(path, []))
            ),
        )
        for path in ordered_paths
    ]


def assert_paired_quality_coverage(
    cases: Sequence[Any],
    *,
    expected_query_ids: Sequence[str],
) -> None:
    """Fail closed unless every frozen query×variant cell has ranked IR evidence."""
    expected_variants = (VARIANT_HYBRID, VARIANT_HYBRID_RERANK)
    seen: set[tuple[str, str]] = set()
    for case in cases:
        key = (str(case.subject_identity), str(case.variant))
        if case.ranked_chunk_ids is None or case.quality is None:
            raise Performance14Error(
                f"quality evidence missing for subject×variant {key}"
            )
        if not case.ranked_chunk_ids:
            raise Performance14Error(
                f"ranked_chunk_ids empty for subject×variant {key}"
            )
        seen.add(key)
    expected = {
        (qid, variant) for qid in expected_query_ids for variant in expected_variants
    }
    missing = sorted(expected - seen)
    if missing:
        raise Performance14Error(
            f"quality evidence incomplete; missing {len(missing)} cells "
            f"(first={missing[0]})"
        )
    if len(seen) != len(expected):
        raise Performance14Error(
            f"quality evidence count mismatch: have {len(seen)} expected {len(expected)}"
        )
