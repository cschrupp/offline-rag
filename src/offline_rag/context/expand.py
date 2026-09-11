"""Source-agnostic structural context expansion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from offline_rag.chunking.tokenize import TokenCounter
from offline_rag.config.models import ContextSettings
from offline_rag.context.clip import (
    candidate_fits,
    make_child_evidence_unit,
    make_parent_evidence_unit,
    try_emit_parent,
)
from offline_rag.context.contracts import (
    STOP_ANCHOR_WOULD_NOT_FIT,
    STOP_CHILD_WOULD_NOT_FIT,
    STOP_COMPLETED,
    STOP_NO_ANCHORS,
    STOP_PARENT_CLIPPED_TO_BUDGET,
)
from offline_rag.context.render import render_plain_evidence
from offline_rag.context.store import ChunkStructureStore, ContextStructureError
from offline_rag.domain.documents import Chunk
from offline_rag.domain.indexing import ContextAssemblyDiagnostics, EvidenceUnit


class RankedAnchor(Protocol):
    """Minimal source-agnostic ranked child anchor."""

    @property
    def chunk_id(self) -> str: ...

    @property
    def rank(self) -> int: ...


@dataclass
class ExpandedContext:
    evidence_units: list[EvidenceUnit] = field(default_factory=list)
    assembled_text: str = ""
    context_token_count: int = 0
    diagnostics: ContextAssemblyDiagnostics | None = None


class ContextExpander:
    """Expand ranked child anchors into budgeted structural evidence."""

    def __init__(
        self,
        *,
        store: ChunkStructureStore,
        counter: TokenCounter,
        context: ContextSettings,
    ) -> None:
        self.store = store
        self.counter = counter
        self.context = context

    def expand(self, anchors: list[RankedAnchor]) -> ExpandedContext:
        ordered = sorted(anchors, key=lambda item: (item.rank, item.chunk_id))
        diagnostics = ContextAssemblyDiagnostics(
            requested_anchor_k=int(self.context.anchor_k),
            actual_anchor_count=len(ordered),
        )
        if not ordered:
            diagnostics.stop_reason = STOP_NO_ANCHORS
            return ExpandedContext(diagnostics=diagnostics)

        units: list[EvidenceUnit] = []
        # structural_id -> unit index
        owned: dict[str, int] = {}
        full_parent_ids: set[str] = set()
        stop_reason = STOP_COMPLETED
        budget_exhausted = False
        clipping_occurred = False
        dedup_hits = 0
        containment_suppressions = 0
        anchors_processed = 0

        for anchor in ordered:
            anchors_processed += 1
            child = self.store.get_child(anchor.chunk_id)
            strategy = self.context.strategy

            if strategy == "child-only":
                outcome = self._handle_child_only(
                    child=child,
                    anchor=anchor,
                    units=units,
                    owned=owned,
                )
            elif strategy == "parent":
                outcome = self._handle_parent(
                    child=child,
                    anchor=anchor,
                    units=units,
                    owned=owned,
                    full_parent_ids=full_parent_ids,
                )
            elif strategy == "neighbors":
                outcome = self._handle_neighbors(
                    child=child,
                    anchor=anchor,
                    units=units,
                    owned=owned,
                )
            elif strategy == "parent+neighbors":
                outcome = self._handle_parent_neighbors(
                    child=child,
                    anchor=anchor,
                    units=units,
                    owned=owned,
                    full_parent_ids=full_parent_ids,
                )
            else:
                raise ContextStructureError(f"unsupported strategy: {strategy}")

            dedup_hits += outcome.dedup_hits
            containment_suppressions += outcome.containment_suppressions
            if outcome.clipping_occurred:
                clipping_occurred = True
            if outcome.stop_reason is not None:
                stop_reason = outcome.stop_reason
                budget_exhausted = outcome.budget_exhausted
                break

        assembled = render_plain_evidence(units)
        token_count = self.counter.count(assembled) if assembled else 0
        if token_count > self.context.max_context_tokens:
            raise ContextStructureError(
                "assembled evidence exceeds max_context_tokens "
                f"({token_count} > {self.context.max_context_tokens})"
            )

        diagnostics.anchors_processed = anchors_processed
        diagnostics.evidence_unit_count = len(units)
        diagnostics.context_token_count = token_count
        diagnostics.budget_exhausted = budget_exhausted
        diagnostics.stop_reason = stop_reason
        diagnostics.clipping_occurred = clipping_occurred
        diagnostics.dedup_hits = dedup_hits
        diagnostics.containment_suppressions = containment_suppressions
        return ExpandedContext(
            evidence_units=units,
            assembled_text=assembled,
            context_token_count=token_count,
            diagnostics=diagnostics,
        )

    def _assembled_so_far(self, units: list[EvidenceUnit]) -> str:
        return render_plain_evidence(units)

    def _record_dedup(
        self,
        *,
        structural_id: str,
        owned: dict[str, int],
        units: list[EvidenceUnit],
        anchor_chunk_id: str,
    ) -> bool:
        """Attach contributing provenance if already owned. Return True if deduped."""
        idx = owned.get(structural_id)
        if idx is None:
            return False
        unit = units[idx]
        if anchor_chunk_id not in unit.contributing_anchor_chunk_ids:
            unit.contributing_anchor_chunk_ids.append(anchor_chunk_id)
        return True

    def _handle_child_only(
        self,
        *,
        child: Chunk,
        anchor: RankedAnchor,
        units: list[EvidenceUnit],
        owned: dict[str, int],
    ) -> _AnchorOutcome:
        if self._record_dedup(
            structural_id=child.chunk_id,
            owned=owned,
            units=units,
            anchor_chunk_id=anchor.chunk_id,
        ):
            return _AnchorOutcome(dedup_hits=1)

        existing = self._assembled_so_far(units)
        if not candidate_fits(
            existing_assembled=existing,
            new_text=child.text,
            max_context_tokens=int(self.context.max_context_tokens),
            counter=self.counter,
        ):
            return _AnchorOutcome(
                stop_reason=STOP_CHILD_WOULD_NOT_FIT,
                budget_exhausted=True,
            )

        unit = make_child_evidence_unit(
            child=child,
            primary_anchor_chunk_id=anchor.chunk_id,
            contributing=[anchor.chunk_id],
            counter=self.counter,
            relationship="anchor",
            distance=0,
        )
        owned[child.chunk_id] = len(units)
        units.append(unit)
        return _AnchorOutcome()

    def _handle_parent(
        self,
        *,
        child: Chunk,
        anchor: RankedAnchor,
        units: list[EvidenceUnit],
        owned: dict[str, int],
        full_parent_ids: set[str],
    ) -> _AnchorOutcome:
        parent = self.store.resolve_parent_for_child(child)
        if self._record_dedup(
            structural_id=parent.chunk_id,
            owned=owned,
            units=units,
            anchor_chunk_id=anchor.chunk_id,
        ):
            return _AnchorOutcome(dedup_hits=1)

        existing = self._assembled_so_far(units)
        decision = try_emit_parent(
            parent=parent,
            anchor=child,
            primary_anchor_chunk_id=anchor.chunk_id,
            contributing=[anchor.chunk_id],
            existing_assembled=existing,
            max_context_tokens=int(self.context.max_context_tokens),
            counter=self.counter,
        )
        if decision is None:
            return _AnchorOutcome(
                stop_reason=STOP_ANCHOR_WOULD_NOT_FIT,
                budget_exhausted=True,
            )

        unit = make_parent_evidence_unit(
            parent=parent,
            decision=decision,
            primary_anchor_chunk_id=anchor.chunk_id,
            contributing=[anchor.chunk_id],
        )
        owned[parent.chunk_id] = len(units)
        units.append(unit)
        if not decision.clipped:
            full_parent_ids.add(parent.chunk_id)
            return _AnchorOutcome()
        return _AnchorOutcome(
            clipping_occurred=True,
            stop_reason=STOP_PARENT_CLIPPED_TO_BUDGET,
            budget_exhausted=True,
        )

    def _neighbor_window_children(self, anchor_child: Chunk) -> list[tuple[Chunk, str, int]]:
        """Return (chunk, relationship, distance) in document order including anchor."""
        window = int(self.context.neighbor_window)
        prev_chain: list[Chunk] = []
        cursor = anchor_child
        for distance in range(1, window + 1):
            if cursor.previous_chunk_id is None:
                break
            neighbor = self.store.get_child(cursor.previous_chunk_id)
            if neighbor.document_id != anchor_child.document_id:
                raise ContextStructureError(
                    f"neighbor walk crossed document for {anchor_child.chunk_id}"
                )
            prev_chain.append(neighbor)
            cursor = neighbor

        next_chain: list[Chunk] = []
        cursor = anchor_child
        for distance in range(1, window + 1):
            if cursor.next_chunk_id is None:
                break
            neighbor = self.store.get_child(cursor.next_chunk_id)
            if neighbor.document_id != anchor_child.document_id:
                raise ContextStructureError(
                    f"neighbor walk crossed document for {anchor_child.chunk_id}"
                )
            next_chain.append(neighbor)
            cursor = neighbor

        ordered: list[tuple[Chunk, str, int]] = []
        for index, chunk in enumerate(reversed(prev_chain)):
            # prev_chain is nearest-first; after reverse, farthest is first.
            distance = len(prev_chain) - index
            ordered.append((chunk, "previous", distance))
        ordered.append((anchor_child, "anchor", 0))
        for distance, chunk in enumerate(next_chain, start=1):
            ordered.append((chunk, "next", distance))
        return ordered

    def _try_add_child_unit(
        self,
        *,
        child: Chunk,
        anchor: RankedAnchor,
        units: list[EvidenceUnit],
        owned: dict[str, int],
        relationship: str,
        distance: int,
        full_parent_ids: set[str] | None = None,
    ) -> _AnchorOutcome | None:
        """Return stop outcome, empty outcome for continue, or None if unit added."""
        if full_parent_ids and child.parent_chunk_id and child.parent_chunk_id in full_parent_ids:
            return _AnchorOutcome(containment_suppressions=1)

        if self._record_dedup(
            structural_id=child.chunk_id,
            owned=owned,
            units=units,
            anchor_chunk_id=anchor.chunk_id,
        ):
            return _AnchorOutcome(dedup_hits=1)

        existing = self._assembled_so_far(units)
        if not candidate_fits(
            existing_assembled=existing,
            new_text=child.text,
            max_context_tokens=int(self.context.max_context_tokens),
            counter=self.counter,
        ):
            return _AnchorOutcome(
                stop_reason=STOP_CHILD_WOULD_NOT_FIT,
                budget_exhausted=True,
            )

        unit = make_child_evidence_unit(
            child=child,
            primary_anchor_chunk_id=anchor.chunk_id,
            contributing=[anchor.chunk_id],
            counter=self.counter,
            relationship=relationship,
            distance=distance,
        )
        owned[child.chunk_id] = len(units)
        units.append(unit)
        return None

    def _handle_neighbors(
        self,
        *,
        child: Chunk,
        anchor: RankedAnchor,
        units: list[EvidenceUnit],
        owned: dict[str, int],
    ) -> _AnchorOutcome:
        total_dedup = 0
        for neighbor, relationship, distance in self._neighbor_window_children(child):
            outcome = self._try_add_child_unit(
                child=neighbor,
                anchor=anchor,
                units=units,
                owned=owned,
                relationship=relationship,
                distance=distance,
            )
            if outcome is None:
                continue
            total_dedup += outcome.dedup_hits
            if outcome.stop_reason is not None:
                outcome.dedup_hits = total_dedup
                return outcome
        return _AnchorOutcome(dedup_hits=total_dedup)

    def _handle_parent_neighbors(
        self,
        *,
        child: Chunk,
        anchor: RankedAnchor,
        units: list[EvidenceUnit],
        owned: dict[str, int],
        full_parent_ids: set[str],
    ) -> _AnchorOutcome:
        parent_outcome = self._handle_parent(
            child=child,
            anchor=anchor,
            units=units,
            owned=owned,
            full_parent_ids=full_parent_ids,
        )
        if parent_outcome.stop_reason is not None:
            return parent_outcome

        total_dedup = parent_outcome.dedup_hits
        total_suppress = 0
        for neighbor, relationship, distance in self._neighbor_window_children(child):
            outcome = self._try_add_child_unit(
                child=neighbor,
                anchor=anchor,
                units=units,
                owned=owned,
                relationship=relationship,
                distance=distance,
                full_parent_ids=full_parent_ids,
            )
            if outcome is None:
                continue
            total_dedup += outcome.dedup_hits
            total_suppress += outcome.containment_suppressions
            if outcome.stop_reason is not None:
                outcome.dedup_hits = total_dedup
                outcome.containment_suppressions = total_suppress
                return outcome
        return _AnchorOutcome(
            dedup_hits=total_dedup,
            containment_suppressions=total_suppress,
        )


@dataclass
class _AnchorOutcome:
    dedup_hits: int = 0
    containment_suppressions: int = 0
    clipping_occurred: bool = False
    stop_reason: str | None = None
    budget_exhausted: bool = False
