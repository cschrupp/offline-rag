"""Anchor-preserving-v1 parent clipping."""

from __future__ import annotations

from offline_rag.chunking.tokenize import TokenCounter
from offline_rag.context.contracts import CLIP_CONTRACT
from offline_rag.context.store import ContextStructureError
from offline_rag.core.ids import evidence_unit_id_from_payload, text_content_hash
from offline_rag.domain.documents import Chunk
from offline_rag.domain.indexing import EvidenceClipInfo, EvidenceUnit


class ClipDecision:
    def __init__(
        self,
        *,
        text: str,
        clipped: bool,
        clip: EvidenceClipInfo | None,
        evidence_unit_id: str,
        token_count: int,
    ) -> None:
        self.text = text
        self.clipped = clipped
        self.clip = clip
        self.evidence_unit_id = evidence_unit_id
        self.token_count = token_count


def locate_anchor_in_parent(parent: Chunk, anchor: Chunk) -> tuple[int, int]:
    """Return half-open [start, end) for the unique/structural anchor placement."""
    parent_text = parent.text
    anchor_text = anchor.text
    if not anchor_text:
        raise ContextStructureError(f"anchor {anchor.chunk_id} has empty text")

    # Prefer order-derived structural hints from metadata when present.
    meta = anchor.metadata or {}
    if "parent_char_start" in meta and "parent_char_end" in meta:
        start = int(meta["parent_char_start"])
        end = int(meta["parent_char_end"])
        if not (0 <= start < end <= len(parent_text)):
            raise ContextStructureError(
                f"anchor {anchor.chunk_id} metadata parent span out of range"
            )
        if parent_text[start:end] != anchor_text:
            raise ContextStructureError(
                f"anchor {anchor.chunk_id} metadata span does not match parent text"
            )
        return start, end

    occurrences: list[int] = []
    start_at = 0
    while True:
        found = parent_text.find(anchor_text, start_at)
        if found < 0:
            break
        occurrences.append(found)
        start_at = found + 1

    if not occurrences:
        raise ContextStructureError(
            f"anchor {anchor.chunk_id} text not found in parent {parent.chunk_id}"
        )
    if len(occurrences) > 1:
        raise ContextStructureError(
            f"anchor {anchor.chunk_id} text occurs {len(occurrences)} times in "
            f"parent {parent.chunk_id}; structural disambiguation required"
        )
    start = occurrences[0]
    return start, start + len(anchor_text)


def full_evidence_unit_id(source_chunk_id: str) -> str:
    return evidence_unit_id_from_payload(
        {
            "source_chunk_id": source_chunk_id,
            "representation": "full",
        }
    )


def clipped_evidence_unit_id(
    *,
    source_chunk_id: str,
    start_char: int,
    end_char: int,
    text: str,
) -> str:
    return evidence_unit_id_from_payload(
        {
            "source_chunk_id": source_chunk_id,
            "representation": "clipped",
            "clip_contract": CLIP_CONTRACT,
            "start_char": start_char,
            "end_char": end_char,
            "text_hash": text_content_hash(text),
        }
    )


def try_emit_parent(
    *,
    parent: Chunk,
    anchor: Chunk,
    primary_anchor_chunk_id: str,
    contributing: list[str],
    existing_assembled: str,
    max_context_tokens: int,
    counter: TokenCounter,
) -> ClipDecision | None:
    """Return a parent evidence decision, or None if the full anchor cannot fit."""

    def rendered_count(candidate_text: str) -> int:
        if existing_assembled:
            return counter.count(existing_assembled + "\n\n" + candidate_text)
        return counter.count(candidate_text)

    full_text = parent.text
    full_count = rendered_count(full_text)
    if full_count <= max_context_tokens:
        unit_tokens = counter.count(full_text)
        return ClipDecision(
            text=full_text,
            clipped=False,
            clip=None,
            evidence_unit_id=full_evidence_unit_id(parent.chunk_id),
            token_count=unit_tokens,
        )

    anchor_start, anchor_end = locate_anchor_in_parent(parent, anchor)
    start = anchor_start
    end = anchor_end
    if rendered_count(parent.text[start:end]) > max_context_tokens:
        return None

    while True:
        grew = False
        if start > 0:
            candidate_start = start - 1
            if rendered_count(parent.text[candidate_start:end]) <= max_context_tokens:
                start = candidate_start
                grew = True
        if end < len(parent.text):
            candidate_end = end + 1
            if rendered_count(parent.text[start:candidate_end]) <= max_context_tokens:
                end = candidate_end
                grew = True
        if not grew:
            break

    excerpt = parent.text[start:end]
    emitted_tokens = counter.count(excerpt)
    original_tokens = counter.count(full_text)
    clip = EvidenceClipInfo(
        contract=CLIP_CONTRACT,
        start_char=start,
        end_char=end,
        anchor_start_char=anchor_start,
        anchor_end_char=anchor_end,
        original_token_count=original_tokens,
        emitted_token_count=emitted_tokens,
    )
    return ClipDecision(
        text=excerpt,
        clipped=True,
        clip=clip,
        evidence_unit_id=clipped_evidence_unit_id(
            source_chunk_id=parent.chunk_id,
            start_char=start,
            end_char=end,
            text=excerpt,
        ),
        token_count=emitted_tokens,
    )


def make_parent_evidence_unit(
    *,
    parent: Chunk,
    decision: ClipDecision,
    primary_anchor_chunk_id: str,
    contributing: list[str],
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=decision.evidence_unit_id,
        source_chunk_id=parent.chunk_id,
        kind="parent",
        text=decision.text,
        clipped=decision.clipped,
        token_count=decision.token_count,
        primary_anchor_chunk_id=primary_anchor_chunk_id,
        contributing_anchor_chunk_ids=list(contributing),
        document_id=parent.document_id,
        parent_chunk_id=None,
        section_path=list(parent.section_path),
        page_start=parent.page_start,
        page_end=parent.page_end,
        line_start=parent.line_start,
        line_end=parent.line_end,
        clip=decision.clip,
    )


def make_child_evidence_unit(
    *,
    child: Chunk,
    primary_anchor_chunk_id: str,
    contributing: list[str],
    counter: TokenCounter,
    relationship: str | None = None,
    distance: int | None = None,
) -> EvidenceUnit:
    return EvidenceUnit(
        evidence_unit_id=full_evidence_unit_id(child.chunk_id),
        source_chunk_id=child.chunk_id,
        kind="child",
        text=child.text,
        clipped=False,
        token_count=counter.count(child.text),
        primary_anchor_chunk_id=primary_anchor_chunk_id,
        contributing_anchor_chunk_ids=list(contributing),
        document_id=child.document_id,
        parent_chunk_id=child.parent_chunk_id,
        section_path=list(child.section_path),
        page_start=child.page_start,
        page_end=child.page_end,
        line_start=child.line_start,
        line_end=child.line_end,
        clip=None,
        relationship=relationship,
        distance=distance,
    )


def candidate_fits(
    *,
    existing_assembled: str,
    new_text: str,
    max_context_tokens: int,
    counter: TokenCounter,
) -> bool:
    if existing_assembled:
        return counter.count(existing_assembled + "\n\n" + new_text) <= max_context_tokens
    return counter.count(new_text) <= max_context_tokens
