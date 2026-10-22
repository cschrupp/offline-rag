"""Fail-closed ladder + execution-lock regressions for CPU-GGUF-01."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from offline_rag.dense.cpu_gguf_client import LlamaCppEmbeddingClient
from offline_rag.dense.cpu_gguf_feasibility import (
    EXECUTION_AUTHORIZED,
    EXPECTED_CHILD_COUNT,
    EXPECTED_CHUNK_MANIFEST_SHA256,
    EXPECTED_DIMENSION,
    EXPECTED_GGUF_SHA256,
    EXPECTED_SCREEN_CHUNK_IDS_DIGEST,
    FROZEN_BATCH_SIZE,
    FROZEN_N_GPU_LAYERS,
    FROZEN_POOLING,
    FROZEN_THREADS,
    FROZEN_THREADS_BATCH,
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
from offline_rag.dense.cpu_gguf_harness import (
    build_full_confirm_result,
    build_screen_result,
    load_chunk_ids_from_manifest,
    run_full_confirm,
    run_parity,
    run_screen,
    run_stage0_compat,
    select_parity_populations,
    select_screen_chunk_ids,
    sha256_text,
)
from offline_rag.dense.cpu_gguf_server import (
    build_llama_server_command,
    verify_official_gguf,
)

REPO = Path(__file__).resolve().parents[3]


def test_execution_remains_locked() -> None:
    assert EXECUTION_AUTHORIZED is False


def test_projection_helpers() -> None:
    minutes = project_full_minutes(0.60681)
    assert 35.0 < minutes < 36.0
    assert classify_screen_projection(20.0) == "viable"
    assert classify_screen_projection(25.0) == "viable"
    assert classify_screen_projection(25.01) == "too_slow"


def test_frozen_runtime_knobs() -> None:
    assert_frozen_runtime_knobs(
        batch_size=FROZEN_BATCH_SIZE,
        normalize=True,
        device="cpu",
        backend="llama_cpp",
        pooling=FROZEN_POOLING,
        n_gpu_layers=FROZEN_N_GPU_LAYERS,
        threads=FROZEN_THREADS,
        threads_batch=FROZEN_THREADS_BATCH,
    )
    with pytest.raises(ValueError, match="n_gpu_layers"):
        assert_frozen_runtime_knobs(
            batch_size=FROZEN_BATCH_SIZE,
            normalize=True,
            device="cpu",
            backend="llama_cpp",
            n_gpu_layers=1,
        )


def test_ladder_starts_at_stage0() -> None:
    plan = plan_next([])
    assert plan.next_action == "run_stage0_compat"
    with pytest.raises(ValueError, match="transition refused"):
        assert_transition_allowed([], "run_screen_q8_0")


def test_screen_after_stage0_then_viable_opens_parity() -> None:
    history = [
        StageResult(stage_id="stage0_compat", ok=True),
        StageResult(
            stage_id="screen_q8_0",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
    ]
    plan = plan_next(history)
    assert plan.next_action == "run_parity_q8_0"
    assert plan.selected_candidate == "q8_0"


def test_too_slow_screen_stops_for_model_change() -> None:
    history = [
        StageResult(stage_id="stage0_compat", ok=True),
        StageResult(
            stage_id="screen_q8_0",
            ok=True,
            chunks_per_sec=0.5,
            projected_full_minutes=project_full_minutes(0.5),
        ),
    ]
    plan = plan_next(history)
    assert plan.terminal == "stop_too_slow"
    assert plan.next_action == "none"
    assert "model_change" in plan.reason


def test_parity_pass_opens_full_confirm_eligibility() -> None:
    history = [
        StageResult(stage_id="stage0_compat", ok=True),
        StageResult(
            stage_id="screen_q8_0",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
        StageResult(stage_id="parity_q8_0", ok=True, parity_ok=True),
    ]
    plan = plan_next(history)
    assert plan.full_confirm_eligible is True
    assert plan.next_action == "run_full_confirm"
    payload = run_full_confirm(history=history, selected_candidate="q8_0")
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["executor_implemented"] is True
    assert payload["full_confirm_executor"] is False


def test_full_confirm_gate_rejects_slow() -> None:
    base = [
        StageResult(stage_id="stage0_compat", ok=True),
        StageResult(
            stage_id="screen_q8_0",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
        StageResult(stage_id="parity_q8_0", ok=True, parity_ok=True),
    ]
    slow = build_full_confirm_result(full_wall_minutes=200.0)
    assert full_confirm_passes(slow) is False
    plan = plan_next([*base, slow])
    assert plan.terminal == "stop_too_slow"


def test_refuse_hub_download() -> None:
    with pytest.raises(ValueError, match="Hub download"):
        refuse_hub_substitution(local_gguf_exists=True, allow_download=True)
    with pytest.raises(ValueError, match="missing"):
        refuse_hub_substitution(local_gguf_exists=False, allow_download=False)


def test_stage0_locked_refuses_without_launch() -> None:
    payload = run_stage0_compat(history=[])
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["execution_authorized"] is False
    assert payload["requested_action"] == "run_stage0_compat"
    assert payload["executor_ready"] is True


def test_screen_locked_preserves_digest() -> None:
    history = [StageResult(stage_id="stage0_compat", ok=True)]
    payload = run_screen(history=history, repo_root=REPO)
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["screen_chunk_ids_digest"] == EXPECTED_SCREEN_CHUNK_IDS_DIGEST
    assert payload["screen_child_count"] == SCREEN_CHILD_COUNT
    assert payload["chunk_manifest_sha256"] == EXPECTED_CHUNK_MANIFEST_SHA256


def test_manifest_and_screen_selection() -> None:
    ids = load_chunk_ids_from_manifest(repo_root=REPO)
    assert len(ids) == EXPECTED_CHILD_COUNT
    selected = select_screen_chunk_ids(ids)
    assert len(selected) == SCREEN_CHILD_COUNT
    assert sha256_text("\n".join(selected)) == EXPECTED_SCREEN_CHUNK_IDS_DIGEST
    docs, queries = select_parity_populations(ids)
    assert len(docs) == 64
    assert len(queries) == 16


def test_llama_server_command_forces_cpu_and_pooling() -> None:
    cmd = build_llama_server_command(
        binary=Path("/tmp/llama-server"),
        model=Path("/tmp/model.gguf"),
        host="127.0.0.1",
        port=8080,
    )
    assert "--embeddings" in cmd
    assert "--pooling" in cmd and "last" in cmd
    assert "--n-gpu-layers" in cmd
    assert cmd[cmd.index("--n-gpu-layers") + 1] == "0"
    assert "--no-webui" in cmd
    with pytest.raises(ValueError, match="n-gpu-layers"):
        build_llama_server_command(
            binary=Path("/tmp/llama-server"),
            model=Path("/tmp/model.gguf"),
            host="127.0.0.1",
            port=8080,
            n_gpu_layers=1,
        )


def test_verify_official_gguf_sha_gate(tmp_path: Path) -> None:
    path = tmp_path / "Qwen3-Embedding-0.6B-Q8_0.gguf"
    path.write_bytes(b"not-the-real-gguf")
    with pytest.raises(ValueError, match="SHA mismatch"):
        verify_official_gguf(path)


def test_client_rejects_bad_embeddings_payload() -> None:
    mock = MagicMock()
    mock.post.return_value.status_code = 200
    mock.post.return_value.raise_for_status = MagicMock()
    mock.post.return_value.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * EXPECTED_DIMENSION},
            {"index": 0, "embedding": [0.2] * EXPECTED_DIMENSION},
        ]
    }
    client = LlamaCppEmbeddingClient(
        base_url="http://127.0.0.1:9",
        client=mock,
        require_normalize=False,
    )
    with pytest.raises(ValueError, match="duplicate"):
        client._embed_batch(["a", "b"])


def test_client_orders_and_normalizes() -> None:
    # Unit vector along first axis after normalize of [3,0,...]
    raw = [3.0] + [0.0] * (EXPECTED_DIMENSION - 1)
    mock = MagicMock()
    mock.post.return_value.status_code = 200
    mock.post.return_value.raise_for_status = MagicMock()
    mock.post.return_value.json.return_value = {
        "data": [
            {"index": 1, "embedding": list(raw)},
            {"index": 0, "embedding": list(raw)},
        ]
    }
    client = LlamaCppEmbeddingClient(
        base_url="http://127.0.0.1:9",
        client=mock,
        require_normalize=True,
    )
    out = client._embed_batch(["a", "b"])
    assert len(out) == 2
    assert abs(out[0][0] - 1.0) < 1e-9
    assert abs(sum(x * x for x in out[0]) - 1.0) < 1e-9


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


def test_build_screen_result_stage_id() -> None:
    result = build_screen_result(chunks_per_sec=1.0)
    assert result.stage_id == "screen_q8_0"
    assert result.projected_full_minutes == project_full_minutes(1.0)


def test_parity_locked_after_viable_screen() -> None:
    history = [
        StageResult(stage_id="stage0_compat", ok=True),
        StageResult(
            stage_id="screen_q8_0",
            ok=True,
            chunks_per_sec=2.0,
            projected_full_minutes=project_full_minutes(2.0),
        ),
    ]
    payload = run_parity(history=history, repo_root=REPO)
    assert payload["status"] == "EXECUTION_NOT_AUTHORIZED"
    assert payload["parity_contract"] == "d2-retrieval-parity-v1"
    assert payload["candidate_lane"].startswith("llama_cpp")


def test_unlocked_stage0_requires_paths() -> None:
    with patch(
        "offline_rag.dense.cpu_gguf_harness.EXECUTION_AUTHORIZED",
        True,
    ), patch(
        "offline_rag.dense.cpu_gguf_feasibility.EXECUTION_AUTHORIZED",
        True,
    ):
        # harness module constant is what run_stage0_compat reads
        import offline_rag.dense.cpu_gguf_harness as harness

        with patch.object(harness, "EXECUTION_AUTHORIZED", True):
            with pytest.raises(ValueError, match="required"):
                harness.run_stage0_compat(history=[])


def test_gguf_pin_constant_matches_authority() -> None:
    assert EXPECTED_GGUF_SHA256 == (
        "a0e820fb3f8f448d3582862f9161bfaf58a63f89b46353f061e017597655821c"
    )
    assert EXPECTED_DIMENSION == 1024
    assert FROZEN_BATCH_SIZE == 32
    assert FROZEN_POOLING == "last"
    assert FROZEN_N_GPU_LAYERS == 0


def test_sha256_text_stable() -> None:
    assert sha256_text("abc") == hashlib.sha256(b"abc").hexdigest()
