"""Deterministic generation configuration hash."""

from __future__ import annotations

from typing import Any

from offline_rag.config.models import AppSettings, GenerationSettings
from offline_rag.core.ids import generation_config_hash
from offline_rag.generation.contracts import (
    ADAPTER_CONTRACT,
    OUTPUT_CONTRACT,
    PROMPT_CONTRACT,
    RECOVERY_CONTRACT,
)


def build_generation_semantic_payload(
    settings: AppSettings | GenerationSettings,
) -> dict[str, Any]:
    gen = settings.generation if isinstance(settings, AppSettings) else settings
    return {
        "provider": gen.provider,
        "adapter_contract": ADAPTER_CONTRACT,
        "model": gen.model,
        "temperature": float(gen.temperature),
        "max_output_tokens": int(gen.max_output_tokens),
        "prompt_contract": PROMPT_CONTRACT,
        "output_contract": OUTPUT_CONTRACT,
        "recovery_contract": RECOVERY_CONTRACT,
    }


def build_generation_config_hash(settings: AppSettings | GenerationSettings) -> str:
    return generation_config_hash(build_generation_semantic_payload(settings))
