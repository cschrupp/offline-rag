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
    if human_trigger_count < 0:
        raise ValueError("human_trigger_count must be >= 0")
    if human_trigger_count == 0:
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
