"""Code-owned generation-semantic judge contract identifiers (Slice 10C)."""

from __future__ import annotations

from offline_rag.core.ids import DIRECT_OUTPUT_V1

ADAPTER_CONTRACT = "openai-compatible-generation-semantic-judge-v1"
PROMPT_CONTRACT = "generation-semantic-judge-v1"
OUTPUT_CONTRACT = "generation-semantic-judge-output-v1"
REASONING_CONTRACT = DIRECT_OUTPUT_V1
SUPPORTED_PROVIDER = "openai_compatible"

DIAGNOSTIC_MAX_ITEMS = 3
DIAGNOSTIC_MAX_CHARS = 500
RATIONALE_MAX_CHARS = 500

PROBE_TIMEOUT_SECONDS = 5.0
