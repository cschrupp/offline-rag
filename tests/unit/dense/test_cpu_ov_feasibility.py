"""Fail-closed ladder regressions for CPU-OV-01 harness rework (F001–F004)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from offline_rag.dense.cpu_ov_feasibility import (
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_DIMENSION,
    EXPECTED_MODEL_REVISION,
    FEASIBLE_MAX_MIN,
    FROZEN_BATCH_SIZE,
    PARITY_DOC_COUNT,
    PARITY_QUERY_COUNT,
    SCREEN_CHILD_COUNT,
    StageResult,
    assert_frozen_runtime_knobs,
    assert_transition_allowed,
    classify_screen_projection,
    full_confirm_passes,
    parity_thresholds_pass,
    plan_next,
    project_full_minutes,
    refuse_hub_substitution,
)
from offline_rag.dense.cpu_ov_harness import (
    build_full_confirm_result,
    build_screen_result,
    load_chunk_ids_from_manifest,
    run_export_compat,
    run_export_int8,
    run_full_confirm,
    run_parity,
    run_screen,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
    verify_local_model_identity,
)

REPO = Path(__file__).resolve().parents[3]


def test_execution_remains_locked() -> None:
    assert EXECUTION_AUTHORIZED is False


def test_projection_helpers() -> None:
    minutes = project_full_minutes(0.0932)
    assert 230.0 < minutes < 232.0
    assert classify_screen_projection(8.0) == "excellent"
    assert classify_screen_projection(20.0) == "viable"
    assert classify_screen_projection(30.0) == "too_slow"


def test_cannot_run_int8_before_fp16_screen() -> None:
    history: list[StageResult] = [
        StageResult(stage_id="export_compat", ok=True),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_screen_fp16"
    with pytest.raises(ValueError, match="unauthorized transition"):
        assert_transition_allowed(history, "run_screen_int8")
    with pytest.raises(ValueError, match="unauthorized transition"):
        assert_transition_allowed(history, "run_export_int8")


def test_stage0_rejects_int8_weight_format() -> None:
    """F004: Stage-0 cannot accept INT8 even with empty history."""
    with pytest.raises(ValueError, match="FP16-only"):
        run_export_compat(
            history=[],
            export_dir=REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "int8",
            weight_format="int8",
            repo_root=REPO,
        )


def test_excellent_fp16_skips_int8_and_requires_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_parity_fp16"
    assert plan.int8_eligible is False
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_screen_int8")
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_export_int8")
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_full_confirm")


def test_fp16_parity_fail_stops_without_int8() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=False),
    ]
    plan = plan_next(history)
    assert plan.terminal == "stop_parity_fail"
    assert plan.next_action == "none"
    assert plan.int8_eligible is False


def test_viable_fp16_requires_export_int8_before_screen() -> None:
    """F004: INT8 eligibility opens export_int8, not screen_int8 directly."""
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=1.2,
            projected_full_minutes=project_full_minutes(1.2),
        ),
    ]
    assert plan_next(history).next_action == "run_parity_fp16"
    history.append(StageResult(stage_id="parity_fp16", ok=True, parity_ok=True))
    plan = plan_next(history)
    assert plan.next_action == "run_export_int8"
    assert plan.int8_eligible is True
    with pytest.raises(ValueError, match="unauthorized"):
        assert_transition_allowed(history, "run_screen_int8")
    history.append(StageResult(stage_id="export_int8", ok=True))
    plan = plan_next(history)
    assert plan.next_action == "run_screen_int8"


def test_too_slow_fp16_opens_export_int8_without_fp16_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=0.5,
            projected_full_minutes=project_full_minutes(0.5),
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_export_int8"
    assert plan.reason == "fp16_too_slow_open_int8_export"


def test_cannot_full_run_before_eligibility() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    with pytest.raises(ValueError, match="full confirm not eligible"):
        run_full_confirm(history=history, selected_candidate="fp16")


def test_full_confirm_eligible_after_excellent_parity() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.full_confirm_eligible is True
    assert plan.selected_candidate == "fp16"
    assert plan.next_action == "run_full_confirm"
    payload = run_full_confirm(history=history, selected_candidate="fp16")
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["full_confirm_eligible"] is True
    assert payload["executor_implemented"] is True


def test_full_confirm_gate_rejects_slow_or_projection() -> None:
    """F003: FEASIBLE_MAX_MIN and exact 1296 counts; projections never pass."""
    base = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
    ]
    slow = build_full_confirm_result(full_wall_minutes=200.0)
    assert full_confirm_passes(slow) is False
    plan = plan_next([*base, slow])
    assert plan.terminal == "stop_too_slow"
    assert plan.next_action == "none"
    assert "exceeds_25_min" in plan.reason

    # ok=true with projection-shaped fields but missing measured counts → fail
    projection_shaped = StageResult(
        stage_id="full_confirm",
        ok=True,
        projected_full_minutes=10.0,
        full_wall_minutes=None,
    )
    assert full_confirm_passes(projection_shaped) is False

    good = build_full_confirm_result(full_wall_minutes=20.0)
    assert full_confirm_passes(good) is True
    assert good.full_wall_minutes <= FEASIBLE_MAX_MIN
    plan_ok = plan_next([*base, good])
    assert plan_ok.terminal == "select_ov_fp16"


def test_choose_faster_between_viable_fp16_and_int8() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=1.2,
            projected_full_minutes=project_full_minutes(1.2),
        ),
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
        StageResult(stage_id="export_int8", ok=True),
        StageResult(
            stage_id="screen_int8",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
        StageResult(stage_id="parity_int8", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.selected_candidate == "int8"
    assert plan.next_action == "run_full_confirm"


def test_frozen_knobs_and_hub_refusal() -> None:
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=True,
        device="cpu",
        backend="openvino",
    )
    with pytest.raises(ValueError, match="batch"):
        assert_frozen_runtime_knobs(
            batch_size=16, normalize=True, device="cpu", backend="openvino"
        )
    with pytest.raises(ValueError, match="Hub"):
        refuse_hub_substitution(local_model_dir_exists=True, allow_download=True)
    with pytest.raises(ValueError, match="missing"):
        refuse_hub_substitution(local_model_dir_exists=False, allow_download=False)


def test_parity_threshold_helper_fail_closed() -> None:
    good = {
        "median_document_vector_cosine": 0.9995,
        "min_document_vector_cosine": 0.996,
        "median_query_vector_cosine": 0.9995,
        "min_query_vector_cosine": 0.996,
        "top1_agreement": 16,
        "mean_top10_set_overlap": 0.99,
        "min_top10_set_overlap": 0.9,
    }
    assert parity_thresholds_pass(good) is True
    bad = dict(good)
    bad["top1_agreement"] = 14
    assert parity_thresholds_pass(bad) is False
    assert parity_thresholds_pass({}) is False


def test_deterministic_selection_sizes() -> None:
    ids = [f"chunk_{i:04d}" for i in range(EXPECTED_CHILD_COUNT)]
    screen = select_screen_chunk_ids(ids)
    assert len(screen) == SCREEN_CHILD_COUNT
    docs, queries = select_parity_populations(ids)
    assert len(docs) == PARITY_DOC_COUNT
    assert len(queries) == PARITY_QUERY_COUNT
    assert queries == docs[:PARITY_QUERY_COUNT]
    assert screen == sorted(ids, key=sha256_text)[:SCREEN_CHILD_COUNT]


def test_locked_export_and_screen_refuse_without_running() -> None:
    history: list[StageResult] = []
    export = run_export_compat(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "fp16",
        repo_root=REPO,
    )
    assert export["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert export["executor_ready"] is True
    assert export["executor_implemented"] is True

    history = [StageResult(stage_id="export_compat", ok=True)]
    screen = run_screen(history=history, weight_format="fp16", repo_root=REPO)
    assert screen["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert screen["screen_child_count"] == SCREEN_CHILD_COUNT
    assert screen["chunk_manifest_sha256"] == EXPECTED_CHUNK_MANIFEST_SHA256

    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    parity = run_parity(history=history, weight_format="fp16", repo_root=REPO)
    assert parity["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert parity["document_count"] == PARITY_DOC_COUNT
    assert parity["query_count"] == PARITY_QUERY_COUNT


def test_locked_export_int8_after_eligibility() -> None:
    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=0.5,
            projected_full_minutes=project_full_minutes(0.5),
        ),
    ]
    payload = run_export_int8(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "int8",
        repo_root=REPO,
    )
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["requested_action"] == "run_export_int8"
    assert payload["weight_format"] == "int8"


def test_projection_never_stored_as_full_wall_in_screen_builder() -> None:
    result = build_screen_result(stage_id="screen_fp16", chunks_per_sec=2.0)
    assert result.projected_full_minutes is not None
    assert result.full_wall_minutes is None


def test_manifest_sha256_fail_closed(tmp_path: Path) -> None:
    """F002: wrong manifest bytes must not select screen populations."""
    manifests = tmp_path / "data" / "chunk-manifests"
    manifests.mkdir(parents=True)
    bad = manifests / (
        "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d.json"
    )
    bad.write_text(
        json.dumps({"total_child_count": EXPECTED_CHILD_COUNT, "documents": []}),
        encoding="utf-8",
    )
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    assert digest != EXPECTED_CHUNK_MANIFEST_SHA256
    with pytest.raises(ValueError, match="manifest SHA256 mismatch"):
        load_chunk_ids_from_manifest(repo_root=tmp_path)


def test_manifest_sha256_matches_frozen_workload() -> None:
    ids = load_chunk_ids_from_manifest(repo_root=REPO)
    assert len(ids) == EXPECTED_CHILD_COUNT
    manifest = (
        REPO
        / "data"
        / "chunk-manifests"
        / "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d.json"
    )
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == (
        EXPECTED_CHUNK_MANIFEST_SHA256
    )


def test_model_identity_requires_provisioning_artifacts(tmp_path: Path) -> None:
    """F002: directory+config without provisioning manifest must fail."""
    model_dir = tmp_path / "fake_model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="identity gate|artifacts"):
        verify_local_model_identity(model_dir)


def test_model_identity_accepts_provisioned_revision() -> None:
    from offline_rag.config import load_settings
    from offline_rag.dense.cpu_ov_harness import resolve_local_pinned_model_dir

    model_dir = resolve_local_pinned_model_dir(repo_root=REPO)
    identity = verify_local_model_identity(model_dir)
    assert identity["resolved_revision"] == EXPECTED_MODEL_REVISION


def test_executor_unlocked_paths_are_wired_not_stubs() -> None:
    """F001: unlocked branches call executor (no NotImplementedError stubs)."""
    import offline_rag.dense.cpu_ov_harness as harness
    import offline_rag.dense.cpu_ov_feasibility as feas

    history_export: list[StageResult] = []
    fake_export = {"status": "ok", "stage_id": "export_compat", "ok": True}

    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_ov_executor.execute_export_compat",
            return_value=fake_export,
        ) as mock_ex,
        patch.object(
            harness,
            "resolve_local_pinned_model_dir",
            return_value=Path("/tmp/model"),
        ),
    ):
        out = harness.run_export_compat(
            history=history_export,
            export_dir=Path("/tmp/export"),
            repo_root=REPO,
        )
    assert out == fake_export
    mock_ex.assert_called_once()

    history_screen = [StageResult(stage_id="export_compat", ok=True)]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_ov_executor.execute_screen",
            return_value={"status": "ok", "stage_id": "screen_fp16"},
        ) as mock_screen,
        patch.object(
            harness,
            "load_chunk_ids_from_manifest",
            return_value=[f"c{i}" for i in range(EXPECTED_CHILD_COUNT)],
        ),
    ):
        out_s = harness.run_screen(
            history=history_screen,
            weight_format="fp16",
            export_dir=Path("/tmp/export"),
            repo_root=REPO,
        )
    assert out_s["stage_id"] == "screen_fp16"
    mock_screen.assert_called_once()


def test_executor_parity_and_full_wired() -> None:
    import offline_rag.dense.cpu_ov_harness as harness
    import offline_rag.dense.cpu_ov_feasibility as feas

    history = [
        StageResult(stage_id="export_compat", ok=True),
        StageResult(
            stage_id="screen_fp16",
            ok=True,
            chunks_per_sec=3.0,
            projected_full_minutes=project_full_minutes(3.0),
        ),
    ]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_ov_executor.execute_parity",
            return_value={"status": "ok", "parity_ok": True},
        ) as mock_parity,
        patch.object(
            harness,
            "load_chunk_ids_from_manifest",
            return_value=[f"c{i}" for i in range(EXPECTED_CHILD_COUNT)],
        ),
    ):
        out = harness.run_parity(
            history=history,
            weight_format="fp16",
            export_dir=Path("/tmp/export"),
            repo_root=REPO,
        )
    assert out["parity_ok"] is True
    mock_parity.assert_called_once()

    history_full = [
        *history,
        StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
    ]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_ov_executor.execute_full_confirm",
            return_value={
                "status": "ok",
                "full_wall_minutes": 12.0,
                "embeddings_generated": EXPECTED_CHILD_COUNT,
                "dimension": EXPECTED_DIMENSION,
            },
        ) as mock_full,
    ):
        out_f = harness.run_full_confirm(
            history=history_full,
            selected_candidate="fp16",
            export_dir=Path("/tmp/export"),
            repo_root=REPO,
        )
    assert out_f["full_wall_minutes"] == 12.0
    mock_full.assert_called_once()


def test_smoke_encode_compat_helper() -> None:
    """F001 component: smoke gate without real OpenVINO."""
    from offline_rag.dense.cpu_ov_executor import smoke_encode_compat

    class _FakeModel:
        def encode(self, texts, **kwargs):  # noqa: ANN001, ANN003
            import numpy as np

            n = 1 if isinstance(texts, str) else len(texts)
            # unit vector along first axis
            arr = np.zeros((n, EXPECTED_DIMENSION), dtype=np.float64)
            arr[:, 0] = 1.0
            if isinstance(texts, str):
                return arr[0]
            return arr

    result = smoke_encode_compat(_FakeModel(), query_text_contract="raw-query-v1")
    assert result["ok"] is True
    assert result["document_dim"] == EXPECTED_DIMENSION
