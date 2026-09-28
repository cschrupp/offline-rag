"""Slice 13A security evaluation contracts (OD-13-1 / OD-13-3 / OD-13-6).

Evaluation-layer only. Deterministic control-plane invariants are PASS/FAIL
truth. No NeMo, LangGraph, live recovery, or product recovery promotion.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.sufficiency.contracts import ExactNonBlankStr

ADVERSARIAL_FIXTURE_V1 = "adversarial-fixture-v1"
SECURITY_INVARIANT_REGISTRY_V1 = "security-invariant-registry-v1"
ADVERSARIAL_EVAL_RESULT_V1 = "adversarial-eval-result-v1"

SLICE13_BASELINE_SHA = "6a3806bdc89a17bcdf992dba068e843f8535de6a"
DESIGN_AUTHORITY_SHA_13 = "571882e062359e258f5843b4289b2f556d22d7f7"

AttackClassV1 = Literal[
    "ignore_instructions",
    "fake_system_message",
    "citation_manipulation",
    "prompt_extraction",
    "shell_tool_abuse",
    "arbitrary_file_access",
    "evidence_suppression",
]
PathUnderTestV1 = Literal["query_path", "recovery_path"]
EvidenceRoleV1 = Literal["benign", "adversarial"]
EvidencePlacementV1 = Literal[
    "retrieved_evidence_body",
    "retrieved_evidence_metadata",
    "recovery_rewriter_forbidden_input_probe",
]
RecoveryExecutionModeV1 = Literal["disabled", "harness_fake", "harness_live"]
RecoveryComponentV1 = Literal[
    "recovery_protocol",
    "rewriter_input",
    "recovery_rewriter",
    "recovery_retrieval",
]

LOCKED_INVARIANT_IDS_V1: tuple[str, ...] = (
    "retry_budget_immutable_v1",
    "corpus_scope_immutable_v1",
    "original_query_immutable_v1",
    "security_policy_immutable_v1",
    "no_unauthorized_capability_invocation_v1",
    "citation_scope_v1",
    "rewriter_input_isolation_v1",
    "evidence_surface_preserved_v1",
    "protected_prompt_canary_non_disclosure_v1",
)


class SecurityEvalError(RuntimeError):
    """Fail-closed Slice 13A security evaluation error."""


class InvariantStatusV1(str, Enum):
    HOLDS = "holds"
    VIOLATED = "violated"
    UNEVALUABLE = "unevaluable"


class FixtureOutcomeV1(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class AdversarialEvidenceUnitV1(BaseModel):
    """Untrusted evidence unit (benign or adversarial text)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: ExactNonBlankStr
    role: EvidenceRoleV1
    text: ExactNonBlankStr
    metadata: dict[str, Any] = Field(default_factory=dict)
    placement: EvidencePlacementV1


class AdversarialFixtureV1(BaseModel):
    """Authoritative adversarial-fixture-v1 record (OD-13-3)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["adversarial-fixture-v1"] = ADVERSARIAL_FIXTURE_V1
    fixture_id: ExactNonBlankStr
    fixture_identity_hash: ExactNonBlankStr
    attack_class: AttackClassV1
    path_under_test: PathUnderTestV1
    slice13_baseline_sha: ExactNonBlankStr
    design_authority_sha: ExactNonBlankStr
    user_query: ExactNonBlankStr
    allowed_citation_evidence_ids: list[ExactNonBlankStr] = Field(min_length=1)
    expected_invariant_ids: list[ExactNonBlankStr] = Field(min_length=1)
    evidence: list[AdversarialEvidenceUnitV1] = Field(min_length=1)

    @field_validator("allowed_citation_evidence_ids", "expected_invariant_ids")
    @classmethod
    def _no_blank_ids(cls, value: list[str]) -> list[str]:
        if any(not str(item).strip() for item in value):
            raise ValueError("IDs must be non-blank")
        return list(value)

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> AdversarialFixtureV1:
        evidence_ids = [unit.evidence_id for unit in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique within a fixture")
        allowed = set(self.allowed_citation_evidence_ids)
        missing = allowed - set(evidence_ids)
        if missing:
            raise ValueError(
                "allowed_citation_evidence_ids must reference evidence_id values "
                f"present in evidence[]; missing={sorted(missing)!r}"
            )
        if self.path_under_test == "recovery_path":
            placements = {unit.placement for unit in self.evidence}
            if "recovery_rewriter_forbidden_input_probe" not in placements:
                raise ValueError(
                    "recovery_path fixtures require at least one evidence unit with "
                    "placement=recovery_rewriter_forbidden_input_probe"
                )
        return self


class SecurityInvariantDefinitionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invariant_id: ExactNonBlankStr
    property: ExactNonBlankStr


class SecurityInvariantRegistryV1(BaseModel):
    """security-invariant-registry-v1 (OD-13-1)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["security-invariant-registry-v1"] = SECURITY_INVARIANT_REGISTRY_V1
    registry_hash: ExactNonBlankStr
    invariants: list[SecurityInvariantDefinitionV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> SecurityInvariantRegistryV1:
        ids = [item.invariant_id for item in self.invariants]
        if len(ids) != len(set(ids)):
            raise ValueError("invariant_id values must be unique in the registry")
        return self


class InvariantOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invariant_id: ExactNonBlankStr
    status: InvariantStatusV1
    detail: ExactNonBlankStr | None = None


class AdversarialEvalResultV1(BaseModel):
    """Minimal adversarial-eval-result-v1 for unit assertions (OD-13-6)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["adversarial-eval-result-v1"] = ADVERSARIAL_EVAL_RESULT_V1
    fixture_id: ExactNonBlankStr
    fixture_identity_hash: ExactNonBlankStr
    registry_hash: ExactNonBlankStr
    outcome: FixtureOutcomeV1
    invariant_outcomes: list[InvariantOutcomeV1] = Field(min_length=1)
    product_default_recovery_enabled: bool = False
    recovery_execution_mode: RecoveryExecutionModeV1
    recovery_components_entered: list[RecoveryComponentV1] = Field(default_factory=list)
    failure_kind: (
        Literal["invariant_violation", "invariant_unevaluable", "validation_error"]
        | None
    ) = None


class SecurityObservationV1(BaseModel):
    """Harness-owned observations required by invariant evaluators.

    Missing fields needed by a requested invariant yield ``unevaluable``
    (fail-closed), never silent skip.
    """

    model_config = ConfigDict(extra="forbid")

    configured_retry_budget: int | None = None
    observed_retry_budget: int | None = None
    configured_corpus_scope: ExactNonBlankStr | None = None
    observed_corpus_scope: ExactNonBlankStr | None = None
    observed_original_query: ExactNonBlankStr | None = None
    configured_security_policy: dict[str, Any] | None = None
    observed_security_policy: dict[str, Any] | None = None
    capability_invocations: list[str] | None = None
    emitted_citation_ids: list[str] | None = None
    rewriter_surface_texts: list[str] | None = None
    required_evidence_surface_ids: list[str] | None = None
    observed_evidence_surface_ids: list[str] | None = None
    protected_prompt_canary: ExactNonBlankStr | None = None
    generated_output_text: str | None = None
    product_default_recovery_enabled: bool = False
    recovery_execution_mode: RecoveryExecutionModeV1 = "disabled"
    recovery_components_entered: list[RecoveryComponentV1] = Field(default_factory=list)
