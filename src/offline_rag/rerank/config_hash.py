"""Deterministic reranker configuration hash."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, RerankerSettings
from offline_rag.core.ids import reranker_config_hash


def build_reranker_config_hash(settings: AppSettings | RerankerSettings) -> str:
    """Hash ranking-policy semantics only (not output_k, device, or paths)."""
    rrk = settings.reranker if isinstance(settings, AppSettings) else settings
    return reranker_config_hash(
        {
            "model_id": rrk.model.model_id,
            "revision": rrk.model.revision,
            "adapter_contract": rrk.model.adapter_contract,
            "input_k": rrk.input_k,
            "input_construction": rrk.input_construction,
            "sequence_contract": rrk.sequence_contract,
            "max_length": rrk.max_length,
            "score_transform": rrk.score_transform,
            "tie_break": rrk.tie_break,
        }
    )
