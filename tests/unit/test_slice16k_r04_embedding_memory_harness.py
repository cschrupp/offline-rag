from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_16k_r04_embedding_memory.cell_executor import (
    _encode_queries,
    _validate_cell_spec,
)
from scripts.diag_16k_r04_embedding_memory.contract import (
    FrozenItem,
    build_workload_manifest,
    classify_oom_diagnostics,
    enforce_cell_budget,
    evaluate_mechanism_pairs,
    evaluate_parity,
    evaluate_production_candidate,
    greedy_token_partitions,
)
from scripts.diag_16k_r04_embedding_memory.runtime import (
    CacheActivationObserver,
    SDPABackendObserver,
    claim_single_cell_process,
    complete_cell_process_claim,
    safe_cell_evidence,
    verify_execution_authority,
)


def _workload_items() -> list[FrozenItem]:
    return [
        FrozenItem(
            chunk_id=f"chunk_{index:02d}",
            embedding_text_sha256=f"{index:064x}",
            embedding_artifact_text_sha256=f"{index + 1:064x}",
            query_input_sha256=f"{index + 2:064x}",
            qwen_token_count=10 + index,
        )
        for index in range(32)
    ]


def test_frozen_workload_manifest_contains_only_hashes_and_token_counts() -> None:
    manifest = build_workload_manifest(
        items=_workload_items(),
        workload_kind="INCIDENT_ADJACENT_SUBSTITUTE",
        source_document_id=f"doc_{'a' * 64}",
        source_sha256="a" * 64,
        corpus_id="corpus_example",
        chunk_set_id="chunkset_example",
        embedding_config_hash="embcfg_example",
        reused_count=893,
        desired_count=1498,
    )

    rendered = json.dumps(manifest)
    assert manifest["item_count"] == 32
    assert manifest["execution_authorized"] is False
    assert manifest["ordered_items"][0]["qwen_token_count"] == 10
    assert manifest["ordered_items"][0]["query_input_sha256"] == f"{2:064x}"
    assert "private source phrase" not in rendered
    assert "input_ids" not in rendered
    assert '"embedding_text":' not in rendered


def test_m4_greedy_partitions_preserve_order_and_budget() -> None:
    token_counts = [5] * 31 + [150]
    partitions = greedy_token_partitions(token_counts)
    assert partitions is not None
    flattened = [index for partition in partitions for index in partition]
    assert flattened == list(range(32))
    p95 = sorted(token_counts)[30]
    budget = 32 * p95
    assert all(
        len(partition) * max(token_counts[index] for index in partition) <= budget
        for partition in partitions
    )
    assert greedy_token_partitions([1] * 31 + [33]) is None


def test_cell_budget_enforces_counts_and_time_caps() -> None:
    assert (
        enforce_cell_budget(
            [{"cell_id": "M0", "duration_seconds": 30.0} for _ in range(3)]
        )["total_processes"]
        == 3
    )
    with pytest.raises(ValueError, match="cell cap"):
        enforce_cell_budget([{"cell_id": "M3_PROFILE"}] * 2)
    with pytest.raises(ValueError, match="15-minute"):
        enforce_cell_budget([{"cell_id": "M0", "duration_seconds": 901}])
    with pytest.raises(ValueError, match="CPU ONNX"):
        enforce_cell_budget([{"cell_id": "CPU_ONNX_REFERENCE"}] * 2)


def test_parity_evaluator_uses_frozen_vector_and_retrieval_thresholds() -> None:
    unit = [1.0] + [0.0] * 1023
    documents = [unit.copy() for _ in range(32)]
    queries = [unit.copy() for _ in range(16)]
    result = evaluate_parity(
        reference_documents=documents,
        candidate_documents=documents,
        reference_queries=queries,
        candidate_queries=queries,
    )
    assert result["passed"] is True
    assert result["top1_agreement"] == 16
    with pytest.raises(ValueError, match="32 passage"):
        evaluate_parity(
            reference_documents=documents[:31],
            candidate_documents=documents,
            reference_queries=queries,
            candidate_queries=queries,
        )


def test_mechanism_comparison_treats_oom_as_right_censored() -> None:
    baseline = [
        {
            "valid": True,
            "target_phase_complete": True,
            "target_peak_bytes": 2_000_000_000,
            "initial_device_free_bytes": 4_000_000_000,
            "external_device_used_bytes": 1_000_000_000,
        }
        for _ in range(3)
    ]
    treatment = [dict(run) for run in baseline]
    treatment[1]["target_phase_complete"] = False
    treatment[1]["status"] = "OOM"
    result = evaluate_mechanism_pairs(
        baseline_runs=baseline,
        treatment_runs=treatment,
        target_peak_key="target_peak_bytes",
    )
    assert result["mechanism"] == "INCONCLUSIVE"
    assert result["reason"] == "right_censored_target_phase"


def test_candidate_requires_all_three_successful_parity_runs() -> None:
    runs = [
        {
            "status": "SUCCESS",
            "valid": True,
            "target_phase_complete": True,
            "full_workload_complete": True,
            "correctness_ok": True,
            "encode_wall_ms": 100,
            "other_peak_bytes": 100,
        }
        for _ in range(3)
    ]
    parity = [{"passed": True} for _ in range(3)]
    result = evaluate_production_candidate(
        mechanism={"mechanism": "SUPPORTED", "pair_results": [{}, {}, {}]},
        baseline_runs=runs,
        treatment_runs=runs,
        parity_results=parity,
        other_peak_keys=("other_peak_bytes",),
    )
    assert result["candidate"] == "QUALIFIED"
    parity[2]["passed"] = False
    result = evaluate_production_candidate(
        mechanism={"mechanism": "SUPPORTED"},
        baseline_runs=runs,
        treatment_runs=runs,
        parity_results=parity,
    )
    assert result["candidate"] == "REJECTED_PARITY"


def test_oom_classifier_keeps_independent_flags_and_owner_uncertainty() -> None:
    mib = 1024 * 1024
    metrics = {
        "oom_observed": True,
        "requested_bytes": 400 * mib,
        "oom_time_free_bytes": 100 * mib,
        "allocated_bytes": 7_000 * mib,
        "reserved_bytes": 7_300 * mib,
        "device_used_bytes": 7_400 * mib,
        "device_total_bytes": 8_590 * mib,
        "snapshot_reusable_bytes": 50 * mib,
        "snapshot_largest_reusable_block_bytes": 40 * mib,
        "snapshot_inactive_split_bytes": 1_600 * mib,
        "snapshot_complete": True,
        "snapshot_oom_event": True,
        "snapshot_oom_requested_bytes": 400 * mib,
        "oom_sample_delay_ms": 10,
        "processes": [],
        "process_observation_valid": True,
        "process_owners_observable": False,
        "paired_device_observation_valid": True,
        "gap_present_at_baseline": False,
        "gap_growth_bytes": 0,
        "reserved_change_bytes": 10 * mib,
    }
    result = classify_oom_diagnostics(metrics)
    assert result["status"] == "CLASSIFIED"
    assert "INSUFFICIENT_DEVICE_HEADROOM" in result["flags"]
    assert result["owner_attribution"] == "NOT_OBSERVABLE"

    metrics["snapshot_reusable_bytes"] = 500 * mib
    metrics["snapshot_largest_reusable_block_bytes"] = 200 * mib
    result = classify_oom_diagnostics(metrics)
    assert "ALLOCATOR_FRAGMENTATION_SUPPORTED" in result["flags"]


def test_cell_evidence_serializer_rejects_private_text_and_unknown_fields() -> None:
    safe = {
        "schema": "cell-v1",
        "cell_id": "M0",
        "status": "SUCCESS",
    }
    assert safe_cell_evidence(safe, private_texts=["sensitive phrase"]) is safe
    with pytest.raises(ValueError, match="private text"):
        safe_cell_evidence(
            {**safe, "runtime_versions": {"text": "sensitive phrase"}},
            private_texts=["sensitive phrase"],
        )
    with pytest.raises(ValueError, match="unsafe evidence fields"):
        safe_cell_evidence({**safe, "source_text": "sensitive phrase"})


def test_cache_observer_delegates_call_without_changing_inputs_or_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torch_stub = types.ModuleType("torch")
    torch_stub.is_grad_enabled = lambda: False
    torch_stub.is_inference_mode_enabled = lambda: True

    class DynamicCache:
        def __init__(self, marker: str) -> None:
            self.marker = marker

        def update(self, key: str) -> str:
            return f"updated:{key}"

    class Output:
        past_key_values = object()

    class Qwen3Model:
        training = False

        def forward(self, input_marker: str, *, use_cache: bool) -> Output:
            self.observed_input = input_marker
            return Output()

    transformers = types.ModuleType("transformers")
    transformers.__path__ = []
    cache_utils = types.ModuleType("transformers.cache_utils")
    cache_utils.DynamicCache = DynamicCache
    models = types.ModuleType("transformers.models")
    models.__path__ = []
    qwen3 = types.ModuleType("transformers.models.qwen3")
    qwen3.__path__ = []
    qwen_modeling = types.ModuleType("transformers.models.qwen3.modeling_qwen3")
    qwen_modeling.Qwen3Model = Qwen3Model
    qwen3.modeling_qwen3 = qwen_modeling
    monkeypatch.setitem(sys.modules, "torch", torch_stub)
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "transformers.cache_utils", cache_utils)
    monkeypatch.setitem(sys.modules, "transformers.models", models)
    monkeypatch.setitem(sys.modules, "transformers.models.qwen3", qwen3)
    monkeypatch.setitem(
        sys.modules, "transformers.models.qwen3.modeling_qwen3", qwen_modeling
    )

    observer = CacheActivationObserver()
    observer.install()
    try:
        cache = DynamicCache("unchanged")
        assert cache.marker == "unchanged"
        assert cache.update("key") == "updated:key"
        model = Qwen3Model()
        output = model.forward("private-input-marker", use_cache=True)
        assert model.observed_input == "private-input-marker"
        assert isinstance(output, Output)
    finally:
        observer.restore()
    summary = observer.summary()
    assert summary["dynamic_cache_construction_attempts"] == 1
    assert summary["cache_update_attempts"] == 1
    assert summary["forward_use_cache_values"] == [True]
    assert summary["activation_witness"] is True
    assert "private-input-marker" not in json.dumps(summary)


def test_query_parity_encoding_uses_frozen_query_contract_without_batching() -> None:
    class CudaStub:
        def __init__(self) -> None:
            self.synchronized = False

        def synchronize(self) -> None:
            self.synchronized = True

    class TorchStub:
        cuda = CudaStub()

    class ModelStub:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def encode(self, text: str, **kwargs: object) -> list[float]:
            self.calls.append((text, kwargs))
            return [1.0, 0.0]

    torch_stub = TorchStub()
    model = ModelStub()
    vectors = _encode_queries(
        torch=torch_stub,
        model=model,
        query_texts=[f"query-{index}" for index in range(16)],
        query_text_contract="raw-query-v1",
        query_instruction="Q: ",
    )
    assert len(vectors) == 16
    assert len(model.calls) == 16
    assert model.calls[0][0] == "Q: query-0"
    assert "batch_size" not in model.calls[0][1]
    assert torch_stub.cuda.synchronized is True

    model = ModelStub()
    _encode_queries(
        torch=torch_stub,
        model=model,
        query_texts=[f"query-{index}" for index in range(16)],
        query_text_contract="model-query-prompt-v1",
        query_instruction=None,
    )
    assert model.calls[0][0] == "query-0"
    assert model.calls[0][1]["prompt_name"] == "query"


def test_sdpa_observer_preserves_arguments_and_records_eligibility() -> None:
    class TensorStub:
        shape = (1, 4, 32, 64)
        dtype = "float16"
        device = types.SimpleNamespace(type="cuda")

    class FakeSDPAParams:
        def __init__(self, *args: object) -> None:
            self.args = args

    class BackendsCuda:
        @staticmethod
        def can_use_flash_attention(params: FakeSDPAParams, debug: bool) -> bool:
            assert len(params.args) == 7
            assert debug is False
            return True

        @staticmethod
        def can_use_efficient_attention(params: FakeSDPAParams, debug: bool) -> bool:
            return False

        @staticmethod
        def can_use_cudnn_attention(params: FakeSDPAParams, debug: bool) -> bool:
            return False

    BackendsCuda.SDPAParams = FakeSDPAParams

    query = TensorStub()
    key = TensorStub()
    value = TensorStub()
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def scaled_dot_product_attention(
        query: object,
        key: object,
        value: object,
        attn_mask: object = None,
        dropout_p: float = 0.0,
        is_causal: bool = False,
        scale: float | None = None,
        enable_gqa: bool = False,
    ) -> str:
        calls.append(
            (
                (query, key, value),
                {
                    "attn_mask": attn_mask,
                    "dropout_p": dropout_p,
                    "is_causal": is_causal,
                    "scale": scale,
                    "enable_gqa": enable_gqa,
                },
            )
        )
        return "unchanged-result"

    functional = types.SimpleNamespace(
        scaled_dot_product_attention=scaled_dot_product_attention
    )
    torch_stub = types.SimpleNamespace(
        nn=types.SimpleNamespace(functional=functional),
        backends=types.SimpleNamespace(cuda=BackendsCuda()),
    )
    observer = SDPABackendObserver(torch_stub)
    observer.install()
    try:
        result = functional.scaled_dot_product_attention(
            query, key, value, None, 0.1, True, 0.5, True
        )
    finally:
        observer.restore()

    assert result == "unchanged-result"
    assert calls == [
        (
            (query, key, value),
            {
                "attn_mask": None,
                "dropout_p": 0.1,
                "is_causal": True,
                "scale": 0.5,
                "enable_gqa": True,
            },
        )
    ]
    assert observer.summary()["calls"][0]["eligible_backends"] == {
        "FLASH_ATTENTION": True,
        "EFFICIENT_ATTENTION": False,
        "CUDNN_ATTENTION": False,
    }


def test_cell_spec_rejects_treatments_outside_frozen_single_variable_scope() -> None:
    common = {
        "workload_sha256": "a" * 64,
        "expected_model_revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
        "replicate": 1,
    }
    _validate_cell_spec({**common, "cell_id": "M0"}, "a" * 64)

    m1 = {
        **common,
        "cell_id": "M1",
        "m0_activation_witness": True,
        "disable_cache": True,
    }
    _validate_cell_spec(m1, "a" * 64)
    with pytest.raises(ValueError, match="only use_cache"):
        _validate_cell_spec({**m1, "dtype_mode": "direct_fp16"}, "a" * 64)

    with pytest.raises(ValueError, match="token partitions"):
        _validate_cell_spec(
            {**common, "cell_id": "M4", "cache_state_accepted": True}, "a" * 64
        )


def test_execution_authority_fails_closed_and_claims_are_single_use(
    tmp_path: Path,
) -> None:
    authority_path = tmp_path / "execution.json"
    authority_path.write_text("{}", encoding="utf-8")
    with pytest.raises(PermissionError, match="not authorized"):
        verify_execution_authority(
            authority_path,
            current_commit="candidate",
            cell_id="M0",
        )

    claim = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id="synthetic-test",
        cell_id="M0",
        replicate=1,
        spec_sha256="a" * 64,
    )
    with pytest.raises(PermissionError, match="unfinished"):
        claim_single_cell_process(
            authority_path=authority_path,
            campaign_id="synthetic-test",
            cell_id="M0",
            replicate=2,
            spec_sha256="b" * 64,
        )
    complete_cell_process_claim(claim, duration_seconds=1.0, result_status="SYNTHETIC")
    with pytest.raises(PermissionError, match="already claimed"):
        claim_single_cell_process(
            authority_path=authority_path,
            campaign_id="synthetic-test",
            cell_id="M0",
            replicate=1,
            spec_sha256="a" * 64,
        )


def test_process_claims_gate_treatments_and_cpu_reference_on_m0_results(
    tmp_path: Path,
) -> None:
    authority_path = tmp_path / "campaign" / "execution.json"
    authority_path.parent.mkdir()
    with pytest.raises(PermissionError, match="three completed M0"):
        claim_single_cell_process(
            authority_path=authority_path,
            campaign_id="gated-campaign",
            cell_id="M1",
            replicate=1,
            spec_sha256="b" * 64,
        )

    for replicate, result_status in ((1, "SUCCESS"), (2, "OOM"), (3, "SUCCESS")):
        claim = claim_single_cell_process(
            authority_path=authority_path,
            campaign_id="gated-campaign",
            cell_id="M0",
            replicate=replicate,
            spec_sha256=f"{replicate:064x}",
        )
        complete_cell_process_claim(
            claim, duration_seconds=1.0, result_status=result_status
        )

    cpu_claim = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id="gated-campaign",
        cell_id="CPU_ONNX_REFERENCE",
        replicate=1,
        spec_sha256="c" * 64,
    )
    complete_cell_process_claim(
        cpu_claim, duration_seconds=1.0, result_status="SUCCESS"
    )
    treatment_claim = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id="gated-campaign",
        cell_id="M1",
        replicate=1,
        spec_sha256="d" * 64,
    )
    assert treatment_claim.is_file()
