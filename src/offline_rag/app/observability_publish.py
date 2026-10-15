"""Adapt pipeline stage/report signals into durable 16K-B metrics + worklist."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from offline_rag.app.workspace.leases import WorkspaceMutationLease
from offline_rag.app.workspace.models import (
    ManagedOperationDenseExecution,
    ManagedOperationDocumentPhase,
    ManagedOperationMetrics,
    ManagedOperationStageDurations,
    ManagedOperationWorklistDocument,
    SourceVersionRecord,
    build_managed_operation_worklist,
)
from offline_rag.app.workspace.mutation_ops import ManagedOperationStore
from offline_rag.core.observability import DocumentPhaseEvent
from offline_rag.domain.chunking import ChunkingReport, DocumentChunkStatus
from offline_rag.domain.indexing import IndexingReport, LexicalIndexingReport
from offline_rag.domain.ingestion import FileIngestionStatus, IngestionReport


_PHASE_RANK = {
    ManagedOperationDocumentPhase.PENDING: 0,
    ManagedOperationDocumentPhase.PARSING: 1,
    ManagedOperationDocumentPhase.PARSED: 2,
    ManagedOperationDocumentPhase.CHUNKING: 3,
    ManagedOperationDocumentPhase.CHUNKED: 4,
    ManagedOperationDocumentPhase.INDEXING: 5,
    ManagedOperationDocumentPhase.INDEXED: 6,
    ManagedOperationDocumentPhase.FAILED: 100,
    ManagedOperationDocumentPhase.REQUIRES_OCR: 100,
}


def _parse_phase(value: str) -> ManagedOperationDocumentPhase | None:
    try:
        return ManagedOperationDocumentPhase(value)
    except ValueError:
        return None


@dataclass
class DurableObservabilityPublisher:
    """Bounded durable metrics/worklist publisher for managed ingest operations."""

    operations: ManagedOperationStore
    workspace_id: str
    operation_id: str
    lease: WorkspaceMutationLease | None = None
    clock: Callable[[], float] | None = None
    _documents: dict[str, ManagedOperationWorklistDocument] = field(
        default_factory=dict, init=False, repr=False
    )
    _metrics: ManagedOperationMetrics = field(
        default_factory=ManagedOperationMetrics, init=False, repr=False
    )
    _stage_started: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _stage_ms: dict[str, int] = field(default_factory=dict, init=False, repr=False)
    _op_started: float | None = field(default=None, init=False, repr=False)
    _dense_generation_started: float | None = field(default=None, init=False, repr=False)
    _membership_frozen: bool = field(default=False, init=False, repr=False)
    write_count: int = field(default=0, init=False)

    def _mono(self) -> float:
        return self.clock() if self.clock is not None else time.monotonic()

    def initialize(
        self,
        *,
        desired: Sequence[SourceVersionRecord],
        pre_active_source_count: int,
    ) -> None:
        """Freeze worklist membership and seed workload metrics at admission."""
        if self._membership_frozen:
            return
        docs: list[ManagedOperationWorklistDocument] = []
        uploaded = 0
        for item in desired:
            doc_id = item.document_id or item.source_id
            docs.append(
                ManagedOperationWorklistDocument(
                    document_id=doc_id,
                    display_name=item.display_name,
                    phase=ManagedOperationDocumentPhase.PENDING,
                )
            )
            if item.byte_size is not None:
                uploaded += item.byte_size
        self._documents = {item.document_id: item for item in docs}
        self._membership_frozen = True
        self._op_started = self._mono()
        self._metrics = ManagedOperationMetrics(
            requested_document_count=len(docs),
            pre_active_source_count=pre_active_source_count,
            uploaded_raw_bytes=uploaded,
            stage_durations=ManagedOperationStageDurations(),
        )
        self._persist()

    def hydrate(
        self,
        *,
        worklist: ManagedOperationWorklist,
        metrics: ManagedOperationMetrics | None,
    ) -> None:
        """Resume publisher state from an already-admitted durable worklist."""
        if self._membership_frozen:
            return
        self._documents = {
            item.document_id: item for item in worklist.documents
        }
        self._membership_frozen = True
        self._op_started = self._mono()
        self._metrics = metrics or ManagedOperationMetrics(
            requested_document_count=worklist.total_document_count,
            stage_durations=ManagedOperationStageDurations(),
        )

    def before_stage(self, stage: str) -> None:
        self._stage_started[stage] = self._mono()
        if stage == "dense":
            # Dense batches may span many documents; mark the full ready set active.
            self._dense_generation_started = self._mono()
            self._advance_all_ready_for(
                from_phases={
                    ManagedOperationDocumentPhase.CHUNKED,
                    ManagedOperationDocumentPhase.PARSED,
                    ManagedOperationDocumentPhase.PENDING,
                },
                to_phase=ManagedOperationDocumentPhase.INDEXING,
            )
            self._persist()
        # Parse/chunk phases are driven by per-document events for truthful 0..N activity.

    def after_stage(self, stage: str) -> None:
        started = self._stage_started.pop(stage, None)
        if started is not None:
            elapsed = max(0, int((self._mono() - started) * 1000))
            self._stage_ms[stage] = elapsed
        if stage == "publish":
            self._metrics = self._metrics.model_copy(
                update={
                    "stage_durations": self._durations_model(),
                    "post_active_source_count": self._metrics.requested_document_count,
                }
            )
            if self._op_started is not None:
                total_ms = max(0, int((self._mono() - self._op_started) * 1000))
                durations = self._metrics.stage_durations or ManagedOperationStageDurations()
                self._metrics = self._metrics.model_copy(
                    update={
                        "stage_durations": durations.model_copy(
                            update={"total_ms": total_ms, "publication_ms": self._stage_ms.get("publish")}
                        )
                    }
                )
            # Mark non-failed documents indexed/prepared at publish completion.
            for doc_id, item in list(self._documents.items()):
                if item.phase not in {
                    ManagedOperationDocumentPhase.FAILED,
                    ManagedOperationDocumentPhase.REQUIRES_OCR,
                }:
                    self._documents[doc_id] = item.model_copy(
                        update={"phase": ManagedOperationDocumentPhase.INDEXED}
                    )
        self._persist()

    def after_stage_report(self, stage: str, report: object) -> None:
        try:
            if stage == "ingest" and isinstance(report, IngestionReport):
                self._apply_ingestion_report(report)
            elif stage == "chunk" and isinstance(report, ChunkingReport):
                self._apply_chunking_report(report)
            elif stage == "dense" and isinstance(report, IndexingReport):
                self._apply_dense_report(report)
            elif stage == "lexical" and isinstance(report, LexicalIndexingReport):
                self._apply_lexical_report(report)
        except Exception:  # noqa: BLE001 — observability must not escape
            return
        self._persist()

    def set_dense_execution(self, execution: ManagedOperationDenseExecution) -> None:
        self._metrics = self._metrics.model_copy(update={"dense_execution": execution})
        self._persist()

    def __call__(self, event: DocumentPhaseEvent) -> None:
        """Document-phase reporter entrypoint (exception-isolated by caller too)."""
        try:
            self._apply_document_phase(event)
            self._persist()
        except Exception:  # noqa: BLE001
            return

    def _apply_document_phase(self, event: DocumentPhaseEvent) -> None:
        if not self._membership_frozen:
            return
        phase = _parse_phase(event.phase)
        if phase is None:
            return
        doc_id = event.document_id
        item = self._documents.get(doc_id)
        if item is None:
            # Match by display name when pipeline keys by source_name only briefly.
            for key, existing in self._documents.items():
                if existing.display_name == event.source_name:
                    doc_id = key
                    item = existing
                    break
        if item is None:
            return
        if item.phase in {
            ManagedOperationDocumentPhase.FAILED,
            ManagedOperationDocumentPhase.REQUIRES_OCR,
        }:
            return
        prior_rank = _PHASE_RANK.get(item.phase, 0)
        next_rank = _PHASE_RANK.get(phase, 0)
        if next_rank < prior_rank and phase not in {
            ManagedOperationDocumentPhase.FAILED,
            ManagedOperationDocumentPhase.REQUIRES_OCR,
        }:
            return
        self._documents[doc_id] = item.model_copy(update={"phase": phase})

    def _apply_ingestion_report(self, report: IngestionReport) -> None:
        durations = self._durations_model().model_copy(
            update={"parsing_ms": self._stage_ms.get("ingest", report.duration_ms)}
        )
        self._metrics = self._metrics.model_copy(
            update={
                "parsed_artifacts_generated": report.files_parsed,
                "parsed_artifacts_reused": report.files_reused,
                "parsed_searchable_document_count": report.files_parsed
                + report.files_reused,
                "stage_durations": durations,
            }
        )
        for file_result in report.files:
            doc_id = file_result.document_id
            if not doc_id:
                continue
            if file_result.status is FileIngestionStatus.FAILED:
                phase = ManagedOperationDocumentPhase.FAILED
                err = (file_result.error or "").lower()
                if "ocr" in err:
                    phase = ManagedOperationDocumentPhase.REQUIRES_OCR
                self._apply_document_phase(
                    DocumentPhaseEvent(
                        document_id=doc_id,
                        source_name=file_result.source_name,
                        phase=str(phase),
                    )
                )
            else:
                self._apply_document_phase(
                    DocumentPhaseEvent(
                        document_id=doc_id,
                        source_name=file_result.source_name,
                        phase=str(ManagedOperationDocumentPhase.PARSED),
                    )
                )

    def _apply_chunking_report(self, report: ChunkingReport) -> None:
        oversized = report.metadata.get("oversized_unsplittable_count")
        oversized_count = int(oversized) if isinstance(oversized, int) else None
        durations = self._durations_model().model_copy(
            update={"chunking_ms": self._stage_ms.get("chunk", report.duration_ms)}
        )
        self._metrics = self._metrics.model_copy(
            update={
                "chunk_artifacts_generated": report.documents_chunked,
                "chunk_artifacts_reused": report.documents_reused,
                "child_chunk_count": report.child_chunks,
                "oversized_unsplittable_count": oversized_count,
                "stage_durations": durations,
            }
        )
        for doc in report.documents:
            item = self._documents.get(doc.document_id)
            display = item.display_name if item is not None else doc.document_id
            if doc.status is DocumentChunkStatus.FAILED:
                self._apply_document_phase(
                    DocumentPhaseEvent(
                        document_id=doc.document_id,
                        source_name=display,
                        phase=str(ManagedOperationDocumentPhase.FAILED),
                    )
                )
                continue
            self._apply_document_phase(
                DocumentPhaseEvent(
                    document_id=doc.document_id,
                    source_name=display,
                    phase=str(ManagedOperationDocumentPhase.CHUNKED),
                )
            )
            if item is not None:
                self._documents[doc.document_id] = self._documents[
                    doc.document_id
                ].model_copy(update={"child_chunk_count": doc.child_count})

    def _apply_dense_report(self, report: IndexingReport) -> None:
        meta_gen = report.metadata.get("dense_generation_ms")
        meta_mat = report.metadata.get("dense_materialization_ms")
        dense_gen_ms = meta_gen if isinstance(meta_gen, int) else self._stage_ms.get("dense")
        dense_mat_ms = meta_mat if isinstance(meta_mat, int) else None
        chunks_per_sec = None
        if (
            report.embeddings_generated > 0
            and isinstance(dense_gen_ms, int)
            and dense_gen_ms > 0
        ):
            chunks_per_sec = (report.embeddings_generated * 1000.0) / float(dense_gen_ms)
        # model_input_tokens_per_sec omitted unless a truthful measurement exists.
        token_rate = report.metadata.get("model_input_tokens_per_sec")
        tokens_per_sec = float(token_rate) if isinstance(token_rate, (int, float)) else None
        execution = self._metrics.dense_execution
        raw_exec = report.metadata.get("dense_execution")
        if isinstance(raw_exec, dict):
            execution = ManagedOperationDenseExecution(
                device=raw_exec.get("device"),
                dtype=raw_exec.get("dtype"),
                batch_size=raw_exec.get("batch_size"),
                attention_backend=raw_exec.get("attention_backend"),
                embedding_dimension=raw_exec.get("embedding_dimension"),
            )
        durations = self._durations_model().model_copy(
            update={
                "dense_generation_ms": dense_gen_ms,
                "dense_materialization_ms": dense_mat_ms,
            }
        )
        self._metrics = self._metrics.model_copy(
            update={
                "embeddings_generated": report.embeddings_generated,
                "embeddings_reused": report.embeddings_reused,
                "child_chunk_count": report.children_total or self._metrics.child_chunk_count,
                "generated_chunks_per_sec": chunks_per_sec,
                "model_input_tokens_per_sec": tokens_per_sec,
                "dense_execution": execution,
                "stage_durations": durations,
            }
        )
        for doc_id, item in list(self._documents.items()):
            if item.phase is ManagedOperationDocumentPhase.INDEXING:
                self._documents[doc_id] = item.model_copy(
                    update={"phase": ManagedOperationDocumentPhase.INDEXED}
                )

    def _apply_lexical_report(self, report: LexicalIndexingReport) -> None:
        durations = self._durations_model().model_copy(
            update={"lexical_ms": self._stage_ms.get("lexical", report.duration_ms)}
        )
        self._metrics = self._metrics.model_copy(update={"stage_durations": durations})

    def _advance_all_ready_for(
        self,
        *,
        from_phases: set[ManagedOperationDocumentPhase],
        to_phase: ManagedOperationDocumentPhase,
    ) -> None:
        for doc_id, item in list(self._documents.items()):
            if item.phase in from_phases:
                self._documents[doc_id] = item.model_copy(update={"phase": to_phase})

    def _durations_model(self) -> ManagedOperationStageDurations:
        current = self._metrics.stage_durations or ManagedOperationStageDurations()
        return current.model_copy(
            update={
                "parsing_ms": self._stage_ms.get("ingest", current.parsing_ms),
                "chunking_ms": self._stage_ms.get("chunk", current.chunking_ms),
                "lexical_ms": self._stage_ms.get("lexical", current.lexical_ms),
                "publication_ms": self._stage_ms.get("publish", current.publication_ms),
            }
        )

    def _persist(self) -> None:
        if not self._membership_frozen:
            return
        worklist = build_managed_operation_worklist(list(self._documents.values()))
        try:
            self.operations.update_metrics(
                self.workspace_id,
                self.operation_id,
                self._metrics,
                lease=self.lease,
            )
            self.operations.update_worklist(
                self.workspace_id,
                self.operation_id,
                worklist,
                lease=self.lease,
            )
            self.write_count += 1
        except Exception:  # noqa: BLE001 — telemetry must not escape
            return

    def snapshot_metrics(self) -> ManagedOperationMetrics:
        return self._metrics

    def snapshot_worklist_docs(self) -> list[ManagedOperationWorklistDocument]:
        return list(self._documents.values())


def dense_execution_from_runtime(
    *,
    embedder: Any,
    batch_size: int | None,
) -> ManagedOperationDenseExecution:
    """Capture observed dense execution facts from the live embedder/settings."""
    device = getattr(embedder, "resolved_device", None) or getattr(embedder, "device", None)
    dtype = getattr(embedder, "dtype", None)
    if dtype is not None and not isinstance(dtype, str):
        dtype = str(dtype)
    attention = getattr(embedder, "attention_backend", None)
    dimension = getattr(embedder, "dimension", None)
    return ManagedOperationDenseExecution(
        device=str(device) if device is not None else None,
        dtype=dtype,
        batch_size=batch_size,
        attention_backend=str(attention) if attention is not None else None,
        embedding_dimension=int(dimension) if isinstance(dimension, int) else None,
    )


__all__ = [
    "DurableObservabilityPublisher",
    "dense_execution_from_runtime",
]
