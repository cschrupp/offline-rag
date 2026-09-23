"""Sufficiency snapshot / manifest / failure-record contracts (11A-2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from offline_rag.domain.types import NonNegativeInt
from offline_rag.sufficiency.config_hash import authoritative_observation_config_hash
from offline_rag.sufficiency.contracts import (
    SUFFICIENCY_OBSERVATION_V1,
    ExactNonBlankStr,
    SufficiencyError,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
    SufficiencyValidationError,
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
    snapshot = SufficiencyEvalContextSnapshotV1(
        suffctx_id=build_suffctx_id(payload),
        provenance=provenance,
        observation=observation,
        audit=audit or SufficiencySnapshotAuditV1(),
    )
    validate_sufficiency_snapshot(snapshot)
    return snapshot


def validate_sufficiency_snapshot(
    snapshot: SufficiencyEvalContextSnapshotV1,
) -> None:
    """Fail-closed OD-11-14 / identity validation for a case snapshot."""
    if snapshot.contract != SUFFICIENCY_EVAL_CONTEXT_V1:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported snapshot contract",
            details=SufficiencyErrorDetailsV1(
                field_name="contract",
                expected=SUFFICIENCY_EVAL_CONTEXT_V1,
                actual=snapshot.contract,
            ),
        )
    if snapshot.observation.observation_contract != SUFFICIENCY_OBSERVATION_V1:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported observation_contract on snapshot",
            details=SufficiencyErrorDetailsV1(
                field_name="observation_contract",
                expected=SUFFICIENCY_OBSERVATION_V1,
                actual=snapshot.observation.observation_contract,
            ),
        )
    expected_hash = authoritative_observation_config_hash()
    if snapshot.observation.observation_config_hash != expected_hash:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONFIG,
            "unsupported observation_config_hash on snapshot",
            details=SufficiencyErrorDetailsV1(
                field_name="observation_config_hash",
                expected=expected_hash,
                actual=snapshot.observation.observation_config_hash,
            ),
        )
    try:
        validate_observation_against_provenance(
            snapshot.observation, snapshot.provenance
        )
    except SufficiencyValidationError as exc:
        raise SufficiencyArtifactError(
            exc.code,
            exc.message,
            details=exc.details,
            cause=exc,
        ) from exc

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


def _canonical_expected_case_ids(case_ids: list[str]) -> list[str]:
    return sorted(case_ids)


def _canonical_attempt_groups(
    groups: list[SufficiencyAttemptGroupV1],
) -> list[SufficiencyAttemptGroupV1]:
    return sorted(groups, key=lambda item: item.case_id)


def _canonical_failures(
    failures: list[SufficiencyFailureRecordV1],
) -> list[SufficiencyFailureRecordV1]:
    return sorted(failures, key=lambda item: (item.case_id, item.failure_stage))


def derive_manifest_accounting(
    *,
    expected_case_ids: list[str],
    attempt_groups: list[SufficiencyAttemptGroupV1],
    failures: list[SufficiencyFailureRecordV1],
) -> dict[str, Any]:
    """Recompute derived manifesto accounting from semantic contents."""
    ordered_expected = _canonical_expected_case_ids(expected_case_ids)
    successful_ids = {group.case_id for group in attempt_groups}
    failed_ids = {failure.case_id for failure in failures}
    expected_count = len(ordered_expected)
    successful_count = len(successful_ids)
    failed_count = len(failed_ids)
    coverage_complete = (successful_ids | failed_ids) == set(ordered_expected)
    authoritative = (
        successful_count == expected_count
        and failed_count == 0
        and successful_ids == set(ordered_expected)
        and coverage_complete
    )
    return {
        "expected_case_ids": ordered_expected,
        "successful_case_ids": sorted(successful_ids),
        "failed_case_ids": sorted(failed_ids),
        "expected_case_count": expected_count,
        "successful_case_count": successful_count,
        "failed_case_count": failed_count,
        "coverage_complete": coverage_complete,
        "authoritative_for_11b": authoritative,
    }


def validate_sufficiency_manifest(
    manifest: SufficiencyEvalContextManifestV1,
) -> None:
    """Fail-closed validation of manifesto identity, order, and derived state."""
    if manifest.contract != SUFFICIENCY_EVAL_CONTEXT_MANIFEST_V1:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported manifesto contract",
            details=SufficiencyErrorDetailsV1(
                field_name="contract",
                expected=SUFFICIENCY_EVAL_CONTEXT_MANIFEST_V1,
                actual=manifest.contract,
            ),
        )
    if not manifest.expected_case_ids:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_ids must be non-empty",
            details=SufficiencyErrorDetailsV1(field_name="expected_case_ids"),
        )
    if len(set(manifest.expected_case_ids)) != len(manifest.expected_case_ids):
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_ids must be unique",
            details=SufficiencyErrorDetailsV1(field_name="expected_case_ids"),
        )

    canonical_expected = _canonical_expected_case_ids(list(manifest.expected_case_ids))
    if list(manifest.expected_case_ids) != canonical_expected:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_ids must be in canonical ascending order",
            details=SufficiencyErrorDetailsV1(field_name="expected_case_ids"),
        )

    canonical_groups = _canonical_attempt_groups(list(manifest.attempt_groups))
    if [g.model_dump(mode="json") for g in manifest.attempt_groups] != [
        g.model_dump(mode="json") for g in canonical_groups
    ]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest attempt_groups must be in canonical case_id order",
            details=SufficiencyErrorDetailsV1(field_name="attempt_groups"),
        )

    canonical_failures = _canonical_failures(list(manifest.failures))
    if [f.model_dump(mode="json") for f in manifest.failures] != [
        f.model_dump(mode="json") for f in canonical_failures
    ]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest failures must be in canonical order",
            details=SufficiencyErrorDetailsV1(field_name="failures"),
        )

    seen_cases: set[str] = set()
    for group in manifest.attempt_groups:
        _validate_slice11_attempt_group(group)
        if group.case_id in seen_cases:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_ATTEMPT_FIELDS,
                "duplicate case_id among attempt groups",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=group.case_id
                ),
            )
        seen_cases.add(group.case_id)
        if group.case_id not in canonical_expected:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "snapshot case_id is outside expected population",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=group.case_id
                ),
            )

    seen_failure_cases: set[str] = set()
    for failure in manifest.failures:
        if failure.case_id in seen_failure_cases:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "at most one terminal failure record per case is allowed",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=failure.case_id
                ),
            )
        seen_failure_cases.add(failure.case_id)
        if failure.case_id not in canonical_expected:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "failure case_id is outside expected population",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=failure.case_id
                ),
            )

    successful_ids = {group.case_id for group in manifest.attempt_groups}
    failed_ids = {failure.case_id for failure in manifest.failures}
    if successful_ids & failed_ids:
        overlap = min(successful_ids & failed_ids)
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "case cannot be both successful snapshot and failure record",
            details=SufficiencyErrorDetailsV1(field_name="case_id", actual=overlap),
        )

    accounting = derive_manifest_accounting(
        expected_case_ids=list(manifest.expected_case_ids),
        attempt_groups=list(manifest.attempt_groups),
        failures=list(manifest.failures),
    )
    if manifest.expected_case_count != accounting["expected_case_count"]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest expected_case_count does not match recomputation",
            details=SufficiencyErrorDetailsV1(
                field_name="expected_case_count",
                expected=accounting["expected_case_count"],
                actual=manifest.expected_case_count,
            ),
        )
    if manifest.successful_case_count != accounting["successful_case_count"]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest successful_case_count does not match recomputation",
            details=SufficiencyErrorDetailsV1(
                field_name="successful_case_count",
                expected=accounting["successful_case_count"],
                actual=manifest.successful_case_count,
            ),
        )
    if manifest.failed_case_count != accounting["failed_case_count"]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest failed_case_count does not match unique failed cases",
            details=SufficiencyErrorDetailsV1(
                field_name="failed_case_count",
                expected=accounting["failed_case_count"],
                actual=manifest.failed_case_count,
            ),
        )
    if manifest.authoritative_for_11b != accounting["authoritative_for_11b"]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifest authoritative_for_11b does not match recomputation",
            details=SufficiencyErrorDetailsV1(
                field_name="authoritative_for_11b",
                expected=accounting["authoritative_for_11b"],
                actual=manifest.authoritative_for_11b,
            ),
        )

    expected_id = build_suffctxrun_id(
        build_suffctxrun_semantic_payload(
            shared_lineage=manifest.shared_lineage,
            attempt_groups=list(manifest.attempt_groups),
            failures=list(manifest.failures),
            expected_case_ids=list(manifest.expected_case_ids),
        )
    )
    if manifest.suffctxrun_id != expected_id:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "manifesto suffctxrun_id does not match semantic payload",
            details=SufficiencyErrorDetailsV1(
                field_name="suffctxrun_id",
                expected=expected_id,
                actual=manifest.suffctxrun_id,
            ),
        )


def build_sufficiency_manifest(
    *,
    snapshots: list[SufficiencyEvalContextSnapshotV1],
    failures: list[SufficiencyFailureRecordV1],
    expected_case_ids: list[str],
    shared_lineage: SufficiencySharedLineageV1 | None = None,
    audit: SufficiencyManifestAuditV1 | None = None,
) -> SufficiencyEvalContextManifestV1:
    """Build a Slice-11-only validated manifesto with content-addressed ID."""
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

    ordered_expected = _canonical_expected_case_ids(expected_case_ids)
    groups: list[SufficiencyAttemptGroupV1] = []
    seen_case_attempts: set[tuple[str, int]] = set()
    lineage: SufficiencySharedLineageV1 | None = shared_lineage

    for snapshot in snapshots:
        validate_sufficiency_snapshot(snapshot)
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
        _validate_slice11_attempt_group(group)
        groups.append(group)

    if lineage is None:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.MISSING_REQUIRED_LINEAGE,
            "manifest requires shared lineage from snapshots or an explicit value",
            details=SufficiencyErrorDetailsV1(field_name="shared_lineage"),
        )

    groups = _canonical_attempt_groups(groups)
    ordered_failures = _canonical_failures(failures)

    seen_failure_cases: set[str] = set()
    for failure in ordered_failures:
        if failure.case_id in seen_failure_cases:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "at most one terminal failure record per case is allowed",
                details=SufficiencyErrorDetailsV1(
                    field_name="case_id", actual=failure.case_id
                ),
            )
        seen_failure_cases.add(failure.case_id)

    accounting = derive_manifest_accounting(
        expected_case_ids=ordered_expected,
        attempt_groups=groups,
        failures=ordered_failures,
    )
    successful_ids = set(accounting["successful_case_ids"])
    failed_ids = set(accounting["failed_case_ids"])
    if successful_ids & failed_ids:
        overlap = min(successful_ids & failed_ids)
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "case cannot be both successful snapshot and failure record",
            details=SufficiencyErrorDetailsV1(field_name="case_id", actual=overlap),
        )
    for case_id in successful_ids | failed_ids:
        if case_id not in ordered_expected:
            raise SufficiencyArtifactError(
                SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
                "case_id is outside expected population",
                details=SufficiencyErrorDetailsV1(field_name="case_id", actual=case_id),
            )

    payload = build_suffctxrun_semantic_payload(
        shared_lineage=lineage,
        attempt_groups=groups,
        failures=ordered_failures,
        expected_case_ids=ordered_expected,
    )
    manifest = SufficiencyEvalContextManifestV1(
        suffctxrun_id=build_suffctxrun_id(payload),
        shared_lineage=lineage,
        attempt_groups=groups,
        failures=ordered_failures,
        expected_case_ids=ordered_expected,
        expected_case_count=accounting["expected_case_count"],
        successful_case_count=accounting["successful_case_count"],
        failed_case_count=accounting["failed_case_count"],
        authoritative_for_11b=accounting["authoritative_for_11b"],
        audit=audit or SufficiencyManifestAuditV1(),
    )
    validate_sufficiency_manifest(manifest)
    return manifest


def require_authoritative_manifest(
    manifest: SufficiencyEvalContextManifestV1,
) -> None:
    """Reject incomplete manifests for frozen 11B analysis (OD-11-28)."""
    validate_sufficiency_manifest(manifest)
    accounting = derive_manifest_accounting(
        expected_case_ids=list(manifest.expected_case_ids),
        attempt_groups=list(manifest.attempt_groups),
        failures=list(manifest.failures),
    )
    if not accounting["authoritative_for_11b"]:
        raise SufficiencyArtifactError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "incomplete manifesto is not authoritative for 11B",
            details=SufficiencyErrorDetailsV1(
                field_name="authoritative_for_11b",
                expected=True,
                actual=False,
            ),
        )
