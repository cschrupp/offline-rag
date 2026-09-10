"""Deterministic fusion configuration hash."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, FusionSettings
from offline_rag.core.ids import RRF_FUSION_CONTRACT, fusion_config_hash


def build_fusion_config_hash(settings: AppSettings | FusionSettings) -> str:
    """Hash fusion-policy semantics only (not output_top_k or index IDs)."""
    fusion = settings.fusion if isinstance(settings, AppSettings) else settings
    return fusion_config_hash(
        {
            "method": fusion.method,
            "contract_version": fusion.contract_version,
            "rrf_k": fusion.rrf_k,
            "dense_top_k": fusion.dense_top_k,
            "lexical_top_k": fusion.lexical_top_k,
            "branch_weights": "equal-v1",
            "missing_policy": "present-only-v1",
            "tie_break": "chunk-id-asc-v1",
            "rank_base": "one-based-v1",
            "expected_contract": RRF_FUSION_CONTRACT,
        }
    )
