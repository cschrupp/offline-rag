"""Product publication registry and snapshot resolution (D03/D04/D10/D15)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from offline_rag.app.corpus import validate_product_corpus_name
from offline_rag.app.errors import AppError, ErrorCode, SafeErrorDetails
from offline_rag.app.snapshot import (
    PRODUCT_MODE_GROUNDED_V1,
    CanonicalSnapshotManifest,
    CorpusReadSnapshot,
    PublishedPointer,
    compute_snapshot_id,
)
from offline_rag.chunking.persistence import load_chunk_set_manifest
from offline_rag.chunking.tokenize import TiktokenTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.context.config_hash import build_context_config_hash
from offline_rag.dense.config_hash import (
    build_embedding_config_hash,
    build_index_config_hash,
)
from offline_rag.dense.persistence import load_index_manifest
from offline_rag.hybrid.config_hash import build_fusion_config_hash
from offline_rag.ingestion.io import atomic_write_text
from offline_rag.ingestion.persistence import load_corpus_manifest
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import load_lexical_index_manifest
from offline_rag.rerank.config_hash import build_reranker_config_hash


def product_dir(corpora_root: Path, corpus_name: str) -> Path:
    return corpora_root / corpus_name / "product"


def current_pointer_path(corpora_root: Path, corpus_name: str) -> Path:
    return product_dir(corpora_root, corpus_name) / "current.json"


def snapshot_manifest_path(
    corpora_root: Path, corpus_name: str, snapshot_id: str
) -> Path:
    return product_dir(corpora_root, corpus_name) / "snapshots" / f"{snapshot_id}.json"


def _manifest_file(root: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute():
        return path
    return root / path.name


class ProductPublicationRegistry:
    """App-owned product publication registry (separate from stage state.json)."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        qdrant: Any | None = None,
    ) -> None:
        self.settings = settings
        self.qdrant = qdrant

    def _resolve_corpus_name(self, corpus_name: str) -> str:
        return validate_product_corpus_name(corpus_name)

    def published_snapshot_id(self, corpus_name: str) -> str | None:
        name = self._resolve_corpus_name(corpus_name)
        pointer = current_pointer_path(self.settings.paths.corpora, name)
        if not pointer.exists():
            return None
        try:
            current = PublishedPointer.model_validate_json(
                pointer.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError):
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(corpus=name, reason="pointer_unreadable"),
            ) from None
        return current.snapshot_id

    def validate_grounded_identity(
        self,
        identity: CanonicalSnapshotManifest,
        *,
        require_current_config_match: bool = True,
    ) -> None:
        """Fail closed when identity cannot certify grounded_v1 readiness."""
        if identity.product_mode_id != PRODUCT_MODE_GROUNDED_V1:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="unsupported_product_mode"),
            )

        try:
            corpus_m = load_corpus_manifest(
                _manifest_file(self.settings.paths.manifests, identity.corpus_manifest)
            )
            chunk_m = load_chunk_set_manifest(
                _manifest_file(
                    self.settings.paths.chunk_manifests, identity.chunk_manifest
                )
            )
            dense_m = load_index_manifest(
                _manifest_file(
                    self.settings.paths.index_manifests, identity.dense_index_manifest
                )
            )
            lexical_m = load_lexical_index_manifest(
                _manifest_file(
                    self.settings.paths.lexical_index_manifests,
                    identity.lexical_index_manifest,
                )
            )
        except FileNotFoundError as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="artifact_missing"),
            ) from exc
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="artifact_corrupt"),
            ) from exc

        if corpus_m.corpus_id != identity.corpus_id:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="corpus_id_mismatch"),
            )
        if chunk_m.corpus_id != identity.corpus_id or chunk_m.chunk_set_id != identity.chunk_set_id:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="chunk_provenance_mismatch"),
            )
        if (
            dense_m.corpus_id != identity.corpus_id
            or dense_m.chunk_set_id != identity.chunk_set_id
            or dense_m.index_id != identity.dense_index_id
        ):
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="dense_provenance_mismatch"),
            )
        if (
            lexical_m.corpus_id != identity.corpus_id
            or lexical_m.chunk_set_id != identity.chunk_set_id
            or lexical_m.lexical_index_id != identity.lexical_index_id
        ):
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="lexical_provenance_mismatch"),
            )

        if dense_m.embedding_config_hash != identity.embedding_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="embedding_config_mismatch"),
            )
        if dense_m.index_config_hash != identity.index_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="index_config_mismatch"),
            )
        if lexical_m.lexical_config_hash != identity.lexical_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="lexical_config_mismatch"),
            )

        if require_current_config_match:
            self._assert_current_config_matches(identity)

        self._assert_dense_backing_complete(dense_m)
        self._assert_lexical_backing_complete(lexical_m)

    def _assert_dense_backing_complete(self, dense_m: Any) -> None:
        """Require complete dense publication semantics (manifest + Qdrant)."""
        if (
            dense_m.expected_child_count != dense_m.indexed_child_count
            or dense_m.indexed_child_count < 1
        ):
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="dense_index_incomplete"),
            )

        if self.qdrant is None:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="qdrant_unavailable"),
            )
        exists = getattr(self.qdrant, "collection_exists", None)
        count = getattr(self.qdrant, "count", None)
        if not callable(exists) or not callable(count):
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="qdrant_unavailable"),
            )
        if not exists(dense_m.collection_name):
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="qdrant_collection_missing"),
            )
        try:
            actual = int(count(dense_m.collection_name))
        except Exception as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="qdrant_count_failed"),
            ) from exc
        if actual != dense_m.indexed_child_count:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="qdrant_count_mismatch"),
            )

    def _assert_lexical_backing_complete(self, lexical_m: Any) -> None:
        """Require complete lexical publication semantics (manifest + validate)."""
        if (
            lexical_m.expected_child_count != lexical_m.indexed_child_count
            or lexical_m.indexed_child_count < 1
        ):
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="lexical_index_incomplete"),
            )

        from offline_rag.lexical.backend import LocalInvertedIndexBackend

        backend = LocalInvertedIndexBackend(self.settings.paths.lexical_indexes)
        if not backend.index_exists(lexical_m.lexical_index_id):
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="lexical_index_missing"),
            )
        if not backend.validate(lexical_m.lexical_index_id):
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(reason="lexical_index_invalid"),
            )

    def _assert_current_config_matches(self, identity: CanonicalSnapshotManifest) -> None:
        settings = self.settings
        if build_embedding_config_hash(settings) != identity.embedding_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="embedding_config_stale"),
            )
        if build_index_config_hash(settings) != identity.index_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="index_config_stale"),
            )
        if build_lexical_config_hash(settings) != identity.lexical_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="lexical_config_stale"),
            )
        if build_fusion_config_hash(settings) != identity.fusion_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="fusion_config_stale"),
            )
        if build_reranker_config_hash(settings) != identity.reranker_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="reranker_config_stale"),
            )
        counter = TiktokenTokenCounter(
            encoding=settings.chunking.tokenizer.encoding,
            artifacts_path=settings.paths.tokenizer_artifacts,
        )
        if build_context_config_hash(settings, token_counter=counter) != identity.context_config_hash:
            raise AppError(
                ErrorCode.CORPUS_NOT_READY,
                details=SafeErrorDetails(reason="context_config_stale"),
            )

    def publish(
        self,
        corpus_name: str,
        identity: CanonicalSnapshotManifest,
        *,
        require_current_config_match: bool = True,
    ) -> str:
        """Atomically publish a validated candidate snapshot (no ingest).

        write durable immutable snapshot manifest → validate → replace pointer.
        Failure before pointer replacement leaves prior publication current.
        """
        name = self._resolve_corpus_name(corpus_name)
        snapshot_id = compute_snapshot_id(identity)
        if compute_snapshot_id(identity) != snapshot_id:
            raise RuntimeError("snapshot_id instability")

        # Validate before any product-visible mutation of the pointer.
        self.validate_grounded_identity(
            identity, require_current_config_match=require_current_config_match
        )

        snap_path = snapshot_manifest_path(self.settings.paths.corpora, name, snapshot_id)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        payload = identity.model_dump_json()
        if snap_path.exists():
            existing = snap_path.read_text(encoding="utf-8")
            if existing != payload:
                raise AppError(
                    ErrorCode.SNAPSHOT_UNAVAILABLE,
                    details=SafeErrorDetails(
                        corpus=name,
                        snapshot_id=snapshot_id,
                        reason="snapshot_conflict",
                    ),
                )
        else:
            atomic_write_text(snap_path, payload)

        # Re-validate after durable write (fail closed before pointer swap).
        self.validate_grounded_identity(
            identity, require_current_config_match=require_current_config_match
        )

        pointer = PublishedPointer(snapshot_id=snapshot_id)
        pointer_path = current_pointer_path(self.settings.paths.corpora, name)
        pointer_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(pointer_path, pointer.model_dump_json())
        # Clear stale retirement current-state marker if a prior 16A retirement
        # left retired.json behind (S16 empty/depublication foundation).
        retired = product_dir(self.settings.paths.corpora, name) / "retired.json"
        retired.unlink(missing_ok=True)
        return snapshot_id

    def resolve(self, corpus_name: str) -> CorpusReadSnapshot:
        """Resolve the product current snapshot or raise D08 corpus/snapshot errors."""
        name = self._resolve_corpus_name(corpus_name)
        pointer_path = current_pointer_path(self.settings.paths.corpora, name)
        if not pointer_path.exists():
            raise AppError(
                ErrorCode.CORPUS_UNKNOWN,
                details=SafeErrorDetails(corpus=name, reason="not_published"),
            )

        try:
            pointer = PublishedPointer.model_validate_json(
                pointer_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(corpus=name, reason="pointer_unreadable"),
            ) from exc

        snap_path = snapshot_manifest_path(
            self.settings.paths.corpora, name, pointer.snapshot_id
        )
        if not snap_path.exists():
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=name,
                    snapshot_id=pointer.snapshot_id,
                    reason="snapshot_missing",
                ),
            )
        try:
            identity = CanonicalSnapshotManifest.model_validate_json(
                snap_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError, ValueError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=name,
                    snapshot_id=pointer.snapshot_id,
                    reason="snapshot_corrupt",
                ),
            ) from exc

        expected_id = compute_snapshot_id(identity)
        if expected_id != pointer.snapshot_id:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=name,
                    snapshot_id=pointer.snapshot_id,
                    reason="snapshot_id_mismatch",
                ),
            )

        self.validate_grounded_identity(identity)

        try:
            corpus_manifest = load_corpus_manifest(
                _manifest_file(self.settings.paths.manifests, identity.corpus_manifest)
            )
        except (OSError, ValidationError, ValueError, FileNotFoundError) as exc:
            raise AppError(
                ErrorCode.SNAPSHOT_UNAVAILABLE,
                details=SafeErrorDetails(
                    corpus=name,
                    snapshot_id=pointer.snapshot_id,
                    reason="corpus_manifest_unreadable",
                ),
            ) from exc

        return CorpusReadSnapshot(
            corpus_name=name,
            snapshot_id=pointer.snapshot_id,
            identity=identity,
            corpus_manifest=corpus_manifest,
        )
