"""Sufficiency snapshot / manifest / failure-record contracts (11A-2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonNegativeInt
from offline_rag.sufficiency.config_hash import authoritative_observation_config_hash
from offline_rag.sufficiency.contracts import (
    ExactNonBlankStr,
    SufficiencyError,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
)
from offline_rag.sufficiency.derive import (
    derive_sufficiency_observation,
    validate_observation_against_provenance,
)
from offline_rag.sufficiency.ids import (
    build_suffctx_id,
    build_suffctx_semantic_payload,
    build_suffctxrun_id,
)

SUFFICIENCY_EVAL_CONTEXT_V1 = "sufficiency-eval-context-v1"
SUFFICIENCY_EVAL_CONTEXT_MANIFEST_V1 = (
    "offline-rag-sufficiency-eval-context-manifest-v1"
)
SUFFICIENCY_FAILURE_RECORD_V1 = "sufficiency-failure-record-v1"


class SufficiencyArtifactError(Exception):
    """Fail-closed artifact/manifest construction or validation error."""

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


class SufficiencySnapshotAuditV1(BaseModel):
    """Non-identity audit metadata for a case snapshot (OD-11-8)."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime | None = None
    latency_ms: float | None = None
    source_path: str | None = None
    host: str | None = None


class SufficiencyEvalContextSnapshotV1(BaseModel):
    """Per-case gold-free sufficiency observation snapshot."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["sufficiency-eval-context-v1"] = SUFFICIENCY_EVAL_CONTEXT_V1
    suffctx_id: ExactNonBlankStr
    provenance: SufficiencyProvenanceV1
    observation: SufficiencyObservationV1
    audit: SufficiencySnapshotAuditV1 = Field(
        default_factory=SufficiencySnapshotAuditV1
    )


class SufficiencyAttemptRefV1(BaseModel):
    """One retrieval/context attempt reference inside an attempt group."""

    model_config = ConfigDict(extra="forbid")

    attempt_number: NonNegativeInt
    attempt_role: Literal["initial", "recovery"]
    suffctx_id: ExactNonBlankStr


class SufficiencyAttemptGroupV1(BaseModel):
    """Ordered attempts for one case (multi-attempt-capable; Slice 11 = one)."""

    model_config = ConfigDict(extra="forbid")

    case_id: ExactNonBlankStr
    original_query: ExactNonBlankStr
    attempts: list[SufficiencyAttemptRefV1] = Field(min_length=1)


class SufficiencySharedLineageV1(BaseModel):
    """Shared retrieval/context/observation lineage for one manifest."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: ExactNonBlankStr
    chunk_set_id: ExactNonBlankStr
    dense_index_id: ExactNonBlankStr
    lexical_index_id: ExactNonBlankStr
    fusion_config_hash: ExactNonBlankStr
    reranker_config_hash: ExactNonBlankStr
    context_config_hash: ExactNonBlankStr
    observation_contract: ExactNonBlankStr
    observation_config_hash: ExactNonBlankStr


class SufficiencyFailureRecordV1(BaseModel):
    """Persisted failure envelope for a case with no suffctx_ artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sufficiency-failure-record-v1"] = (
        SUFFICIENCY_FAILURE_RECORD_V1
    )
    case_id: ExactNonBlankStr
    original_query: ExactNonBlankStr | None = None
    failure_stage: ExactNonBlankStr
    reason_code: SufficiencyErrorCodeV1
    diagnostic: str
    details: SufficiencyErrorDetailsV1 | None = None


class SufficiencyManifestAuditV1(BaseModel):
    """Non-identity audit metadata for a run manifest."""

    model_config = ConfigDict(extra="forbid")

    created_at: datetime | None = None
    output_path: str | None = None
    host: str | None = None


class SufficiencyEvalContextManifestV1(BaseModel):
    """Run manifesto binding shared lineage + attempt groups + failures."""

    model_config = ConfigDict(extra="forbid")

    contract: Literal["offline-rag-sufficiency-eval-context-manifest-v1"] = (
        SUFFICIENCY_EVAL_CONTEXT_MANIFEST_V1
    )
    suffctxrun_id: ExactNonBlankStr
    shared_lineage: SufficiencySharedLineageV1
    attempt_groups: list[SufficiencyAttemptGroupV1] = Field(default_factory=list)
    failures: list[SufficiencyFailureRecordV1] = Field(default_factory=list)
    expected_case_ids: list[ExactNonBlankStr] = Field(default_factory=list)
    expected_case_count: NonNegativeInt = 0
    successful_case_count: NonNegativeInt = 0
    failed_case_count: NonNegativeInt = 0
    authoritative_for_11b: bool = False
    audit: SufficiencyManifestAuditV1 = Field(
        default_factory=SufficiencyManifestAuditV1
    )


def shared_lineage_from_provenance(
    provenance: SufficiencyProvenanceV1,
    *,
    observation_contract: str,
    observation_config_hash: str,
) -> SufficiencySharedLineageV1:
    return SufficiencySharedLineageV1(
        corpus_id=provenance.corpus_id,
        chunk_set_id=provenance.chunk_set_id,
        dense_index_id=provenance.dense_index_id,
        lexical_index_id=provenance.lexical_index_id,
        fusion_config_hash=provenance.fusion_config_hash,
        reranker_config_hash=provenance.reranker_config_hash,
        context_config_hash=provenance.context_config_hash,
        observation_contract=observation_contract,
        observation_config_hash=observation_config_hash,
    )


def build_failure_record(
    *,
    case_id: str,
    failure_stage: str,
    error: SufficiencyError | SufficiencyArtifactError,
    original_query: str | None = None,
) -> SufficiencyFailureRecordV1:
    """Serialize a domain/artifact error into a persistence failure record."""
    return SufficiencyFailureRecordV1(
        case_id=case_id,
        original_query=original_query,
        failure_stage=failure_stage,
        reason_code=error.code,
        diagnostic=error.message,
        details=error.details,
    )


def build_sufficiency_snapshot(
    provenance: SufficiencyProvenanceV1,
    *,
    observation: SufficiencyObservationV1 | None = None,
    audit: SufficiencySnapshotAuditV1 | None = None,
) -> SufficiencyEvalContextSnapshotV1:
    """Derive/validate observation and build an immutable case snapshot.

    Raises domain/artifact errors; callers must not write a partial artifact.
    """
    if observation is None:
        observation = derive_sufficiency_observation(provenance)
    else:
        validate_observation_against_provenance(observation, provenance)

    expected_hash = authoritative_observation_config_hash()
    if observation.observation_config_hash != expected_hash:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONFIG,
            "snapshot observation_config_hash is unsupported by this software",
            details=SufficiencyErrorDetailsV1(
                field_name="observation_config_hash",
                expected=expected_hash,
                actual=observation.observation_config_hash,
            ),
        )

    payload = build_suffctx_semantic_payload(provenance, observation)
    suffctx_id = build_suffctx_id(payload)
    return SufficiencyEvalContextSnapshotV1(
        suffctx_id=suffctx_id,
        provenance=provenance,
        observation=observation,
        audit=audit or SufficiencySnapshotAuditV1(),
    )


def _lineage_tuple(lineage: SufficiencySharedLineageV1) -> tuple[str, ...]:
    return (
        lineage.corpus_id,
        lineage.chunk_set_id,
        lineage.dense_index_id,
        lineage.lexical_index_id,
        lineage.fusion_config_hash,
        lineage.reranker_config_hash,
        lineage.context_config_hash,
        lineage.observation_contract,
        lineage.observation_config_hash,
    )


def build_suffctxrun_semantic_payload(
    *,
    shared_lineage: SufficiencySharedLineageV1,
    attempt_groups: list[SufficiencyAttemptGroupV1],
    failures: list[SufficiencyFailureRecordV1],
    expected_case_ids: list[str],
) -> dict[str, Any]:
    """Explicit allowlisted semantic payload for ``suffctxrun_`` identity."""
    return {
        "contract": SUFFICIENCY_EVAL_CONTEXT_MANIFEST_V1,
        "shared_lineage": shared_lineage.model_dump(mode="json"),
        "expected_case_ids": list(expected_case_ids),
        "attempt_groups": [group.model_dump(mode="json") for group in attempt_groups],
        "failures": [
            {
                "case_id": failure.case_id,
                "original_query": failure.original_query,
                "failure_stage": failure.failure_stage,
                "reason_code": failure.reason_code.value,
                "details": (
                    None
                    if failure.details is None
                    else failure.details.model_dump(mode="json")
                ),
            }
            for failure in failures
        ],
    }


def _validate_slice11_attempt_group(group: SufficiencyAttemptGroupV1) -> None:
    if len(group.attempts) != 1:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
            "Slice 11 manifests require exactly one attempt per case",
            details=SufficiencyErrorDetailsV1(
                field_name="attempts",
                expected=1,
                actual=len(group.attempts),
            ),
        )
    attempt = group.attempts[0]
    if attempt.attempt_number != 0 or attempt.attempt_role != "initial":
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
            "Slice 11 attempts must be attempt_number=0 role=initial",
            details=SufficiencyErrorDetailsV1(
                field_name="attempt_role",
                expected="initial",
                actual=attempt.attempt_role,
                attempt_number=attempt.attempt_number,
            ),
        )


def build_sufficiency_manifest(
    *,
    snapshots: list[SufficiencyEvalContextSnapshotV1],
    failures: list[SufficiencyFailureRecordV1],
    expected_case_ids: list[str],
    shared_lineage: SufficiencySharedLineageV1 | None = None,
    audit: SufficiencyManifestAuditV1 | None = None,
    enforce_slice11_initial_only: bool = True,
) -> SufficiencyEvalContextManifestV1:
    """Build a validated run manifesto; compute content-addressed suffctxrun_id."""
    if not expected_case_ids:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_ids must be non-empty",
            details=SufficiencyErrorDetailsV1(field_name="expected_case_ids"),
        )
    if len(set(expected_case_ids)) != len(expected_case_ids):
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_ids must be unique",
            details=SufficiencyErrorDetailsV1(field_name="expected_case_ids"),
        )

    ordered_expected = sorted(expected_case_ids)
    groups: list[SufficiencyAttemptGroupV1] = []
    seen_case_attempts: set[tuple[str, int]] = set()
    lineage: SufficiencySharedLineageV1 | None = shared_lineage

    for snapshot in snapshots:
        provenance = snapshot.provenance
        snap_lineage = shared_lineage_from_provenance(
            provenance,
            observation_contract=snapshot.observation.observation_contract,
            observation_config_hash=snapshot.observation.observation_config_hash,
        )
        if lineage is None:
            lineage = snap_lineage
        elif _lineage_tuple(lineage) != _lineage_tuple(snap_lineage):
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "mixed shared lineage across snapshots is not allowed",
                details=SufficiencyErrorDetailsV1(
                    field_name="shared_lineage",
                    actual=provenance.case_id,
                ),
            )

        expected_id = build_suffctx_id(
            build_suffctx_semantic_payload(snapshot.provenance, snapshot.observation)
        )
        if snapshot.suffctx_id != expected_id:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "snapshot suffctx_id does not match semantic payload",
                details=SufficiencyErrorDetailsV1(
                    field_name="suffctx_id",
                    expected=expected_id,
                    actual=snapshot.suffctx_id,
                ),
            )

        key = (provenance.case_id, provenance.attempt_number)
        if key in seen_case_attempts:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
                "duplicate (case_id, attempt_number) in manifest snapshots",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id",
                    actual=provenance.case_id,
                    attempt_number=provenance.attempt_number,
                ),
            )
        seen_case_attempts.add(key)

        group = SufficiencyAttemptGroupV1(
            case_id=provenance.case_id,
            original_query=provenance.original_query,
            attempts=[
                SufficiencyAttemptRefV1(
                    attempt_number=provenance.attempt_number,
                    attempt_role=provenance.attempt_role,
                    suffctx_id=snapshot.suffctx_id,
                )
            ],
        )
        if enforce_slice11_initial_only:
            _validate_slice11_attempt_group(group)
        groups.append(group)

    if lineage is None:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.MISSING_REQUIRED_LINEAGE,
            "manifest requires shared lineage from snapshots or an explicit value",
            details=SufficiencyErrorDetailsV1(field_name="shared_lineage"),
        )

    # Canonical case_id ascending order for attempt groups (OD-11-7).
    groups.sort(key=lambda item: item.case_id)
    ordered_failures = sorted(
        failures, key=lambda item: (item.case_id, item.failure_stage)
    )

    successful_ids = {group.case_id for group in groups}
    failed_ids = {failure.case_id for failure in ordered_failures}
    if successful_ids & failed_ids:
        overlap = min(successful_ids & failed_ids)
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "case cannot be both successful snapshot and failure record",
            details=SufficiencyErrorDetailsV1(field_name="case_id", actual=overlap),
        )

    for group in groups:
        if group.case_id not in ordered_expected:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "snapshot case_id is outside expected population",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=group.case_id
                ),
            )
    for failure in ordered_failures:
        if failure.case_id not in ordered_expected:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "failure case_id is outside expected population",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=failure.case_id
                ),
            )

    expected_count = len(ordered_expected)
    successful_count = len(groups)
    failed_count = len(ordered_failures)
    covered = successful_ids | failed_ids
    if covered != set(ordered_expected):
        # Incomplete coverage is allowed as an execution record, but not authoritative.
        pass

    authoritative = (
        successful_count == expected_count
        and failed_count == 0
        and successful_ids == set(ordered_expected)
    )

    payload = build_suffctxrun_semantic_payload(
        shared_lineage=lineage,
        attempt_groups=groups,
        failures=ordered_failures,
        expected_case_ids=ordered_expected,
    )
    suffctxrun_id = build_suffctxrun_id(payload)
    return SufficiencyEvalContextManifestV1(
        suffctxrun_id=suffctxrun_id,
        shared_lineage=lineage,
        attempt_groups=groups,
        failures=ordered_failures,
        expected_case_ids=ordered_expected,
        expected_case_count=expected_count,
        successful_case_count=successful_count,
        failed_case_count=failed_count,
        authoritative_for_11b=authoritative,
        audit=audit or SufficiencyManifestAuditV1(),
    )


def require_authoritative_manifest(
    manifest: SufficiencyEvalContextManifestV1,
) -> None:
    """Reject incomplete manifests for frozen 11B analysis (OD-11-28)."""
    if not manifest.authoritative_for_11b:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "incomplete manifesto is not authoritative for 11B",
            details=SufficiencyErrorDetailsV1(
                field_name="authoritative_for_11b",
                expected=True,
                actual=False,
            ),
        )
