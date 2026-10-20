"""F001–F004 regressions for D2 implementation rework."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.dense.d2_campaign import (
    ACCEPTED_DESIGN_SUBJECT,
    EXECUTION_AUTHORIZED,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CORPUS_MANIFEST_SHA256,
)
from offline_rag.dense.d2_execution import (
    execute_d2_cell,
    execute_d2_cell_unlocked,
    observe_workload_identity,
    run_d2_preflight,
)
from offline_rag.dense.embedder import EmbedderError
from offline_rag.dense.precision import apply_fp16_after_load

REPO = Path(__file__).resolve().parents[3]


def test_observe_workload_hashes_match_frozen_constants() -> None:
    observed = observe_workload_identity(repo_root=REPO)
    assert observed["chunk_manifest_exists"] is True
    assert observed["corpus_manifest_exists"] is True
    assert observed["child_count"] == EXPECTED_CHILD_COUNT
    assert observed["chunk_manifest_sha256"] == EXPECTED_CHUNK_MANIFEST_SHA256
    assert observed["corpus_manifest_sha256"] == EXPECTED_CORPUS_MANIFEST_SHA256


def test_preflight_verifies_observed_facts(tmp_path: Path) -> None:
    work = tmp_path / "d2_work"
    result = run_d2_preflight(
        cell_id="G1-1",
        work_root=work,
        require_design_subject=False,
        repo_root=REPO,
        prepare_tree=True,
    )
    # Dirty tree in a working session may fail tracked_clean; assert observed
    # workload checks are present and matching when tree is the only concern.
    payload = result.payload
    assert payload["workload_observed"]["chunk_manifest_sha256"] == (
        EXPECTED_CHUNK_MANIFEST_SHA256
    )
    assert payload["workload_observed"]["child_count"] == EXPECTED_CHILD_COUNT
    assert payload["isolation"]["embeddings_empty"] is True
    assert payload["isolation"]["qdrant_empty"] is True
    assert payload["effective_settings"]["configured_precision"] == "fp16"
    assert payload["effective_settings"]["batch_size"] == 32
    assert payload["effective_settings"]["configured_device"] == "cuda"
    assert payload["effective_settings"]["strict_offline"] is True
    # Failures must be real issues only (e.g. dirty tree), never silent OK on
    # mismatched constants.
    if "chunk_manifest_sha256_mismatch" in result.issues:
        pytest.fail("frozen chunk manifest hash mismatch")
    if "child_count_mismatch" in result.issues:
        pytest.fail("frozen child count mismatch")


def test_require_design_subject_enforces_head_match(tmp_path: Path) -> None:
    work = tmp_path / "d2_work"
    result = run_d2_preflight(
        cell_id="C0",
        work_root=work,
        require_design_subject=True,
        repo_root=REPO,
        prepare_tree=True,
    )
    # Current tip is not the design subject after implementation commits.
    assert any("execution_head_mismatch" in i for i in result.issues)
    assert result.ok is False
    assert result.payload["require_design_subject"] is True
    assert result.payload["accepted_design_subject"] == ACCEPTED_DESIGN_SUBJECT


def test_execute_cell_locked_but_executor_ready(tmp_path: Path) -> None:
    assert EXECUTION_AUTHORIZED is False
    payload = execute_d2_cell(
        cell_id="G1-1",
        work_root=tmp_path / "work",
        repo_root=REPO,
    )
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["executor_ready"] is True
    assert "execute_d2_cell_unlocked" in payload["unlocked_entrypoint"]
    assert callable(execute_d2_cell_unlocked)


def test_apply_fp16_fails_closed_when_post_dtype_unobservable() -> None:
    model = MagicMock()
    model.half = MagicMock()
    # Indexing into model raises after half().
    model.__len__.return_value = 1
    model.__getitem__.side_effect = RuntimeError("broken dtype inspection")

    with pytest.raises(EmbedderError, match="could not be observed"):
        apply_fp16_after_load(model)
    model.half.assert_called_once()


def test_apply_fp16_fails_closed_when_auto_model_missing() -> None:
    first = MagicMock()
    first.auto_model = None
    model = MagicMock()
    model.half = MagicMock()
    model.__len__.return_value = 1
    model.__getitem__.return_value = first

    with pytest.raises(EmbedderError, match="missing auto_model"):
        apply_fp16_after_load(model)


def test_unlocked_executor_wires_indexing_and_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the locked-behind-gate path is a real executor, not a stub."""
    from offline_rag.domain.indexing import IndexingStatus

    import offline_rag.dense.d2_execution as exe

    work = tmp_path / "work"
    history = tmp_path / "history.json"
    evidence = tmp_path / "evidence"

    class _Report:
        status = IndexingStatus.SUCCESS
        errors: list[str] = []
        embeddings_generated = EXPECTED_CHILD_COUNT
        embeddings_reused = 0
        embeddings_failed = 0
        vectors_materialized = EXPECTED_CHILD_COUNT
        children_total = EXPECTED_CHILD_COUNT
        duration_ms = 1000
        metadata = {
            "dense_generation_ms": 900,
            "dense_materialization_ms": 50,
            "dense_execution": {
                "device": "cpu",
                "dtype": "float32",
                "batch_size": 32,
            },
        }

    embedder = MagicMock()
    embedder._load = MagicMock()

    monkeypatch.setattr(
        exe,
        "run_d2_preflight",
        lambda **kwargs: exe.PreflightResult(
            ok=True, issues=(), payload={"status": "PREFLIGHT_OK"}
        ),
    )
    monkeypatch.setattr(
        "offline_rag.config.load_settings",
        lambda environ=None: MagicMock(),
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedder.make_embedder",
        lambda settings: embedder,
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedder.observe_embedder_execution_facts",
        lambda e: {"dtype": "float32", "attention_backend": "sdpa"},
    )
    monkeypatch.setattr(
        exe,
        "capture_cpu_baseline_facts",
        lambda **kwargs: {
            "effective_dtype": "float32",
            "batch_size": 32,
            "torch_num_threads": 1,
        },
    )
    monkeypatch.setattr(exe, "capture_gpu_memory_facts", lambda: {})
    called: dict[str, object] = {}

    def _run_indexing(**kwargs):
        called["run_indexing"] = kwargs
        return _Report()

    monkeypatch.setattr("offline_rag.dense.pipeline.run_indexing", _run_indexing)

    payload = execute_d2_cell_unlocked(
        cell_id="C0",
        work_root=work,
        history_path=history,
        evidence_dir=evidence,
        repo_root=REPO,
    )
    assert payload["status"] == "CELL_EXECUTED"
    assert payload["validity"] == "valid"
    assert "run_indexing" in called
    assert history.exists()
    assert any(evidence.glob("d2_c0_*.json"))
