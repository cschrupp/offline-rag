"""Deterministic recovery-rewriter configuration hash (OD-12-1)."""

from __future__ import annotations

from typing import Any

from offline_rag.config.models import AppSettings, RecoveryRewriterSettings
from offline_rag.core.ids import recovery_rewriter_config_hash
from offline_rag.generation.openai_compatible import normalize_endpoint
from offline_rag.recovery.rewrite_contracts import (
    RECOVERY_REWRITE_OUTPUT_V1,
    RECOVERY_REWRITE_PROMPT_V1,
)


def build_recovery_rewriter_semantic_payload(
    settings: AppSettings | RecoveryRewriterSettings,
) -> dict[str, Any]:
    """Identity-bearing rewriter surface. Excludes api_key / credentials."""
    rewriter = (
        settings.retrieval_recovery.rewriter
        if isinstance(settings, AppSettings)
        else settings
    )
    endpoint = normalize_endpoint(rewriter.base_url)
    approved_endpoints = sorted(
        {normalize_endpoint(item) for item in rewriter.approved_endpoints}
    )
    approved_models = sorted({str(item) for item in rewriter.approved_models})
    return {
        "provider": rewriter.provider,
        "adapter_contract": rewriter.adapter_contract,
        "base_url": endpoint,
        "model": rewriter.model,
        "temperature": float(rewriter.temperature),
        "max_output_tokens": int(rewriter.max_output_tokens),
        "timeout_seconds": int(rewriter.timeout_seconds),
        "approved_endpoints": approved_endpoints,
        "approved_models": approved_models,
        "prompt_contract": rewriter.prompt_contract,
        "output_contract": rewriter.output_contract,
        "network_policy": rewriter.network_policy,
        # Frozen contract anchors (must match settings literals).
        "prompt_contract_literal": RECOVERY_REWRITE_PROMPT_V1,
        "output_contract_literal": RECOVERY_REWRITE_OUTPUT_V1,
    }


def build_recovery_rewriter_config_hash(
    settings: AppSettings | RecoveryRewriterSettings,
) -> str:
    return recovery_rewriter_config_hash(
        build_recovery_rewriter_semantic_payload(settings)
    )
