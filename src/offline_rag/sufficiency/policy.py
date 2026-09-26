"""Runtime sufficiency-v1 policy contract and deterministic evaluator (Slice 11C).

Authorized gate set after 11B: ``empty_context => insufficient`` only.
No score, margin, cross-retriever, or diversity gates.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.config.models import AppSettings
from offline_rag.domain.indexing import EvidenceUnit
from offline_rag.sufficiency.contracts import ExactNonBlankStr

SUFFICIENCY_POLICY_V1 = "sufficiency-v1"
EMPTY_CONTEXT_GATE_V1 = "empty_context_v1"


class SufficiencyPolicyError(RuntimeError):
    """Fail-closed runtime policy configuration / evaluation error."""


class SufficiencyPolicyDecisionV1(BaseModel):
    """Deterministic sufficiency-v1 decision surface (runtime + audit)."""

    model_config = ConfigDict(extra="forbid")

    policy_contract: Literal["sufficiency-v1"] = SUFFICIENCY_POLICY_V1
    policy_version: Literal["v1"] = "v1"
    sufficient: bool
    triggered_gates: list[ExactNonBlankStr] = Field(default_factory=list)
    evidence_unit_count: int
    empty_context: bool
    diagnostics: dict[str, bool | int | str | list[str]] = Field(default_factory=dict)


def empty_context_from_evidence_units(
    evidence_units: Sequence[EvidenceUnit],
) -> bool:
    """OD-11-18: empty_context iff final assembled EvidenceUnit count is zero."""
    return len(evidence_units) == 0


def evaluate_sufficiency_policy_v1(
    *,
    evidence_units: Sequence[EvidenceUnit],
) -> SufficiencyPolicyDecisionV1:
    """Evaluate the frozen sufficiency-v1 ordered rule set.

    Rules (ordered, exclusive authorization after 11B):
    1. ``empty_context`` → insufficient
    """
    units = list(evidence_units)
    evidence_unit_count = len(units)
    empty = evidence_unit_count == 0
    if empty:
        return SufficiencyPolicyDecisionV1(
            sufficient=False,
            triggered_gates=[EMPTY_CONTEXT_GATE_V1],
            evidence_unit_count=0,
            empty_context=True,
            diagnostics={
                "rule": "empty_context => insufficient",
                "authorized_gates": [EMPTY_CONTEXT_GATE_V1],
            },
        )
    return SufficiencyPolicyDecisionV1(
        sufficient=True,
        triggered_gates=[],
        evidence_unit_count=evidence_unit_count,
        empty_context=False,
        diagnostics={
            "rule": "non-empty final EvidenceUnits => sufficient",
            "authorized_gates": [EMPTY_CONTEXT_GATE_V1],
        },
    )


def require_runtime_sufficiency_policy(settings: AppSettings) -> str:
    """Resolve the configured runtime policy contract; fail closed if unsupported."""
    abstention = settings.abstention
    policy = abstention.policy
    if policy != SUFFICIENCY_POLICY_V1:
        raise SufficiencyPolicyError(
            f"unsupported abstention.policy={policy!r}; "
            f"authorized runtime contract is {SUFFICIENCY_POLICY_V1!r}"
        )
    if abstention.threshold is not None:
        raise SufficiencyPolicyError(
            f"{SUFFICIENCY_POLICY_V1} forbids numeric threshold; "
            f"got threshold={abstention.threshold!r}"
        )
    if not abstention.enabled:
        raise SufficiencyPolicyError(
            f"{SUFFICIENCY_POLICY_V1} requires abstention.enabled=true "
            "(empty_context hard gate cannot be disabled)"
        )
    return SUFFICIENCY_POLICY_V1


def evaluate_runtime_sufficiency(
    settings: AppSettings,
    *,
    evidence_units: Sequence[EvidenceUnit],
) -> SufficiencyPolicyDecisionV1:
    """Resolve configured policy and evaluate against final EvidenceUnits."""
    require_runtime_sufficiency_policy(settings)
    return evaluate_sufficiency_policy_v1(evidence_units=evidence_units)


def decision_diagnostics(decision: SufficiencyPolicyDecisionV1) -> dict[str, object]:
    """Compact diagnostics block for GroundedAnswerResult.diagnostics."""
    return {
        "sufficiency_policy_contract": decision.policy_contract,
        "sufficiency_policy_version": decision.policy_version,
        "sufficient": decision.sufficient,
        "triggered_gates": list(decision.triggered_gates),
        "empty_context": decision.empty_context,
        "evidence_unit_count": decision.evidence_unit_count,
    }
