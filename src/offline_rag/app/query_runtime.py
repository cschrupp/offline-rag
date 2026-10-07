"""Corpus/snapshot-scoped product query runtime cache (15E / D02)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.query_binding import SnapshotQueryBinding
from offline_rag.config.models import AppSettings
from offline_rag.context.assemble import HybridRerankContextAssembler
from offline_rag.context.store import (
    ChunkStructureStore,
    ContextStructureError,
    load_structure_store_for_chunk_manifest,
)
from offline_rag.dense.retrieve import DenseRetriever
from offline_rag.domain.generation import GroundedAnswerResult
from offline_rag.generation.orchestrate import GroundedAnswerOrchestrator
from offline_rag.hybrid.retrieve import HybridRetriever
from offline_rag.lexical.retrieve import LexicalRetriever
from offline_rag.rerank.retrieve import HybridRerankRetriever

ResourcesProvider = Callable[[], Any]
CheckpointFn = Callable[[str], None]


@dataclass
class _SnapshotQueryRuntimeEntry:
    """Owned corpus-scoped wiring for one published snapshot identity."""

    binding: SnapshotQueryBinding
    store: ChunkStructureStore
    dense: DenseRetriever
    lexical: LexicalRetriever
    hybrid: HybridRetriever
    rerank: HybridRerankRetriever
    assembler: HybridRerankContextAssembler
    orchestrator: GroundedAnswerOrchestrator
    ref_count: int = 0
    closed: bool = False

    @property
    def key(self) -> tuple[str, str]:
        return (self.binding.corpus_name, self.binding.snapshot_id)

    def answer(
        self,
        question: str,
        *,
        checkpoint: CheckpointFn | None = None,
        document_ids: frozenset[str] | None = None,
    ) -> GroundedAnswerResult:
        if self.closed:
            raise AppError(ErrorCode.RUNTIME_NOT_READY)
        binding = self.binding
        return self.orchestrator.answer(
            query=question,
            corpus_name=binding.corpus_name,
            check_ready=False,
            allow_recovery=False,
            source_name_by_document_id=binding.source_name_by_document_id(),
            dense_index_id=binding.dense_index_id,
            dense_collection_name=binding.dense_collection_name,
            lexical_index_id=binding.lexical_index_id,
            chunk_set_id=binding.chunk_set_id,
            corpus_id=binding.corpus_id,
            document_ids=document_ids,
            checkpoint=checkpoint,
            product_v2=True,
        )

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        # Close corpus-scoped handles only. Process embedder/reranker/generator/qdrant
        # are injected and must not be closed here.
        close_orch = getattr(self.orchestrator, "close", None)
        if callable(close_orch):
            close_orch()
        self.lexical.close()
        self.dense.close()


@dataclass(frozen=True, slots=True)
class SnapshotQueryRuntimeHandle:
    """Borrow of a cached snapshot query runtime (refcounted)."""

    _entry: _SnapshotQueryRuntimeEntry

    @property
    def binding(self) -> SnapshotQueryBinding:
        return self._entry.binding

    @property
    def key(self) -> tuple[str, str]:
        return self._entry.key

    @property
    def lexical(self) -> LexicalRetriever:
        return self._entry.lexical

    @property
    def orchestrator(self) -> GroundedAnswerOrchestrator:
        return self._entry.orchestrator

    def answer(
        self,
        question: str,
        *,
        checkpoint: CheckpointFn | None = None,
        document_ids: frozenset[str] | None = None,
    ) -> GroundedAnswerResult:
        return self._entry.answer(
            question, checkpoint=checkpoint, document_ids=document_ids
        )


@dataclass
class QueryRuntimeCache:
    """App-owned cache keyed by immutable (corpus_name, snapshot_id)."""

    settings: AppSettings
    resources_provider: ResourcesProvider
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _entries: dict[tuple[str, str], _SnapshotQueryRuntimeEntry] = field(
        default_factory=dict, init=False
    )
    _current_snapshot_by_corpus: dict[str, str] = field(default_factory=dict, init=False)
    _closed: bool = field(default=False, init=False)
    build_counts: dict[tuple[str, str], int] = field(default_factory=dict, init=False)

    def acquire(self, binding: SnapshotQueryBinding) -> SnapshotQueryRuntimeHandle:
        """Return cached wiring for the snapshot, building once if needed.

        Structure-store / immutable backing validation occurs here and maps to
        ``snapshot_unavailable`` before product execution begins.
        """
        key = (binding.corpus_name, binding.snapshot_id)
        with self._lock:
            if self._closed:
                raise AppError(ErrorCode.RUNTIME_NOT_READY)
            entry = self._entries.get(key)
            if entry is None or entry.closed:
                entry = self._build_entry(binding)
                self._entries[key] = entry
                self.build_counts[key] = self.build_counts.get(key, 0) + 1
            # Latest acquired snapshot for the corpus is the invalidation frontier.
            self._current_snapshot_by_corpus[binding.corpus_name] = binding.snapshot_id
            entry.ref_count += 1
            self._prune_idle_superseded(binding.corpus_name)
            return SnapshotQueryRuntimeHandle(entry)

    def release(self, handle: SnapshotQueryRuntimeHandle) -> None:
        with self._lock:
            entry = handle._entry
            if entry.ref_count > 0:
                entry.ref_count -= 1
            self._prune_idle_superseded(entry.binding.corpus_name)

    def close(self) -> None:
        """Shutdown: close every cached corpus-scoped runtime."""
        with self._lock:
            self._closed = True
            for entry in list(self._entries.values()):
                entry.close()
            self._entries.clear()
            self._current_snapshot_by_corpus.clear()

    def _prune_idle_superseded(self, corpus_name: str) -> None:
        """Close unreferenced same-corpus entries that are not the latest acquire."""
        current_sid = self._current_snapshot_by_corpus.get(corpus_name)
        stale_keys = [
            key
            for key, entry in self._entries.items()
            if key[0] == corpus_name
            and entry.ref_count == 0
            and (current_sid is None or key[1] != current_sid)
        ]
        for key in stale_keys:
            entry = self._entries.pop(key, None)
            if entry is not None:
                entry.close()

    def _build_entry(self, binding: SnapshotQueryBinding) -> _SnapshotQueryRuntimeEntry:
        resources = self.resources_provider()
        if resources is None:
            raise AppError(ErrorCode.RUNTIME_NOT_READY)

        try:
            store = load_structure_store_for_chunk_manifest(
                self.settings, binding.chunk_manifest_name
            )
        except ContextStructureError as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=binding.corpus_name,
                    snapshot_id=binding.snapshot_id,
                    reason="chunk_structure_unavailable",
                ),
            ) from exc
        except (OSError, ValueError, ValidationError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=binding.corpus_name,
                    snapshot_id=binding.snapshot_id,
                    reason="chunk_structure_unreadable",
                ),
            ) from exc

        dense = DenseRetriever(
            self.settings,
            embedder=resources.embedder,
            backend=resources.qdrant,
        )
        lexical = LexicalRetriever(self.settings)
        hybrid = HybridRetriever(self.settings, dense=dense, lexical=lexical)
        rerank = HybridRerankRetriever(
            self.settings,
            hybrid=hybrid,
            reranker=resources.reranker,
        )
        assembler = HybridRerankContextAssembler(
            self.settings,
            retriever=rerank,
            store=store,
        )
        orchestrator = GroundedAnswerOrchestrator(
            self.settings,
            context_assembler=assembler,
            generator=resources.generator_client,
        )
        return _SnapshotQueryRuntimeEntry(
            binding=binding,
            store=store,
            dense=dense,
            lexical=lexical,
            hybrid=hybrid,
            rerank=rerank,
            assembler=assembler,
            orchestrator=orchestrator,
        )
