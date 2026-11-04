"""Dense query-text contracts (query-side bi-encoder representation)."""

from __future__ import annotations

from offline_rag.core.ids import MODEL_QUERY_PROMPT_V1, RAW_QUERY_V1

RAW_QUERY_STRATEGY = "raw"
MODEL_QUERY_PROMPT_STRATEGY = "model_query_prompt"

# SentenceTransformers registered prompt name for retrieval queries.
MODEL_QUERY_PROMPT_NAME = "query"


def require_registered_query_prompt(model: object) -> str:
    """Return the non-empty registered query prompt or fail closed.

    The prompt value is returned for validation/reference use only. Callers
    should pass ``prompt_name="query"`` to SentenceTransformers so the model's
    registered prompt semantics (including prompt-aware pooling) are preserved.
    Error messages intentionally omit prompt contents.
    """
    prompts = getattr(model, "prompts", None)
    if not isinstance(prompts, dict):
        raise TypeError("model-query-prompt-v1 requires a registered query prompt")
    value = prompts.get(MODEL_QUERY_PROMPT_NAME)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "model-query-prompt-v1 requires a non-empty registered query prompt"
        )
    return value


def resolve_query_text_contract(*, strategy: str, contract_version: str) -> str:
    """Return the validated query-text contract version for the given pair."""
    if strategy == RAW_QUERY_STRATEGY and contract_version == RAW_QUERY_V1:
        return RAW_QUERY_V1
    if (
        strategy == MODEL_QUERY_PROMPT_STRATEGY
        and contract_version == MODEL_QUERY_PROMPT_V1
    ):
        return MODEL_QUERY_PROMPT_V1
    raise ValueError(
        "unsupported dense query_text pair: "
        f"{strategy}/{contract_version}"
    )
