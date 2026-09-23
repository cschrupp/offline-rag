"""Sufficiency observation core — public contract surface (OD-11-34)."""

from offline_rag.sufficiency.config_hash import build_observation_config_hash
from offline_rag.sufficiency.contracts import (
    SUFFICIENCY_OBSERVATION_V1,
    SUFFICIENCY_PROVENANCE_V1,
    SufficiencyDerivationError,
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
from offline_rag.sufficiency.ids import build_suffctx_id, build_suffctxrun_id

__all__ = [
    "SUFFICIENCY_OBSERVATION_V1",
    "SUFFICIENCY_PROVENANCE_V1",
    "SufficiencyDerivationError",
    "SufficiencyError",
    "SufficiencyErrorCodeV1",
    "SufficiencyErrorDetailsV1",
    "SufficiencyObservationV1",
    "SufficiencyProvenanceV1",
    "SufficiencyValidationError",
    "build_observation_config_hash",
    "build_suffctx_id",
    "build_suffctxrun_id",
    "derive_sufficiency_observation",
    "validate_observation_against_provenance",
]
