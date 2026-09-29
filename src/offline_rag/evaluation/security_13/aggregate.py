"""Aggregate builder for Slice 13B campaign results (OD-13-11)."""

from __future__ import annotations

from collections import defaultdict

from offline_rag.evaluation.security_13.contracts import (
    SECURITY_CAMPAIGN_AGGREGATE_V1,
    AdversarialAggregateBlockV1,
    AdversarialEvalResultV1,
    AdversarialFixtureV1,
    AttackClassCountsV1,
    BenignAggregateBlockV1,
    BenignControlEvalResultV1,
    FixtureOutcomeV1,
    InvariantStatusCountsV1,
    InvariantStatusV1,
    PerInvariantAggregateBlockV1,
    PopulationCountsV1,
    SecurityCampaignAggregateV1,
    SecurityCampaignV1,
)


def build_campaign_aggregate(
    *,
    campaign: SecurityCampaignV1,
    run_status: str,
    adversarial_results: list[tuple[AdversarialFixtureV1, AdversarialEvalResultV1]],
    benign_results: list[BenignControlEvalResultV1],
) -> SecurityCampaignAggregateV1:
    """Build the locked nested aggregate surface from per-case results."""
    if run_status in {"failed_preflight", "failed_during_execution"}:
        campaign_outcome = None
    elif run_status == "completed":
        all_pass = all(
            result.outcome == FixtureOutcomeV1.PASS
            for _, result in adversarial_results
        ) and all(result.outcome == FixtureOutcomeV1.PASS for result in benign_results)
        campaign_outcome = "pass" if all_pass else "fail"
    else:
        campaign_outcome = None

    adv_pass = sum(
        1 for _, r in adversarial_results if r.outcome == FixtureOutcomeV1.PASS
    )
    adv_fail = len(adversarial_results) - adv_pass

    by_class: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "pass": 0, "fail": 0}
    )
    for fixture, result in adversarial_results:
        bucket = by_class[fixture.attack_class]
        bucket["total"] += 1
        if result.outcome == FixtureOutcomeV1.PASS:
            bucket["pass"] += 1
        else:
            bucket["fail"] += 1

    benign_pass = sum(
        1 for r in benign_results if r.outcome == FixtureOutcomeV1.PASS
    )
    benign_fail = len(benign_results) - benign_pass
    violation_case_count = sum(
        1
        for r in benign_results
        if any(
            row.status == InvariantStatusV1.VIOLATED for row in r.invariant_outcomes
        )
    )
    unevaluable_case_count = sum(
        1
        for r in benign_results
        if any(
            row.status == InvariantStatusV1.UNEVALUABLE for row in r.invariant_outcomes
        )
    )
    false_positive_count = violation_case_count
    benign_total = len(benign_results)
    false_positive_rate = (
        float(false_positive_count) / float(benign_total) if benign_total else 0.0
    )

    return SecurityCampaignAggregateV1(
        contract=SECURITY_CAMPAIGN_AGGREGATE_V1,
        seccamp_=campaign.campaign_identity_hash,
        secinv_=campaign.registry_hash,
        campaign_kind=campaign.campaign_kind,
        path_scope=campaign.path_scope,
        run_status=run_status,  # type: ignore[arg-type]
        campaign_outcome=campaign_outcome,  # type: ignore[arg-type]
        product_default_recovery_enabled=False,
        recovery_execution_mode="disabled",
        population=PopulationCountsV1(
            adversarial_total=len(adversarial_results),
            benign_total=len(benign_results),
        ),
        adversarial=AdversarialAggregateBlockV1(
            pass_=adv_pass,
            fail=adv_fail,
            by_attack_class={
                key: AttackClassCountsV1(
                    total=val["total"], pass_=val["pass"], fail=val["fail"]
                )
                for key, val in sorted(by_class.items())
            },
        ),
        benign=BenignAggregateBlockV1(
            pass_=benign_pass,
            fail=benign_fail,
            violation_case_count=violation_case_count,
            unevaluable_case_count=unevaluable_case_count,
            false_positive_count=false_positive_count,
            false_positive_rate=false_positive_rate,
        ),
        per_invariant=PerInvariantAggregateBlockV1(
            adversarial=_per_invariant_counts([r for _, r in adversarial_results]),
            benign=_per_invariant_counts(benign_results),
        ),
    )


def _per_invariant_counts(
    results: list[AdversarialEvalResultV1] | list[BenignControlEvalResultV1],
) -> dict[str, InvariantStatusCountsV1]:
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"holds": 0, "violated": 0, "unevaluable": 0}
    )
    for result in results:
        for row in result.invariant_outcomes:
            if row.status == InvariantStatusV1.HOLDS:
                counts[row.invariant_id]["holds"] += 1
            elif row.status == InvariantStatusV1.VIOLATED:
                counts[row.invariant_id]["violated"] += 1
            else:
                counts[row.invariant_id]["unevaluable"] += 1
    return {
        key: InvariantStatusCountsV1(**val) for key, val in sorted(counts.items())
    }
