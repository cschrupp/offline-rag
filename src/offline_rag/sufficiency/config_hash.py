"""Canonical observation derivation config and obsconfig_ hash."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from offline_rag.core.ids import canonical_config_hash
from offline_rag.sufficiency.contracts import SUFFICIENCY_OBSERVATION_V1

# Frozen semantic derivation definitions for sufficiency-observation-v1 (OD-11-16).
# Changing any entry that affects an OD-11-2 feature must change observation_config_hash.
OBSERVATION_DERIVATION_CONFIG_V1: dict[str, Any] = {
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


def build_observation_derivation_config_v1() -> dict[str, Any]:
    """Return a deep-enough copy of the frozen derivation config object."""
    # Structural copy sufficient for hashing/tests; nested dicts are literals.
    return {
        "contract": OBSERVATION_DERIVATION_CONFIG_V1["contract"],
        "features": dict(OBSERVATION_DERIVATION_CONFIG_V1["features"]),
        "canonicalization": dict(OBSERVATION_DERIVATION_CONFIG_V1["canonicalization"]),
    }


def build_observation_config_hash(
    config: Mapping[str, Any] | None = None,
) -> str:
    """Return ``obsconfig_<sha256>`` for a canonical semantic derivation config."""
    payload = dict(config) if config is not None else build_observation_derivation_config_v1()
    return canonical_config_hash(payload).replace("cfg_", "obsconfig_", 1)
