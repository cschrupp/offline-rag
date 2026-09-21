"""Deterministic generation-semantic judge configuration hash (``judgecfg_``)."""

from __future__ import annotations

from typing import Any

from offline_rag.config.models import (
    AppSettings,
    GenerationSemanticJudgeSettings,
)
from offline_rag.core.ids import judge_config_hash
from offline_rag.core.network_policy import (
    NetworkPolicyError,
    normalize_openai_compatible_endpoint,
)
from offline_rag.evaluation.generation_semantic.judge_contracts import (
    ADAPTER_CONTRACT,
    OUTPUT_CONTRACT,
    PROMPT_CONTRACT,
    REASONING_CONTRACT,
)


def _judge_settings(
    settings: AppSettings | GenerationSemanticJudgeSettings,
) -> GenerationSemanticJudgeSettings:
    if isinstance(settings, AppSettings):
        return settings.evaluation.generation_semantic_judge
    return settings


def build_judge_semantic_payload(
    settings: AppSettings | GenerationSemanticJudgeSettings,
) -> dict[str, Any]:
    """Semantic payload for ``judgecfg_`` (no api_key, paths, or allowlists)."""
    judge = _judge_settings(settings)
    try:
        normalized = normalize_openai_compatible_endpoint(judge.base_url)
    except NetworkPolicyError:
        normalized = judge.base_url.strip()
    return {
        "provider": judge.provider,
        "normalized_endpoint": normalized,
        "model": judge.model,
        "temperature": float(judge.temperature),
        "max_output_tokens": int(judge.max_output_tokens),
        "adapter_contract": judge.adapter_contract or ADAPTER_CONTRACT,
        "prompt_contract": judge.prompt_contract or PROMPT_CONTRACT,
        "output_contract": judge.output_contract or OUTPUT_CONTRACT,
        "reasoning_contract": REASONING_CONTRACT,
        "network_policy": judge.network_policy,
    }


def build_judge_config_hash(
    settings: AppSettings | GenerationSemanticJudgeSettings,
) -> str:
    return judge_config_hash(build_judge_semantic_payload(settings))
