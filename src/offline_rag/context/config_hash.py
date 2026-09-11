"""Deterministic context-assembly configuration hash."""

from __future__ import annotations

from typing import Any

from offline_rag.chunking.tokenize import TokenCounter
from offline_rag.config.models import AppSettings, ContextSettings
from offline_rag.context.contracts import (
    ASSEMBLY_CONTRACT,
    CLIP_CONTRACT,
    CONTAINMENT_CONTRACT,
    DEDUP_CONTRACT,
    NEIGHBOR_CONTRACT,
    RENDER_CONTRACT,
)
from offline_rag.core.ids import context_config_hash


def resolved_token_counter_identity(counter: TokenCounter) -> dict[str, str]:
    return {
        "implementation": counter.name,
        "encoding": counter.encoding,
        "contract_version": counter.version,
    }


def build_context_semantic_payload(
    settings: AppSettings | ContextSettings,
    *,
    token_counter: TokenCounter,
) -> dict[str, Any]:
    """Build effective assembly semantics (strategy-conditional)."""
    ctx = settings.context if isinstance(settings, AppSettings) else settings
    payload: dict[str, Any] = {
        "strategy": ctx.strategy,
        "anchor_k": int(ctx.anchor_k),
        "max_context_tokens": int(ctx.max_context_tokens),
        "assembly_contract": ASSEMBLY_CONTRACT,
        "dedup_contract": DEDUP_CONTRACT,
        "render_contract": RENDER_CONTRACT,
        "token_counter": resolved_token_counter_identity(token_counter),
    }
    if ctx.strategy == "parent":
        payload["clip_contract"] = CLIP_CONTRACT
    elif ctx.strategy == "neighbors":
        payload["neighbor_contract"] = NEIGHBOR_CONTRACT
        payload["neighbor_window"] = int(ctx.neighbor_window)
    elif ctx.strategy == "parent+neighbors":
        payload["clip_contract"] = CLIP_CONTRACT
        payload["neighbor_contract"] = NEIGHBOR_CONTRACT
        payload["neighbor_window"] = int(ctx.neighbor_window)
        payload["containment_contract"] = CONTAINMENT_CONTRACT
    return payload


def build_context_config_hash(
    settings: AppSettings | ContextSettings,
    *,
    token_counter: TokenCounter,
) -> str:
    return context_config_hash(
        build_context_semantic_payload(settings, token_counter=token_counter)
    )
