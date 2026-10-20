"""16K-D D1 stall-attribution tooling proofs (no scientific campaign)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from offline_rag.chunking.pipeline import run_chunking
from offline_rag.chunking.tokenize import FakeTokenCounter
from offline_rag.config.models import AppSettings
from offline_rag.dense.embedder import FakeEmbedder
from offline_rag.dense.pipeline import run_indexing
from offline_rag.dense.profiling import (
    DIAG_DENSE_PROFILE_ENV,
    PROFILE_CONTRACT,
    batch_identity_digest,
    dense_profile_enabled,
    profiled_encode_timing,
    sample_external_gpu_state,
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


def _prepare_corpus(tmp_path: Path) -> tuple[AppSettings, str]:
    settings = _settings(tmp_path, batch_size=2)
    docs = tmp_path / "inputs"
    docs.mkdir(parents=True, exist_ok=True)
    for i in range(3):
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


def test_disabled_path_does_not_sample_external_gpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profiler-disabled path must not invoke nvidia-smi / CUDA-event tooling."""
    settings, corpus = _prepare_corpus(tmp_path)
    monkeypatch.delenv(DIAG_DENSE_PROFILE_ENV, raising=False)
    assert dense_profile_enabled() is False
    with patch(
        "offline_rag.dense.pipeline.sample_external_gpu_state",
        side_effect=AssertionError("external GPU sample must not run when disabled"),
    ), patch(
        "offline_rag.dense.pipeline.profiled_encode_timing",
        side_effect=AssertionError("CUDA-event encode timing must not run when disabled"),
    ):
        report = run_indexing(
            settings=settings,
            corpus_name=corpus,
            embedder=FakeEmbedder(dimension=8),
        )
    assert report.status is IndexingStatus.SUCCESS
    assert "dense_profile" not in report.metadata


def test_enabled_path_records_stall_attribution_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, corpus = _prepare_corpus(tmp_path)
    monkeypatch.setenv(DIAG_DENSE_PROFILE_ENV, "1")
    report = run_indexing(
        settings=settings,
        corpus_name=corpus,
        embedder=FakeEmbedder(dimension=8),
    )
    assert report.status is IndexingStatus.SUCCESS
    profile = report.metadata["dense_profile"]
    assert profile["contract"] == PROFILE_CONTRACT
    assert profile["stall_attribution_tooling"] is True
    assert profile["batch_count"] >= 1
    batch = profile["batches"][0]
    assert batch["batch_identity_digest"]
    assert batch["chunk_ids_digest"]
    assert batch["item_count"] > 0
    assert "encode_cuda_device_status" in batch
    # FakeEmbedder: device timing unavailable, never fabricated.
    if batch["encode_cuda_device_status"] != "observed":
        assert batch["encode_cuda_device_ms"] is None
    assert batch["process_cpu_delta"] is not None
    assert batch["process_cpu_delta"]["status"] in {"observed", "unavailable"}
    assert "gpu_external_before" in batch
    assert "gpu_external_after" in batch
    assert "cuda_allocator_after" in batch


def test_batch_identity_digest_is_deterministic() -> None:
    a = batch_identity_digest(["c1", "c2", "c3"])
    b = batch_identity_digest(["c1", "c2", "c3"])
    c = batch_identity_digest(["c3", "c2", "c1"])
    assert a == b
    assert a != c


def test_profiled_encode_timing_explicit_when_no_cuda() -> None:
    embedder = FakeEmbedder(dimension=8)
    with profiled_encode_timing() as timing:
        embedder.embed_documents(["hello", "world"])
    assert timing["encode_ms"] >= 0
    assert timing["encode_cuda_device_status"] in {"observed", "unavailable"}
    if timing["encode_cuda_device_status"] != "observed":
        assert timing["encode_cuda_device_ms"] is None
        assert timing["encode_cuda_device_error"]


def test_process_cpu_delta_brackets_only_encode_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F001: rusage interval must exclude CUDA event setup and end sync.

    Sentinel-ordered boundaries — not loose wall-clock assertions — so a
    regression that again includes profiler setup in process_cpu_delta fails.
    """
    import types

    import offline_rag.dense.profiling as profiling

    events: list[str] = []

    class _FakeCudaEvent:
        def __init__(self, *args: object, **kwargs: object) -> None:
            events.append("event_create")

        def record(self) -> None:
            events.append("event_record")

        def synchronize(self) -> None:
            events.append("event_synchronize")

        def elapsed_time(self, _other: object) -> float:
            return 1.25

    fake_cuda = types.SimpleNamespace(
        is_available=lambda: True,
        Event=_FakeCudaEvent,
    )
    fake_torch = types.SimpleNamespace(cuda=fake_cuda)
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)

    rusage_calls = 0

    def _sentinel_rusage() -> dict:
        nonlocal rusage_calls
        events.append(f"rusage_{rusage_calls}")
        # Distinct sentinels so delta proves which snapshots were used.
        base_user = 10.0 if rusage_calls == 0 else 10.5
        base_sys = 1.0 if rusage_calls == 0 else 1.25
        base_vol = 100 if rusage_calls == 0 else 103
        base_invol = 20 if rusage_calls == 0 else 21
        rusage_calls += 1
        return {
            "status": "observed",
            "error": None,
            "user_time_s": base_user,
            "system_time_s": base_sys,
            "voluntary_context_switches": base_vol,
            "involuntary_context_switches": base_invol,
        }

    monkeypatch.setattr(profiling, "_process_rusage_snapshot", _sentinel_rusage)

    with profiling.profiled_encode_timing() as timing:
        events.append("encode_body")

    assert events == [
        "event_create",
        "event_create",
        "event_record",
        "rusage_0",
        "encode_body",
        "rusage_1",
        "event_record",
        "event_synchronize",
    ]
    delta = timing["process_cpu_delta"]
    assert delta is not None
    assert delta["status"] == "observed"
    assert delta["user_time_s"] == pytest.approx(0.5)
    assert delta["system_time_s"] == pytest.approx(0.25)
    assert delta["cpu_time_s"] == pytest.approx(0.75)
    assert delta["voluntary_context_switches"] == 3
    assert delta["involuntary_context_switches"] == 1
    assert timing["encode_cuda_device_status"] == "observed"
    assert timing["encode_cuda_device_ms"] == pytest.approx(1.25)


def test_external_gpu_sample_never_fabricates_values() -> None:
    sample = sample_external_gpu_state()
    assert sample["status"] in {"observed", "unavailable"}
    if sample["status"] == "unavailable":
        assert sample["sample"] is None
        assert sample["error"]
    else:
        assert isinstance(sample["sample"], dict)


def test_defaults_unchanged() -> None:
    assert AppSettings().indexing.embedding.batch_size == 32
