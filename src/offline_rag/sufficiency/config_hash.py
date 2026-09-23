"""Canonical observation derivation config and obsconfig_ hash."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from offline_rag.core.ids import canonical_config_hash
from offline_rag.sufficiency.contracts import SUFFICIENCY_OBSERVATION_V1

# Private mutable template used only as the deepcopy source. Do not mutate.
_OBSERVATION_DERIVATION_CONFIG_V1_TEMPLATE: dict[str, Any] = {
    "contract": SUFFICIENCY_OBSERVATION_V1,
    "features": {
        "empty_context": {
            "definition": "len(final_evidence_units) == 0",
            "version": "empty-context-v1",
        },
        "top_reranker_score": {
            "source": "reranker_raw_logit",
            "score_transform": "raw-logit-v1",
            "anchor_selection": "rank_1",
            "version": "top-reranker-score-v1",
        },
        "top1_top2_margin": {
            "definition": "top1_score - top2_score",
            "fewer_than_two": "null",
            "version": "top1-top2-margin-v1",
        },
        "top_anchor_cross_retriever_support": {
            "definition": "top anchor has both dense_rank and lexical_rank non-null",
            "version": "top-anchor-cross-retriever-v1",
        },
        "anchor_count": {
            "definition": "len(ordered_reranked_anchors)",
            "version": "anchor-count-v1",
        },
        "distinct_document_count": {
            "identity_field": "document_id",
            "normalization": "exact",
            "version": "distinct-document-count-v1",
        },
        "distinct_section_count": {
            "identity_tuple": ["document_id", "normalized_section_path"],
            "section_path_normalization": "structural-only-v1",
            "empty_path": [],
            "version": "distinct-section-count-v1",
        },
    },
    "canonicalization": {
        "field_order": "canonical",
        "null_handling": "explicit",
        "numeric_serialization": "canonical-json",
        "anchor_order": "preserve",
        "evidence_unit_order": "preserve",
    },
}


def _freeze_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze_mapping(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_mapping(item) for item in value)
    return value


# Read-only public view; nested mappings/lists are also immutable.
OBSERVATION_DERIVATION_CONFIG_V1 = _freeze_mapping(
    copy.deepcopy(_OBSERVATION_DERIVATION_CONFIG_V1_TEMPLATE)
)

_AUTHORITATIVE_OBSERVATION_CONFIG_HASH = canonical_config_hash(
    copy.deepcopy(_OBSERVATION_DERIVATION_CONFIG_V1_TEMPLATE)
).replace("cfg_", "obsconfig_", 1)


def build_observation_derivation_config_v1() -> dict[str, Any]:
    """Return an independent deep copy of the frozen derivation config object."""
    return copy.deepcopy(_OBSERVATION_DERIVATION_CONFIG_V1_TEMPLATE)


def authoritative_observation_config_hash() -> str:
    """Return the frozen ``obsconfig_`` hash for sufficiency-observation-v1."""
    return _AUTHORITATIVE_OBSERVATION_CONFIG_HASH


def build_observation_config_hash(
    config: Mapping[str, Any] | None = None,
) -> str:
    """Return ``obsconfig_<sha256>`` via shared ``canonical_config_hash``."""
    if config is None:
        return _AUTHORITATIVE_OBSERVATION_CONFIG_HASH
    return canonical_config_hash(dict(config)).replace("cfg_", "obsconfig_", 1)
