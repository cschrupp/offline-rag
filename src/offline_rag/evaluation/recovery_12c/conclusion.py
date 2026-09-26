"""Deterministic OD-12C-6 conclusion mapping (pure; exhaustive precedence)."""

from __future__ import annotations

from offline_rag.evaluation.recovery_12c.contracts import RecoveryEvalConclusionV1


def conclude_recovery_eval(
    *,
    human_trigger_count: int,
    gold_positive_recovery_count: int,
    unsupported_recovery_count: int,
    recovery_failure_count: int,
    happy_path_divergence_count: int,
) -> RecoveryEvalConclusionV1:
    """Map aggregate counts to exactly one predeclared conclusion.

    Precedence:
    1. no human triggers → insufficient evidence
    2. any regression signal → retain disabled / regression
    3. triggers but zero Gold-positive recovery → retain disabled / no benefit
    4. otherwise promotion candidate
    """
    counts = {
        "human_trigger_count": human_trigger_count,
        "gold_positive_recovery_count": gold_positive_recovery_count,
        "unsupported_recovery_count": unsupported_recovery_count,
        "recovery_failure_count": recovery_failure_count,
        "happy_path_divergence_count": happy_path_divergence_count,
    }
    for name, value in counts.items():
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{name} must be an int")
        if value < 0:
            raise ValueError(f"{name} must be >= 0")

    if gold_positive_recovery_count > human_trigger_count:
        raise ValueError(
            "gold_positive_recovery_count cannot exceed human_trigger_count"
        )
    if unsupported_recovery_count > human_trigger_count:
        raise ValueError("unsupported_recovery_count cannot exceed human_trigger_count")
    if recovery_failure_count > human_trigger_count:
        raise ValueError("recovery_failure_count cannot exceed human_trigger_count")

    if human_trigger_count == 0:
        if (
            gold_positive_recovery_count
            or unsupported_recovery_count
            or recovery_failure_count
        ):
            raise ValueError(
                "non-zero recovery outcome counts are impossible when "
                "human_trigger_count == 0"
            )
        return RecoveryEvalConclusionV1.INSUFFICIENT_EVIDENCE_FOR_RECOVERY_EFFICACY

    if (
        unsupported_recovery_count > 0
        or recovery_failure_count > 0
        or happy_path_divergence_count > 0
    ):
        return RecoveryEvalConclusionV1.RETAIN_DISABLED_RECOVERY_REGRESSION

    if gold_positive_recovery_count == 0:
        return RecoveryEvalConclusionV1.RETAIN_DISABLED_NO_MEASURED_BENEFIT

    return RecoveryEvalConclusionV1.PROMOTION_CANDIDATE
