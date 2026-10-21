"""Fail-closed ladder + ONNX INT8 identity regressions for CPU-ONNX-01."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from offline_rag.dense.cpu_onnx_feasibility import (
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_DIMENSION,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    FEASIBLE_MAX_MIN,
    FROZEN_BATCH_SIZE,
    FROZEN_ORT_INTER_OP_THREADS,
    FROZEN_ORT_INTRA_OP_THREADS,
    FROZEN_QINT8_TARGET,
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
from offline_rag.dense.cpu_onnx_harness import (
    build_full_confirm_result,
    build_screen_result,
    load_chunk_ids_from_manifest,
    run_export_fp32,
    run_export_qint8_avx2,
    run_full_confirm,
    run_parity,
    run_screen,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
)

REPO = Path(__file__).resolve().parents[3]


def test_execution_remains_locked() -> None:
    assert EXECUTION_AUTHORIZED is False


def test_projection_helpers() -> None:
    minutes = project_full_minutes(0.0932)
    assert 230.0 < minutes < 232.0
    assert classify_screen_projection(20.0) == "viable"
    assert classify_screen_projection(25.0) == "viable"
    assert classify_screen_projection(25.01) == "too_slow"


def test_frozen_runtime_knobs() -> None:
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=True,
        device="cpu",
        backend="onnx",
        ort_intra_op_threads=FROZEN_ORT_INTRA_OP_THREADS,
        ort_inter_op_threads=FROZEN_ORT_INTER_OP_THREADS,
    )
    with pytest.raises(ValueError, match="ort_intra_op_threads"):
        assert_frozen_runtime_knobs(
            batch_size=FROZEN_BATCH_SIZE,
            normalize=True,
            device="cpu",
            backend="onnx",
            ort_intra_op_threads=4,
            ort_inter_op_threads=1,
        )


def test_ladder_starts_at_fp32_export() -> None:
    plan = plan_next([])
    assert plan.next_action == "run_export_fp32"
    with pytest.raises(ValueError, match="transition refused"):
        assert_transition_allowed([], "run_export_qint8_avx2")
    with pytest.raises(ValueError, match="transition refused"):
        assert_transition_allowed([], "run_screen_qint8_avx2")


def test_qint8_requires_fp32_ok() -> None:
    history = [StageResult(stage_id="export_fp32", ok=True)]
    plan = plan_next(history)
    assert plan.next_action == "run_export_qint8_avx2"
    assert FROZEN_QINT8_TARGET == "avx2"
    with pytest.raises(ValueError, match="transition refused"):
        assert_transition_allowed(history, "run_screen_qint8_avx2")


def test_screen_after_qint8_then_viable_opens_parity() -> None:
    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
        StageResult(
            stage_id="screen_qint8_avx2",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_parity_qint8_avx2"
    assert plan.selected_candidate == "qint8_avx2"


def test_too_slow_screen_stops_for_llamacpp() -> None:
    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
        StageResult(
            stage_id="screen_qint8_avx2",
            ok=True,
            chunks_per_sec=0.5,
            projected_full_minutes=project_full_minutes(0.5),
        ),
    ]
    plan = plan_next(history)
    assert plan.terminal == "stop_too_slow"
    assert plan.next_action == "none"
    assert "llamacpp" in plan.reason


def test_parity_pass_opens_full_confirm_eligibility() -> None:
    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
        StageResult(
            stage_id="screen_qint8_avx2",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
        StageResult(stage_id="parity_qint8_avx2", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.full_confirm_eligible is True
    assert plan.next_action == "run_full_confirm"
    payload = run_full_confirm(history=history, selected_candidate="qint8_avx2")
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["executor_implemented"] is True
    assert payload["full_confirm_executor"] is False


def test_full_confirm_gate_rejects_slow_or_projection() -> None:
    base = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
        StageResult(
            stage_id="screen_qint8_avx2",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
        StageResult(stage_id="parity_qint8_avx2", ok=True, parity_ok=True),
    ]
    slow = build_full_confirm_result(full_wall_minutes=200.0)
    assert full_confirm_passes(slow) is False
    plan = plan_next([*base, slow])
    assert plan.terminal == "stop_too_slow"

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
    assert plan_ok.terminal == "select_onnx_qint8_avx2"


def test_locked_export_and_screen_refuse_without_running() -> None:
    payload = run_export_fp32(
        history=[],
        export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "fp32",
        repo_root=REPO,
    )
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["execution_authorized"] is False
    assert payload["executor_ready"] is True

    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
    ]
    screen = run_screen(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
        repo_root=REPO,
    )
    assert screen["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert screen["screen_child_count"] == SCREEN_CHILD_COUNT
    assert screen["screen_chunk_ids_digest"] == EXPECTED_SCREEN_CHUNK_IDS_DIGEST


def test_locked_export_qint8_after_fp32() -> None:
    history = [StageResult(stage_id="export_fp32", ok=True)]
    payload = run_export_qint8_avx2(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
        source_export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "fp32",
        repo_root=REPO,
    )
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["requested_weight_format"] == "qint8_avx2"
    assert "observed_ONNX_INT8_quantization" in payload["quantization_identity"]


def test_locked_parity_interface() -> None:
    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
        StageResult(
            stage_id="screen_qint8_avx2",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
    ]
    payload = run_parity(
        history=history,
        export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
        repo_root=REPO,
    )
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["document_count"] == PARITY_DOC_COUNT
    assert payload["query_count"] == PARITY_QUERY_COUNT
    assert payload["parity_contract"] == "d2-retrieval-parity-v1"


def test_manifest_sha256_matches_frozen_workload() -> None:
    ids = load_chunk_ids_from_manifest(repo_root=REPO)
    assert len(ids) == EXPECTED_CHILD_COUNT
    selected = select_screen_chunk_ids(ids)
    assert len(selected) == SCREEN_CHILD_COUNT
    assert sha256_text("\n".join(selected)) == EXPECTED_SCREEN_CHUNK_IDS_DIGEST
    docs, queries = select_parity_populations(ids)
    assert len(docs) == PARITY_DOC_COUNT
    assert len(queries) == PARITY_QUERY_COUNT
    manifest = (
        REPO
        / "data"
        / "chunk-manifests"
        / (
            "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d"
            ".json"
        )
    )
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert digest == EXPECTED_CHUNK_MANIFEST_SHA256


def test_manifest_sha256_fail_closed(tmp_path: Path) -> None:
    bad = tmp_path / "data" / "chunk-manifests"
    bad.mkdir(parents=True)
    src = (
        REPO
        / "data"
        / "chunk-manifests"
        / (
            "chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d"
            ".json"
        )
    )
    dest = bad / src.name
    dest.write_text(src.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="chunk manifest SHA256 mismatch"):
        load_chunk_ids_from_manifest(repo_root=tmp_path)


def test_refuse_hub_substitution() -> None:
    with pytest.raises(ValueError, match="Hub download"):
        refuse_hub_substitution(local_model_dir_exists=True, allow_download=True)
    with pytest.raises(ValueError, match="local pinned"):
        refuse_hub_substitution(local_model_dir_exists=False, allow_download=False)


def test_parity_thresholds_helper() -> None:
    good = {
        "median_document_vector_cosine": 0.9995,
        "min_document_vector_cosine": 0.996,
        "median_query_vector_cosine": 0.9995,
        "min_query_vector_cosine": 0.996,
        "top1_agreement": 15,
        "mean_top10_set_overlap": 0.96,
        "min_top10_set_overlap": 0.85,
    }
    assert parity_thresholds_pass(good) is True
    bad = dict(good)
    bad["top1_agreement"] = 14
    assert parity_thresholds_pass(bad) is False


def test_build_screen_result_keeps_projection_out_of_full_wall() -> None:
    result = build_screen_result(chunks_per_sec=1.0)
    assert result.full_wall_minutes is None
    assert result.projected_full_minutes == project_full_minutes(1.0)
    assert result.dimension is None or result.dimension == EXPECTED_DIMENSION


def _write_minimal_onnx(
    path: Path,
    *,
    with_int8_initializer: bool,
    with_quant_ops: bool = False,
    float_rows: int = 2,
) -> None:
    """Write a tiny ONNX ModelProto for identity-inspection unit tests."""
    onnx = pytest.importorskip("onnx")
    from onnx import TensorProto, helper, numpy_helper
    import numpy as np

    if with_int8_initializer:
        weights = numpy_helper.from_array(
            np.array([[1, -2], [3, -4]], dtype=np.int8), name="W"
        )
    else:
        weights = numpy_helper.from_array(
            np.arange(float_rows * 2, dtype=np.float32).reshape(float_rows, 2),
            name="W",
        )
    x = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 2])
    y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 2])
    nodes = [helper.make_node("Identity", ["X"], ["Y"])]
    if with_quant_ops:
        # Add QuantizeLinear / DequantizeLinear markers even if not executable.
        scale = numpy_helper.from_array(
            np.array([0.1], dtype=np.float32), name="scale"
        )
        zp = numpy_helper.from_array(np.array([0], dtype=np.int8), name="zp")
        initializers = [weights, scale, zp]
        nodes = [
            helper.make_node(
                "QuantizeLinear", ["X", "scale", "zp"], ["X_q"], name="q"
            ),
            helper.make_node(
                "DequantizeLinear", ["X_q", "scale", "zp"], ["Y"], name="dq"
            ),
        ]
    else:
        initializers = [weights]
    graph = helper.make_graph(nodes, "t", [x], [y], initializer=initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))


def test_inspect_onnx_quantization_fail_closed(tmp_path: Path) -> None:
    from offline_rag.dense.cpu_onnx_executor import (
        assert_requested_onnx_quantization,
        inspect_onnx_quantization,
    )

    fp32 = tmp_path / "model.onnx"
    _write_minimal_onnx(fp32, with_int8_initializer=False)
    fp_obs = inspect_onnx_quantization(fp32)
    assert fp_obs["observed_ONNX_INT8_quantization"]["verified"] is False

    q = tmp_path / "model_qint8_avx2.onnx"
    _write_minimal_onnx(q, with_int8_initializer=True)
    q_obs = inspect_onnx_quantization(q)
    assert q_obs["observed_ONNX_INT8_quantization"]["verified"] is True
    assert q_obs["int8_initializer_count"] >= 1

    with pytest.raises(ValueError, match="not verified"):
        assert_requested_onnx_quantization(
            requested_weight_format="qint8_avx2",
            observed_ONNX_INT8_quantization=fp_obs["observed_ONNX_INT8_quantization"],
        )
    assert_requested_onnx_quantization(
        requested_weight_format="qint8_avx2",
        observed_ONNX_INT8_quantization=q_obs["observed_ONNX_INT8_quantization"],
    )


def test_filename_alone_never_proves_int8(tmp_path: Path) -> None:
    """A ``_qint8_avx2`` filename with FP32 weights must not verify INT8."""
    from offline_rag.dense.cpu_onnx_executor import (
        assert_requested_onnx_quantization,
        build_onnx_precision_identity,
        inspect_onnx_quantization,
    )

    decoy = tmp_path / "onnx" / "model_qint8_avx2.onnx"
    _write_minimal_onnx(decoy, with_int8_initializer=False)
    obs = inspect_onnx_quantization(decoy)
    assert obs["observed_ONNX_INT8_quantization"]["verified"] is False
    identity = build_onnx_precision_identity(
        requested_weight_format="qint8_avx2",
        export_dir=tmp_path,
        quantization_target="avx2",
    )
    assert identity["observed_ONNX_INT8_quantization"]["verified"] is False
    with pytest.raises(ValueError, match="not verified"):
        assert_requested_onnx_quantization(
            requested_weight_format="qint8_avx2",
            observed_ONNX_INT8_quantization=identity[
                "observed_ONNX_INT8_quantization"
            ],
        )


def test_select_prefers_graph_verified_int8(tmp_path: Path) -> None:
    from offline_rag.dense.cpu_onnx_executor import select_onnx_artifact_for_weight_format

    fp32 = tmp_path / "onnx" / "model.onnx"
    q8 = tmp_path / "onnx" / "model_qint8_avx2.onnx"
    # Larger FP32 weight blob so a naive size pick would choose the wrong file.
    _write_minimal_onnx(fp32, with_int8_initializer=False, float_rows=2048)
    _write_minimal_onnx(q8, with_int8_initializer=True)
    assert fp32.stat().st_size > q8.stat().st_size
    path, identity = select_onnx_artifact_for_weight_format(
        export_dir=tmp_path,
        weight_format="qint8_avx2",
    )
    assert path.resolve() == q8.resolve()
    assert identity["observed_ONNX_INT8_quantization"]["verified"] is True


def test_unlocked_export_delegates_to_executor() -> None:
    import offline_rag.dense.cpu_onnx_feasibility as feas
    import offline_rag.dense.cpu_onnx_harness as harness

    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_onnx_executor.execute_export_fp32",
            return_value={"status": "ok", "ok": True},
        ) as mocked,
        patch.object(
            harness,
            "resolve_local_pinned_model_dir",
            return_value=Path("/tmp/model"),
        ),
    ):
        out = harness.run_export_fp32(
            history=[],
            export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "fp32",
            repo_root=REPO,
        )
    assert out["status"] == "ok"
    mocked.assert_called_once()


def test_unlocked_screen_delegates_to_executor() -> None:
    import offline_rag.dense.cpu_onnx_feasibility as feas
    import offline_rag.dense.cpu_onnx_harness as harness

    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
    ]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch(
            "offline_rag.dense.cpu_onnx_executor.execute_screen",
            return_value={"status": "ok", "ok": True},
        ) as mocked,
    ):
        out = harness.run_screen(
            history=history,
            export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
            repo_root=REPO,
        )
    assert out["status"] == "ok"
    mocked.assert_called_once()


def _load_cpu_onnx_cli():
    path = REPO / "scripts" / "diag_16k_d_dense" / "run_cpu_onnx_feasibility.py"
    spec = importlib.util.spec_from_file_location("run_cpu_onnx_feasibility_cli", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_plan_empty_history(tmp_path: Path) -> None:
    cli = _load_cpu_onnx_cli()
    out = tmp_path / "plan.json"
    rc = cli.main(["plan", "--out", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["execution_authorized"] is False
    assert payload["plan"]["next_action"] == "run_export_fp32"


def test_cli_export_fp32_locked(tmp_path: Path) -> None:
    cli = _load_cpu_onnx_cli()
    out = tmp_path / "export.json"
    rc = cli.main(
        [
            "export-fp32",
            "--export-dir",
            str(tmp_path / "fp32"),
            "--out",
            str(out),
        ]
    )
    assert rc == 20
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
