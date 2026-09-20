"""Historical ChunkSet resolution for fixed-evidence evaluation."""

from __future__ import annotations

from pathlib import Path

from offline_rag.chunking.access import (
    ChunkAccessError,
    CorpusChunkSnapshot,
    load_chunk_set_snapshot,
)
from offline_rag.config.models import AppSettings
from offline_rag.evaluation.gold import LoadedGoldDataset
from offline_rag.ingestion.persistence import (
    corpus_state_path,
    load_corpus_manifest,
    load_corpus_state,
)


class HistoricalChunkSetError(RuntimeError):
    """Fail-closed historical ChunkSet / corpus-manifest resolution error."""


def resolve_corpus_manifest_name(
    settings: AppSettings,
    *,
    corpus_name: str,
    corpus_id: str,
) -> str | None:
    """Resolve authoritative corpus manifest filename for a historical corpus_id."""
    state_path = corpus_state_path(settings.paths.corpora, corpus_name)
    if state_path.exists():
        try:
            state = load_corpus_state(state_path)
        except Exception:  # noqa: BLE001 - best-effort then scan
            state = None
        if state is not None and state.current_corpus_id == corpus_id:
            return Path(state.current_manifest).name

    manifests_root = settings.paths.manifests
    if not manifests_root.exists():
        return None
    for path in sorted(manifests_root.glob("*.json")):
        try:
            manifest = load_corpus_manifest(path)
        except Exception:  # noqa: BLE001, S112
            continue
        if manifest.corpus_id == corpus_id:
            return path.name
    return None


def load_gold_historical_chunk_snapshot(
    settings: AppSettings,
    gold: LoadedGoldDataset,
    *,
    corpus_name: str,
) -> CorpusChunkSnapshot:
    """Load the exact historical ChunkSet named by GoldDataset (not CURRENT)."""
    meta = gold.meta
    if not meta.chunk_set_id:
        raise HistoricalChunkSetError("GoldDataset chunk_set_id is required")
    corpus_id = meta.corpus_id
    if not corpus_id:
        raise HistoricalChunkSetError("GoldDataset corpus_id is required")
    if meta.corpus_name is not None and meta.corpus_name != corpus_name:
        raise HistoricalChunkSetError(
            f"corpus name mismatch: cli={corpus_name} gold={meta.corpus_name}"
        )

    manifest_name = resolve_corpus_manifest_name(
        settings, corpus_name=corpus_name, corpus_id=corpus_id
    )
    try:
        return load_chunk_set_snapshot(
            settings,
            corpus_name=corpus_name,
            corpus_id=corpus_id,
            chunk_set_id=meta.chunk_set_id,
            corpus_manifest_name=manifest_name,
        )
    except ChunkAccessError as exc:
        raise HistoricalChunkSetError(str(exc)) from exc
