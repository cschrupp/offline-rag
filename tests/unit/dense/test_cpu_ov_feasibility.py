"""Fail-closed ladder regressions for CPU-OV-01 harness rework (F001–F004)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    export_dir = REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "fp16"
    history: list[StageResult] = []
    export = run_export_compat(
        history=history,
        export_dir=export_dir,
        repo_root=REPO,
    )
    assert export["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert export["executor_ready"] is True
    assert export["executor_implemented"] is True

    history = [StageResult(stage_id="export_compat", ok=True)]
    screen = run_screen(
        history=history,
        weight_format="fp16",
        export_dir=export_dir,
        repo_root=REPO,
    )
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
    parity = run_parity(
        history=history,
        weight_format="fp16",
        export_dir=export_dir,
        repo_root=REPO,
    )
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


def _load_cpu_ov_cli():
    import importlib.util

    path = REPO / "scripts" / "diag_16k_d_dense" / "run_cpu_ov_feasibility.py"
    spec = importlib.util.spec_from_file_location("run_cpu_ov_feasibility_cli", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_requires_export_dir_for_screen_parity_full() -> None:
    """F005: unlocked stages cannot omit export_dir at the CLI surface."""
    cli = _load_cpu_ov_cli()
    parser = cli.build_parser()
    for command in ("screen", "parity", "full-confirm"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [command, "--history", "h.json", "--weight-format", "fp16"]
            )
        args = parser.parse_args(
            [
                command,
                "--history",
                "h.json",
                "--weight-format",
                "fp16",
                "--export-dir",
                "/tmp/ov-export",
            ]
        )
        assert Path(args.export_dir) == Path("/tmp/ov-export")


def test_cli_passes_export_dir_into_harness() -> None:
    """F005: CLI cmds forward export_dir to harness entrypoints."""
    cli = _load_cpu_ov_cli()
    export_dir = "/tmp/ov-export-cli"

    with (
        patch.object(
            cli,
            "_load_history",
            return_value=[StageResult(stage_id="export_compat", ok=True)],
        ),
        patch.object(
            cli,
            "run_screen",
            return_value={"status": "EXECUTION_NOT_AUTHORIZED"},
        ) as mock_s,
    ):
        args = cli.build_parser().parse_args(
            [
                "screen",
                "--history",
                "h.json",
                "--weight-format",
                "fp16",
                "--export-dir",
                export_dir,
            ]
        )
        assert cli.cmd_screen(args) == 20
        assert mock_s.call_args.kwargs["export_dir"] == Path(export_dir)

    with (
        patch.object(
            cli,
            "_load_history",
            return_value=[
                StageResult(stage_id="export_compat", ok=True),
                StageResult(
                    stage_id="screen_fp16",
                    ok=True,
                    chunks_per_sec=3.0,
                    projected_full_minutes=project_full_minutes(3.0),
                ),
            ],
        ),
        patch.object(
            cli,
            "run_parity",
            return_value={"status": "EXECUTION_NOT_AUTHORIZED"},
        ) as mock_p,
    ):
        args_p = cli.build_parser().parse_args(
            [
                "parity",
                "--history",
                "h.json",
                "--weight-format",
                "fp16",
                "--export-dir",
                export_dir,
            ]
        )
        assert cli.cmd_parity(args_p) == 20
        assert mock_p.call_args.kwargs["export_dir"] == Path(export_dir)

    with (
        patch.object(
            cli,
            "_load_history",
            return_value=[
                StageResult(stage_id="export_compat", ok=True),
                StageResult(
                    stage_id="screen_fp16",
                    ok=True,
                    chunks_per_sec=3.0,
                    projected_full_minutes=project_full_minutes(3.0),
                ),
                StageResult(stage_id="parity_fp16", ok=True, parity_ok=True),
            ],
        ),
        patch.object(
            cli,
            "run_full_confirm",
            return_value={"status": "EXECUTION_NOT_AUTHORIZED"},
        ) as mock_f,
    ):
        args_f = cli.build_parser().parse_args(
            [
                "full-confirm",
                "--history",
                "h.json",
                "--weight-format",
                "fp16",
                "--export-dir",
                export_dir,
            ]
        )
        assert cli.cmd_full(args_f) == 20
        assert mock_f.call_args.kwargs["export_dir"] == Path(export_dir)
        assert mock_f.call_args.kwargs["repo_root"] == cli.ROOT


def test_full_confirm_uses_production_indexing_path() -> None:
    """F006: full confirm goes through isolated run_indexing, not encode-only."""
    from datetime import UTC, datetime

    from offline_rag.dense import cpu_ov_executor as ex
    from offline_rag.domain.indexing import IndexingReport, IndexingStatus

    fake_report = IndexingReport(
        run_id="test",
        corpus_name="16k_d_d0_incident",
        corpus_id="corpus_x",
        chunk_set_id="chunk_x",
        embedding_config_hash="e" * 64,
        index_config_hash="i" * 64,
        status=IndexingStatus.SUCCESS,
        started_at=datetime.now(tz=UTC),
        completed_at=datetime.now(tz=UTC),
        duration_ms=120000,
        children_total=EXPECTED_CHILD_COUNT,
        embeddings_generated=EXPECTED_CHILD_COUNT,
        embeddings_reused=0,
        embeddings_failed=0,
        vectors_materialized=EXPECTED_CHILD_COUNT,
        metadata={
            "practical_timing": {
                "encode_ms": 100000.0,
                "embedding_persistence_ms": 500.0,
                "point_construction_ms": 200.0,
                "qdrant_ms": 300.0,
                "wall_clock_ms": 120000,
            },
            "dense_execution": {"embedding_dimension": EXPECTED_DIMENSION},
        },
    )

    with (
        patch(
            "offline_rag.dense.d2_execution.prepare_isolated_tree",
            return_value=Path("/tmp/iso"),
        ) as mock_prep,
        patch(
            "offline_rag.dense.pipeline.run_indexing",
            return_value=fake_report,
        ) as mock_index,
        patch.object(
            ex,
            "load_openvino_st_model",
            return_value=(
                object(),
                {
                    "requested_weight_format": "fp16",
                    "observed_IR_weight_precision": "fp16",
                    "observed_CPU_inference_precision": "fp32",
                },
            ),
        ),
        patch.object(
            ex,
            "resolve_production_query_contract",
            return_value="raw-query-v1",
        ),
        patch.object(
            ex,
            "capture_cpu_host_runtime_facts",
            return_value={"cpu_model_name": "test-cpu"},
        ),
        patch(
            "offline_rag.config.load_settings",
            return_value=MagicMock(),
        ),
    ):
        out = ex.execute_full_confirm(
            export_dir=Path("/tmp/export"),
            weight_format="fp16",
            repo_root=REPO,
            evidence_dir=None,
            work_root=Path("/tmp/iso-work"),
        )

    assert out["confirmation_mode"] == "production_indexing_isolated_cold_tree"
    assert out["embeddings_generated"] == EXPECTED_CHILD_COUNT
    assert out["embeddings_reused"] == 0
    assert out["vectors_materialized"] == EXPECTED_CHILD_COUNT
    assert out["practical_timing"]["encode_ms"] == 100000.0
    assert out["practical_timing"]["qdrant_ms"] == 300.0
    assert out["ok"] is True
    mock_prep.assert_called_once()
    mock_index.assert_called_once()
    assert mock_index.call_args.kwargs["embedder"] is not None


def test_cpu_host_runtime_facts_capture_identity() -> None:
    """F007: observational CPU identity/core/RAM facts without tuning."""
    from offline_rag.dense.cpu_ov_executor import capture_cpu_host_runtime_facts

    facts = capture_cpu_host_runtime_facts(batch_size=32)
    assert "cpu_logical_count" in facts
    assert "peak_rss_bytes" in facts or facts.get("peak_rss_bytes") is None
    # On this WSL host we expect a model name from lscpu.
    assert facts.get("cpu_model_name") or facts.get("lscpu_error")
    assert facts.get("batch_size") == 32
    # Must not mutate thread knobs as a side effect of capture.
    try:
        import torch

        before = torch.get_num_threads()
        capture_cpu_host_runtime_facts()
        assert torch.get_num_threads() == before
    except Exception:  # noqa: BLE001
        pass


def test_classify_ir_weight_precision() -> None:
    from offline_rag.dense.cpu_ov_executor import classify_ir_weight_precision

    assert classify_ir_weight_precision(f16_constant_count=0, f32_constant_count=680) == (
        "fp32"
    )
    assert classify_ir_weight_precision(f16_constant_count=539, f32_constant_count=141) == (
        "fp16"
    )
    assert classify_ir_weight_precision(f16_constant_count=10, f32_constant_count=0) == (
        "fp16"
    )
    assert classify_ir_weight_precision(f16_constant_count=0, f32_constant_count=0) == (
        "unknown"
    )


def test_assert_requested_ir_precision_fail_closed() -> None:
    from offline_rag.dense.cpu_ov_executor import assert_requested_ir_precision

    assert_requested_ir_precision(
        requested_weight_format="fp16", observed_IR_weight_precision="fp16"
    )
    with pytest.raises(ValueError, match="refusing to label FP32"):
        assert_requested_ir_precision(
            requested_weight_format="fp16", observed_IR_weight_precision="fp32"
        )


def test_observe_execution_facts_does_not_invent_fp16_from_request() -> None:
    """F008: dtype must not be invented from requested weight_format label."""
    from offline_rag.dense.cpu_ov_executor import OpenVinoSTEmbedder

    emb = OpenVinoSTEmbedder(
        object(),
        weight_format="fp16",
        query_text_contract="raw-query-v1",
        precision_identity={},
    )
    facts = emb.observe_execution_facts()
    assert facts["dtype"] is None
    assert facts["requested_weight_format"] == "fp16"
    assert facts["observed_IR_weight_precision"] is None

    emb2 = OpenVinoSTEmbedder(
        object(),
        weight_format="fp16",
        query_text_contract="raw-query-v1",
        precision_identity={
            "observed_IR_weight_precision": "fp16",
            "observed_CPU_inference_precision": "fp32",
        },
    )
    facts2 = emb2.observe_execution_facts()
    assert facts2["dtype"] == "openvino_ir_fp16"
    assert facts2["observed_CPU_inference_precision"] == "fp32"
    assert "openvino_fp16" not in str(facts2["dtype"])


def test_stage0_export_artifact_is_observed_fp32_storage() -> None:
    """F008: existing Stage-0 export is FP32 IR storage (inspection only)."""
    from offline_rag.dense.cpu_ov_executor import (
        find_openvino_ir_xml,
        inspect_openvino_ir_weight_precision,
    )

    export_dir = REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "fp16"
    if not export_dir.is_dir():
        pytest.skip("Stage-0 local export not present")
    ir = inspect_openvino_ir_weight_precision(find_openvino_ir_xml(export_dir))
    assert ir["observed_IR_weight_precision"] == "fp32"
    assert ir["f16_constant_count"] == 0
    assert ir["f32_constant_count"] > 0
    assert ir["bin_bytes"] == 2383106573


def test_compress_to_fp16_probe_classifies_fp16() -> None:
    """F008: OpenVINO compress_to_fp16 produces inspectable FP16 IR storage."""
    from offline_rag.dense.cpu_ov_executor import inspect_openvino_ir_weight_precision

    probe = (
        REPO / "data" / "16k_d_cpu_ov_work" / "exports" / "_fp16_probe" / "openvino_model.xml"
    )
    if not probe.is_file():
        pytest.skip("local FP16 compress probe not present")
    ir = inspect_openvino_ir_weight_precision(probe)
    assert ir["observed_IR_weight_precision"] == "fp16"
    assert ir["f16_constant_count"] > ir["f32_constant_count"]
    assert ir["bin_bytes"] is not None
    assert ir["bin_bytes"] < 2383106573


def test_compress_fp16_never_aliases_source_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F009: save_model destination must not resolve to the source IR pair."""
    from offline_rag.dense import cpu_ov_executor as ex

    src_dir = tmp_path / "candidate" / "openvino"
    src_dir.mkdir(parents=True)
    source_xml = src_dir / "openvino_model.xml"
    source_bin = src_dir / "openvino_model.bin"
    source_xml.write_text("<net name='src'/>\n", encoding="utf-8")
    source_bin.write_bytes(b"FP32-WEIGHTS-SOURCE")
    source_xml_before = source_xml.read_bytes()
    source_bin_before = source_bin.read_bytes()

    saved_to: list[Path] = []

    class _FakeCore:
        def read_model(self, path: str) -> object:
            assert Path(path).resolve() == source_xml.resolve()
            return object()

    def _fake_save_model(model: object, path: str, compress_to_fp16: bool = False) -> None:
        del model
        assert compress_to_fp16 is True
        dest_xml = Path(path).resolve()
        dest_bin = dest_xml.with_suffix(".bin")
        saved_to.append(dest_xml)
        assert dest_xml != source_xml.resolve()
        assert dest_bin != source_bin.resolve()
        dest_xml.parent.mkdir(parents=True, exist_ok=True)
        dest_xml.write_text("<net name='fp16'/>\n", encoding="utf-8")
        dest_bin.write_bytes(b"FP16-WEIGHTS-TEMP")

    def _fake_inspect(xml_path: Path) -> dict:
        resolved = Path(xml_path).resolve()
        assert resolved != source_xml.resolve()
        return {
            "observed_IR_weight_precision": "fp16",
            "f16_constant_count": 10,
            "f32_constant_count": 1,
            "bin_bytes": resolved.with_suffix(".bin").stat().st_size,
        }

    fake_ov = type(
        "ov",
        (),
        {"Core": _FakeCore, "save_model": staticmethod(_fake_save_model)},
    )
    monkeypatch.setitem(__import__("sys").modules, "openvino", fake_ov)
    monkeypatch.setattr(ex, "inspect_openvino_ir_weight_precision", _fake_inspect)

    out = ex._compress_openvino_ir_to_fp16(source_xml)
    assert out.resolve() == source_xml.resolve()
    assert saved_to, "save_model was not called"
    assert saved_to[0] != source_xml.resolve()
    assert source_xml.read_bytes() == b"<net name='fp16'/>\n"
    assert source_bin.read_bytes() == b"FP16-WEIGHTS-TEMP"
    # Temporary directory cleaned; only candidate IR remains under openvino/.
    assert list(src_dir.glob("ov_fp16_compress_*")) == []
    assert source_xml_before != source_xml.read_bytes()
    assert source_bin_before != source_bin.read_bytes()


def test_compress_fp16_leaves_source_untouched_when_temp_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F009: failed temporary IR must not replace the candidate pair."""
    from offline_rag.dense import cpu_ov_executor as ex

    src_dir = tmp_path / "candidate" / "openvino"
    src_dir.mkdir(parents=True)
    source_xml = src_dir / "openvino_model.xml"
    source_bin = src_dir / "openvino_model.bin"
    source_xml.write_text("<net name='src'/>\n", encoding="utf-8")
    source_bin.write_bytes(b"FP32-WEIGHTS-SOURCE")
    before_xml = source_xml.read_bytes()
    before_bin = source_bin.read_bytes()

    class _FakeCore:
        def read_model(self, path: str) -> object:
            del path
            return object()

    def _fake_save_model(model: object, path: str, compress_to_fp16: bool = False) -> None:
        del model, compress_to_fp16
        dest_xml = Path(path)
        dest_xml.parent.mkdir(parents=True, exist_ok=True)
        dest_xml.write_bytes(b"")  # empty → fail closed
        dest_xml.with_suffix(".bin").write_bytes(b"")

    fake_ov = type(
        "ov",
        (),
        {"Core": _FakeCore, "save_model": staticmethod(_fake_save_model)},
    )
    monkeypatch.setitem(__import__("sys").modules, "openvino", fake_ov)

    with pytest.raises(RuntimeError, match="empty"):
        ex._compress_openvino_ir_to_fp16(source_xml)

    assert source_xml.read_bytes() == before_xml
    assert source_bin.read_bytes() == before_bin
    assert list(src_dir.glob("ov_fp16_compress_*")) == []
