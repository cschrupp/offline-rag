"""Typed sufficiency provenance/observation contracts and domain errors."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from offline_rag.domain.types import NonNegativeInt, PositiveInt

SUFFICIENCY_OBSERVATION_V1 = "sufficiency-observation-v1"
SUFFICIENCY_PROVENANCE_V1 = "sufficiency-provenance-v1"
SUFFICIENCY_ERROR_DETAILS_V1 = "sufficiency-error-details-v1"
SUFFICIENCY_ATTEMPT_ROLE_INITIAL = "initial"
SUFFICIENCY_ATTEMPT_ROLE_RECOVERY = "recovery"


def _exact_nonblank_str(value: Any) -> str:
    """Require a nonblank string without stripping or rewriting it."""
    if not isinstance(value, str):
        raise TypeError("must be a string")
    if value == "" or value.strip() == "":
        raise ValueError("must be a nonblank string")
    return value


ExactNonBlankStr = Annotated[str, AfterValidator(_exact_nonblank_str)]


class SufficiencyErrorCodeV1(str, Enum):
    """Serialized string values are the stable external contract (OD-11-38)."""

    MISSING_REQUIRED_LINEAGE = "missing_required_lineage"
    MISSING_REQUIRED_PROVENANCE = "missing_required_provenance"
    INVALID_ATTEMPT_FIELDS = "invalid_attempt_fields"
    INVALID_ANCHOR_ORDER = "invalid_anchor_order"
    MISSING_DOCUMENT_ID = "missing_document_id"
    INVALID_SECTION_PATH = "invalid_section_path"
    INVALID_RERANKER_SCORE = "invalid_reranker_score"
    INVALID_RRF_SCORE = "invalid_rrf_score"
    INVALID_BRANCH_SCORE = "invalid_branch_score"
    OBSERVATION_RECOMPUTE_MISMATCH = "observation_recompute_mismatch"
    UNSUPPORTED_OBSERVATION_CONTRACT = "unsupported_observation_contract"
    UNSUPPORTED_OBSERVATION_CONFIG = "unsupported_observation_config"
    INVALID_SEMANTIC_PAYLOAD = "invalid_semantic_payload"
    DUPLICATE_ANCHOR_CHUNK_ID = "duplicate_anchor_chunk_id"
    DUPLICATE_EVIDENCE_UNIT_ID = "duplicate_evidence_unit_id"
    INVALID_RERANK_RANK = "invalid_rerank_rank"
    INVALID_BRANCH_RANK = "invalid_branch_rank"
    INVALID_BRANCH_RANK_SCORE_PAIR = "invalid_branch_rank_score_pair"
    INVALID_HYBRID_RANK = "invalid_hybrid_rank"
    INVALID_DIAGNOSTICS = "invalid_diagnostics"
    INVALID_QUERY_FIELDS = "invalid_query_fields"


class SufficiencyErrorDetailsV1(BaseModel):
    """Narrow optional structured diagnostics (OD-11-37)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sufficiency-error-details-v1"] = (
        SUFFICIENCY_ERROR_DETAILS_V1
    )
    field_name: str | None = None
    expected: str | int | float | bool | None = None
    actual: str | int | float | bool | None = None
    attempt_number: int | None = None


class SufficiencyError(Exception):
    """Base sufficiency domain error with stable reason code."""

    def __init__(
        self,
        code: SufficiencyErrorCodeV1,
        message: str,
        *,
        details: SufficiencyErrorDetailsV1 | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.__cause__ = cause


class SufficiencyDerivationError(SufficiencyError):
    """Raised when provenance cannot produce a valid observation."""


class SufficiencyValidationError(SufficiencyError):
    """Raised when stored observation fails recomputation validation."""


class SufficiencyAnchorProvenance(BaseModel):
    """Nested reranked-anchor projection (parent-versioned; OD-11-41)."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: ExactNonBlankStr
    rerank_rank: PositiveInt
    reranker_score: float
    hybrid_rank: PositiveInt
    rrf_score: float
    dense_rank: PositiveInt | None = None
    dense_score: float | None = None
    lexical_rank: PositiveInt | None = None
    lexical_score: float | None = None


class SufficiencyEvidenceUnitProvenance(BaseModel):
    """Nested final EvidenceUnit projection without body text (OD-11-42/43)."""

    model_config = ConfigDict(extra="forbid")

    evidence_unit_id: ExactNonBlankStr
    document_id: ExactNonBlankStr
    section_path: list[str] = Field(default_factory=list)
    source_chunk_id: ExactNonBlankStr
    primary_anchor_chunk_id: ExactNonBlankStr

    @field_validator("section_path", mode="before")
    @classmethod
    def _canonicalize_section_path(cls, value: Any) -> list[str]:
        # OD-11-23: missing/None -> []; otherwise preserve segment strings exactly.
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("section_path must be a list of strings or null")
        for segment in value:
            if not isinstance(segment, str):
                raise TypeError("section_path segments must be strings")
        return list(value)


class SufficiencyAssemblyDiagnosticsV1(BaseModel):
    """Deterministic assembly diagnostics (OD-11-26)."""

    model_config = ConfigDict(extra="forbid")

    evidence_unit_count: NonNegativeInt = 0
    context_token_count: NonNegativeInt = 0
    clipping_occurred: bool = False
    budget_exhausted: bool = False
    stop_reason: ExactNonBlankStr = "completed"
    dedup_hits: NonNegativeInt = 0
    containment_suppressions: NonNegativeInt = 0


class SufficiencyProvenanceV1(BaseModel):
    """Neutral typed provenance input for observation derivation (OD-11-32)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sufficiency-provenance-v1"] = SUFFICIENCY_PROVENANCE_V1
    case_id: ExactNonBlankStr
    corpus_id: ExactNonBlankStr
    chunk_set_id: ExactNonBlankStr
    dense_index_id: ExactNonBlankStr
    lexical_index_id: ExactNonBlankStr
    fusion_config_hash: ExactNonBlankStr
    reranker_config_hash: ExactNonBlankStr
    context_config_hash: ExactNonBlankStr
    original_query: ExactNonBlankStr
    active_retrieval_query: ExactNonBlankStr
    attempt_number: NonNegativeInt
    attempt_role: Literal["initial", "recovery"]
    anchors: list[SufficiencyAnchorProvenance] = Field(default_factory=list)
    final_evidence_units: list[SufficiencyEvidenceUnitProvenance] = Field(
        default_factory=list
    )
    diagnostics: SufficiencyAssemblyDiagnosticsV1


class SufficiencyObservationV1(BaseModel):
    """Seven-feature OD-11-2 observation plus derivation identity."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sufficiency-observation-v1"] = SUFFICIENCY_OBSERVATION_V1
    observation_contract: Literal["sufficiency-observation-v1"] = (
        SUFFICIENCY_OBSERVATION_V1
    )
    observation_config_hash: ExactNonBlankStr
    empty_context: bool
    top_reranker_score: float | None = None
    top1_top2_margin: float | None = None
    top_anchor_cross_retriever_support: bool | None = None
    anchor_count: NonNegativeInt
    distinct_document_count: NonNegativeInt
    distinct_section_count: NonNegativeInt
