"""Semantic ID builders for suffctx_ / suffctxrun_ (OD-11-17)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from offline_rag.sufficiency.contracts import (
    SUFFICIENCY_OBSERVATION_V1,
    SUFFICIENCY_PROVENANCE_V1,
    SufficiencyErrorCodeV1,
    SufficiencyErrorDetailsV1,
    SufficiencyObservationV1,
    SufficiencyProvenanceV1,
    SufficiencyValidationError,
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _content_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return f"{prefix}_{_sha256_hex(_canonical_json_bytes(payload))}"


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


def build_suffctx_id(payload: Mapping[str, Any]) -> str:
    """Return ``suffctx_<sha256>`` for an explicit semantic case payload."""
    if not isinstance(payload, Mapping) or not payload:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctx payload must be a non-empty mapping",
        )
    try:
        return _content_id("suffctx", payload)
    except (TypeError, ValueError) as exc:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctx payload is not canonically serializable",
            cause=exc,
        ) from exc


def build_suffctxrun_id(payload: Mapping[str, Any]) -> str:
    """Return ``suffctxrun_<sha256>`` for an explicit semantic run-manifest payload."""
    if not isinstance(payload, Mapping) or not payload:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctxrun payload must be a non-empty mapping",
        )
    try:
        return _content_id("suffctxrun", payload)
    except (TypeError, ValueError) as exc:
        raise SufficiencyValidationError(
            SufficiencyErrorCodeV1.INVALID_SEMANTIC_PAYLOAD,
            "suffctxrun payload is not canonically serializable",
            cause=exc,
        ) from exc
