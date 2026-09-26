"""Evidence-surface helpers for Slice 12C (11B chunk-ID overlap rule)."""

from __future__ import annotations

from collections.abc import Sequence

from offline_rag.domain.indexing import HybridRerankCandidate, HybridRerankContextResult
from offline_rag.evaluation.recovery_12c.contracts import RecoveryEvalError


def evidence_surface_chunk_ids_from_context(
    context: HybridRerankContextResult,
) -> set[str]:
    """Exact chunk-ID evidence surface (anchors + final evidence unit IDs)."""
    surface: set[str] = set()
    for anchor in context.anchors:
        surface.add(anchor.chunk_id)
    for unit in context.evidence_units:
        surface.add(unit.source_chunk_id)
        surface.add(unit.primary_anchor_chunk_id)
    return surface


def ranked_anchor_chunk_ids(
    anchors: Sequence[HybridRerankCandidate],
) -> list[str]:
    """Return chunk IDs in ascending rerank rank order (stable for IR metrics)."""
    ordered = sorted(anchors, key=lambda item: int(item.rank))
    return [item.chunk_id for item in ordered]


def gold_positive_overlap(
    *,
    gold_positive_chunk_ids: set[str] | Sequence[str],
    evidence_surface: set[str] | Sequence[str],
) -> tuple[bool, list[str]]:
    """Return (has_overlap, sorted overlapping Gold-positive chunk IDs)."""
    positives = set(gold_positive_chunk_ids)
    surface = set(evidence_surface)
    present = sorted(positives & surface)
    return bool(present), present


def context_latency_ms(context: HybridRerankContextResult) -> float | None:
    """Extract deterministic context latency when present in metadata."""
    metadata = dict(context.metadata or {})
    latency = metadata.get("latency_ms")
    if isinstance(latency, dict):
        total = latency.get("total")
        if isinstance(total, (int, float)):
            return float(total)
    if isinstance(latency, (int, float)):
        return float(latency)
    return None


def require_nonempty_gold_positives_for_metrics(
    gold_positive_chunk_ids: set[str] | Sequence[str],
    *,
    case_id: str,
) -> set[str]:
    positives = set(gold_positive_chunk_ids)
    if not positives:
        raise RecoveryEvalError(
            f"case {case_id!r} has no Gold-positive chunk IDs; "
            "cannot score Gold-positive recovery metrics"
        )
    return positives
