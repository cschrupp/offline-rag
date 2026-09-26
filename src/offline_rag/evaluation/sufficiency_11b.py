"""OD-11-4 / Slice 11B sufficiency measurement analysis (eval layer only).

Joins authoritative gold-free ``suffctx_`` / ``suffctxrun_`` artifacts to a
frozen GoldDataset solely for cohort labeling and one-dimensional threshold
tradeoff reporting. Does not mutate snapshots, call retrieval/generation, or
wire runtime gates.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.evaluation.gold import GoldCase, LoadedGoldDataset, load_gold_dataset
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.sufficiency import (
    SufficiencyEvalContextManifestV1,
    SufficiencyEvalContextSnapshotV1,
    SufficiencyObservationV1,
    default_snapshot_artifact_path,
    load_sufficiency_manifest,
    load_sufficiency_snapshot,
    require_authoritative_manifest,
)
from offline_rag.sufficiency.contracts import ExactNonBlankStr

ANALYSIS_CONTRACT = "sufficiency-11b-analysis-v1"
EVAL_LABEL_CONTRACT = "sufficiency-eval-label-v1"
COHORT_DEFINITION_CONTRACT = "sufficiency-11b-cohort-definition-v1"
PRESENCE_MATCHING_RULE_ID = "evidence-surface-chunk-id-overlap-v1"
PRESENCE_MATCHING_RULE_VERSION = "v1"

FEATURE_NAMES: tuple[str, ...] = (
    "empty_context",
    "top_reranker_score",
    "top1_top2_margin",
    "top_anchor_cross_retriever_support",
    "anchor_count",
    "distinct_document_count",
    "distinct_section_count",
)

NUMERIC_FEATURES: frozenset[str] = frozenset(
    {
        "top_reranker_score",
        "top1_top2_margin",
        "anchor_count",
        "distinct_document_count",
        "distinct_section_count",
    }
)

BOOLEAN_FEATURES: frozenset[str] = frozenset(
    {
        "empty_context",
        "top_anchor_cross_retriever_support",
    }
)

ComparisonOp = Literal["<", "<=", ">", ">="]


class Sufficiency11BError(RuntimeError):
    """Fail-closed 11B analysis / join error."""


class PositivePresenceMatchingRuleV1(BaseModel):
    """Deterministic chunk-ID presence rule (no text similarity / model judgment)."""

    model_config = ConfigDict(extra="forbid")

    rule_id: Literal["evidence-surface-chunk-id-overlap-v1"] = (
        PRESENCE_MATCHING_RULE_ID
    )
    version: Literal["v1"] = PRESENCE_MATCHING_RULE_VERSION
    description: str = (
        "A human-positive Gold chunk is present when its chunk_id appears in the "
        "current retrieval/context evidence surface: the union of "
        "provenance.anchors[].chunk_id, "
        "provenance.final_evidence_units[].source_chunk_id, and "
        "provenance.final_evidence_units[].primary_anchor_chunk_id. "
        "Presence is exact chunk_id set overlap only."
    )
    evidence_surface_fields: tuple[str, ...] = (
        "provenance.anchors[].chunk_id",
        "provenance.final_evidence_units[].source_chunk_id",
        "provenance.final_evidence_units[].primary_anchor_chunk_id",
    )


class CohortDefinitionContractV1(BaseModel):
    """OD-11-4 population contract recorded in the analysis artifact."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-11b-cohort-definition-v1"] = (
        COHORT_DEFINITION_CONTRACT
    )
    version: Literal["v1"] = "v1"
    population_a: Literal["known_positive_present"] = "known_positive_present"
    population_b: Literal["known_positive_missing"] = "known_positive_missing"
    population_a_definition: str = (
        "Gold has ≥1 positive chunk and at least one human-positive Gold chunk_id "
        "is represented in the current retrieval/context evidence surface."
    )
    population_b_definition: str = (
        "Gold has ≥1 positive chunk, but no human-positive Gold chunk_id is "
        "represented in the current retrieval/context evidence surface "
        "(retrieval-failure / insufficiency proxy; not proof of unanswerability)."
    )
    exclusions: tuple[str, ...] = (
        "slice_10d_hard_negatives_as_threshold_truth",
        "generator_outputs",
        "same_model_judge_labels",
        "rejected_gold_cases",
        "unreviewed_or_non_exported_cases_outside_frozen_population",
        "synthetic_stripped_evidence_as_threshold_truth",
    )


class ObservedFeatureVectorV1(BaseModel):
    """Frozen OD-11-2 observation features copied from the immutable snapshot."""

    model_config = ConfigDict(extra="forbid")

    empty_context: bool
    top_reranker_score: float | None = None
    top1_top2_margin: float | None = None
    top_anchor_cross_retriever_support: bool | None = None
    anchor_count: int
    distinct_document_count: int
    distinct_section_count: int


class SufficiencyEvalLabelV1(BaseModel):
    """Per-case 11B evaluation record (eval layer only; gold outside snapshots)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-eval-label-v1"] = EVAL_LABEL_CONTRACT
    case_id: ExactNonBlankStr
    suffctx_id: ExactNonBlankStr
    gold_dataset_id: ExactNonBlankStr
    cohort: Literal["A", "B"]
    gold_positive_chunk_ids: list[ExactNonBlankStr]
    present_positive_chunk_ids: list[ExactNonBlankStr]
    evidence_surface_chunk_ids: list[ExactNonBlankStr]
    features: ObservedFeatureVectorV1
    original_query: ExactNonBlankStr


class FeatureDistributionV1(BaseModel):
    """Descriptive per-feature separation across cohorts."""

    model_config = ConfigDict(extra="forbid")

    feature: ExactNonBlankStr
    value_kind: Literal["boolean", "numeric", "nullable_boolean", "nullable_numeric"]
    non_discriminative: bool
    distinct_values: list[bool | int | float | None]
    population_a_values: list[bool | int | float | None]
    population_b_values: list[bool | int | float | None]
    population_a_min: float | None = None
    population_a_median: float | None = None
    population_a_max: float | None = None
    population_b_min: float | None = None
    population_b_median: float | None = None
    population_b_max: float | None = None
    overlap_values: list[bool | int | float | None]
    notes: list[str] = Field(default_factory=list)


class ThresholdCandidateEvalV1(BaseModel):
    """One deterministic 1-D gate rule evaluated on the labeled population."""

    model_config = ConfigDict(extra="forbid")

    feature: ExactNonBlankStr
    rule_kind: Literal["numeric_threshold", "boolean_state"]
    operator: ExactNonBlankStr
    threshold: bool | float | None = None
    rule_id: ExactNonBlankStr
    population_a_gated_count: int
    population_a_gated_rate: float
    population_b_gated_count: int
    population_b_gated_rate: float
    false_refusal_candidate_count: int
    retrieval_failure_proxy_capture_count: int
    gated_case_ids: list[ExactNonBlankStr]
    gated_cohort_a_case_ids: list[ExactNonBlankStr]
    gated_cohort_b_case_ids: list[ExactNonBlankStr]
    eligible_for_recommendation: bool
    eligibility_notes: list[str] = Field(default_factory=list)


class Sufficiency11BAnalysisV1(BaseModel):
    """Deterministic, reviewable 11B analysis artifact."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-11b-analysis-v1"] = ANALYSIS_CONTRACT
    analysis_version: Literal["v1"] = "v1"
    suffctxrun_id: ExactNonBlankStr
    gold_dataset_id: ExactNonBlankStr
    cohort_definition: CohortDefinitionContractV1
    positive_presence_matching_rule: PositivePresenceMatchingRuleV1
    expected_case_count: int
    population_a_count: int
    population_b_count: int
    population_a_case_ids: list[ExactNonBlankStr]
    population_b_case_ids: list[ExactNonBlankStr]
    case_labels: list[SufficiencyEvalLabelV1]
    feature_distributions: list[FeatureDistributionV1]
    threshold_evaluations: list[ThresholdCandidateEvalV1]
    recommended_candidate_rule_ids: list[ExactNonBlankStr]
    conclusion: Literal[
        "no_additional_gate_promoted",
        "candidate_gate_reported_for_review",
    ]
    conclusion_notes: list[str] = Field(default_factory=list)
    intrinsic_gate_remains: Literal["empty_context => insufficient"] = (
        "empty_context => insufficient"
    )
    created_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Sufficiency11BAnalysisResult:
    analysis: Sufficiency11BAnalysisV1
    analysis_json_path: Path
    analysis_md_path: Path


def evidence_surface_chunk_ids(
    snapshot: SufficiencyEvalContextSnapshotV1,
) -> set[str]:
    """Exact chunk-ID evidence surface used for positive-present matching."""
    surface: set[str] = set()
    for anchor in snapshot.provenance.anchors:
        surface.add(anchor.chunk_id)
    for unit in snapshot.provenance.final_evidence_units:
        surface.add(unit.source_chunk_id)
        surface.add(unit.primary_anchor_chunk_id)
    return surface


def assign_cohort(
    *,
    gold_positive_chunk_ids: set[str],
    evidence_surface: set[str],
) -> tuple[Literal["A", "B"], set[str]]:
    """Return (cohort, present_positive_ids). Fail closed on empty Gold positives."""
    if not gold_positive_chunk_ids:
        raise Sufficiency11BError(
            "case has no Gold positive chunks; cannot assign OD-11-4 cohort A/B"
        )
    present = gold_positive_chunk_ids & evidence_surface
    if present:
        return "A", present
    return "B", present


def observation_feature_vector(
    observation: SufficiencyObservationV1,
) -> ObservedFeatureVectorV1:
    return ObservedFeatureVectorV1(
        empty_context=observation.empty_context,
        top_reranker_score=observation.top_reranker_score,
        top1_top2_margin=observation.top1_top2_margin,
        top_anchor_cross_retriever_support=(
            observation.top_anchor_cross_retriever_support
        ),
        anchor_count=observation.anchor_count,
        distinct_document_count=observation.distinct_document_count,
        distinct_section_count=observation.distinct_section_count,
    )


def _feature_value(
    features: ObservedFeatureVectorV1, feature: str
) -> bool | int | float | None:
    return getattr(features, feature)


def _sorted_unique_values(
    values: Sequence[bool | int | float | None],
) -> list[bool | int | float | None]:
    present = [v for v in values if v is not None]
    nulls = [v for v in values if v is None]
    if not present and nulls:
        return [None]
    if all(isinstance(v, bool) for v in present):
        ordered = sorted(set(present), key=lambda v: (0 if v is False else 1))
    else:
        ordered = sorted(set(present), key=lambda v: float(v))  # type: ignore[arg-type]
    if nulls:
        ordered.append(None)
    return ordered


def _numeric_stats(
    values: Sequence[bool | int | float | None],
) -> tuple[float | None, float | None, float | None]:
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return None, None, None
    return min(nums), float(statistics.median(nums)), max(nums)


def _build_feature_distributions(
    labels: Sequence[SufficiencyEvalLabelV1],
) -> list[FeatureDistributionV1]:
    a_labels = [item for item in labels if item.cohort == "A"]
    b_labels = [item for item in labels if item.cohort == "B"]
    out: list[FeatureDistributionV1] = []
    for feature in FEATURE_NAMES:
        all_vals = [_feature_value(item.features, feature) for item in labels]
        a_vals = [_feature_value(item.features, feature) for item in a_labels]
        b_vals = [_feature_value(item.features, feature) for item in b_labels]
        distinct = _sorted_unique_values(all_vals)
        non_null_distinct = [v for v in distinct if v is not None]
        non_discriminative = len(non_null_distinct) <= 1
        notes: list[str] = []
        if non_discriminative:
            notes.append(
                "constant (or single non-null value) across the labeled population; "
                "no discriminative threshold value on this fixture"
            )
        if feature in BOOLEAN_FEATURES:
            value_kind: Literal[
                "boolean", "numeric", "nullable_boolean", "nullable_numeric"
            ] = (
                "nullable_boolean"
                if any(v is None for v in all_vals)
                else "boolean"
            )
            a_min = a_med = a_max = b_min = b_med = b_max = None
        else:
            value_kind = (
                "nullable_numeric"
                if any(v is None for v in all_vals)
                else "numeric"
            )
            a_min, a_med, a_max = _numeric_stats(a_vals)
            b_min, b_med, b_max = _numeric_stats(b_vals)
        a_set = {v for v in a_vals}
        b_set = {v for v in b_vals}
        overlap = _sorted_unique_values(sorted(a_set & b_set, key=str))
        out.append(
            FeatureDistributionV1(
                feature=feature,
                value_kind=value_kind,
                non_discriminative=non_discriminative,
                distinct_values=distinct,
                population_a_values=_sorted_unique_values(a_vals),
                population_b_values=_sorted_unique_values(b_vals),
                population_a_min=a_min,
                population_a_median=a_med,
                population_a_max=a_max,
                population_b_min=b_min,
                population_b_median=b_med,
                population_b_max=b_max,
                overlap_values=overlap,
                notes=notes,
            )
        )
    return out


def _apply_numeric_rule(
    value: bool | float | None, *, operator: ComparisonOp, threshold: float
) -> bool:
    if value is None or isinstance(value, bool):
        return False
    number = float(value)
    if operator == "<":
        return number < threshold
    if operator == "<=":
        return number <= threshold
    if operator == ">":
        return number > threshold
    return number >= threshold


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


def _eligibility(
    *,
    false_refusal_candidate_count: int,
    retrieval_failure_proxy_capture_count: int,
    non_discriminative: bool,
    trivial_all_or_none: bool,
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if non_discriminative:
        notes.append("feature is non-discriminative on this fixture")
    if trivial_all_or_none:
        notes.append("rule gates all cases or no cases")
    if false_refusal_candidate_count > 0:
        notes.append(
            "false-refusal candidates > 0 on Population A; not eligible under "
            "conservative n=22 discipline"
        )
    if retrieval_failure_proxy_capture_count == 0:
        notes.append("retrieval-failure-proxy capture count is 0 on Population B")
    eligible = (
        not non_discriminative
        and not trivial_all_or_none
        and false_refusal_candidate_count == 0
        and retrieval_failure_proxy_capture_count > 0
    )
    if eligible:
        notes.append(
            "eligible as review candidate only: zero Population A gates and "
            "non-zero Population B capture on this fixture (not production calibration)"
        )
    return eligible, notes


def enumerate_threshold_evaluations(
    labels: Sequence[SufficiencyEvalLabelV1],
    *,
    feature_distributions: Sequence[FeatureDistributionV1],
) -> list[ThresholdCandidateEvalV1]:
    """Enumerate deterministic 1-D rules from observed feature values only."""
    by_feature = {item.feature: item for item in feature_distributions}
    a_total = sum(1 for item in labels if item.cohort == "A")
    b_total = sum(1 for item in labels if item.cohort == "B")
    evaluations: list[ThresholdCandidateEvalV1] = []

    for feature in FEATURE_NAMES:
        dist = by_feature[feature]
        if feature in BOOLEAN_FEATURES:
            states = [v for v in dist.distinct_values if isinstance(v, bool)]
            for state in sorted(states, key=lambda v: (0 if v is False else 1)):
                gated = [
                    item
                    for item in labels
                    if _feature_value(item.features, feature) is state
                ]
                evaluations.append(
                    _finalize_threshold_eval(
                        feature=feature,
                        rule_kind="boolean_state",
                        operator="==",
                        threshold=state,
                        rule_id=f"{feature}=={str(state).lower()}",
                        gated=gated,
                        a_total=a_total,
                        b_total=b_total,
                        non_discriminative=dist.non_discriminative,
                        labels_total=len(labels),
                    )
                )
            continue

        thresholds = [
            float(v)
            for v in dist.distinct_values
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        for threshold in thresholds:
            for operator in ("<", "<=", ">", ">="):
                gated = [
                    item
                    for item in labels
                    if _apply_numeric_rule(
                        _feature_value(item.features, feature),
                        operator=operator,  # type: ignore[arg-type]
                        threshold=threshold,
                    )
                ]
                evaluations.append(
                    _finalize_threshold_eval(
                        feature=feature,
                        rule_kind="numeric_threshold",
                        operator=operator,
                        threshold=threshold,
                        rule_id=f"{feature}{operator}{threshold}",
                        gated=gated,
                        a_total=a_total,
                        b_total=b_total,
                        non_discriminative=dist.non_discriminative,
                        labels_total=len(labels),
                    )
                )

    evaluations.sort(key=lambda item: item.rule_id)
    return evaluations


def _finalize_threshold_eval(
    *,
    feature: str,
    rule_kind: Literal["numeric_threshold", "boolean_state"],
    operator: str,
    threshold: bool | float | None,
    rule_id: str,
    gated: Sequence[SufficiencyEvalLabelV1],
    a_total: int,
    b_total: int,
    non_discriminative: bool,
    labels_total: int,
) -> ThresholdCandidateEvalV1:
    gated_a = [item.case_id for item in gated if item.cohort == "A"]
    gated_b = [item.case_id for item in gated if item.cohort == "B"]
    gated_ids = sorted(item.case_id for item in gated)
    a_count = len(gated_a)
    b_count = len(gated_b)
    trivial = len(gated_ids) in (0, labels_total)
    eligible, notes = _eligibility(
        false_refusal_candidate_count=a_count,
        retrieval_failure_proxy_capture_count=b_count,
        non_discriminative=non_discriminative,
        trivial_all_or_none=trivial,
    )
    return ThresholdCandidateEvalV1(
        feature=feature,
        rule_kind=rule_kind,
        operator=operator,
        threshold=threshold,
        rule_id=rule_id,
        population_a_gated_count=a_count,
        population_a_gated_rate=_rate(a_count, a_total),
        population_b_gated_count=b_count,
        population_b_gated_rate=_rate(b_count, b_total),
        false_refusal_candidate_count=a_count,
        retrieval_failure_proxy_capture_count=b_count,
        gated_case_ids=gated_ids,
        gated_cohort_a_case_ids=sorted(gated_a),
        gated_cohort_b_case_ids=sorted(gated_b),
        eligible_for_recommendation=eligible,
        eligibility_notes=notes,
    )


def _load_and_bind_case(
    *,
    group_case_id: str,
    group_query: str,
    suffctx_id: str,
    artifacts_root: Path,
    gold_by_id: Mapping[str, GoldCase],
    gold_dataset_id: str,
) -> SufficiencyEvalLabelV1:
    if group_case_id not in gold_by_id:
        raise Sufficiency11BError(
            f"manifest case_id not present in GoldDataset: {group_case_id}"
        )
    gold_case = gold_by_id[group_case_id]
    if gold_case.query != group_query:
        raise Sufficiency11BError(
            f"exact case/query binding mismatch for {group_case_id}: "
            "manifest original_query does not equal Gold query"
        )

    snapshot_path = default_snapshot_artifact_path(artifacts_root, suffctx_id)
    if not snapshot_path.is_file():
        raise Sufficiency11BError(
            f"manifest-referenced snapshot missing: {snapshot_path}"
        )
    snapshot = load_sufficiency_snapshot(snapshot_path)
    if snapshot.suffctx_id != suffctx_id:
        raise Sufficiency11BError(
            f"snapshot ID mismatch at {snapshot_path}: "
            f"expected {suffctx_id}, got {snapshot.suffctx_id}"
        )
    if snapshot.provenance.case_id != group_case_id:
        raise Sufficiency11BError(
            f"snapshot case_id mismatch for {suffctx_id}: "
            f"expected {group_case_id}, got {snapshot.provenance.case_id}"
        )
    if snapshot.provenance.original_query != group_query:
        raise Sufficiency11BError(
            f"snapshot original_query mismatch for {group_case_id}"
        )
    if snapshot.provenance.original_query != gold_case.query:
        raise Sufficiency11BError(
            f"snapshot/Gold query mismatch for {group_case_id}"
        )

    positives = set(gold_case.positive_chunk_ids())
    surface = evidence_surface_chunk_ids(snapshot)
    cohort, present = assign_cohort(
        gold_positive_chunk_ids=positives,
        evidence_surface=surface,
    )
    return SufficiencyEvalLabelV1(
        case_id=group_case_id,
        suffctx_id=suffctx_id,
        gold_dataset_id=gold_dataset_id,
        cohort=cohort,
        gold_positive_chunk_ids=sorted(positives),
        present_positive_chunk_ids=sorted(present),
        evidence_surface_chunk_ids=sorted(surface),
        features=observation_feature_vector(snapshot.observation),
        original_query=gold_case.query,
    )


def join_authoritative_labels(
    *,
    manifest: SufficiencyEvalContextManifestV1,
    gold: LoadedGoldDataset,
    artifacts_root: Path,
) -> list[SufficiencyEvalLabelV1]:
    """Fail-closed Gold join over an authoritative Path-B manifest."""
    require_authoritative_manifest(manifest)
    if not manifest.authoritative_for_11b:
        raise Sufficiency11BError(
            "manifest authoritative_for_11b is false; refusing 11B analysis"
        )
    if manifest.failures:
        raise Sufficiency11BError(
            "authoritative manifest unexpectedly contains failures"
        )

    gold_by_id = {case.id: case for case in gold.cases}
    gold_ids = sorted(gold_by_id)
    expected = list(manifest.expected_case_ids)
    if expected != sorted(expected):
        raise Sufficiency11BError(
            "manifest expected_case_ids are not in canonical ascending order"
        )
    if expected != gold_ids:
        raise Sufficiency11BError(
            "exact Gold/manifest case coverage mismatch: "
            f"manifest={expected!r} gold={gold_ids!r}"
        )
    if len(expected) != manifest.expected_case_count:
        raise Sufficiency11BError("expected_case_count disagrees with expected_case_ids")
    if manifest.successful_case_count != len(expected):
        raise Sufficiency11BError(
            "successful_case_count does not equal expected coverage"
        )
    if len(manifest.attempt_groups) != len(expected):
        raise Sufficiency11BError(
            "attempt_groups count does not equal expected case coverage"
        )

    labels: list[SufficiencyEvalLabelV1] = []
    seen_cases: set[str] = set()
    for group in manifest.attempt_groups:
        if group.case_id in seen_cases:
            raise Sufficiency11BError(f"duplicate attempt group for {group.case_id}")
        seen_cases.add(group.case_id)
        if len(group.attempts) != 1:
            raise Sufficiency11BError(
                f"11B requires exactly one snapshot attempt per case; "
                f"{group.case_id} has {len(group.attempts)}"
            )
        attempt = group.attempts[0]
        labels.append(
            _load_and_bind_case(
                group_case_id=group.case_id,
                group_query=group.original_query,
                suffctx_id=attempt.suffctx_id,
                artifacts_root=artifacts_root,
                gold_by_id=gold_by_id,
                gold_dataset_id=gold.dataset_id,
            )
        )

    if sorted(seen_cases) != expected:
        raise Sufficiency11BError(
            "attempt_groups case set does not match expected_case_ids"
        )
    labels.sort(key=lambda item: item.case_id)
    return labels


def build_11b_analysis(
    *,
    manifest: SufficiencyEvalContextManifestV1,
    gold: LoadedGoldDataset,
    artifacts_root: Path,
    created_at: datetime | None = None,
) -> Sufficiency11BAnalysisV1:
    """Build the deterministic 11B analysis object (no I/O beyond snapshot loads)."""
    labels = join_authoritative_labels(
        manifest=manifest,
        gold=gold,
        artifacts_root=artifacts_root,
    )
    distributions = _build_feature_distributions(labels)
    thresholds = enumerate_threshold_evaluations(
        labels, feature_distributions=distributions
    )
    recommended = [
        item.rule_id for item in thresholds if item.eligible_for_recommendation
    ]
    a_ids = [item.case_id for item in labels if item.cohort == "A"]
    b_ids = [item.case_id for item in labels if item.cohort == "B"]

    notes = [
        "Development/regression experiment only; n is small and non-promotional.",
        "No weighted composite, ML learner, cross-validation, or multi-feature search.",
        "No runtime sufficiency gating is authorized by this artifact.",
    ]
    if not b_ids:
        notes.append(
            "Population B is empty under the documented presence rule: every "
            "frozen case has ≥1 Gold positive chunk_id on the evidence surface. "
            "Retrieval-failure-proxy capture cannot be demonstrated on this fixture."
        )

    conclusion_notes: list[str] = []
    if recommended:
        conclusion: Literal[
            "no_additional_gate_promoted",
            "candidate_gate_reported_for_review",
        ] = "candidate_gate_reported_for_review"
        conclusion_notes.append(
            "One or more 1-D rules show zero Population A gates and non-zero "
            "Population B capture on this fixture; report for independent review "
            "only — do not wire into runtime yet."
        )
    else:
        conclusion = "no_additional_gate_promoted"
        conclusion_notes.append(
            "No additional gate promoted: the 22-case evidence does not show a "
            "clear useful separation with acceptably low false-refusal behavior "
            "beyond the intrinsic empty_context => insufficient gate."
        )

    return Sufficiency11BAnalysisV1(
        suffctxrun_id=manifest.suffctxrun_id,
        gold_dataset_id=gold.dataset_id,
        cohort_definition=CohortDefinitionContractV1(),
        positive_presence_matching_rule=PositivePresenceMatchingRuleV1(),
        expected_case_count=len(labels),
        population_a_count=len(a_ids),
        population_b_count=len(b_ids),
        population_a_case_ids=a_ids,
        population_b_case_ids=b_ids,
        case_labels=labels,
        feature_distributions=distributions,
        threshold_evaluations=thresholds,
        recommended_candidate_rule_ids=recommended,
        conclusion=conclusion,
        conclusion_notes=conclusion_notes,
        created_at=created_at if created_at is not None else datetime.now(tz=UTC),
        notes=notes,
    )


def analysis_semantic_payload(analysis: Sufficiency11BAnalysisV1) -> dict[str, Any]:
    """Allowlisted semantic surface for deterministic rerun equality."""
    payload = analysis.model_dump(mode="json")
    payload.pop("created_at", None)
    return payload


def render_11b_markdown_report(analysis: Sufficiency11BAnalysisV1) -> str:
    """Concise human-readable 11B report (deterministic section order)."""
    lines: list[str] = [
        "# Sufficiency 11B Measurement Analysis",
        "",
        f"- contract: `{analysis.contract}`",
        f"- suffctxrun_id: `{analysis.suffctxrun_id}`",
        f"- gold_dataset_id: `{analysis.gold_dataset_id}`",
        (
            f"- cohort_definition: `{analysis.cohort_definition.contract}` "
            f"{analysis.cohort_definition.version}"
        ),
        (
            f"- presence_rule: `{analysis.positive_presence_matching_rule.rule_id}` "
            f"{analysis.positive_presence_matching_rule.version}"
        ),
        f"- expected_case_count: {analysis.expected_case_count}",
        f"- population_A (known_positive_present): {analysis.population_a_count}",
        f"- population_B (known_positive_missing): {analysis.population_b_count}",
        f"- conclusion: `{analysis.conclusion}`",
        f"- intrinsic_gate_remains: `{analysis.intrinsic_gate_remains}`",
        "",
        "## Positive-presence matching rule",
        "",
        analysis.positive_presence_matching_rule.description,
        "",
        "## Cohort case IDs",
        "",
        "### Population A",
        "",
    ]
    if analysis.population_a_case_ids:
        lines.extend(f"- `{case_id}`" for case_id in analysis.population_a_case_ids)
    else:
        lines.append("- (none)")
    lines.extend(["", "### Population B", ""])
    if analysis.population_b_case_ids:
        lines.extend(f"- `{case_id}`" for case_id in analysis.population_b_case_ids)
    else:
        lines.append("- (none)")

    lines.extend(["", "## Per-feature descriptive separation", ""])
    for dist in analysis.feature_distributions:
        lines.append(f"### `{dist.feature}`")
        lines.append("")
        lines.append(f"- value_kind: `{dist.value_kind}`")
        lines.append(f"- non_discriminative: `{dist.non_discriminative}`")
        lines.append(f"- distinct_values: `{dist.distinct_values}`")
        lines.append(f"- A values: `{dist.population_a_values}`")
        lines.append(f"- B values: `{dist.population_b_values}`")
        lines.append(f"- overlap: `{dist.overlap_values}`")
        if dist.population_a_min is not None:
            lines.append(
                
                    f"- A min/median/max: {dist.population_a_min} / "
                    f"{dist.population_a_median} / {dist.population_a_max}"
                
            )
        if dist.population_b_min is not None:
            lines.append(
                
                    f"- B min/median/max: {dist.population_b_min} / "
                    f"{dist.population_b_median} / {dist.population_b_max}"
                
            )
        for note in dist.notes:
            lines.append(f"- note: {note}")
        lines.append("")

    lines.extend(
        [
            "## Per-case review table",
            "",
            (
                "| case_id | cohort | empty_context | top_reranker_score | "
                "top1_top2_margin | cross_support | anchor_count | "
                "distinct_document_count | distinct_section_count | "
                "present_positive_count |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for item in analysis.case_labels:
        f = item.features
        lines.append(
            
                f"| `{item.case_id}` | {item.cohort} | {f.empty_context} | "
                f"{f.top_reranker_score} | {f.top1_top2_margin} | "
                f"{f.top_anchor_cross_retriever_support} | {f.anchor_count} | "
                f"{f.distinct_document_count} | {f.distinct_section_count} | "
                f"{len(item.present_positive_chunk_ids)} |"
            
        )

    lines.extend(["", "## Threshold / boolean rule evaluations", ""])
    if not analysis.threshold_evaluations:
        lines.append("(none)")
    else:
        for item in analysis.threshold_evaluations:
            lines.extend(
                [
                    f"### `{item.rule_id}`",
                    "",
                    (
                        f"- A gated: {item.population_a_gated_count} "
                        f"({item.population_a_gated_rate:.4f})"
                    ),
                    (
                        f"- B gated: {item.population_b_gated_count} "
                        f"({item.population_b_gated_rate:.4f})"
                    ),
                    (
                        f"- false_refusal_candidate_count: "
                        f"{item.false_refusal_candidate_count}"
                    ),
                    (
                        f"- retrieval_failure_proxy_capture_count: "
                        f"{item.retrieval_failure_proxy_capture_count}"
                    ),
                    (
                        f"- eligible_for_recommendation: "
                        f"`{item.eligible_for_recommendation}`"
                    ),
                    (
                        f"- gated_case_ids: "
                        f"{', '.join(f'`{c}`' for c in item.gated_case_ids) or '(none)'}"
                    ),
                ]
            )
            for note in item.eligibility_notes:
                lines.append(f"- note: {note}")
            lines.append("")

    lines.extend(
        [
            "## Conclusion",
            "",
            f"- `{analysis.conclusion}`",
            (
                f"- recommended_candidate_rule_ids: "
                f"{analysis.recommended_candidate_rule_ids or []}"
            ),
        ]
    )
    for note in analysis.conclusion_notes:
        lines.append(f"- {note}")
    for note in analysis.notes:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def persist_11b_analysis(
    analysis: Sufficiency11BAnalysisV1,
    *,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write JSON + Markdown analysis artifacts under ``output_dir``."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "sufficiency-11b-analysis-v1.json"
    md_path = out / "sufficiency-11b-analysis-v1.md"
    atomic_write_text(
        json_path,
        json.dumps(analysis.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )
    atomic_write_text(md_path, render_11b_markdown_report(analysis))
    return json_path, md_path


def run_11b_analysis(
    *,
    manifest_path: Path,
    gold_dataset_path: Path,
    artifacts_root: Path,
    output_dir: Path,
) -> Sufficiency11BAnalysisResult:
    """Load authoritative artifacts + Gold, analyze, and persist review outputs."""
    manifest = load_sufficiency_manifest(Path(manifest_path))
    gold = load_gold_dataset(Path(gold_dataset_path))
    analysis = build_11b_analysis(
        manifest=manifest,
        gold=gold,
        artifacts_root=Path(artifacts_root),
    )
    json_path, md_path = persist_11b_analysis(analysis, output_dir=Path(output_dir))
    return Sufficiency11BAnalysisResult(
        analysis=analysis,
        analysis_json_path=json_path,
        analysis_md_path=md_path,
    )


DEFAULT_FROZEN_DATASET = Path(
    "data/corpora/ics_modules/gold_authoring/gold/"
    "authorrun_b28d88f64054491a837cb4a144cbe056"
)
DEFAULT_ACCEPTED_SUFFCTXRUN_ID = (
    "suffctxrun_9c15bf6eee2e7b18317df7daa95328827be62bfa2d369b20272d7820c7fb32d4"
)
DEFAULT_PATH_B_ARTIFACTS_ROOT = Path(
    "eval/results/sufficiency/path_b_measure_once"
)


def main(argv: Sequence[str] | None = None) -> int:
    """Thin internal entry point for authorized local 11B analysis."""
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Slice 11B sufficiency measurement analysis "
            "(internal; reads accepted Path-B artifacts only; no retrieval)."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_FROZEN_DATASET)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=DEFAULT_PATH_B_ARTIFACTS_ROOT,
        help="Root containing sufficiency/manifests and sufficiency/snapshots",
    )
    parser.add_argument(
        "--suffctxrun-id",
        default=DEFAULT_ACCEPTED_SUFFCTXRUN_ID,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for sufficiency-11b-analysis-v1.{json,md}",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    artifacts_root = Path(args.artifacts_root)
    manifest_path = (
        artifacts_root / "sufficiency" / "manifests" / f"{args.suffctxrun_id}.json"
    )
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = (
            Path("eval/results/sufficiency/11b_analysis") / str(args.suffctxrun_id)
        )

    result = run_11b_analysis(
        manifest_path=manifest_path,
        gold_dataset_path=Path(args.dataset),
        artifacts_root=artifacts_root,
        output_dir=Path(output_dir),
    )
    summary = {
        "suffctxrun_id": result.analysis.suffctxrun_id,
        "gold_dataset_id": result.analysis.gold_dataset_id,
        "population_a_count": result.analysis.population_a_count,
        "population_b_count": result.analysis.population_b_count,
        "conclusion": result.analysis.conclusion,
        "recommended_candidate_rule_ids": (
            result.analysis.recommended_candidate_rule_ids
        ),
        "analysis_json_path": str(result.analysis_json_path),
        "analysis_md_path": str(result.analysis_md_path),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
