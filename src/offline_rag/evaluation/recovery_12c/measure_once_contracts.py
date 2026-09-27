"""Orchestration-layer persistence contracts for Slice 12C-2 measure-once."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from offline_rag.evaluation.generation_semantic.models import LabelCohort
from offline_rag.evaluation.recovery_12c.contracts import (
    FROZEN_GOLD_DATASET_ID_12C,
    NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES,
    AttemptObservationV1,
    GoldJudgmentRefV1,
    RecoveryEvalConclusionV1,
)
from offline_rag.recovery.contracts import RECOVERY_PROTOCOL_V1
from offline_rag.recovery.lineage import RecoveryLineageV1
from offline_rag.sufficiency.contracts import ExactNonBlankStr
from offline_rag.sufficiency.policy import EMPTY_CONTEXT_GATE_V1, SUFFICIENCY_POLICY_V1

RECOVERY_EVAL_PREPARED_CASE_V1 = "recovery-eval-prepared-case-v1"
RECOVERY_EVAL_CENSUS_STOP_V1 = "recovery-eval-census-stop-v1"
RECOVERY_EVAL_RUN_MANIFEST_V1 = "recovery-eval-run-manifest-v1"

AUTHORITY_BASELINE_SHA_12C = "47656d17b1e907f5965a60b0fe988a83942855ca"
ACCEPTED_HARNESS_SHA_12C = "c4f8734d57f45d3aa111997abf2bc8890322ff33"

RunStatusV1 = Literal[
    "completed",
    "stopped_not_evaluable",
    "failed_before_stage_a",
    "failed_after_stage_a",
]


class RecoveryEvalPreparedCaseV1(BaseModel):
    """Sanitized Stage-A-only case artifact (no recovery fields / body text)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-prepared-case-v1"] = RECOVERY_EVAL_PREPARED_CASE_V1
    case_id: ExactNonBlankStr
    adjudication_cohort: LabelCohort
    original_query: ExactNonBlankStr
    gold_judgments: list[GoldJudgmentRefV1] = Field(default_factory=list)
    gold_positive_chunk_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    initial: AttemptObservationV1
    triggered: bool
    initial_ranking: dict[str, float | None] | None = None

    @model_validator(mode="after")
    def _prepared_invariants(self) -> RecoveryEvalPreparedCaseV1:
        positives = sorted(
            j.chunk_id for j in self.gold_judgments if int(j.relevance) > 0
        )
        if list(self.gold_positive_chunk_ids) != positives:
            raise ValueError(
                "gold_positive_chunk_ids must equal positive gold_judgments chunk_ids"
            )
        if self.triggered != (not self.initial.sufficient):
            raise ValueError("triggered must equal (not initial.sufficient)")
        if self.original_query.strip() == "":
            raise ValueError("original_query must be non-blank")
        return self


class RetrievalStackIdentityV1(BaseModel):
    """Query-excluded retrieval/config stack identity."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: ExactNonBlankStr
    chunk_set_id: ExactNonBlankStr
    dense_index_id: ExactNonBlankStr
    lexical_index_id: ExactNonBlankStr
    fusion_config_hash: ExactNonBlankStr
    reranker_config_hash: ExactNonBlankStr
    context_config_hash: ExactNonBlankStr


class RecoveryEvalCensusStopAggregateV1(BaseModel):
    """Authoritative aggregate when Stage B is forbidden (T_H == 0)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-census-stop-v1"] = RECOVERY_EVAL_CENSUS_STOP_V1
    authoritative: Literal[True] = True
    run_status: Literal["stopped_not_evaluable"] = "stopped_not_evaluable"
    stage_b_executed: Literal[False] = False
    total_case_count: int
    human_reviewed_count: int
    assistant_only_count: int
    human_stage_a_trigger_count: int
    assistant_stage_a_trigger_count: int
    measured_recovery_case_count: Literal[0] = 0
    rewrite_call_count: Literal[0] = 0
    recovery_retrieval_attempt_count: Literal[0] = 0
    conclusion: RecoveryEvalConclusionV1
    stop_reason: Literal["not_evaluable_no_human_recovery_opportunities"] = (
        NOT_EVALUABLE_NO_HUMAN_RECOVERY_OPPORTUNITIES
    )
    gold_dataset_id: ExactNonBlankStr
    cohort_map_identity_hash: ExactNonBlankStr
    prepared_case_set_hash: ExactNonBlankStr
    rewriter_config_hash: ExactNonBlankStr
    evaluation_identity_hash: ExactNonBlankStr
    retrieval_lineage: RetrievalStackIdentityV1
    sufficiency_policy: Literal["sufficiency-v1"] = SUFFICIENCY_POLICY_V1
    sufficiency_gate: Literal["empty_context_v1"] = EMPTY_CONTEXT_GATE_V1
    recovery_protocol: Literal["recovery-protocol-v1"] = RECOVERY_PROTOCOL_V1
    trigger_census_artifact: ExactNonBlankStr = "trigger_census.json"
    experimental_limitation: str = (
        "Current Gold fixture does not provide authoritative "
        "unanswerable/negative truth; 12C cannot establish false-recovery "
        "rate on genuinely unanswerable questions."
    )

    @model_validator(mode="after")
    def _census_stop_invariants(self) -> RecoveryEvalCensusStopAggregateV1:
        if self.total_case_count != (
            self.human_reviewed_count + self.assistant_only_count
        ):
            raise ValueError("human + assistant counts must equal total_case_count")
        if self.human_stage_a_trigger_count != 0:
            raise ValueError(
                "census-stop aggregate requires human_stage_a_trigger_count == 0"
            )
        if self.gold_dataset_id != FROZEN_GOLD_DATASET_ID_12C:
            raise ValueError("census-stop aggregate requires frozen Gold dataset ID")
        if (
            self.conclusion
            != RecoveryEvalConclusionV1.INSUFFICIENT_EVIDENCE_FOR_RECOVERY_EFFICACY
        ):
            raise ValueError(
                "census-stop aggregate conclusion must be "
                "insufficient_evidence_for_recovery_efficacy"
            )
        for name in (
            "total_case_count",
            "human_reviewed_count",
            "assistant_only_count",
            "assistant_stage_a_trigger_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0")
        return self


class RewriterManifestIdentityV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ExactNonBlankStr
    adapter_contract: ExactNonBlankStr
    base_url: ExactNonBlankStr
    model: ExactNonBlankStr
    network_policy: ExactNonBlankStr
    prompt_contract: ExactNonBlankStr
    output_contract: ExactNonBlankStr


class RecoveryEvalRunManifestV1(BaseModel):
    """Identity/provenance-only run manifest (no secrets / evidence text)."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["recovery-eval-run-manifest-v1"] = RECOVERY_EVAL_RUN_MANIFEST_V1
    authority_baseline_sha: ExactNonBlankStr
    accepted_harness_sha: ExactNonBlankStr
    run_status: RunStatusV1
    gold_dataset_id: ExactNonBlankStr | None = None
    cohort_map_identity_hash: ExactNonBlankStr | None = None
    prepared_case_set_hash: ExactNonBlankStr | None = None
    recovery_rewriter_config_hash: ExactNonBlankStr | None = None
    recovery_eval_identity_hash: ExactNonBlankStr | None = None
    retrieval_lineage: RetrievalStackIdentityV1 | None = None
    rewriter: RewriterManifestIdentityV1 | None = None
    stage_b_executed: bool = False
    case_record_status: ExactNonBlankStr
    case_record_artifact: ExactNonBlankStr | None = None
    prepared_case_artifact: ExactNonBlankStr | None = None
    started_at: ExactNonBlankStr | None = None
    completed_at: ExactNonBlankStr | None = None
    failure_message: ExactNonBlankStr | None = None

    @field_validator("authority_baseline_sha", "accepted_harness_sha")
    @classmethod
    def _known_anchors(cls, value: str) -> str:
        return value


def stack_identity_from_lineage(lineage: RecoveryLineageV1) -> RetrievalStackIdentityV1:
    return RetrievalStackIdentityV1(
        corpus_id=lineage.corpus_id,
        chunk_set_id=lineage.chunk_set_id,
        dense_index_id=lineage.dense_index_id,
        lexical_index_id=lineage.lexical_index_id,
        fusion_config_hash=lineage.fusion_config_hash,
        reranker_config_hash=lineage.reranker_config_hash,
        context_config_hash=lineage.context_config_hash,
    )
