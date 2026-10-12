"""Ensure candidate-pooling-v1 artifacts exist for an exact historical identity."""

from __future__ import annotations

from offline_rag.config.models import AppSettings
from offline_rag.core.ids import dense_index_id, lexical_index_id
from offline_rag.core.progress import ProgressReporter
from offline_rag.dense.backend import DenseIndexBackend
from offline_rag.dense.config_hash import build_index_config_hash
from offline_rag.dense.embedder import Embedder
from offline_rag.dense.historical_auxiliary import (
    HistoricalAuxiliaryBuildResult,
    HistoricalAuxiliaryError,
    build_historical_auxiliary_dense_index,
)
from offline_rag.dense.persistence import try_load_index_manifest
from offline_rag.gold_authoring.chunk_access import (
    ChunkAccessError,
    load_chunk_set_snapshot,
)
from offline_rag.gold_authoring.pool_contract import arm_h_index_identity
from offline_rag.gold_authoring.pool_preflight import (
    PoolPreflightError,
    ResolvedPoolingArtifacts,
    preflight_pooling_artifacts_for_ids,
)
from offline_rag.lexical.config_hash import build_lexical_config_hash
from offline_rag.lexical.persistence import try_load_lexical_index_manifest


class PoolEnsureError(RuntimeError):
    """Pooling artifact establishment failure (maps to pooling_artifact_unavailable)."""

    def __init__(self, message: str, *, subcause: str) -> None:
        super().__init__(message)
        self.subcause = subcause


def ensure_pooling_artifacts(
    settings: AppSettings,
    *,
    corpus_id: str,
    corpus_name: str,
    chunk_set_id: str,
    qdrant: DenseIndexBackend,
    embedder: Embedder,
    on_progress: ProgressReporter | None = None,
) -> ResolvedPoolingArtifacts:
    """Validate ordinary publication artifacts and ensure Arm-H for captured identity.

    Never resolves CURRENT workspace state. Never rebuilds baseline dense or lexical.
    Never writes index_state / publication CURRENT. Ends with pure preflight.
    """
    chunk_set_id = str(chunk_set_id).strip()
    corpus_id = str(corpus_id).strip()
    corpus_name = str(corpus_name).strip() or "default"
    if not chunk_set_id:
        raise PoolEnsureError(
            "authoring run missing chunk_set_id",
            subcause="historical_chunk_set_missing",
        )
    if not corpus_id:
        raise PoolEnsureError(
            "authoring run missing corpus_id",
            subcause="historical_chunk_set_missing",
        )

    chunk_manifest_name = f"{chunk_set_id}.json"
    try:
        load_chunk_set_snapshot(
            settings,
            corpus_name=corpus_name,
            corpus_id=corpus_id,
            chunk_set_id=chunk_set_id,
            corpus_manifest_name=f"{corpus_id}.json",
        )
    except ChunkAccessError as exc:
        raise PoolEnsureError(
            str(exc), subcause="historical_chunk_set_missing"
        ) from exc

    _require_baseline_and_lexical(
        settings,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
    )

    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    try:
        build_historical_auxiliary_dense_index(
            settings=arm_h.settings,
            corpus_id=corpus_id,
            corpus_name=corpus_name,
            chunk_set_id=chunk_set_id,
            chunk_manifest_name=chunk_manifest_name,
            embedder=embedder,
            backend=qdrant,
            on_progress=on_progress,
        )
    except HistoricalAuxiliaryError as exc:
        raise PoolEnsureError(str(exc), subcause=exc.subcause) from exc

    try:
        return preflight_pooling_artifacts_for_ids(
            settings,
            corpus_id=corpus_id,
            corpus_name=corpus_name,
            chunk_set_id=chunk_set_id,
        )
    except PoolPreflightError as exc:
        raise PoolEnsureError(
            str(exc), subcause="arm_h_identity_mismatch"
        ) from exc


def ensure_arm_h_only(
    settings: AppSettings,
    *,
    corpus_id: str,
    corpus_name: str,
    chunk_set_id: str,
    qdrant: DenseIndexBackend,
    embedder: Embedder,
    on_progress: ProgressReporter | None = None,
) -> HistoricalAuxiliaryBuildResult:
    """Build/reuse Arm-H only (test helper; still requires ordinary prerequisites)."""
    _require_baseline_and_lexical(
        settings,
        corpus_id=corpus_id,
        chunk_set_id=chunk_set_id,
    )
    arm_h = arm_h_index_identity(settings, chunk_set_id=chunk_set_id)
    try:
        return build_historical_auxiliary_dense_index(
            settings=arm_h.settings,
            corpus_id=corpus_id,
            corpus_name=corpus_name,
            chunk_set_id=chunk_set_id,
            chunk_manifest_name=f"{chunk_set_id}.json",
            embedder=embedder,
            backend=qdrant,
            on_progress=on_progress,
        )
    except HistoricalAuxiliaryError as exc:
        raise PoolEnsureError(str(exc), subcause=exc.subcause) from exc


def _require_baseline_and_lexical(
    settings: AppSettings,
    *,
    corpus_id: str,
    chunk_set_id: str,
) -> None:
    lex_cfg = build_lexical_config_hash(settings)
    lex_id = lexical_index_id(
        chunk_set_id,
        lex_cfg,
        backend_contract=settings.lexical.backend_contract,
    )
    lex_manifest = try_load_lexical_index_manifest(
        settings.paths.lexical_index_manifests, lex_id
    )
    if lex_manifest is None or lex_manifest.chunk_set_id != chunk_set_id:
        raise PoolEnsureError(
            f"lexical artifact missing/mismatched for chunk_set_id={chunk_set_id}",
            subcause="lexical_index_missing",
        )
    if lex_manifest.corpus_id != corpus_id:
        raise PoolEnsureError(
            f"lexical artifact corpus_id mismatch for chunk_set_id={chunk_set_id}",
            subcause="lexical_index_missing",
        )

    baseline_cfg = build_index_config_hash(settings)
    baseline_id = dense_index_id(chunk_set_id, baseline_cfg)
    baseline_manifest = try_load_index_manifest(
        settings.paths.index_manifests, baseline_id
    )
    if baseline_manifest is None or baseline_manifest.chunk_set_id != chunk_set_id:
        raise PoolEnsureError(
            f"dense baseline artifact missing/mismatched for chunk_set_id={chunk_set_id}",
            subcause="baseline_dense_missing",
        )
    if baseline_manifest.corpus_id != corpus_id:
        raise PoolEnsureError(
            f"dense baseline corpus_id mismatch for chunk_set_id={chunk_set_id}",
            subcause="baseline_dense_missing",
        )
