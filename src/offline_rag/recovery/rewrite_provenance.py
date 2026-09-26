"""Canonical recovery-rewriter attempt provenance (Slice 12B)."""

from __future__ import annotations

from offline_rag.config.models import AppSettings, RecoveryRewriterSettings
from offline_rag.generation.openai_compatible import normalize_endpoint
from offline_rag.recovery.rewrite_config_hash import build_recovery_rewriter_config_hash
from offline_rag.recovery.rewrite_contracts import RecoveryRewriteProvenanceV1


def build_recovery_rewrite_attempt_provenance(
    settings: AppSettings | RecoveryRewriterSettings,
    *,
    rewrite_call_count: int = 1,
    rewritten_query: str | None = None,
) -> RecoveryRewriteProvenanceV1:
    """Build static rewriter identity before/without a successful provider parse.

    Safe for failure traces: never includes API keys or auth headers.
    ``rewritten_query`` remains null until a valid structured output exists.
    """
    rewriter = (
        settings.retrieval_recovery.rewriter
        if isinstance(settings, AppSettings)
        else settings
    )
    return RecoveryRewriteProvenanceV1(
        prompt_contract=rewriter.prompt_contract,
        output_contract=rewriter.output_contract,
        adapter_contract=rewriter.adapter_contract,
        rewriter_config_hash=build_recovery_rewriter_config_hash(settings),
        provider=rewriter.provider,
        normalized_endpoint=normalize_endpoint(rewriter.base_url),
        model=rewriter.model,
        rewrite_call_count=rewrite_call_count,
        rewritten_query=rewritten_query,
    )
