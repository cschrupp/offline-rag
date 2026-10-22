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
    EXPECTED_FP32_STAGE0_EXPORT_TREE_SHA256,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    FEASIBLE_MAX_MIN,
    FROZEN_BATCH_SIZE,
    FROZEN_ORT_INTER_OP_THREADS,
    FROZEN_ORT_INTRA_OP_THREADS,
    FROZEN_QINT8_TARGET,
    IMPLEMENTATION_POSITION_IDS_COMPAT_AUTH,
    PARITY_DOC_COUNT,
    PARITY_QUERY_COUNT,
    POSITION_IDS_COMPAT_SEMANTICS,
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
        # Op markers only: float scale/zp so no INT8/UINT8 weight initializers.
        scale = numpy_helper.from_array(
            np.array([0.1], dtype=np.float32), name="scale"
        )
        zp = numpy_helper.from_array(
            np.array([0.0], dtype=np.float32), name="zp"
        )
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
            expected_candidate_tree_sha256="a" * 64,
            repo_root=REPO,
        )
    assert out["status"] == "ok"
    mocked.assert_called_once()
    assert mocked.call_args.kwargs["expected_candidate_tree_sha256"] == "a" * 64


def test_f001_qint8_requires_source_tree_sha(tmp_path: Path) -> None:
    """F001: missing/wrong FP32 source SHA fails before copy/quantization."""
    from offline_rag.dense.cpu_onnx_executor import materialize_qint8_avx2_derivative

    source = tmp_path / "fp32"
    dest = tmp_path / "qint8"
    source.mkdir()
    _write_minimal_onnx(source / "model.onnx", with_int8_initializer=False)

    with pytest.raises(ValueError, match="expected_source_tree_sha256 is required"):
        materialize_qint8_avx2_derivative(
            source_export_dir=source,
            export_dir=dest,
            expected_source_tree_sha256="",
        )
    assert not dest.exists()

    with pytest.raises(ValueError, match="source tree SHA256 mismatch"):
        materialize_qint8_avx2_derivative(
            source_export_dir=source,
            export_dir=dest,
            expected_source_tree_sha256="0" * 64,
        )
    assert not dest.exists()


def test_f001_unlocked_harness_requires_source_sha() -> None:
    import offline_rag.dense.cpu_onnx_feasibility as feas
    import offline_rag.dense.cpu_onnx_harness as harness

    history = [StageResult(stage_id="export_fp32", ok=True)]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
        patch.object(
            harness,
            "resolve_local_pinned_model_dir",
            return_value=Path("/tmp/model"),
        ),
    ):
        with pytest.raises(ValueError, match="expected_source_tree_sha256 is required"):
            harness.run_export_qint8_avx2(
                history=history,
                export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
                source_export_dir=REPO
                / "data"
                / "16k_d_cpu_onnx_work"
                / "exports"
                / "fp32",
                expected_source_tree_sha256=None,
                repo_root=REPO,
            )


def test_f002_quant_ops_alone_do_not_verify(tmp_path: Path) -> None:
    """F002: QuantizeLinear/DequantizeLinear without INT8/UINT8 weights ≠ verified."""
    from offline_rag.dense.cpu_onnx_executor import (
        assert_requested_onnx_quantization,
        inspect_onnx_quantization,
    )

    path = tmp_path / "ops_only.onnx"
    _write_minimal_onnx(
        path, with_int8_initializer=False, with_quant_ops=True
    )
    obs = inspect_onnx_quantization(path)
    oc = obs["observed_ONNX_INT8_quantization"]
    assert oc["demonstrable_quantization_ops"] is True
    assert oc["quantization_op_count"] >= 1
    assert oc["demonstrable_integer_initializers"] is False
    assert oc["verified"] is False
    with pytest.raises(ValueError, match="not verified|INT8/UINT8"):
        assert_requested_onnx_quantization(
            requested_weight_format="qint8_avx2",
            observed_ONNX_INT8_quantization=oc,
        )


def test_f003_screen_enforces_candidate_tree_immutability(tmp_path: Path) -> None:
    """F003: expected SHA required; mismatch before/after encode fails closed."""
    from offline_rag.dense import cpu_onnx_executor as ex
    from offline_rag.dense.cpu_onnx_feasibility import (
        EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    )
    from offline_rag.dense.cpu_onnx_harness import hash_export_tree

    export_dir = tmp_path / "qint8"
    export_dir.mkdir()
    _write_minimal_onnx(export_dir / "model_qint8_avx2.onnx", with_int8_initializer=True)
    tree = hash_export_tree(export_dir)
    good_sha = str(tree["tree_sha256"])

    with pytest.raises(ValueError, match="expected_candidate_tree_sha256 is required"):
        ex.execute_screen(
            export_dir=export_dir,
            repo_root=REPO,
            expected_candidate_tree_sha256="",
        )

    with pytest.raises(ValueError, match="mismatch before screen"):
        ex.execute_screen(
            export_dir=export_dir,
            repo_root=REPO,
            expected_candidate_tree_sha256="0" * 64,
        )

    good_tree = {"tree_sha256": good_sha, "files": [], "file_count": 0}
    mutated_tree = {"tree_sha256": "f" * 64, "files": [], "file_count": 0}
    hash_calls = {"n": 0}

    def _hash(_path: Path) -> dict:
        hash_calls["n"] += 1
        return good_tree if hash_calls["n"] == 1 else mutated_tree

    with (
        patch(
            "offline_rag.dense.cpu_onnx_executor.hash_export_tree",
            side_effect=_hash,
        ),
        patch.object(ex, "load_children_by_id", return_value={"id0": object()}),
        patch(
            "offline_rag.dense.cpu_onnx_executor.select_screen_chunk_ids",
            return_value=["id0"] * 128,
        ),
        patch(
            "offline_rag.dense.cpu_onnx_executor.sha256_text",
            return_value=EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
        ),
        patch.object(
            ex,
            "document_embedding_texts",
            return_value=[("id0", "h", "text")] * 128,
        ),
        patch.object(
            ex,
            "load_onnx_st_model",
            return_value=(
                object(),
                {"observed_ONNX_INT8_quantization": {"verified": True}},
            ),
        ),
        patch.object(
            ex, "resolve_production_query_contract", return_value="raw-query-v1"
        ),
        patch.object(ex, "capture_cpu_host_runtime_facts", return_value={}),
        patch.object(
            ex.OnnxSTEmbedder,
            "embed_documents",
            return_value=[[0.0] * 1024] * 128,
        ),
    ):
        with pytest.raises(ValueError, match="mutated during screen"):
            ex.execute_screen(
                export_dir=export_dir,
                repo_root=REPO,
                expected_candidate_tree_sha256=good_sha,
            )


def test_f003_unlocked_harness_requires_candidate_sha() -> None:
    import offline_rag.dense.cpu_onnx_feasibility as feas
    import offline_rag.dense.cpu_onnx_harness as harness

    history = [
        StageResult(stage_id="export_fp32", ok=True),
        StageResult(stage_id="export_qint8_avx2", ok=True),
    ]
    with (
        patch.object(feas, "EXECUTION_AUTHORIZED", True),
        patch.object(harness, "EXECUTION_AUTHORIZED", True),
    ):
        with pytest.raises(
            ValueError, match="expected_candidate_tree_sha256 is required"
        ):
            harness.run_screen(
                history=history,
                export_dir=REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "qint8",
                expected_candidate_tree_sha256=None,
                repo_root=REPO,
            )


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


# --- POSITION_IDS compat (AUTH-001): pure construction; no Qwen/ONNX scientific run ---


def test_position_ids_compat_auth_constants() -> None:
    assert EXECUTION_AUTHORIZED is False
    assert (
        IMPLEMENTATION_POSITION_IDS_COMPAT_AUTH
        == "S16-K-D-POST-CPUOV-CPU-ONNX-POSITION-IDS-COMPAT-IMPLEMENTATION-AUTH-001"
    )
    assert POSITION_IDS_COMPAT_SEMANTICS == "qwen3_direct_forward_zero_based_arange"
    assert EXPECTED_FP32_STAGE0_EXPORT_TREE_SHA256.startswith("3e1b23a7")


def test_position_ids_single_batch_zero_based_arange() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import (
        build_qwen3_direct_forward_position_ids,
    )

    input_ids = torch.tensor([[10, 20, 30, 40]], dtype=torch.long)
    pos = build_qwen3_direct_forward_position_ids(input_ids)
    assert pos.dtype == torch.long
    assert pos.shape == (1, 4)
    assert pos.tolist() == [[0, 1, 2, 3]]


def test_position_ids_batched_identical_rows() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import (
        build_qwen3_direct_forward_position_ids,
    )

    input_ids = torch.tensor([[1, 2, 3], [4, 5, 6], [7, 8, 9]], dtype=torch.long)
    pos = build_qwen3_direct_forward_position_ids(input_ids)
    assert pos.shape == (3, 3)
    assert pos.tolist() == [[0, 1, 2], [0, 1, 2], [0, 1, 2]]


def test_position_ids_not_attention_mask_cumsum() -> None:
    """Protect against generation-style cumsum semantics.

    attention_mask=[0,0,1,1] must still yield [0,1,2,3], not [0,0,0,1].
    """
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import (
        apply_seneca_onnx_position_ids_compat,
        build_qwen3_direct_forward_position_ids,
    )

    attention_mask = torch.tensor([[0, 0, 1, 1]], dtype=torch.long)
    input_ids = torch.tensor([[9, 9, 9, 9]], dtype=torch.long)
    # Generation-style (FORBIDDEN for this adapter):
    generation_style = attention_mask.long().cumsum(-1) - 1
    generation_style = generation_style.masked_fill(attention_mask == 0, 0)
    assert generation_style.tolist() == [[0, 0, 0, 1]]

    authorized = build_qwen3_direct_forward_position_ids(input_ids)
    assert authorized.tolist() == [[0, 1, 2, 3]]

    features = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids, "attention_mask": attention_mask},
        required_onnx_inputs=["input_ids", "attention_mask", "position_ids"],
    )
    assert features["position_ids"].tolist() == [[0, 1, 2, 3]]
    assert features["attention_mask"].tolist() == [[0, 0, 1, 1]]
    assert features["input_ids"].tolist() == [[9, 9, 9, 9]]


def test_position_ids_padding_does_not_alter_positions() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    input_ids = torch.tensor([[1, 2, 3, 4]], dtype=torch.long)
    left_pad = torch.tensor([[0, 0, 1, 1]], dtype=torch.long)
    right_pad = torch.tensor([[1, 1, 0, 0]], dtype=torch.long)
    required = ["input_ids", "attention_mask", "position_ids"]

    left = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids, "attention_mask": left_pad},
        required_onnx_inputs=required,
    )
    right = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids.clone(), "attention_mask": right_pad},
        required_onnx_inputs=required,
    )
    assert left["position_ids"].tolist() == right["position_ids"].tolist() == [
        [0, 1, 2, 3]
    ]


def test_position_ids_preserves_valid_supplied() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    input_ids = torch.tensor([[1, 2, 3]], dtype=torch.long)
    supplied = torch.tensor([[5, 6, 7]], dtype=torch.long)
    out = apply_seneca_onnx_position_ids_compat(
        {
            "input_ids": input_ids,
            "attention_mask": torch.ones_like(input_ids),
            "position_ids": supplied,
        },
        required_onnx_inputs=["input_ids", "attention_mask", "position_ids"],
    )
    assert out["position_ids"] is supplied
    assert out["position_ids"].tolist() == [[5, 6, 7]]


def test_position_ids_noop_when_graph_does_not_require() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    features = {
        "input_ids": torch.tensor([[1, 2]], dtype=torch.long),
        "attention_mask": torch.tensor([[1, 1]], dtype=torch.long),
    }
    out = apply_seneca_onnx_position_ids_compat(
        features,
        required_onnx_inputs=["input_ids", "attention_mask"],
    )
    assert "position_ids" not in out
    assert out["input_ids"].tolist() == [[1, 2]]


def test_position_ids_fail_closed_missing_input_ids() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    with pytest.raises(ValueError, match="requires input_ids"):
        apply_seneca_onnx_position_ids_compat(
            {"attention_mask": torch.tensor([[1, 1]], dtype=torch.long)},
            required_onnx_inputs=["input_ids", "attention_mask", "position_ids"],
        )


def test_position_ids_fail_closed_rank_mismatch() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import (
        apply_seneca_onnx_position_ids_compat,
        build_qwen3_direct_forward_position_ids,
    )

    with pytest.raises(ValueError, match="rank-2"):
        build_qwen3_direct_forward_position_ids(torch.tensor([1, 2, 3], dtype=torch.long))
    with pytest.raises(ValueError, match="rank-2"):
        apply_seneca_onnx_position_ids_compat(
            {"input_ids": torch.tensor([1, 2, 3], dtype=torch.long)},
            required_onnx_inputs=["input_ids", "position_ids"],
        )


def test_position_ids_fail_closed_incompatible_supplied_shape() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    with pytest.raises(ValueError, match="incompatible"):
        apply_seneca_onnx_position_ids_compat(
            {
                "input_ids": torch.tensor([[1, 2, 3]], dtype=torch.long),
                "position_ids": torch.tensor([[0, 1]], dtype=torch.long),
            },
            required_onnx_inputs=["input_ids", "position_ids"],
        )


def test_position_ids_dtype_long_ort_compatible() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import (
        apply_seneca_onnx_position_ids_compat,
        build_qwen3_direct_forward_position_ids,
    )

    input_ids = torch.tensor([[1, 2]], dtype=torch.long)
    pos = build_qwen3_direct_forward_position_ids(input_ids)
    assert pos.dtype == torch.long
    assert pos.numpy().dtype.name == "int64"
    out = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids},
        required_onnx_inputs=["input_ids", "position_ids"],
    )
    assert out["position_ids"].dtype == torch.long


def test_position_ids_does_not_modify_input_ids_or_attention_mask() -> None:
    torch = pytest.importorskip("torch")
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    input_ids = torch.tensor([[3, 4, 5]], dtype=torch.long)
    attention_mask = torch.tensor([[1, 0, 1]], dtype=torch.long)
    input_ids_before = input_ids.clone()
    attention_before = attention_mask.clone()
    out = apply_seneca_onnx_position_ids_compat(
        {"input_ids": input_ids, "attention_mask": attention_mask},
        required_onnx_inputs=["input_ids", "attention_mask", "position_ids"],
    )
    assert torch.equal(out["input_ids"], input_ids_before)
    assert torch.equal(out["attention_mask"], attention_before)
    assert out["input_ids"] is input_ids
    assert out["attention_mask"] is attention_mask


def test_position_ids_graph_detection_from_onnx(tmp_path: Path) -> None:
    from offline_rag.dense.cpu_onnx_executor import (
        onnx_graph_input_names,
        onnx_graph_requires_position_ids,
    )

    path = tmp_path / "with_pos.onnx"
    _write_minimal_onnx(path, with_int8_initializer=False)
    # Minimal Identity graph has only X — not position_ids.
    assert onnx_graph_requires_position_ids(path) is False
    assert "position_ids" not in onnx_graph_input_names(path)


def test_position_ids_compat_does_not_touch_fp32_export_tree() -> None:
    """Compat code must not mutate the immutable Stage-0A FP32 tree bytes."""
    from offline_rag.dense.cpu_onnx_harness import hash_export_tree
    from offline_rag.dense.cpu_onnx_executor import apply_seneca_onnx_position_ids_compat

    torch = pytest.importorskip("torch")
    export = REPO / "data" / "16k_d_cpu_onnx_work" / "exports" / "fp32_v1"
    if not export.is_dir():
        pytest.skip("Stage-0A FP32 export tree not present locally")
    before = hash_export_tree(export)
    assert before["tree_sha256"] == EXPECTED_FP32_STAGE0_EXPORT_TREE_SHA256

    apply_seneca_onnx_position_ids_compat(
        {
            "input_ids": torch.tensor([[1, 2, 3, 4]], dtype=torch.long),
            "attention_mask": torch.tensor([[0, 0, 1, 1]], dtype=torch.long),
        },
        required_onnx_inputs=["input_ids", "attention_mask", "position_ids"],
    )
    after = hash_export_tree(export)
    assert after["tree_sha256"] == before["tree_sha256"] == (
        EXPECTED_FP32_STAGE0_EXPORT_TREE_SHA256
    )
