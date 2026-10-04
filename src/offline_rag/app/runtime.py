"""Process application runtime lifecycle (D02 / D09 / D15 / D19) — Slice 15B–15F."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from offline_rag.app.candidate_recovery import recover_abandoned_candidates
from offline_rag.app.capacity import CapacityGate
from offline_rag.app.errors import AppError, ErrorCode
from offline_rag.app.ingest_hooks import ProductIngestHooks
from offline_rag.app.operations import OperationRegistry
from offline_rag.app.paths import ensure_data_directories, required_data_directories
from offline_rag.app.publication import ProductPublicationRegistry
from offline_rag.app.query_runtime import QueryRuntimeCache
from offline_rag.app.startup_validation import validate_global_startup_requirements
from offline_rag.config.models import AppSettings

ResourceFactory = Callable[[AppSettings], Any]


class RuntimeState(StrEnum):
    NOT_STARTED = "not_started"
    STARTING = "starting"
    READY = "ready"
    NOT_READY = "not_ready"
    DRAINING = "draining"
    STOPPED = "stopped"


@dataclass
class ResourceFactories:
    """Injectable constructors for process-scoped resources."""

    embedder: ResourceFactory
    reranker: ResourceFactory
    generator_client: ResourceFactory
    qdrant: ResourceFactory | None = None


@dataclass
class ProcessResources:
    embedder: Any = None
    reranker: Any = None
    generator_client: Any = None
    qdrant: Any = None

    def close(self) -> None:
        for name in ("generator_client", "reranker", "embedder", "qdrant"):
            obj = getattr(self, name)
            if obj is None:
                continue
            close = getattr(obj, "close", None)
            if callable(close):
                close()
            setattr(self, name, None)


@dataclass
class ConstructionCounters:
    embedder: int = 0
    reranker: int = 0
    generator_client: int = 0
    qdrant: int = 0


def default_resource_factories() -> ResourceFactories:
    """Production factories — construct once at startup, never from health."""

    def embedder(settings: AppSettings) -> Any:
        from offline_rag.dense.embedder import make_embedder

        return make_embedder(settings)

    def reranker(settings: AppSettings) -> Any:
        if not settings.reranker.enabled:
            return None
        from offline_rag.rerank.cross_encoder import CrossEncoderReranker

        return CrossEncoderReranker.from_settings(settings)

    def generator_client(settings: AppSettings) -> Any:
        # Construct client only — no /models or chat probe (D09/D16).
        from offline_rag.generation.openai_compatible import OpenAICompatibleGenerator

        return OpenAICompatibleGenerator(settings)

    def qdrant(settings: AppSettings) -> Any:
        from offline_rag.dense.qdrant_local import QdrantLocalBackend

        return QdrantLocalBackend(settings.paths.qdrant_storage)

    return ResourceFactories(
        embedder=embedder,
        reranker=reranker,
        generator_client=generator_client,
        qdrant=qdrant,
    )


def _assert_required_paths_usable(settings: AppSettings) -> None:
    for path in required_data_directories(settings):
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"required data directory missing: {path}")
        if not os.access(path, os.W_OK):
            raise RuntimeError(f"required data directory not writable: {path}")


@dataclass
class ApplicationRuntime:
    """Owns process settings, readiness, resources, and operation control."""

    settings: AppSettings
    factories: ResourceFactories = field(default_factory=default_resource_factories)
    product_ingest_hooks: ProductIngestHooks | None = None
    state: RuntimeState = field(default=RuntimeState.NOT_STARTED, init=False)
    resources: ProcessResources | None = field(default=None, init=False)
    failure_reason: str | None = field(default=None, init=False)
    construction_counts: ConstructionCounters = field(
        default_factory=ConstructionCounters, init=False
    )
    query_capacity: CapacityGate = field(init=False)
    ingest_capacity: CapacityGate = field(init=False)
    operations: OperationRegistry = field(init=False)
    _shutdown_count: int = field(default=0, init=False)
    _publication: ProductPublicationRegistry | None = field(default=None, init=False)
    _query_runtimes: QueryRuntimeCache | None = field(default=None, init=False)
    _finalize_lock: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        import threading

        self.query_capacity = CapacityGate(
            max_concurrent=int(self.settings.api.max_concurrent_query)
        )
        self.ingest_capacity = CapacityGate(
            max_concurrent=int(self.settings.api.max_concurrent_ingest)
        )
        self.operations = OperationRegistry(
            settings=self.settings,
            query_capacity=self.query_capacity,
            ingest_capacity=self.ingest_capacity,
        )
        self._finalize_lock = threading.Lock()

    @property
    def is_ready(self) -> bool:
        return self.state is RuntimeState.READY

    @property
    def is_live(self) -> bool:
        return self.state is not RuntimeState.STOPPED

    @property
    def publication(self) -> ProductPublicationRegistry:
        if self._publication is None:
            qdrant = None if self.resources is None else self.resources.qdrant
            self._publication = ProductPublicationRegistry(
                self.settings, qdrant=qdrant
            )
        return self._publication

    @property
    def query_runtimes(self) -> QueryRuntimeCache:
        """Corpus/snapshot-scoped product query wiring cache (D02)."""
        if self._query_runtimes is None:
            self._query_runtimes = QueryRuntimeCache(
                settings=self.settings,
                resources_provider=lambda: self.resources,
            )
        return self._query_runtimes

    def start(self) -> None:
        """Initialize process resources at most once per startup attempt.

        Failures leave the runtime NOT_READY (fail closed). Does not download
        models or probe the generator.
        """
        if self.state is RuntimeState.READY:
            return
        if self.state is RuntimeState.STARTING:
            return

        self.state = RuntimeState.STARTING
        self.failure_reason = None
        embedder: Any = None
        reranker: Any = None
        generator_client: Any = None
        qdrant: Any = None
        try:
            ensure_data_directories(self.settings)
            _assert_required_paths_usable(self.settings)
            # Static global asset/config gates — never download or probe (D09/D16).
            validate_global_startup_requirements(self.settings)
            # D15: quarantine unpublished candidates; never auto-publish.
            recover_abandoned_candidates(self.settings)

            self.construction_counts.embedder += 1
            embedder = self.factories.embedder(self.settings)

            self.construction_counts.reranker += 1
            reranker = self.factories.reranker(self.settings)

            self.construction_counts.generator_client += 1
            generator_client = self.factories.generator_client(self.settings)

            if self.factories.qdrant is not None:
                self.construction_counts.qdrant += 1
                qdrant = self.factories.qdrant(self.settings)

            self.resources = ProcessResources(
                embedder=embedder,
                reranker=reranker,
                generator_client=generator_client,
                qdrant=qdrant,
            )
            self._publication = ProductPublicationRegistry(
                self.settings, qdrant=qdrant
            )
            self._query_runtimes = QueryRuntimeCache(
                settings=self.settings,
                resources_provider=lambda: self.resources,
            )
            self.state = RuntimeState.READY
        except Exception:  # noqa: BLE001 — fail closed on any startup fault
            for obj in (generator_client, reranker, embedder, qdrant):
                close = getattr(obj, "close", None) if obj is not None else None
                if callable(close):
                    close()
            self.resources = None
            self._publication = None
            if self._query_runtimes is not None:
                self._query_runtimes.close()
            self._query_runtimes = None
            self.state = RuntimeState.NOT_READY
            self.failure_reason = "startup_failed"

    def require_ready(self) -> None:
        if not self.is_ready:
            raise AppError(ErrorCode.RUNTIME_NOT_READY)

    def begin_drain(self) -> None:
        """Enter DRAINING: readiness false; signal cooperative cancellation."""
        if self.state is RuntimeState.STOPPED:
            return
        if self.state is RuntimeState.DRAINING:
            self.operations.signal_shutdown()
            return
        self.state = RuntimeState.DRAINING
        self._shutdown_count += 1
        self.operations.signal_shutdown()

    def wait_for_drain(self, timeout_seconds: float | None = None) -> bool:
        """Wait for active operations to finish (sync). Grace expiry ≠ timeout."""
        grace = (
            float(self.settings.api.shutdown_grace_seconds)
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        return self.operations.wait_until_idle(grace)

    def finalize_shutdown(self) -> None:
        """Close corpus-scoped then process-scoped resources; enter STOPPED."""
        with self._finalize_lock:
            if self.state is RuntimeState.STOPPED:
                return
            if self.state is not RuntimeState.DRAINING:
                self.state = RuntimeState.DRAINING
            if self._query_runtimes is not None:
                self._query_runtimes.close()
                self._query_runtimes = None
            if self.resources is not None:
                self.resources.close()
                self.resources = None
            self._publication = None
            self.state = RuntimeState.STOPPED

    def shutdown(self) -> None:
        """Idempotent sync drain (tests / non-ASGI). Does not invent timeouts."""
        if self.state is RuntimeState.STOPPED:
            return
        self.begin_drain()
        self.wait_for_drain()
        self.finalize_shutdown()

    async def drain_async(self) -> None:
        """ASGI lifespan drain: keep the event loop responsive while waiting."""
        if self.state is RuntimeState.STOPPED:
            return
        self.begin_drain()
        grace = float(self.settings.api.shutdown_grace_seconds)
        await asyncio.to_thread(self.wait_for_drain, grace)
        self.finalize_shutdown()

    @property
    def shutdown_count(self) -> int:
        return self._shutdown_count
