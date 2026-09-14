"""prelabel-agreement-v1: exact-grade agreement and review-priority aids."""

from __future__ import annotations

from offline_rag.gold_authoring.contracts import PRELABEL_AGREEMENT_CONTRACT
from offline_rag.gold_authoring.prelabel_models import (
    AgreementLabel,
    CandidatePrelabelSummary,
    DisagreementSeverity,
    ModelJudgment,
    PrelabelSummary,
    ReviewPriority,
)


class AgreementError(ValueError):
    """Agreement derivation failure."""


def _severity(g1: int, g2: int) -> tuple[AgreementLabel, DisagreementSeverity]:
    if g1 == g2:
        return AgreementLabel.AGREE, DisagreementSeverity.NONE
    delta = abs(g1 - g2)
    if delta == 1:
        return AgreementLabel.DISAGREE, DisagreementSeverity.ADJACENT
    if delta == 2:
        return AgreementLabel.DISAGREE, DisagreementSeverity.POLAR
    raise AgreementError(f"unsupported grade pair: {g1}/{g2}")


def derive_prelabel_summary(
    judgments: list[ModelJudgment],
    *,
    candidate_ids: list[str],
    source_seed_chunk_id: str | None,
) -> PrelabelSummary:
    expected = list(candidate_ids)
    if len(set(expected)) != len(expected):
        raise AgreementError("duplicate candidate ids")
    expected_set = set(expected)
    by_pass: dict[str, dict[str, ModelJudgment]] = {"pass_1": {}, "pass_2": {}}
    for judgment in judgments:
        bucket = by_pass[judgment.pass_id]
        if judgment.chunk_id in bucket:
            raise AgreementError(
                f"duplicate judgment for {judgment.pass_id}/{judgment.chunk_id}"
            )
        bucket[judgment.chunk_id] = judgment
    if set(by_pass["pass_1"]) != expected_set or set(by_pass["pass_2"]) != expected_set:
        raise AgreementError("judgment membership does not match candidate set")

    summaries: list[CandidatePrelabelSummary] = []
    has_disagreement = False
    has_polar = False
    competing_grade_2: set[str] = set()
    all_zero = True

    for chunk_id in sorted(expected_set):
        g1 = by_pass["pass_1"][chunk_id].grade
        g2 = by_pass["pass_2"][chunk_id].grade
        agreement, severity = _severity(int(g1), int(g2))
        summaries.append(
            CandidatePrelabelSummary(
                chunk_id=chunk_id,
                agreement=agreement,
                disagreement_severity=severity,
            )
        )
        if agreement == AgreementLabel.DISAGREE:
            has_disagreement = True
        if severity == DisagreementSeverity.POLAR:
            has_polar = True
        if g1 == 2 or g2 == 2:
            competing_grade_2.add(chunk_id)
        if g1 != 0 or g2 != 0:
            all_zero = False

    seed_zero = False
    if source_seed_chunk_id is not None and source_seed_chunk_id in expected_set:
        sg1 = by_pass["pass_1"][source_seed_chunk_id].grade
        sg2 = by_pass["pass_2"][source_seed_chunk_id].grade
        seed_zero = sg1 == 0 or sg2 == 0

    competing = len(competing_grade_2) >= 2
    no_positive = all_zero

    if has_polar:
        priority = ReviewPriority.HIGH
    elif has_disagreement or seed_zero or competing or no_positive:
        priority = ReviewPriority.MEDIUM
    else:
        priority = ReviewPriority.LOW

    return PrelabelSummary(
        candidate_summaries=summaries,
        case_has_disagreement=has_disagreement,
        case_has_polar_disagreement=has_polar,
        case_has_source_seed_zero=seed_zero,
        case_has_competing_grade_2=competing,
        case_has_no_positive_prelabel=no_positive,
        review_priority=priority,
    )


def agreement_contract_id() -> str:
    return PRELABEL_AGREEMENT_CONTRACT
