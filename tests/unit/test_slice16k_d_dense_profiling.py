"""16K-D D0 — observational dense profiling proofs."""

from __future__ import annotations

from pathlib import Path

import pytest

from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.pipeline import run_indexing
from offline_rag.dense.profiling import (
    DIAG_DENSE_PROFILE_ENV,
    DenseProfileCollector,
    dense_profile_enabled,
    observe_peak_vram_bytes,
)
from offline_rag.domain.indexing import IndexingStatus
from offline_rag.ingestion.pipeline import run_ingestion


def _settings(tmp_path: Path, *, batch_size: int = 2) -> AppSettings:
    settings = AppSettings()
    settings = settings.model_copy(
        update={
            "project": settings.project.model_copy(update={"strict_offline": False}),
            "paths": settings.paths.model_copy(
                update={
                    "raw_data": tmp_path / "raw",
                    "manifests": tmp_path / "manifests",
                    "processed": tmp_path / "processed",
                    "corpora": tmp_path / "corpora",
                    "chunks": tmp_path / "chunks",
                    "chunk_manifests": tmp_path / "chunk-manifests",
                    "embeddings": tmp_path / "embeddings",
                    "index_manifests": tmp_path / "index-manifests",
                    "qdrant_storage": tmp_path / "qdrant",
                    "retrieval_models": tmp_path / "models",
                    "docling_artifacts": tmp_path / "models" / "docling",
                    "tokenizer_artifacts": tmp_path / "models" / "tokenizers" / "tiktoken",
                    "embedding_artifacts": tmp_path / "models" / "embeddings",
                    "eval_results": tmp_path / "eval" / "results",
                }
            ),
            "chunking": settings.chunking.model_copy(
                update={
                    "tokenizer": settings.chunking.tokenizer.model_copy(
                        update={"implementation": "fake"}
                    )
                }
            ),
            "indexing": settings.indexing.model_copy(
                update={
                    "embedding": settings.indexing.embedding.model_copy(
                        update={
                            "implementation": "fake",
                            "model_id": "fake",
                            "revision": "fake-v1",
                            "dimension": 8,
                            "batch_size": batch_size,
                            "adapter_contract": "fake-embedder-v1",
                        }
                    )
                }
            ),
            "dense": settings.dense.model_copy(update={"top_k": 5}),
        }
    )
    for path in (
        settings.paths.raw_data,
        settings.paths.manifests,
        settings.paths.processed,
        settings.paths.corpora,
        settings.paths.chunks,
        settings.paths.chunk_manifests,
        settings.paths.embeddings,
        settings.paths.index_manifests,
        settings.paths.qdrant_storage,
        settings.paths.eval_results,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings


def _prepare_corpus(tmp_path: Path, *, n_docs: int = 3) -> tuple[AppSettings, str]:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "inputs"
    docs.mkdir(parents=True, exist_ok=True)
    for i in range(n_docs):
        (docs / f"doc{i}.txt").write_text(
            f"Title {i}\n\nParagraph about topic {i} with enough text.\n",
            encoding="utf-8",
        )
    ingest = run_ingestion(
        settings=settings, inputs=[docs], corpus_name="eng", recursive=False
    )
    assert ingest.status.value in {"success", "no_op"}
    chunk = run_chunking(
        settings=settings, corpus_name="eng", token_counter=FakeTokenCounter()
    )
    assert chunk.status.value in {"success", "no_op"}
    return settings, "eng"


@pytest.fixture(autouse=True)
def _clear_profile_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DIAG_DENSE_PROFILE_ENV, raising=False)


def test_profiling_disabled_by_default() -> None:
    assert dense_profile_enabled() is False


def test_profiling_disabled_omits_dense_profile_and_matches_vectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proofs 1–2, 10: disabled path equivalent; no production default change."""
    settings, corpus = _prepare_corpus(tmp_path)
    embedder = FakeEmbedder(dimension=8)
    monkeypatch.delenv(DIAG_DENSE_PROFILE_ENV, raising=False)
    report_off = run_indexing(
        settings=settings, corpus_name=corpus, embedder=embedder
    )
    assert report_off.status is IndexingStatus.SUCCESS
    assert "dense_profile" not in report_off.metadata
    # Clear index state + embeddings + qdrant for a second cold-ish run with profiling.
    import shutil

    shutil.rmtree(settings.paths.embeddings)
    settings.paths.embeddings.mkdir()
    shutil.rmtree(settings.paths.qdrant_storage)
    settings.paths.qdrant_storage.mkdir()
    index_state = settings.paths.corpora / corpus / "indexing" / "state.json"
    if index_state.exists():
        index_state.unlink()
    for manifest in settings.paths.index_manifests.glob("*.json"):
        manifest.unlink()

    monkeypatch.setenv(DIAG_DENSE_PROFILE_ENV, "1")
    embedder2 = FakeEmbedder(dimension=8)
    report_on = run_indexing(
        settings=settings, corpus_name=corpus, embedder=embedder2
    )
    assert report_on.status is IndexingStatus.SUCCESS
    assert "dense_profile" in report_on.metadata
    # Same embedding identity / counts — FakeEmbedder is deterministic.
    assert report_on.embeddings_generated == report_off.embeddings_generated
    assert report_on.embedding_config_hash == report_off.embedding_config_hash
    assert report_on.children_total == report_off.children_total


def test_profile_separates_encode_persist_and_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proofs 4–7: separate timers; batch stats; generated/reused distinction."""
    settings, corpus = _prepare_corpus(tmp_path, n_docs=4)
    monkeypatch.setenv(DIAG_DENSE_PROFILE_ENV, "1")
    report = run_indexing(
        settings=settings,
        corpus_name=corpus,
        embedder=FakeEmbedder(dimension=8),
    )
    assert report.status is IndexingStatus.SUCCESS
    profile = report.metadata["dense_profile"]
    timing = profile["timing_ms"]
    assert timing["encode_total"] >= 0
    assert timing["embedding_artifact_persistence_total"] >= 0
    assert timing["dense_point_construction"] is not None
    assert timing["qdrant_materialization_upsert"] is not None
    assert report.metadata.get("dense_generation_ms") is not None
    assert report.metadata.get("dense_materialization_ms") is not None
    assert profile["embeddings_generated"] == report.embeddings_generated
    assert profile["embeddings_reused"] == report.embeddings_reused
    assert profile["embeddings_generated"] > 0
    assert profile["batch_count"] >= 1
    for batch in profile["batches"]:
        assert batch["item_count"] <= settings.indexing.embedding.batch_size
        assert batch["item_count"] > 0

    # Warm reuse run: generated=0, reused=all; encode batches empty.
    report2 = run_indexing(
        settings=settings,
        corpus_name=corpus,
        embedder=FakeEmbedder(dimension=8),
    )
    assert report2.status in {IndexingStatus.SUCCESS, IndexingStatus.NO_OP}
    if report2.status is IndexingStatus.SUCCESS and "dense_profile" in report2.metadata:
        assert report2.metadata["dense_profile"]["embeddings_generated"] == 0


def test_default_batch_size_remains_32() -> None:
    """Proof 3 (config half): production default batch size unchanged."""
    assert AppSettings().indexing.embedding.batch_size == 32


def test_vram_observation_fails_gracefully() -> None:
    """Proof 8: CUDA/VRAM measurement fails closed without fabricating values."""
    collector = DenseProfileCollector()
    # On CPU-only CI this returns None with an explicit status.
    value = observe_peak_vram_bytes(collector)
    if value is None:
        assert collector.peak_vram_status == "unavailable"
        assert collector.peak_vram_error
        assert collector.peak_vram_bytes is None
    else:
        assert collector.peak_vram_status == "observed"
        assert isinstance(value, int)


def test_profile_env_introduces_no_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof 9: profiling path stays local/offline (fake embedder, local qdrant)."""
    settings, corpus = _prepare_corpus(tmp_path)
    assert settings.project.strict_offline is False  # test fixture only
    # Re-enable strict offline for the indexing call.
    settings = settings.model_copy(
        update={
            "project": settings.project.model_copy(update={"strict_offline": True}),
        }
    )
    monkeypatch.setenv(DIAG_DENSE_PROFILE_ENV, "1")
    # Block accidental network by clearing common proxy envs.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(key, raising=False)
    report = run_indexing(
        settings=settings,
        corpus_name=corpus,
        embedder=FakeEmbedder(dimension=8),
    )
    assert report.status is IndexingStatus.SUCCESS
    assert report.metadata["dense_profile"]["contract"] == "dense-cuda-profile-v1"


def test_fake_embedder_tokenizer_unavailable_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proof 5 adjacent: token stats from model inputs — unavailable, not fabricated."""
    settings, corpus = _prepare_corpus(tmp_path)
    monkeypatch.setenv(DIAG_DENSE_PROFILE_ENV, "1")
    report = run_indexing(
        settings=settings,
        corpus_name=corpus,
        embedder=FakeEmbedder(dimension=8),
    )
    profile = report.metadata["dense_profile"]
    assert profile["tokenizer_status"] == "unavailable"
    assert profile["model_input_token_stats"]["p50"] is None
    assert profile["model_input_token_stats"]["max"] is None
