"""Semantic ID builders for suffctx_ / suffctxrun_ (OD-11-17)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from offline_rag.core.ids import canonical_config_hash
from offline_rag.sufficiency.contracts import (
    SUFFICIENCY_OBSERVATION_V1,
    SUFFICIENCY_PROVENANCE_V1,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
    SufficiencyValidationError,
)


def build_suffctx_semantic_payload(
    provenance: SufficiencyProvenanceV1,
    observation: SufficiencyObservationV1,
) -> dict[str, Any]:
    """Explicit allowlisted semantic payload for ``suffctx_`` identity (OD-11-8/26)."""
    if provenance.schema_version != SUFFICIENCY_PROVENANCE_V1:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported provenance schema_version for suffctx payload",
            details=SufficiencyErrorDetailsV1(
                field_name="schema_version",
                expected=SUFFICIENCY_PROVENANCE_V1,
                actual=provenance.schema_version,
            ),
        )
    if observation.observation_contract != SUFFICIENCY_OBSERVATION_V1:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.UNSUPPORTED_OBSERVATION_CONTRACT,
            "unsupported observation_contract for suffctx payload",
            details=SufficiencyErrorDetailsV1(
                field_name="observation_contract",
                expected=SUFFICIENCY_OBSERVATION_V1,
                actual=observation.observation_contract,
            ),
        )
    return {
        "contract": "sufficiency-eval-context-v1",
        "provenance": provenance.model_dump(mode="json"),
        "observation": observation.model_dump(mode="json"),
    }


def _require_mapping_payload(payload: Mapping[str, Any], *, kind: str) -> None:
    if not isinstance(payload, Mapping) or not payload:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            f"{kind} payload must be a non-empty mapping",
        )


def build_suffctx_id(payload: Mapping[str, Any]) -> str:
    """Return ``suffctx_<sha256>`` using shared canonical hashing (OD-11-17)."""
    _require_mapping_payload(payload, kind="suffctx")
    try:
        return canonical_config_hash(payload).replace("cfg_", "suffctx_", 1)
    except (TypeError, ValueError) as exc:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctx payload is not canonically serializable",
            cause=exc,
        ) from exc


def build_suffctxrun_id(payload: Mapping[str, Any]) -> str:
    """Return ``suffctxrun_<sha256>`` using shared canonical hashing (OD-11-17)."""
    _require_mapping_payload(payload, kind="suffctxrun")
    try:
        return canonical_config_hash(payload).replace("cfg_", "suffctxrun_", 1)
    except (TypeError, ValueError) as exc:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctxrun payload is not canonically serializable",
            cause=exc,
        ) from exc
