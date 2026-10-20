"""F006–F009 regressions for D2 implementation rework-2."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from offline_rag.dense.d2_campaign import (
    EXPECTED_CHILD_COUNT,
    EXPECTED_EXECUTION_HEAD,
    assert_transition_allowed,
    plan_next,
)
from offline_rag.dense.d2_execution import (
    execute_d2_cell_unlocked,
    load_campaign_history,
    record_confirmation_assessment,
    run_d2_preflight,
    verify_prepared_workload_state,
    write_campaign_history,
)
from offline_rag.dense.d2_campaign import CellResult

REPO = Path(__file__).resolve().parents[3]


def test_empty_history_allows_only_g1_1(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    assert load_campaign_history(history_path) == []
    assert_transition_allowed([], "G1-1")
    with pytest.raises(ValueError, match="unauthorized transition"):
        assert_transition_allowed([], "G2-3")


def test_unlocked_executor_requires_history_and_rejects_g2_without_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import offline_rag.dense.d2_execution as exe

    history = tmp_path / "history.json"
    work = tmp_path / "work"

    monkeypatch.setattr(
        exe,
        "run_d2_preflight",
        lambda **kwargs: exe.PreflightResult(
            ok=True, issues=(), payload={"status": "PREFLIGHT_OK"}
        ),
    )
    # Should fail transition before indexing.
    with pytest.raises(ValueError, match="unauthorized transition"):
        execute_d2_cell_unlocked(
            cell_id="G2-3",
            work_root=work,
            history_path=history,
            repo_root=REPO,
            expected_execution_head="deadbeef",
        )


def test_require_execution_head_fail_closed(tmp_path: Path) -> None:
    assert EXPECTED_EXECUTION_HEAD is None
    result = run_d2_preflight(
        cell_id="G1-1",
        work_root=tmp_path / "work",
        prepare_tree=True,
        require_execution_head=True,
        repo_root=REPO,
    )
    assert result.ok is False
    assert any("expected_execution_head_not_frozen" in i for i in result.issues)

    result2 = run_d2_preflight(
        cell_id="G1-1",
        work_root=tmp_path / "work2",
        prepare_tree=True,
        require_execution_head=True,
        expected_execution_head="0" * 40,
        repo_root=REPO,
    )
    assert result2.ok is False
    assert any("execution_head_mismatch" in i for i in result2.issues)


def test_prepared_state_matches_frozen_ids(tmp_path: Path) -> None:
    from offline_rag.dense.d2_execution import prepare_isolated_tree

    work = prepare_isolated_tree(tmp_path / "work", repo_root=REPO)
    prepared = verify_prepared_workload_state(work)
    assert prepared["issues"] == []
    assert prepared["current_corpus_id"].startswith("corpus_")
    assert prepared["current_chunk_set_id"].startswith("chunkset_")


def test_assessment_recording_updates_plan(tmp_path: Path) -> None:
    history_path = tmp_path / "history.json"
    write_campaign_history(
        history_path,
        [
            CellResult("G1-1", "valid", 9.0),
            CellResult("G1-2", "valid", 9.0),
            CellResult("C0", "valid", 40.0),
            CellResult("G1-3", "valid", 9.0, parity_ok=None, correctness_ok=None),
        ],
    )
    before = plan_next(load_campaign_history(history_path))
    assert before.selected_lane is None

    out = record_confirmation_assessment(
        history_path=history_path,
        cell_id="G1-3",
        parity_ok=True,
        correctness_ok=True,
        evidence_digest="abc123",
        evidence_path="docs/evidence/example.json",
    )
    assert out["status"] == "ASSESSMENT_RECORDED"
    assert out["plan"]["selected_lane"] == "G1"
    hist = load_campaign_history(history_path)
    assert hist[-1].parity_ok is True
    assert hist[-1].correctness_ok is True
    assert hist[-1].wall_minutes == 9.0
    assert hist[-1].assessment_evidence_digest == "abc123"

    with pytest.raises(ValueError, match="already has assessment"):
        record_confirmation_assessment(
            history_path=history_path,
            cell_id="G1-3",
            parity_ok=False,
            correctness_ok=True,
            evidence_digest="other",
        )


def test_unlocked_executor_publishes_practical_timing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from offline_rag.domain.indexing import IndexingStatus

    import offline_rag.dense.d2_execution as exe

    history = tmp_path / "history.json"
    # Seed G1 screens so C0 is the authorized next cell (F006).
    write_campaign_history(
        history,
        [
            CellResult("G1-1", "valid", 9.0),
            CellResult("G1-2", "valid", 9.0),
        ],
    )
    work = tmp_path / "work"
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
            "dense_materialization_ms": 80,
            "dense_execution": {"device": "cpu", "dtype": "float32", "batch_size": 32},
            "practical_timing": {
                "encode_ms": 700.0,
                "embedding_persistence_ms": 100.0,
                "point_construction_ms": 50.0,
                "qdrant_ms": 30.0,
                "wall_clock_ms": 1000,
                "chunks_per_sec": 1.0,
                "tokens_per_sec": None,
                "tokens_per_sec_status": "not_collected",
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
    monkeypatch.setattr("offline_rag.config.load_settings", lambda environ=None: MagicMock())
    monkeypatch.setattr(
        "offline_rag.dense.embedder.make_embedder", lambda settings: embedder
    )
    monkeypatch.setattr(
        "offline_rag.dense.embedder.observe_embedder_execution_facts",
        lambda e: {"dtype": "float32", "attention_backend": "sdpa"},
    )
    monkeypatch.setattr(
        exe,
        "capture_cpu_baseline_facts",
        lambda **kwargs: {
            "process_cpu_time_s": 1.0,
            "peak_rss_bytes": 1000,
            "batch_size": 32,
        },
    )
    monkeypatch.setattr(exe, "capture_gpu_memory_facts", lambda: {})
    monkeypatch.setattr(
        "offline_rag.dense.pipeline.run_indexing",
        lambda **kwargs: _Report(),
    )

    payload = execute_d2_cell_unlocked(
        cell_id="C0",
        work_root=work,
        history_path=history,
        evidence_dir=evidence,
        repo_root=REPO,
        expected_execution_head="unused-because-preflight-mocked",
    )
    assert payload["status"] == "CELL_EXECUTED"
    assert payload["practical_timing"]["encode_ms"] == 700.0
    assert payload["practical_timing"]["qdrant_ms"] == 30.0
    assert payload["cpu_facts"]["sampled"] == "after_run_indexing"
    assert history.exists()
    assert load_campaign_history(history)[-1].cell_id == "C0"
