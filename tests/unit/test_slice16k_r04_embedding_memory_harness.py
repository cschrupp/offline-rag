from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.diag_16k_r04_embedding_memory.campaign import (
    _active_condition,
    _eligible_sdpa_backends,
    _has_authorized_replicates,
    _m3_opening_supported,
    _m4_opening_supported,
    _observed_baseline_sdpa_backend,
    _qualified_treatments,
    authorize_cell_start,
)
from scripts.diag_16k_r04_embedding_memory.cell_executor import (
    _encode_queries,
    _validate_cell_spec,
)
from scripts.diag_16k_r04_embedding_memory.contract import (
    ACCEPTED_DESIGN_SUBJECT,
    EXPECTED_MODEL_REVISION,
    FrozenItem,
    authorized_cell_spec_hashes,
    build_workload_manifest,
    classify_oom_diagnostics,
    enforce_cell_budget,
    evaluate_mechanism_pairs,
    evaluate_parity,
    evaluate_production_candidate,
    greedy_token_partitions,
    safe_exception_summary,
)
from scripts.diag_16k_r04_embedding_memory.evidence import (
    reduce_authorized_cell_evidence,
)
from scripts.diag_16k_r04_embedding_memory.freeze_workload import (
    incident_batch_identity_matches,
    ordered_chunk_ids_digest,
)
from scripts.diag_16k_r04_embedding_memory.runtime import (
    CacheActivationObserver,
    SDPABackendObserver,
    claim_single_cell_process,
    complete_cell_process_claim,
    effective_cell_deadline_seconds,
    failure_classification,
    is_cuda_oom,
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


def test_exact_incident_batch_requires_ordered_historical_identity_witness() -> None:
    ids = [f"chunk_{index:02d}" for index in range(32)]
    digest = ordered_chunk_ids_digest(ids)
    identity = {
        "first_pending_batch_count": 32,
        "ordered_first_pending_chunk_ids_sha256": digest,
    }
    assert incident_batch_identity_matches(
        identity,
        context_matches=True,
        selected_chunk_ids_sha256=digest,
    )
    identity.pop("ordered_first_pending_chunk_ids_sha256")
    assert not incident_batch_identity_matches(
        identity,
        context_matches=True,
        selected_chunk_ids_sha256=digest,
    )


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


def test_effective_deadline_caps_final_cell_by_wall_and_cumulative_remainder() -> None:
    assert (
        effective_cell_deadline_seconds(
            remaining_campaign_wall_seconds=60.25,
            remaining_cumulative_seconds=300.5,
        )
        == 60.25
    )
    assert (
        effective_cell_deadline_seconds(
            remaining_campaign_wall_seconds=300.5,
            remaining_cumulative_seconds=5.75,
        )
        == 5.75
    )


def test_runtime_module_import_remains_lazy_for_torch_and_transformers() -> None:
    script = (
        "import importlib, sys; "
        "modules = ("
        "'campaign', 'cell_executor', 'contract', 'cpu_reference', 'evidence', "
        "'freeze_workload', 'runtime', 'analyze'); "
        "[importlib.import_module('scripts.diag_16k_r04_embedding_memory.' + name) "
        "for name in modules]; "
        "assert 'torch' not in sys.modules; "
        "assert 'transformers' not in sys.modules; "
        "assert 'sentence_transformers' not in sys.modules"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=Path(__file__).resolve().parents[2],
    )


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
            "cell_id": "M0",
            "implementation_subject": "candidate",
            "workload_sha256": "w" * 64,
            "model_revision": EXPECTED_MODEL_REVISION,
            "runtime_versions": {"torch": "2.9.0"},
            "device_identity": {"device_name": "GPU"},
            "effective_controls": {
                "dtype_mode": "post_load_half",
                "disable_cache": False,
                "attention_backend": None,
                "batch_strategy": "fixed32",
                "profiler_characterization": False,
            },
        }
        for _ in range(3)
    ]
    treatment = [dict(run) for run in baseline]
    for run in treatment:
        run["cell_id"] = "M1"
        run["effective_controls"] = {
            **run["effective_controls"],
            "disable_cache": True,
        }
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
        "failure_classification": "NONE",
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


@pytest.mark.parametrize(
    ("baseline_operator", "eligible_by_call", "expected_alternatives"),
    [
        (
            "aten::_scaled_dot_product_attention_math",
            {"MATH": True},
            set(),
        ),
        (
            "aten::_scaled_dot_product_attention_math",
            {"MATH": True, "EFFICIENT_ATTENTION": True},
            {"EFFICIENT_ATTENTION"},
        ),
        (
            "aten::_scaled_dot_product_efficient_attention",
            {"EFFICIENT_ATTENTION": True, "FLASH_ATTENTION": True},
            {"FLASH_ATTENTION"},
        ),
        (
            "aten::_scaled_dot_product_efficient_attention",
            {"EFFICIENT_ATTENTION": True},
            set(),
        ),
        ("aten::scaled_dot_product_attention", {"FLASH_ATTENTION": True}, set()),
    ],
)
def test_m3_uses_observed_baseline_to_derive_only_alternate_backends(
    baseline_operator: str,
    eligible_by_call: dict[str, bool],
    expected_alternatives: set[str],
) -> None:
    completed = [
        {
            "claim": {"cell_id": "M3_PROFILE", "replicate": 1},
            "reduced": {
                "full_workload_complete": True,
                "profiler_operators": [baseline_operator],
                "sdpa_observation": {
                    "calls": [{"eligible_backends": eligible_by_call}]
                },
            },
        }
    ]

    baseline = _observed_baseline_sdpa_backend(completed)
    alternatives = _eligible_sdpa_backends(completed)

    assert alternatives == expected_alternatives
    if baseline == "UNKNOWN":
        assert alternatives == set()
    else:
        assert baseline not in alternatives


def test_m3_eligible_backend_must_be_supported_for_every_observed_call() -> None:
    completed = [
        {
            "claim": {"cell_id": "M3_PROFILE", "replicate": 1},
            "reduced": {
                "full_workload_complete": True,
                "profiler_operators": ["aten::_scaled_dot_product_flash_attention"],
                "sdpa_observation": {
                    "calls": [
                        {
                            "eligible_backends": {
                                "FLASH_ATTENTION": True,
                                "EFFICIENT_ATTENTION": True,
                            }
                        },
                        {
                            "eligible_backends": {
                                "FLASH_ATTENTION": True,
                                "EFFICIENT_ATTENTION": False,
                            }
                        },
                    ]
                },
            },
        }
    ]

    assert _eligible_sdpa_backends(completed) == set()


def test_m3_rejects_the_observed_baseline_as_a_proposed_treatment() -> None:
    completed = [
        {
            "claim": {"cell_id": "M3_PROFILE", "replicate": 1},
            "reduced": {
                "full_workload_complete": True,
                "profiler_operators": ["aten::_scaled_dot_product_efficient_attention"],
                "sdpa_observation": {
                    "calls": [
                        {
                            "eligible_backends": {
                                "EFFICIENT_ATTENTION": True,
                                "FLASH_ATTENTION": True,
                            }
                        }
                    ]
                },
            },
        }
    ]

    baseline = _observed_baseline_sdpa_backend(completed)
    proposed_treatment = "EFFICIENT_ATTENTION"

    assert baseline == proposed_treatment
    assert proposed_treatment not in _eligible_sdpa_backends(completed)


def test_m3_ambiguous_profiled_baseline_fails_closed() -> None:
    completed = [
        {
            "claim": {"cell_id": "M3_PROFILE", "replicate": 1},
            "reduced": {
                "full_workload_complete": True,
                "profiler_operators": [
                    "aten::_scaled_dot_product_efficient_attention",
                    "aten::_scaled_dot_product_flash_attention",
                ],
                "sdpa_observation": {
                    "calls": [{"eligible_backends": {"FLASH_ATTENTION": True}}]
                },
            },
        }
    ]

    assert _observed_baseline_sdpa_backend(completed) == "UNKNOWN"
    assert _eligible_sdpa_backends(completed) == set()


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
        "disable_cache": True,
    }
    _validate_cell_spec(m1, "a" * 64)
    with pytest.raises(ValueError, match="only use_cache"):
        _validate_cell_spec({**m1, "dtype_mode": "direct_fp16"}, "a" * 64)

    with pytest.raises(ValueError, match="token partitions"):
        _validate_cell_spec({**common, "cell_id": "M4"}, "a" * 64)
    with pytest.raises(ValueError, match="unsupported controls"):
        _validate_cell_spec({**m1, "m0_activation_witness": True}, "a" * 64)


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
            replicate=1,
            cell_spec_sha256="a" * 64,
        )
    spec_path = tmp_path / "m0.json"
    spec_path.write_text("{}", encoding="utf-8")
    workload_path = tmp_path / "workload.json"
    workload_path.write_text("{}", encoding="utf-8")
    claim = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id="synthetic-test",
        cell_id="M0",
        replicate=1,
        spec_sha256="a" * 64,
        spec_path=spec_path,
        workload_path=workload_path,
        authority={},
        workload={},
        cell_spec={"cell_id": "M0", "replicate": 1},
        implementation_subject="candidate",
    )
    assert claim.path.is_file()
    assert claim.deadline_seconds > 0
    with pytest.raises(PermissionError, match="unfinished"):
        claim_single_cell_process(
            authority_path=authority_path,
            campaign_id="synthetic-test",
            cell_id="M0",
            replicate=2,
            spec_sha256="b" * 64,
            spec_path=spec_path,
            workload_path=workload_path,
            authority={},
            workload={},
            cell_spec={"cell_id": "M0", "replicate": 2},
            implementation_subject="candidate",
        )


def test_campaign_ignores_operator_prerequisite_booleans_and_requires_raw_evidence(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    claims.mkdir()
    forged = {
        "cell_id": "M1",
        "replicate": 1,
        "m0_activation_witness": True,
        "disable_cache": True,
    }
    with pytest.raises(PermissionError, match="three valid M0"):
        authorize_cell_start(
            claims_dir=claims,
            requested_replicate=1,
            requested_spec=forged,
            authority={"cell_spec_sha256": {}},
            workload={"workload_sha256": "a" * 64},
            implementation_subject="candidate",
        )


def test_campaign_eligibility_is_reduced_from_three_completed_m0_evidence_files(
    tmp_path: Path,
) -> None:
    import hashlib

    from scripts.diag_16k_r04_embedding_memory.campaign import (
        _load_completed_claims,
    )

    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    evidence_rows = []
    spec_hashes: dict[str, dict[str, str]] = {"M0": {}}
    workload: dict[str, object] | None = None
    for replicate in (1, 2, 3):
        cell_dir = tmp_path / f"replicate-{replicate}"
        cell_dir.mkdir()
        evidence_path, spec_path, _authority, cell_workload = _write_valid_raw_cell(
            cell_dir, replicate=replicate
        )
        workload = cell_workload
        spec_bytes = spec_path.read_bytes()
        spec_hashes["M0"][str(replicate)] = hashlib.sha256(spec_bytes).hexdigest()
        evidence_rows.append((evidence_path, spec_path))
    assert workload is not None
    authority = {
        "implementation_subject": "candidate",
        "workload_sha256": workload["workload_sha256"],
        "cell_spec_sha256": spec_hashes,
    }
    for replicate, (evidence_path, spec_path) in enumerate(evidence_rows, start=1):
        reduced = reduce_authorized_cell_evidence(
            evidence_path=evidence_path,
            cell_spec_path=spec_path,
            authority=authority,
            workload=workload,
        )
        claim = {
            "status": "COMPLETED",
            "cell_id": "M0",
            "replicate": replicate,
            "cell_spec_sha256": reduced["cell_spec_sha256"],
            "cell_spec_path": str(spec_path),
            "evidence_path": str(evidence_path),
            "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "evidence_validity": reduced["valid"],
            "gate_facts": reduced["gate_facts"],
            "implementation_subject": "candidate",
            "workload_sha256": workload["workload_sha256"],
            "claimed_at_utc": f"2026-10-29T00:00:0{replicate}+00:00",
        }
        (claims_dir / f"M0-replicate-{replicate}.json").write_text(
            json.dumps(claim), encoding="utf-8"
        )

    completed = _load_completed_claims(
        claims_dir=claims_dir,
        authority=authority,
        workload=workload,
        implementation_subject="candidate",
    )
    assert len(completed) == 3
    authorize_cell_start(
        claims_dir=claims_dir,
        requested_replicate=1,
        requested_spec={"cell_id": "M1", "disable_cache": True},
        authority=authority,
        workload=workload,
        implementation_subject="candidate",
    )

    claim_path = claims_dir / "M0-replicate-2.json"
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    claim["gate_facts"]["cache_activation_witness"] = False
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    with pytest.raises(PermissionError, match="gate facts do not match"):
        authorize_cell_start(
            claims_dir=claims_dir,
            requested_replicate=1,
            requested_spec={"cell_id": "M1", "m0_activation_witness": True},
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )


def test_execution_authority_binds_spec_hash_to_cell_and_replicate(
    tmp_path: Path,
) -> None:
    from scripts.diag_16k_r04_embedding_memory.contract import ACCEPTED_DESIGN_SUBJECT

    authority = {
        "execution_authorized": True,
        "authority": "S16-K-R04-EMBEDDING-MEMORY-SCIENTIFIC-EXECUTION-AUTH-001",
        "allow_model_execution": True,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "implementation_subject": "candidate",
        "allowed_cells": ["M0"],
        "cell_spec_sha256": {"M0": {"1": "a" * 64, "2": "b" * 64, "3": "c" * 64}},
        "human_authorization": "ACCEPTED",
    }
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(authority), encoding="utf-8")
    verified = verify_execution_authority(
        path,
        current_commit="candidate",
        cell_id="M0",
        replicate=1,
        cell_spec_sha256="a" * 64,
    )
    assert verified["implementation_subject"] == "candidate"
    for replicate, digest in ((2, "b" * 64), (3, "c" * 64)):
        verify_execution_authority(
            path,
            current_commit="candidate",
            cell_id="M0",
            replicate=replicate,
            cell_spec_sha256=digest,
        )
    with pytest.raises(PermissionError, match="cell/replicate spec hash"):
        verify_execution_authority(
            path,
            current_commit="candidate",
            cell_id="M0",
            replicate=4,
            cell_spec_sha256="a" * 64,
        )


def test_authorized_cell_spec_hashes_supports_legacy_and_finite_sets() -> None:
    first = "a" * 64
    second = "b" * 64
    legacy = {"cell_spec_sha256": {"M0": {"1": first}}}
    finite = {"cell_spec_sha256": {"M2": {"1": [first, second]}}}

    assert authorized_cell_spec_hashes(legacy, cell_id="M0", replicate=1) == {first}
    assert authorized_cell_spec_hashes(finite, cell_id="M2", replicate=1) == {
        first,
        second,
    }
    assert authorized_cell_spec_hashes(finite, cell_id="M2", replicate=2) == set()


@pytest.mark.parametrize(
    "value",
    [
        [],
        ["a" * 64, "a" * 64],
        ["bad"],
        [123],
        [["a" * 64]],
        {"hash": "a" * 64},
        None,
        "A" * 64,
        "a" * 63,
        "a" * 65,
        "g" * 64,
        True,
    ],
)
def test_authorized_cell_spec_hashes_rejects_malformed_entries(value: object) -> None:
    authority = {"cell_spec_sha256": {"M2": {"1": value}}}
    with pytest.raises((TypeError, ValueError)):
        authorized_cell_spec_hashes(authority, cell_id="M2", replicate=1)


def test_m3_availability_requires_valid_hashes_for_every_replicate() -> None:
    authority = {
        "cell_spec_sha256": {
            "M3_A": {
                "1": ["a" * 64],
                "2": ["b" * 64],
                "3": ["c" * 64],
            }
        }
    }
    assert _has_authorized_replicates(authority, cell_id="M3_A", replicate_count=3)
    invalid_authority = {
        "cell_spec_sha256": {
            **authority["cell_spec_sha256"],
            "M3_B": {"1": []},
        }
    }
    with pytest.raises(ValueError, match="must not be empty"):
        _has_authorized_replicates(invalid_authority, cell_id="M3_B", replicate_count=3)
    assert not _has_authorized_replicates(
        {"cell_spec_sha256": {"M3_B": {"1": ["a" * 64]}}},
        cell_id="M3_B",
        replicate_count=3,
    )


def test_execution_authority_accepts_only_exact_finite_spec_variants(
    tmp_path: Path,
) -> None:
    from scripts.diag_16k_r04_embedding_memory.contract import ACCEPTED_DESIGN_SUBJECT

    first = "a" * 64
    second = "b" * 64
    path = tmp_path / "authority.json"
    path.write_text(
        json.dumps(
            {
                "execution_authorized": True,
                "authority": "S16-K-R04-EMBEDDING-MEMORY-SCIENTIFIC-EXECUTION-AUTH-001",
                "allow_model_execution": True,
                "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
                "implementation_subject": "candidate",
                "allowed_cells": ["M2"],
                "cell_spec_sha256": {"M2": {"1": [first, second]}},
                "human_authorization": "ACCEPTED",
            }
        ),
        encoding="utf-8",
    )

    for digest in (first, second):
        verify_execution_authority(
            path,
            current_commit="candidate",
            cell_id="M2",
            replicate=1,
            cell_spec_sha256=digest,
        )
    with pytest.raises(PermissionError, match="does not match"):
        verify_execution_authority(
            path,
            current_commit="candidate",
            cell_id="M2",
            replicate=1,
            cell_spec_sha256="c" * 64,
        )


def test_evidence_reducer_binds_one_actual_spec_from_finite_allowlist(
    tmp_path: Path,
) -> None:
    import hashlib

    evidence_path, first_spec_path, authority, workload = _write_valid_raw_cell(
        tmp_path
    )
    first_hash = hashlib.sha256(first_spec_path.read_bytes()).hexdigest()
    first_spec = json.loads(first_spec_path.read_text(encoding="utf-8"))
    second_spec = {**first_spec, "dtype_mode": "post_load_half"}
    second_spec_path = tmp_path / "spec-M0-1-explicit-default.json"
    second_spec_path.write_text(
        json.dumps(second_spec, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    second_hash = hashlib.sha256(second_spec_path.read_bytes()).hexdigest()
    authority["cell_spec_sha256"]["M0"]["1"] = [first_hash, second_hash]

    reduced_first = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=first_spec_path,
        authority=authority,
        workload=workload,
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["cell_spec_sha256"] = second_hash
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    reduced_second = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=second_spec_path,
        authority=authority,
        workload=workload,
    )

    assert reduced_first["cell_spec_sha256"] == first_hash
    assert reduced_second["cell_spec_sha256"] == second_hash
    unapproved_spec = {**first_spec, "disable_cache": False}
    unapproved_path = tmp_path / "spec-M0-1-unapproved.json"
    unapproved_path.write_text(
        json.dumps(unapproved_spec, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not bound"):
        reduce_authorized_cell_evidence(
            evidence_path=evidence_path,
            cell_spec_path=unapproved_path,
            authority=authority,
            workload=workload,
        )


def test_pre_authorized_m2_variant_still_requires_campaign_admission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import hashlib

    from scripts.diag_16k_r04_embedding_memory import campaign

    mib = 1024 * 1024
    workload_sha = "w" * 64
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    m1_controls = {**m0_controls, "disable_cache": True}
    completed = [
        *_synthetic_campaign_condition(
            "M0",
            m0_controls,
            target_peak_bytes=2_000 * mib,
            load_peak_bytes=1_500 * mib,
        ),
        *_synthetic_campaign_condition(
            "M1",
            m1_controls,
            target_peak_bytes=1_400 * mib,
            load_peak_bytes=1_500 * mib,
        ),
    ]
    for row in completed:
        row["reduced"]["workload_sha256"] = workload_sha
    monkeypatch.setattr(campaign, "_load_completed_claims", lambda **_kwargs: completed)

    def m2_spec(disable_cache: bool) -> dict[str, object]:
        return {
            "cell_id": "M2",
            "replicate": 1,
            "workload_sha256": workload_sha,
            "expected_model_revision": EXPECTED_MODEL_REVISION,
            "dtype_mode": "direct_fp16",
            "disable_cache": disable_cache,
            "attention_backend": None,
            "batch_strategy": "fixed32",
            "profiler_characterization": False,
        }

    retained = m2_spec(False)
    disabled = m2_spec(True)
    retained_hash = hashlib.sha256(
        json.dumps(retained, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    disabled_hash = hashlib.sha256(
        json.dumps(disabled, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    authority = {
        "execution_authorized": True,
        "authority": "S16-K-R04-EMBEDDING-MEMORY-SCIENTIFIC-EXECUTION-AUTH-001",
        "allow_model_execution": True,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "implementation_subject": "candidate",
        "allowed_cells": ["M2"],
        "cell_spec_sha256": {
            "M2": {"1": [retained_hash, disabled_hash]},
        },
        "human_authorization": "ACCEPTED",
    }
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")

    for spec, digest in ((retained, retained_hash), (disabled, disabled_hash)):
        verify_execution_authority(
            authority_path,
            current_commit="candidate",
            cell_id="M2",
            replicate=1,
            cell_spec_sha256=digest,
        )
        if spec is disabled:
            authorize_cell_start(
                claims_dir=tmp_path / "claims",
                requested_replicate=1,
                requested_spec=spec,
                authority=authority,
                workload={"workload_sha256": workload_sha},
                implementation_subject="candidate",
            )
        else:
            with pytest.raises(
                PermissionError, match="preserve the accepted prior state"
            ):
                authorize_cell_start(
                    claims_dir=tmp_path / "claims",
                    requested_replicate=1,
                    requested_spec=spec,
                    authority=authority,
                    workload={"workload_sha256": workload_sha},
                    implementation_subject="candidate",
                )


def test_sdpa_observer_does_not_introspect_c_bound_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.diag_16k_r04_embedding_memory import runtime

    class OpaqueCallable:
        def __call__(self, *args: object, **kwargs: object) -> str:
            return "delegated"

    class Functional:
        scaled_dot_product_attention = OpaqueCallable()

    torch_stub = types.SimpleNamespace(
        nn=types.SimpleNamespace(functional=Functional()),
        backends=types.SimpleNamespace(cuda=types.SimpleNamespace()),
    )
    monkeypatch.setattr(
        runtime.inspect,
        "signature",
        lambda _callable: (_ for _ in ()).throw(AssertionError("introspection")),
    )
    observer = SDPABackendObserver(torch_stub)
    observer.install()
    try:
        marker = object()
        assert (
            torch_stub.nn.functional.scaled_dot_product_attention(marker) == "delegated"
        )
    finally:
        observer.restore()


def test_installed_torch_sdpa_observer_delegates_cpu_operator() -> None:
    torch = pytest.importorskip("torch")
    query = torch.randn(1, 1, 2, 8, device="cpu")
    key = torch.randn(1, 1, 2, 8, device="cpu")
    value = torch.randn(1, 1, 2, 8, device="cpu")
    expected = torch.nn.functional.scaled_dot_product_attention(query, key, value)
    observer = SDPABackendObserver(torch)
    observer.install()
    try:
        actual = torch.nn.functional.scaled_dot_product_attention(query, key, value)
    finally:
        observer.restore()
    assert torch.equal(actual, expected)
    assert observer.summary()["sdpa_call_count"] == 1


def _write_valid_raw_cell(
    tmp_path: Path,
    *,
    replicate: int = 1,
    cell_id: str = "M0",
) -> tuple[Path, Path, dict[str, object], dict[str, object]]:
    import hashlib

    vectors_path = tmp_path / f"vectors-{cell_id}-{replicate}.json"
    unit = [1.0] + [0.0] * 1023
    vector_payload = json.dumps(
        {"documents": [unit] * 32, "queries": [unit] * 16},
        separators=(",", ":"),
    )
    vectors_path.write_text(vector_payload + "\n", encoding="utf-8")
    controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
        "profiler_characterization": False,
    }
    workload = build_workload_manifest(
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
    workload_sha256 = workload["workload_sha256"]
    ordered_chunk_ids_sha256 = workload["ordered_chunk_ids_sha256"]
    spec = {
        "cell_id": cell_id,
        "replicate": replicate,
        "workload_sha256": workload_sha256,
        "expected_model_revision": EXPECTED_MODEL_REVISION,
    }
    spec_path = tmp_path / f"spec-{cell_id}-{replicate}.json"
    spec_bytes = json.dumps(spec, sort_keys=True).encode()
    spec_path.write_bytes(spec_bytes)
    spec_digest = hashlib.sha256(spec_bytes).hexdigest()
    authority = {
        "implementation_subject": "candidate",
        "workload_sha256": workload_sha256,
        "cell_spec_sha256": {cell_id: {str(replicate): spec_digest}},
    }
    evidence = {
        "schema": "seneca-16k-r04-embedding-memory-cell-v1",
        "design_subject": ACCEPTED_DESIGN_SUBJECT,
        "implementation_subject": "candidate",
        "cell_id": cell_id,
        "replicate": replicate,
        "cell_spec_sha256": spec_digest,
        "effective_controls": controls,
        "workload_sha256": workload_sha256,
        "model_revision": EXPECTED_MODEL_REVISION,
        "runtime_versions": {
            "sentence_transformers": "5.7.0",
            "transformers": "4.57.1",
            "torch": "2.9.0",
            "cuda_build": "12.8",
        },
        "device_facts": {
            "cuda_available": True,
            "device_name": "Synthetic GPU",
            "device_total_bytes": 8_000_000_000,
            "capability": [7, 5],
            "driver_version": "synthetic",
        },
        "stage_snapshots": [
            {
                "stage": "before_model_load",
                "status": "observed",
                "device_free_bytes": 6_000_000_000,
                "device_used_bytes": 2_000_000_000,
                "reserved_bytes": 1_000_000_000,
                "monotonic_seconds": 1.0,
            },
            {
                "stage": "after_post_load_half",
                "status": "observed",
                "allocated_bytes": 1_000_000_000,
                "peak_allocated_bytes": 1_200_000_000,
                "peak_reserved_bytes": 1_300_000_000,
                "monotonic_seconds": 1.5,
            },
            {
                "stage": "before_encode",
                "status": "observed",
                "allocated_bytes": 1_000_000_000,
                "monotonic_seconds": 2.0,
            },
            {
                "stage": "after_encode_success",
                "status": "observed",
                "peak_allocated_bytes": 2_000_000_000,
                "wall_seconds": 1.0,
                "monotonic_seconds": 3.0,
            },
            {
                "stage": "after_query_parity_encode",
                "status": "observed",
            },
        ],
        "device_samples": [],
        "encode_result": {
            "status": "SUCCESS",
            "document_vector_count": 32,
            "query_vector_count": 16,
            "vector_dimension": 1024,
            "ordered_chunk_ids_sha256": ordered_chunk_ids_sha256,
            "vectors_sha256": hashlib.sha256(vector_payload.encode()).hexdigest(),
            "vectors_path": str(vectors_path),
        },
        "cache_observation": {
            "forward_use_cache_values": [True],
            "dynamic_cache_construction_attempts": 1,
            "cache_update_attempts": 1,
            "non_null_cache_returns": 0,
        },
        "model_facts": {"config_states": [{"use_cache": True}]},
        "status": "SUCCESS",
        "failure_classification": "NONE",
    }
    evidence_path = tmp_path / f"cell-{cell_id}-{replicate}.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    return evidence_path, spec_path, authority, workload


def test_accelerator_error_cuda_oom_survives_redaction_and_claim_finalization(
    tmp_path: Path,
) -> None:
    import hashlib

    class AcceleratorError(RuntimeError):
        pass

    private_exception_text = "CUDA error: out of memory while embedding private text"
    failure = AcceleratorError(private_exception_text)
    assert is_cuda_oom(failure)
    assert failure_classification(failure) == "CUDA_OOM"

    evidence_path, spec_path, authority, workload = _write_valid_raw_cell(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence.update(
        {
            "status": "FAILED",
            "failure_classification": failure_classification(failure),
            "exception": safe_exception_summary(failure),
            "profiler_operators": ["aten::_scaled_dot_product_attention_math"],
            "oom_diagnostics": {
                "snapshot_written": False,
                "oom_event_observed": False,
                "classification": {"status": "INCONCLUSIVE"},
            },
        }
    )
    evidence["stage_snapshots"] = [
        stage
        for stage in evidence["stage_snapshots"]
        if stage["stage"] != "after_encode_success"
    ]
    evidence["encode_result"]["status"] = "FAILED"
    safe = safe_cell_evidence(evidence)
    serialized_evidence = json.dumps(safe)
    assert private_exception_text not in serialized_evidence
    assert safe["failure_classification"] == "CUDA_OOM"
    assert safe["exception"]["message"] == "REDACTED"
    evidence_path.write_text(json.dumps(safe, sort_keys=True) + "\n", encoding="utf-8")

    reduced = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    assert reduced["status"] == "OOM"
    assert reduced["profiler_operators"] == ["aten::_scaled_dot_product_attention_math"]
    assert reduced["gate_facts"]["forward_oom_observed"] is True
    assert reduced["valid"] is False
    assert reduced["validity_reasons"]["resource_evidence"] is False

    spec_bytes = spec_path.read_bytes()
    spec_digest = hashlib.sha256(spec_bytes).hexdigest()
    authority["cell_spec_sha256"]["M0"]["1"] = spec_digest
    authority_path = tmp_path / "authority.json"
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    workload_path = tmp_path / "workload.json"
    workload_path.write_text(json.dumps(workload), encoding="utf-8")
    claim = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id="synthetic-accelerator-oom",
        cell_id="M0",
        replicate=1,
        spec_sha256=spec_digest,
        spec_path=spec_path,
        workload_path=workload_path,
        authority=authority,
        workload=workload,
        cell_spec=json.loads(spec_bytes),
        implementation_subject="candidate",
    )
    complete_cell_process_claim(
        claim,
        duration_seconds=0.01,
        result_status="OOM",
        evidence_path=evidence_path,
    )
    finalized = json.loads(claim.path.read_text(encoding="utf-8"))
    assert finalized["status"] == "COMPLETED"
    assert finalized["result_status"] == "OOM"
    assert finalized["evidence_validity"] is False


def test_raw_reducer_marks_forward_oom_only_after_load_and_encode_entry(
    tmp_path: Path,
) -> None:
    evidence_path, spec_path, authority, workload = _write_valid_raw_cell(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["status"] = "FAILED"
    evidence["failure_classification"] = "CUDA_OOM"
    evidence["exception"] = {"type": "AcceleratorError", "message": "REDACTED"}
    evidence["encode_result"]["status"] = "FAILED"
    evidence["stage_snapshots"] = [
        stage
        for stage in evidence["stage_snapshots"]
        if stage["stage"] != "after_encode_success"
    ]
    evidence["oom_diagnostics"] = {
        "snapshot_written": True,
        "oom_event_observed": True,
        "classification": {"status": "INCONCLUSIVE"},
    }
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    reduced_forward_oom = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    assert reduced_forward_oom["status"] == "OOM"
    assert reduced_forward_oom["valid"] is True
    assert reduced_forward_oom["gate_facts"]["forward_oom_observed"] is True

    evidence["stage_snapshots"] = [
        stage
        for stage in evidence["stage_snapshots"]
        if stage["stage"] != "before_encode"
    ]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    reduced_before_encode = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    assert reduced_before_encode["status"] == "OOM"
    assert reduced_before_encode["gate_facts"]["forward_oom_observed"] is False


def test_non_oom_failure_evidence_stops_campaign_progression(tmp_path: Path) -> None:
    import hashlib

    from scripts.diag_16k_r04_embedding_memory.campaign import _load_completed_claims

    evidence_path, spec_path, authority, workload = _write_valid_raw_cell(tmp_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["status"] = "FAILED"
    evidence["failure_classification"] = "NON_OOM_FAILURE"
    evidence["exception"] = {"type": "RuntimeError", "message": "REDACTED"}
    evidence["encode_result"]["status"] = "FAILED"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    reduced = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    assert reduced["status"] == "NON_OOM_FAILURE"
    assert reduced["valid"] is False

    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    claim = {
        "status": "COMPLETED",
        "cell_id": "M0",
        "replicate": 1,
        "implementation_subject": "candidate",
        "workload_sha256": workload["workload_sha256"],
        "evidence_path": str(evidence_path),
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "evidence_validity": False,
    }
    (claims_dir / "M0-replicate-1.json").write_text(json.dumps(claim), encoding="utf-8")
    with pytest.raises(PermissionError, match="invalid prior evidence stops"):
        _load_completed_claims(
            claims_dir=claims_dir,
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )


def _mark_m0_cache_unactivated(rows: list[dict[str, object]]) -> None:
    for row in rows:
        facts = row["reduced"]["gate_facts"]
        facts["cache_config_enabled"] = False
        facts["cache_activation_witness"] = False


def test_raw_cell_reducer_binds_authority_and_derives_cache_witness(
    tmp_path: Path,
) -> None:
    evidence_path, spec_path, authority, workload = _write_valid_raw_cell(tmp_path)
    reduced = reduce_authorized_cell_evidence(
        evidence_path=evidence_path,
        cell_spec_path=spec_path,
        authority=authority,
        workload=workload,
    )
    assert reduced["valid"] is True
    assert reduced["full_workload_complete"] is True
    assert reduced["gate_facts"]["cache_activation_witness"] is True
    tampered_workload = json.loads(json.dumps(workload))
    tampered_workload["ordered_items"][0]["chunk_id"] = "different_chunk"
    with pytest.raises(ValueError, match="item digest"):
        reduce_authorized_cell_evidence(
            evidence_path=evidence_path,
            cell_spec_path=spec_path,
            authority=authority,
            workload=tampered_workload,
        )
    authority["cell_spec_sha256"]["M0"]["1"] = "0" * 64
    with pytest.raises(ValueError, match="not bound"):
        reduce_authorized_cell_evidence(
            evidence_path=evidence_path,
            cell_spec_path=spec_path,
            authority=authority,
            workload=workload,
        )


def test_pair_evaluator_rejects_runtime_or_device_identity_mismatch() -> None:
    baseline = [
        {
            "valid": True,
            "target_phase_complete": True,
            "target_peak_bytes": 2_000_000_000,
            "initial_device_free_bytes": 4_000_000_000,
            "external_device_used_bytes": 1_000_000_000,
            "implementation_subject": "candidate",
            "workload_sha256": "w" * 64,
            "model_revision": EXPECTED_MODEL_REVISION,
            "runtime_versions": {"torch": "2.9.0"},
            "device_identity": {"device_name": "GPU A"},
            "cell_id": "M0",
            "effective_controls": {
                "dtype_mode": "post_load_half",
                "disable_cache": False,
                "attention_backend": None,
                "batch_strategy": "fixed32",
                "profiler_characterization": False,
            },
        }
        for _ in range(3)
    ]
    treatment = [dict(run) for run in baseline]
    for run in treatment:
        run["cell_id"] = "M1"
        run["effective_controls"] = {
            **run["effective_controls"],
            "disable_cache": True,
        }
    treatment[1]["device_identity"] = {"device_name": "GPU B"}
    result = evaluate_mechanism_pairs(
        baseline_runs=baseline,
        treatment_runs=treatment,
        target_peak_key="target_peak_bytes",
    )
    assert result["mechanism"] == "INCONCLUSIVE"
    assert result["reason"] == "campaign_identity_mismatch"


def _synthetic_campaign_condition(
    cell_id: str,
    controls: dict[str, object],
    *,
    target_peak_bytes: int = 2_000_000_000,
    load_peak_bytes: int = 1_500_000_000,
    forward_peaks: list[int | None] | None = None,
    forward_bases: list[int | None] | None = None,
    statuses: list[str] | None = None,
    forward_ooms: list[bool] | None = None,
    token_counts: list[int] | None = None,
    valid: bool = True,
) -> list[dict[str, object]]:
    unit = [1.0] + [0.0] * 1023
    vectors = {"documents": [unit] * 32, "queries": [unit] * 16}
    forward_peaks = forward_peaks or [4_000_000_000] * 3
    forward_bases = forward_bases or [1_000_000_000] * 3
    statuses = statuses or ["SUCCESS"] * 3
    forward_ooms = forward_ooms or [False] * 3
    token_counts = token_counts or [10] * 32
    rows: list[dict[str, object]] = []
    for replicate in (1, 2, 3):
        run_controls = {
            "dtype_mode": "post_load_half",
            "disable_cache": False,
            "attention_backend": None,
            "batch_strategy": "fixed32",
            "profiler_characterization": False,
            **controls,
        }
        is_m1 = cell_id == "M1"
        reduced = {
            "cell_id": cell_id,
            "replicate": replicate,
            "valid": valid,
            "status": statuses[replicate - 1],
            "target_phase_complete": statuses[replicate - 1] == "SUCCESS",
            "load_phase_complete": True,
            "encode_phase_reached": True,
            "forward_phase_complete": statuses[replicate - 1] == "SUCCESS",
            "full_workload_complete": statuses[replicate - 1] == "SUCCESS",
            "correctness_ok": statuses[replicate - 1] == "SUCCESS",
            "forward_peak_bytes": forward_peaks[replicate - 1],
            "forward_base_allocated_bytes": forward_bases[replicate - 1],
            "forward_incremental_allocated_bytes": (
                max(0, forward_peaks[replicate - 1] - forward_bases[replicate - 1])
                if forward_peaks[replicate - 1] is not None
                and forward_bases[replicate - 1] is not None
                else None
            ),
            "target_peak_bytes": target_peak_bytes,
            "load_device_peak_bytes": load_peak_bytes,
            "load_peak_allocated_bytes": 1_000_000_000,
            "load_peak_reserved_bytes": 1_100_000_000,
            "initial_device_free_bytes": 6_000_000_000,
            "external_device_used_bytes": 100_000_000,
            "encode_wall_ms": 100.0,
            "implementation_subject": "candidate",
            "workload_sha256": "w" * 64,
            "model_revision": EXPECTED_MODEL_REVISION,
            "runtime_versions": {"torch": "synthetic"},
            "device_identity": {"device_name": "synthetic-gpu"},
            "effective_controls": run_controls,
            "vectors": vectors if statuses[replicate - 1] == "SUCCESS" else None,
            "token_metrics": {"token_counts": list(token_counts)},
            "gate_facts": {
                "valid": valid,
                "status": statuses[replicate - 1],
                "target_phase_complete": statuses[replicate - 1] == "SUCCESS",
                "load_phase_complete": True,
                "encode_phase_reached": True,
                "forward_phase_complete": statuses[replicate - 1] == "SUCCESS",
                "forward_oom_observed": forward_ooms[replicate - 1],
                "forward_base_allocated_bytes": forward_bases[replicate - 1],
                "forward_incremental_allocated_bytes": (
                    max(0, forward_peaks[replicate - 1] - forward_bases[replicate - 1])
                    if forward_peaks[replicate - 1] is not None
                    and forward_bases[replicate - 1] is not None
                    else None
                ),
                "full_workload_complete": statuses[replicate - 1] == "SUCCESS",
                "correctness_ok": statuses[replicate - 1] == "SUCCESS",
                "cache_config_known": True,
                "cache_config_enabled": not (
                    is_m1 and bool(run_controls["disable_cache"])
                ),
                "cache_activation_witness": not (
                    is_m1 and bool(run_controls["disable_cache"])
                ),
                "effective_controls": run_controls,
                "token_metrics": {"token_counts": list(token_counts)},
            },
        }
        rows.append(
            {
                "claim": {"cell_id": cell_id, "replicate": replicate},
                "reduced": reduced,
            }
        )
    return rows


def test_m3_successful_forward_applicability_uses_incremental_active_state() -> None:
    mib = 1024 * 1024
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    above = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_700 * mib] * 3,
    )
    assert _m3_opening_supported(above)

    below = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_750 * mib] * 3,
    )
    assert not _m3_opening_supported(below)

    one_high_only = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_700 * mib, 3_800 * mib, 3_800 * mib],
    )
    assert not _m3_opening_supported(one_high_only)

    two_of_three = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_700 * mib, 3_700 * mib, 3_800 * mib],
    )
    assert _m3_opening_supported(two_of_three)


def test_m3_oom_applicability_requires_two_forward_ooms_after_encode_entry() -> None:
    controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    two_forward_ooms = _synthetic_campaign_condition(
        "M0",
        controls,
        statuses=["OOM", "OOM", "SUCCESS"],
        forward_ooms=[True, True, False],
        forward_peaks=[None, None, 4_000_000_000],
        forward_bases=[None, None, 1_000_000_000],
    )
    assert _m3_opening_supported(two_forward_ooms)

    one_forward_oom = _synthetic_campaign_condition(
        "M0",
        controls,
        statuses=["OOM", "SUCCESS", "SUCCESS"],
        forward_ooms=[True, False, False],
        forward_peaks=[None, 4_000_000_000, 4_000_000_000],
        forward_bases=[None, 1_000_000_000, 1_000_000_000],
    )
    assert not _m3_opening_supported(one_forward_oom)

    oom_before_encode = _synthetic_campaign_condition(
        "M0",
        controls,
        statuses=["OOM", "SUCCESS", "SUCCESS"],
        forward_ooms=[False, False, False],
        forward_peaks=[None, 4_000_000_000, 4_000_000_000],
        forward_bases=[None, 1_000_000_000, 1_000_000_000],
    )
    assert not _m3_opening_supported(oom_before_encode)

    non_oom_failure = _synthetic_campaign_condition(
        "M0",
        controls,
        statuses=["NON_OOM_FAILURE", "SUCCESS", "SUCCESS"],
        valid=False,
    )
    assert not _m3_opening_supported(non_oom_failure)


def test_m3_uses_active_controls_instead_of_unqualified_m2_measurements() -> None:
    mib = 1024 * 1024
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=1_500 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    m2 = _synthetic_campaign_condition(
        "M2",
        {**m0_controls, "dtype_mode": "direct_fp16"},
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=1_500 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_000 * mib] * 3,
    )
    active = _active_condition([*m0, *m2], through="M2")
    assert active is not None
    active_cell, active_controls, active_runs = active
    assert active_cell == "M0"
    assert active_controls == m0_controls
    assert active_runs == m0
    assert not _m3_opening_supported([*m0, *m2])


def test_active_controls_advance_only_for_supported_qualified_treatments() -> None:
    mib = 1024 * 1024
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=2_000 * mib,
    )
    m1_controls = {**m0_controls, "disable_cache": True}
    m1 = _synthetic_campaign_condition(
        "M1",
        m1_controls,
        target_peak_bytes=1_400 * mib,
        load_peak_bytes=2_000 * mib,
    )
    active_after_m1 = _active_condition([*m0, *m1], through="M1")
    assert active_after_m1 is not None
    assert active_after_m1[0] == "M1"
    assert active_after_m1[1] == m1_controls

    rejected_m1 = _synthetic_campaign_condition(
        "M1",
        m1_controls,
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=2_000 * mib,
    )
    active_after_rejected_m1 = _active_condition([*m0, *rejected_m1], through="M1")
    assert active_after_rejected_m1 is not None
    assert active_after_rejected_m1[0] == "M0"
    assert active_after_rejected_m1[1] == m0_controls

    m2_controls = {**m1_controls, "dtype_mode": "direct_fp16"}
    m2 = _synthetic_campaign_condition(
        "M2",
        m2_controls,
        target_peak_bytes=1_400 * mib,
        load_peak_bytes=1_400 * mib,
    )
    active_after_m2 = _active_condition([*m0, *m1, *m2], through="M2")
    assert active_after_m2 is not None
    assert active_after_m2[0] == "M2"
    assert active_after_m2[1] == m2_controls

    rejected_m2 = _synthetic_campaign_condition(
        "M2",
        m2_controls,
        target_peak_bytes=1_400 * mib,
        load_peak_bytes=2_000 * mib,
    )
    active_after_rejected_m2 = _active_condition([*m0, *m1, *rejected_m2], through="M2")
    assert active_after_rejected_m2 is not None
    assert active_after_rejected_m2[0] == "M1"
    assert active_after_rejected_m2[1] == m1_controls


def test_multiple_qualified_m3_alternatives_fail_closed() -> None:
    mib = 1024 * 1024
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    m0 = _synthetic_campaign_condition(
        "M0", m0_controls, target_peak_bytes=2_000 * mib, load_peak_bytes=2_000 * mib
    )
    m1_controls = {**m0_controls, "disable_cache": True}
    m1 = _synthetic_campaign_condition(
        "M1", m1_controls, target_peak_bytes=1_500 * mib, load_peak_bytes=2_000 * mib
    )
    m2_controls = {**m1_controls, "dtype_mode": "direct_fp16"}
    m2 = _synthetic_campaign_condition(
        "M2", m2_controls, target_peak_bytes=1_400 * mib, load_peak_bytes=1_500 * mib
    )
    m3_a = _synthetic_campaign_condition(
        "M3_A",
        {**m2_controls, "attention_backend": "SDPA_A"},
        target_peak_bytes=1_000 * mib,
    )
    m3_b = _synthetic_campaign_condition(
        "M3_B",
        {**m2_controls, "attention_backend": "SDPA_B"},
        target_peak_bytes=1_000 * mib,
    )
    with pytest.raises(PermissionError, match="multiple qualified M3 alternatives"):
        _qualified_treatments([*m0, *m1, *m2, *m3_a, *m3_b], through="M3")


def test_m5_requires_a_qualified_candidate_and_resolved_applicable_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.diag_16k_r04_embedding_memory import campaign

    mib = 1024 * 1024
    m0_controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=2_000 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    m1_controls = {**m0_controls, "disable_cache": True}
    m1 = _synthetic_campaign_condition(
        "M1",
        m1_controls,
        target_peak_bytes=1_400 * mib,
        load_peak_bytes=2_000 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    m2_controls = {**m1_controls, "dtype_mode": "direct_fp16"}
    m2 = _synthetic_campaign_condition(
        "M2",
        m2_controls,
        target_peak_bytes=1_400 * mib,
        load_peak_bytes=2_000 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    completed = [*m0, *m1, *m2]
    monkeypatch.setattr(campaign, "_load_completed_claims", lambda **_kwargs: completed)
    authority = {"cell_spec_sha256": {}}
    workload = {"workload_sha256": "w" * 64}
    exact_m5 = {
        "cell_id": "M5",
        "replicate": 1,
        "selected_candidate_settings": m1_controls,
    }
    authorize_cell_start(
        claims_dir=Path("/unused"),
        requested_replicate=1,
        requested_spec=exact_m5,
        authority=authority,
        workload=workload,
        implementation_subject="candidate",
    )
    with pytest.raises(PermissionError, match="final evidence-derived ACTIVE_CONTROLS"):
        authorize_cell_start(
            claims_dir=Path("/unused"),
            requested_replicate=1,
            requested_spec={
                **exact_m5,
                "selected_candidate_settings": m0_controls,
            },
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )

    no_qualified_m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    _mark_m0_cache_unactivated(no_qualified_m0)
    no_qualified_m2 = _synthetic_campaign_condition(
        "M2",
        {**m0_controls, "dtype_mode": "direct_fp16"},
        target_peak_bytes=2_000 * mib,
        load_peak_bytes=2_000 * mib,
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    completed[:] = [*no_qualified_m0, *no_qualified_m2]
    with pytest.raises(PermissionError, match="without a qualified treatment"):
        authorize_cell_start(
            claims_dir=Path("/unused"),
            requested_replicate=1,
            requested_spec={
                "cell_id": "M5",
                "replicate": 1,
                "selected_candidate_settings": m0_controls,
            },
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )

    active_oom_m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        statuses=["OOM", "OOM", "SUCCESS"],
        forward_ooms=[True, True, False],
        forward_peaks=[None, None, 4_000 * mib],
        forward_bases=[None, None, 3_000 * mib],
    )
    _mark_m0_cache_unactivated(active_oom_m0)
    completed[:] = [*active_oom_m0, *no_qualified_m2]
    with pytest.raises(PermissionError, match="opened M3 path to be resolved"):
        authorize_cell_start(
            claims_dir=Path("/unused"),
            requested_replicate=1,
            requested_spec={
                "cell_id": "M5",
                "replicate": 1,
                "selected_candidate_settings": m0_controls,
            },
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )

    m4_applicable_m0 = _synthetic_campaign_condition(
        "M0",
        m0_controls,
        token_counts=[10] * 31 + [100],
        forward_peaks=[4_000 * mib] * 3,
        forward_bases=[3_900 * mib] * 3,
    )
    _mark_m0_cache_unactivated(m4_applicable_m0)
    completed[:] = [*m4_applicable_m0, *no_qualified_m2]
    with pytest.raises(PermissionError, match="opened M4 path to be resolved"):
        authorize_cell_start(
            claims_dir=Path("/unused"),
            requested_replicate=1,
            requested_spec={
                "cell_id": "M5",
                "replicate": 1,
                "selected_candidate_settings": m0_controls,
            },
            authority=authority,
            workload=workload,
            implementation_subject="candidate",
        )


def test_m4_uses_frozen_token_padding_savings_proxy() -> None:
    controls = {
        "dtype_mode": "post_load_half",
        "disable_cache": False,
        "attention_backend": None,
        "batch_strategy": "fixed32",
    }
    substantial_shape = [10] * 31 + [100]
    opens = _synthetic_campaign_condition(
        "M0", controls, token_counts=substantial_shape
    )
    assert _m4_opening_supported(opens)
    assert "mechanism" not in opens[0]["reduced"]

    mismatched = _synthetic_campaign_condition(
        "M0", controls, token_counts=substantial_shape
    )
    mismatched[2]["reduced"]["token_metrics"]["token_counts"][0] = 11
    mismatched[2]["reduced"]["gate_facts"]["token_metrics"]["token_counts"][0] = 11
    assert not _m4_opening_supported(mismatched)

    single_partition = _synthetic_campaign_condition(
        "M0", controls, token_counts=[10] * 32
    )
    assert not _m4_opening_supported(single_partition)

    below_five_percent = _synthetic_campaign_condition(
        "M0", controls, token_counts=[100] * 31 + [101]
    )
    assert not _m4_opening_supported(below_five_percent)

    oversized = _synthetic_campaign_condition(
        "M0", controls, token_counts=[10] * 31 + [1_000]
    )
    assert not _m4_opening_supported(oversized)
