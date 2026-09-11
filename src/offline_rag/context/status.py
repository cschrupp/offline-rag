"""Derived Context readiness (no persisted ContextState)."""

from __future__ import annotations

from pydantic import ValidationError

from offline_rag.chunking.pipeline import make_token_counter
from offline_rag.chunking.tokenize import validate_tiktoken_artifacts
from offline_rag.config.models import AppSettings, ContextSettings
from offline_rag.context.store import (
    load_structure_store_for_corpus,
    validate_neighbor_links,
    validate_parent_links,
)
from offline_rag.core.ids import TIKTOKEN_TOKENIZER_CONTRACT
from offline_rag.ingestion.discovery import validate_corpus_name
from offline_rag.rerank.status import (
    describe_hybrid_rerank_status,
    hybrid_rerank_status_for_corpus,
)


def _context_config_ok(settings: AppSettings) -> tuple[bool, str | None]:
    try:
        ContextSettings.model_validate(settings.context.model_dump())
    except ValidationError as exc:
        return False, f"invalid context configuration: {exc.errors()[0]['msg']}"
    return True, None


def _token_counter_ready(settings: AppSettings) -> tuple[bool, str | None]:
    tok = settings.chunking.tokenizer
    if tok.implementation == "fake":
        # Explicit test/CI configuration only.
        return True, None
    if tok.implementation != "tiktoken":
        return False, f"unsupported token-counter implementation: {tok.implementation}"
    if tok.encoding != "cl100k_base":
        return False, f"unsupported token-counter encoding: {tok.encoding}"
    ok, reason = validate_tiktoken_artifacts(
        settings.paths.tokenizer_artifacts,
        encoding=tok.encoding,
    )
    if not ok:
        return False, f"tiktoken-cl100k-v1 unavailable offline: {reason}"
    try:
        counter = make_token_counter(settings)
    except Exception as exc:  # noqa: BLE001 - readiness must not raise
        return False, f"token counter initialization failed: {exc}"
    if counter.version != TIKTOKEN_TOKENIZER_CONTRACT and tok.implementation != "fake":
        return False, f"unexpected token-counter contract: {counter.version}"
    return True, None


def _structure_ready(settings: AppSettings, corpus_name: str) -> tuple[bool, str | None]:
    strategy = settings.context.strategy
    try:
        store = load_structure_store_for_corpus(settings, corpus_name)
    except Exception as exc:  # noqa: BLE001
        return False, f"chunk structure unavailable: {exc}"

    if strategy == "child-only":
        if not store.children:
            return False, "chunk set has no child chunks"
        return True, None

    if strategy in {"parent", "parent+neighbors"}:
        problems = validate_parent_links(store)
        if problems:
            return False, problems[0]

    if strategy in {"neighbors", "parent+neighbors"}:
        problems = [
            item for item in validate_neighbor_links(store) if "parent_chunk_id" not in item
        ]
        if problems:
            return False, problems[0]
    return True, None


def context_status_for_corpus(settings: AppSettings, corpus_name: str) -> str:
    """Return READY or NOT_READY for hybrid-rerank-context (derived)."""
    name = validate_corpus_name(corpus_name)
    if not settings.context.enabled:
        return "NOT_READY"
    if hybrid_rerank_status_for_corpus(settings, name) != "READY":
        return "NOT_READY"
    ok, _ = _context_config_ok(settings)
    if not ok:
        return "NOT_READY"
    ok, _ = _token_counter_ready(settings)
    if not ok:
        return "NOT_READY"
    ok, _ = _structure_ready(settings, name)
    if not ok:
        return "NOT_READY"
    return "READY"


def describe_context_status(
    settings: AppSettings, corpus_name: str
) -> dict[str, object]:
    name = validate_corpus_name(corpus_name)
    reasons: list[str] = []
    if not settings.context.enabled:
        reasons.append("context.enabled is false")
    hybrid_status = hybrid_rerank_status_for_corpus(settings, name)
    if hybrid_status != "READY":
        reasons.append("upstream hybrid-rerank is unavailable")
    ok, reason = _context_config_ok(settings)
    if not ok and reason:
        reasons.append(reason)
    ok, reason = _token_counter_ready(settings)
    if not ok and reason:
        reasons.append(reason)
    if settings.context.enabled and hybrid_status == "READY":
        ok, reason = _structure_ready(settings, name)
        if not ok and reason:
            reasons.append(reason)

    hybrid_details = describe_hybrid_rerank_status(settings, name)
    counter_contract = None
    try:
        counter = make_token_counter(settings)
        counter_contract = counter.version
    except Exception:  # noqa: BLE001
        counter_contract = None

    return {
        "status": context_status_for_corpus(settings, name),
        "corpus_name": name,
        "hybrid_rerank_status": hybrid_status,
        "context_enabled": "true" if settings.context.enabled else "false",
        "strategy": settings.context.strategy,
        "token_counter_contract": counter_contract,
        "dense_index_id": hybrid_details.get("dense_index_id"),
        "lexical_index_id": hybrid_details.get("lexical_index_id"),
        "active_chunk_set_id": hybrid_details.get("active_chunk_set_id"),
        "reasons": reasons,
    }
