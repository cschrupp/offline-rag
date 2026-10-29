"""One-cell R04 executor, protected by a separate future execution authority.

This implementation is intentionally inert until a future authority JSON binds
the exact committed implementation subject, workload, cell and cell-spec hash.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import signal
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

if __package__:
    from .contract import (
        ACCEPTED_DESIGN_SUBJECT,
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_REVISION,
        MIB,
        MODEL_QUERY_PROMPT_V1,
        classify_oom_diagnostics,
        greedy_token_partitions,
        safe_exception_summary,
    )
    from .runtime import (
        CacheActivationObserver,
        DeviceSampler,
        SDPABackendObserver,
        allocator_history,
        claim_single_cell_process,
        complete_cell_process_claim,
        cuda_stage_snapshot,
        failure_classification,
        is_cuda_oom,
        model_runtime_facts,
        parse_requested_allocation_bytes,
        require_local_untracked_path,
        reset_stage_peaks,
        safe_cell_evidence,
        verify_execution_authority,
    )
else:
    from contract import (
        ACCEPTED_DESIGN_SUBJECT,
        EXPECTED_BATCH_SIZE,
        EXPECTED_MODEL_REVISION,
        MIB,
        MODEL_QUERY_PROMPT_V1,
        classify_oom_diagnostics,
        greedy_token_partitions,
        safe_exception_summary,
    )
    from runtime import (
        CacheActivationObserver,
        DeviceSampler,
        SDPABackendObserver,
        allocator_history,
        claim_single_cell_process,
        complete_cell_process_claim,
        cuda_stage_snapshot,
        failure_classification,
        is_cuda_oom,
        model_runtime_facts,
        parse_requested_allocation_bytes,
        require_local_untracked_path,
        reset_stage_peaks,
        safe_cell_evidence,
        verify_execution_authority,
    )


class CellDeadlineExceeded(TimeoutError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _current_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _alarm_handler(_signum: int, _frame: Any) -> None:
    raise CellDeadlineExceeded("cell deadline exceeded")


def _validate_cell_spec(spec: dict[str, Any], workload_sha256: str) -> None:
    allowed = {
        "cell_id",
        "replicate",
        "workload_sha256",
        "expected_model_revision",
        "dtype_mode",
        "disable_cache",
        "attention_backend",
        "batch_strategy",
        "profiler_characterization",
        "selected_candidate_settings",
    }
    if set(spec) - allowed:
        raise ValueError("cell spec contains unsupported controls")
    if spec.get("workload_sha256") != workload_sha256:
        raise ValueError("cell spec workload digest mismatch")
    if spec.get("expected_model_revision") != EXPECTED_MODEL_REVISION:
        raise ValueError("cell spec model revision mismatch")
    if spec.get("cell_id") not in {
        "M0",
        "M1",
        "M2",
        "M3_PROFILE",
        "M3_A",
        "M3_B",
        "M4",
        "M5",
        "CPU_ONNX_REFERENCE",
    }:
        raise ValueError("unknown cell")
    if spec.get("cell_id") == "CPU_ONNX_REFERENCE":
        raise ValueError("CPU ONNX reference requires its separate future executor")
    dtype_mode = spec.get("dtype_mode", "post_load_half")
    if dtype_mode not in {"post_load_half", "direct_fp16"}:
        raise ValueError("unsupported dtype treatment")
    batch_strategy = spec.get("batch_strategy", "fixed32")
    if batch_strategy not in {"fixed32", "m4_partitions"}:
        raise ValueError("unsupported batch treatment")
    attention_backend = spec.get("attention_backend")
    allowed_backends = {
        None,
        "FLASH_ATTENTION",
        "EFFICIENT_ATTENTION",
        "CUDNN_ATTENTION",
        "MATH",
    }
    if attention_backend not in allowed_backends:
        raise ValueError("unsupported SDPA backend")
    disable_cache = spec.get("disable_cache", False)
    if not isinstance(disable_cache, bool):
        raise TypeError("disable_cache must be boolean")
    profiler_characterization = spec.get("profiler_characterization", False)
    if not isinstance(profiler_characterization, bool):
        raise TypeError("profiler_characterization must be boolean")
    replicate = spec.get("replicate")
    if not isinstance(replicate, int) or isinstance(replicate, bool):
        raise TypeError("replicate must be an integer")
    if not 1 <= replicate <= 3:
        raise ValueError("replicate must be in the frozen 1..3 range")
    cell_id = spec["cell_id"]
    if cell_id == "M1" and (
        dtype_mode != "post_load_half"
        or attention_backend is not None
        or batch_strategy != "fixed32"
        or disable_cache is not True
    ):
        raise ValueError("M1 may change only use_cache")
    if cell_id == "M2" and (
        dtype_mode != "direct_fp16"
        or attention_backend is not None
        or batch_strategy != "fixed32"
    ):
        raise ValueError("M2 may change only model materialization dtype")
    if cell_id in {"M3_A", "M3_B"} and not attention_backend:
        raise ValueError("M3 treatment requires one eligible native SDPA backend")
    if cell_id in {"M3_PROFILE", "M3_A", "M3_B"} and batch_strategy != "fixed32":
        raise ValueError("M3 cells must preserve the fixed batch")
    if cell_id == "M4" and batch_strategy != "m4_partitions":
        raise ValueError("M4 must use the frozen token partitions")
    if (
        spec["cell_id"] == "M3_PROFILE"
        and spec.get("profiler_characterization") is not True
    ):
        raise ValueError("M3_PROFILE must perform its one profiler characterization")
    if cell_id == "M0" and any(
        (
            disable_cache,
            attention_backend is not None,
            batch_strategy != "fixed32",
            dtype_mode != "post_load_half",
        )
    ):
        raise ValueError("M0 must preserve the current baseline path")
    selected = spec.get("selected_candidate_settings")
    if selected is not None:
        if spec["cell_id"] != "M5" or not isinstance(selected, dict):
            raise ValueError("selected candidate settings are valid only for M5")
        if set(selected) - {
            "dtype_mode",
            "disable_cache",
            "attention_backend",
            "batch_strategy",
        }:
            raise ValueError("M5 candidate settings contain unsupported changes")
        if set(selected) != {
            "dtype_mode",
            "disable_cache",
            "attention_backend",
            "batch_strategy",
        }:
            raise ValueError("M5 candidate settings must freeze all treatment controls")
        if selected.get("dtype_mode") not in {"post_load_half", "direct_fp16"}:
            raise ValueError("M5 selected dtype is unsupported")
        if not isinstance(selected.get("disable_cache"), bool):
            raise ValueError("M5 selected cache state must be boolean")
        if selected.get("attention_backend") not in allowed_backends:
            raise ValueError("M5 selected SDPA backend is unsupported")
        if selected.get("batch_strategy") not in {"fixed32", "m4_partitions"}:
            raise ValueError("M5 selected batch strategy is unsupported")


def _model_config_kwargs(spec: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    model_kwargs: dict[str, Any] = {
        "local_files_only": True,
        "trust_remote_code": False,
    }
    config_kwargs: dict[str, Any] = {}
    if spec.get("dtype_mode") == "direct_fp16":
        import torch

        model_kwargs["torch_dtype"] = torch.float16
    if spec.get("disable_cache") is True:
        config_kwargs["use_cache"] = False
    return model_kwargs, config_kwargs


def _effective_cell_spec(spec: dict[str, Any]) -> dict[str, Any]:
    effective = dict(spec)
    if spec["cell_id"] == "M5":
        effective.update(spec.get("selected_candidate_settings") or {})
    return effective


def _measure_token_metrics(
    tokenizer: Any, texts: list[str], max_length: int
) -> dict[str, Any]:
    counts: list[int] = []
    for text in texts:
        encoded = tokenizer(
            text,
            add_special_tokens=True,
            truncation=True,
            max_length=max_length,
            padding=False,
            return_attention_mask=False,
            return_token_type_ids=False,
        )
        ids = encoded.get("input_ids")
        if ids is None:
            raise RuntimeError("tokenizer did not return input_ids")
        counts.append(len(ids))
        del encoded, ids
    ordered = sorted(counts)
    p95_index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    maximum = ordered[-1]
    padded = len(ordered) * maximum
    return {
        "item_count": len(counts),
        "token_counts": counts,
        "sum_tokens": sum(counts),
        "max_sequence_length": maximum,
        "p95_sequence_length": ordered[p95_index],
        "padded_tokens_batch32": padded,
        "padding_tokens_batch32": padded - sum(counts),
        "padding_fraction_batch32": (padded - sum(counts)) / padded if padded else 0.0,
    }


def _gpu_sample_near(
    samples: list[dict[str, Any]], monotonic_seconds: float | None
) -> dict[str, Any] | None:
    if monotonic_seconds is None:
        return None
    candidates = [
        sample
        for sample in samples
        if sample.get("status") == "observed"
        and sample.get("monotonic_seconds") is not None
    ]
    if not candidates:
        return None
    nearest = min(
        candidates,
        key=lambda sample: abs(sample["monotonic_seconds"] - monotonic_seconds),
    )
    if abs(nearest["monotonic_seconds"] - monotonic_seconds) > 0.25:
        return None
    return nearest


def _oom_classification(
    *,
    history: dict[str, Any],
    oom_sample: dict[str, Any] | None,
    device_samples: list[dict[str, Any]],
    baseline_stage: dict[str, Any] | None,
) -> dict[str, Any]:
    if oom_sample is None:
        return {
            "status": "NOT_APPLICABLE",
            "flags": [],
            "missing_metrics": [],
        }
    oom_gpu = _gpu_sample_near(device_samples, oom_sample.get("monotonic_seconds"))
    baseline_gpu = _gpu_sample_near(
        device_samples,
        baseline_stage.get("monotonic_seconds") if baseline_stage else None,
    )
    oom_gpu_row = (oom_gpu or {}).get("gpus", [{}])
    baseline_gpu_row = (baseline_gpu or {}).get("gpus", [{}])
    oom_gpu_row = oom_gpu_row[0] if oom_gpu_row else {}
    baseline_gpu_row = baseline_gpu_row[0] if baseline_gpu_row else {}

    def mib_to_bytes(value: Any) -> int | None:
        return int(value) * MIB if isinstance(value, int) else None

    oom_used = oom_sample.get("device_used_bytes")
    if oom_used is None:
        oom_used = mib_to_bytes(oom_gpu_row.get("used_mib"))
    baseline_used = mib_to_bytes(baseline_gpu_row.get("used_mib"))
    total = oom_sample.get("device_total_bytes") or mib_to_bytes(
        oom_gpu_row.get("total_mib")
    )
    oom_reserved = oom_sample.get("reserved_bytes")
    baseline_reserved = baseline_stage.get("reserved_bytes") if baseline_stage else None
    oom_gap = (
        max(0, int(oom_used) - int(oom_reserved))
        if isinstance(oom_used, int) and isinstance(oom_reserved, int)
        else None
    )
    baseline_gap = (
        max(0, int(baseline_used) - int(baseline_reserved))
        if isinstance(baseline_used, int) and isinstance(baseline_reserved, int)
        else None
    )
    gap_threshold = (
        max(512 * MIB, int(0.10 * total)) if isinstance(total, int) else 512 * MIB
    )
    processes = (oom_gpu or {}).get("processes")
    metrics = {
        "oom_observed": True,
        "requested_bytes": history.get("requested_allocation_bytes"),
        "oom_time_free_bytes": oom_sample.get("device_free_bytes"),
        "allocated_bytes": oom_sample.get("allocated_bytes"),
        "reserved_bytes": oom_reserved,
        "device_used_bytes": oom_used,
        "device_total_bytes": total,
        "snapshot_reusable_bytes": history.get("snapshot_reusable_bytes"),
        "snapshot_largest_reusable_block_bytes": history.get(
            "snapshot_largest_reusable_block_bytes"
        ),
        "snapshot_inactive_split_bytes": history.get("inactive_split_bytes"),
        "snapshot_complete": history.get("snapshot_written") is True,
        "snapshot_oom_event": history.get("oom_event_observed") is True,
        "snapshot_oom_requested_bytes": history.get("snapshot_oom_requested_bytes"),
        "oom_sample_delay_ms": oom_sample.get("delay_ms_from_catch"),
        "processes": processes,
        "paired_device_observation_valid": oom_gpu is not None
        and baseline_gpu is not None
        and bool(oom_gpu_row)
        and bool(baseline_gpu_row),
        "process_observation_valid": bool(
            oom_gpu and oom_gpu.get("processes_status") == "observed"
        ),
        "process_owners_observable": bool(
            oom_gpu and oom_gpu.get("process_owners_observable") is True
        ),
        "gap_present_at_baseline": (
            isinstance(baseline_gap, int) and baseline_gap >= gap_threshold
        ),
        "gap_growth_bytes": (
            max(0, int(oom_gap) - int(baseline_gap))
            if isinstance(oom_gap, int) and isinstance(baseline_gap, int)
            else None
        ),
        "reserved_change_bytes": (
            abs(int(oom_reserved) - int(baseline_reserved))
            if isinstance(oom_reserved, int) and isinstance(baseline_reserved, int)
            else None
        ),
    }
    return classify_oom_diagnostics(metrics)


def _encode(
    *,
    torch: Any,
    model: Any,
    texts: list[str],
    spec: dict[str, Any],
    workload: dict[str, Any],
) -> tuple[list[list[float]], list[str]]:
    profiler = None
    if spec.get("profiler_characterization"):
        profiler = torch.profiler.profile(
            activities=[
                torch.profiler.ProfilerActivity.CPU,
                torch.profiler.ProfilerActivity.CUDA,
            ],
            record_shapes=False,
            profile_memory=False,
            with_stack=False,
        )
    attention_context = nullcontext()
    backend_name = spec.get("attention_backend")
    if backend_name:
        from torch.nn.attention import SDPBackend, sdpa_kernel

        attention_context = sdpa_kernel(backends=[getattr(SDPBackend, backend_name)])

    partitions: list[list[int]]
    if spec.get("batch_strategy", "fixed32") == "m4_partitions":
        counts = [item["qwen_token_count"] for item in workload["ordered_items"]]
        result = greedy_token_partitions(counts)
        if result is None:
            raise ValueError("M4 is not applicable: one sequence exceeds token budget")
        partitions = result
    else:
        partitions = [list(range(EXPECTED_BATCH_SIZE))]

    vectors_by_index: dict[int, list[float]] = {}
    with attention_context:
        profile_context = profiler if profiler is not None else nullcontext()
        with profile_context:
            for partition in partitions:
                batch = [texts[index] for index in partition]
                encoded = model.encode(
                    batch,
                    batch_size=len(batch)
                    if spec.get("batch_strategy") == "m4_partitions"
                    else EXPECTED_BATCH_SIZE,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                for index, vector in zip(partition, encoded, strict=True):
                    vectors_by_index[index] = [float(value) for value in vector]
                del encoded, batch
    torch.cuda.synchronize()
    vectors = [vectors_by_index[index] for index in range(EXPECTED_BATCH_SIZE)]
    operators: list[str] = []
    if profiler is not None:
        operators = sorted({str(event.key) for event in profiler.key_averages()})
    return vectors, operators


def _encode_queries(
    *,
    torch: Any,
    model: Any,
    query_texts: list[str],
    query_text_contract: str,
    query_instruction: str | None,
) -> list[list[float]]:
    if len(query_texts) != 16:
        raise ValueError("parity requires exactly 16 frozen query texts")
    options: dict[str, Any] = {}
    if query_text_contract == MODEL_QUERY_PROMPT_V1:
        options["prompt_name"] = "query"
    vectors: list[list[float]] = []
    for text in query_texts:
        payload = text
        if query_text_contract != MODEL_QUERY_PROMPT_V1 and query_instruction:
            payload = f"{query_instruction}{text}"
        vector = model.encode(
            payload,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
            **options,
        )
        vectors.append([float(value) for value in vector])
    torch.cuda.synchronize()
    return vectors


def run_cell(
    *,
    authority_path: Path,
    cell_spec_path: Path,
    workload_path: Path,
    output_path: Path,
    vector_output_path: Path,
    snapshot_path: Path,
    chunk_manifest_path: Path,
    corpus_manifest_path: Path,
    chunks_root: Path,
    embeddings_root: Path,
    incident_identity_path: Path | None,
    source_document_id: str,
    source_sha256: str,
    settings_path: Path | None = None,
    model_dir_arg: Path | None = None,
) -> dict[str, Any]:
    """Run exactly one authorized cell in this fresh process."""
    current_commit = _current_commit()
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    spec = json.loads(cell_spec_path.read_text(encoding="utf-8"))
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    _validate_cell_spec(spec, str(workload.get("workload_sha256", "")))
    spec_sha = _sha256_file(cell_spec_path)
    authorized = verify_execution_authority(
        authority_path,
        current_commit=current_commit,
        cell_id=str(spec["cell_id"]),
        replicate=int(spec["replicate"]),
        cell_spec_sha256=spec_sha,
    )
    if authority.get("workload_sha256") != workload.get("workload_sha256"):
        raise PermissionError("execution authority does not bind this workload")
    output_paths = [
        require_local_untracked_path(path, repo_root=ROOT)
        for path in (output_path, vector_output_path, snapshot_path)
    ]
    if len(set(output_paths)) != len(output_paths):
        raise ValueError("cell evidence, vectors and snapshot paths must be distinct")
    if any(path.exists() for path in output_paths):
        raise FileExistsError("cell output path already exists; retries are forbidden")

    # Execution authority is checked before importing torch/Transformers.
    from offline_rag.config.loader import load_settings
    from offline_rag.dense.provision import resolve_embedding_model_dir

    if __package__:
        from .freeze_workload import reconstruct_workload_with_texts
    else:
        from freeze_workload import reconstruct_workload_with_texts

    settings = load_settings(yaml_paths=[settings_path] if settings_path else None)
    incident_identity = (
        json.loads(incident_identity_path.read_text(encoding="utf-8"))
        if incident_identity_path
        else None
    )
    model_dir = resolve_embedding_model_dir(
        embedding_artifacts_root=settings.paths.embedding_artifacts,
        model_path=model_dir_arg,
    )
    reconstructed, texts, query_texts = reconstruct_workload_with_texts(
        chunk_manifest_path=chunk_manifest_path,
        corpus_manifest_path=corpus_manifest_path,
        chunks_root=chunks_root,
        embeddings_root=embeddings_root,
        model_dir=model_dir,
        settings=settings,
        source_document_id=source_document_id,
        expected_source_sha256=source_sha256,
        incident_identity=incident_identity,
    )
    if reconstructed["workload_sha256"] != workload["workload_sha256"]:
        raise ValueError("reconstructed workload does not match frozen manifest")
    if len(texts) != EXPECTED_BATCH_SIZE:
        raise ValueError("reconstructed private text count mismatch")
    claim_path = claim_single_cell_process(
        authority_path=authority_path,
        campaign_id=str(authority.get("campaign_id", "")),
        cell_id=str(spec["cell_id"]),
        replicate=int(spec["replicate"]),
        spec_sha256=spec_sha,
        spec_path=cell_spec_path,
        workload_path=workload_path,
        authority=authority,
        workload=workload,
        cell_spec=spec,
        implementation_subject=current_commit,
    )
    effective_spec = _effective_cell_spec(spec)

    started = time.monotonic()
    signal.signal(signal.SIGALRM, _alarm_handler)
    remaining_deadline = claim_path.deadline_seconds - (
        time.monotonic() - claim_path.claimed_monotonic
    )
    if remaining_deadline <= 0:
        raise CellDeadlineExceeded("campaign deadline elapsed before runtime start")
    signal.setitimer(signal.ITIMER_REAL, remaining_deadline)
    from importlib.metadata import version

    import torch
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer

    sampler = DeviceSampler(interval_seconds=0.1)
    stages: list[dict[str, Any]] = []
    cache_observer = CacheActivationObserver()
    sdpa_observer = SDPABackendObserver(torch)
    history_state: dict[str, Any] = {}
    profiler_operators: list[str] = []
    vectors: list[list[float]] | None = None
    query_vectors: list[list[float]] | None = None
    oom_sample: dict[str, Any] | None = None
    requested_bytes: int | None = None
    failure: Exception | None = None
    token_metrics: dict[str, Any] = {}
    runtime_versions = {
        "sentence_transformers": version("sentence-transformers"),
        "transformers": version("transformers"),
        "torch": str(torch.__version__),
        "cuda_build": getattr(torch.version, "cuda", None),
    }
    device_facts: dict[str, Any] = {"cuda_available": bool(torch.cuda.is_available())}
    if not device_facts["cuda_available"]:
        raise RuntimeError("authorized CUDA cell has no available CUDA device")
    properties = torch.cuda.get_device_properties(0)
    device_facts.update(
        {
            "device_name": str(properties.name),
            "device_total_bytes": int(properties.total_memory),
            "capability": list(torch.cuda.get_device_capability(0)),
        }
    )
    reset_stage_peaks(torch)
    stages.append(cuda_stage_snapshot(torch, stage="before_model_load"))
    sampler.start()
    model = None
    try:
        try:
            with allocator_history(torch, snapshot_path=snapshot_path) as history_state:
                try:
                    cache_observer.install()
                    if effective_spec.get("profiler_characterization") is True:
                        sdpa_observer.install()
                    model_kwargs, config_kwargs = _model_config_kwargs(effective_spec)
                    load_started = time.monotonic()
                    model = SentenceTransformer(
                        str(model_dir),
                        device="cuda",
                        model_kwargs=model_kwargs,
                        config_kwargs=config_kwargs,
                        local_files_only=True,
                    )
                    if effective_spec.get("disable_cache") is True:
                        config_states = model_runtime_facts(model)["config_states"]
                        cache_values = [
                            state.get("use_cache")
                            for state in config_states
                            if "use_cache" in state
                        ]
                        if not cache_values or any(
                            value is not False for value in cache_values
                        ):
                            raise RuntimeError(
                                "M1 cache disable was not reflected in model configs"
                            )
                    stages.append(
                        {
                            **cuda_stage_snapshot(torch, stage="after_st_construction"),
                            "wall_seconds": time.monotonic() - load_started,
                        }
                    )
                    if (
                        effective_spec.get("dtype_mode", "post_load_half")
                        == "post_load_half"
                    ):
                        reset_stage_peaks(torch)
                        conversion_started = time.monotonic()
                        model.half()
                        torch.cuda.synchronize()
                        stages.append(
                            {
                                **cuda_stage_snapshot(
                                    torch, stage="after_post_load_half"
                                ),
                                "wall_seconds": time.monotonic() - conversion_started,
                            }
                        )
                    model.eval()
                    qwen_config = json.loads(
                        (model_dir / "config.json").read_text(encoding="utf-8")
                    )
                    tokenizer = AutoTokenizer.from_pretrained(
                        str(model_dir), local_files_only=True, trust_remote_code=False
                    )
                    token_metrics = _measure_token_metrics(
                        tokenizer, texts, int(qwen_config["max_position_embeddings"])
                    )
                    frozen_counts = [
                        item["qwen_token_count"] for item in workload["ordered_items"]
                    ]
                    if token_metrics["token_counts"] != frozen_counts:
                        raise ValueError("Qwen tokenizer workload counts changed")
                    del tokenizer
                    reset_stage_peaks(torch)
                    stages.append(cuda_stage_snapshot(torch, stage="before_encode"))
                    encode_started = time.monotonic()
                    try:
                        vectors, profiler_operators = _encode(
                            torch=torch,
                            model=model,
                            texts=texts,
                            spec=effective_spec,
                            workload=workload,
                        )
                    except Exception as exc:
                        caught_at = time.monotonic()
                        oom_sample = cuda_stage_snapshot(
                            torch, stage="oom_exception_path", synchronize=False
                        )
                        oom_sample["delay_ms_from_catch"] = max(
                            0.0, (time.monotonic() - caught_at) * 1000.0
                        )
                        if is_cuda_oom(exc):
                            requested_bytes = parse_requested_allocation_bytes(str(exc))
                        raise
                    stages.append(
                        {
                            **cuda_stage_snapshot(torch, stage="after_encode_success"),
                            "wall_seconds": time.monotonic() - encode_started,
                        }
                    )
                    reset_stage_peaks(torch)
                    query_started = time.monotonic()
                    query_vectors = _encode_queries(
                        torch=torch,
                        model=model,
                        query_texts=query_texts[:16],
                        query_text_contract=settings.dense.query_text.contract_version,
                        query_instruction=settings.indexing.embedding.query_instruction,
                    )
                    stages.append(
                        {
                            **cuda_stage_snapshot(
                                torch, stage="after_query_parity_encode"
                            ),
                            "wall_seconds": time.monotonic() - query_started,
                        }
                    )
                except Exception as exc:
                    if is_cuda_oom(exc) and oom_sample is None:
                        caught_at = time.monotonic()
                        oom_sample = cuda_stage_snapshot(
                            torch, stage="oom_exception_path", synchronize=False
                        )
                        oom_sample["delay_ms_from_catch"] = max(
                            0.0, (time.monotonic() - caught_at) * 1000.0
                        )
                        requested_bytes = parse_requested_allocation_bytes(str(exc))
                    raise
                finally:
                    cache_observer.restore()
                    sdpa_observer.restore()
        except Exception as exc:  # noqa: BLE001 - record sanitized runtime failure
            failure = exc
        if failure is None and vectors is not None and query_vectors is not None:
            vector_payload = json.dumps(
                {"documents": vectors, "queries": query_vectors},
                separators=(",", ":"),
                allow_nan=False,
            )
            vector_output_path.parent.mkdir(parents=True, exist_ok=True)
            vector_output_path.write_text(vector_payload + "\n", encoding="utf-8")
            vector_digest = hashlib.sha256(vector_payload.encode("utf-8")).hexdigest()
        else:
            vector_digest = None
        model_facts = model_runtime_facts(model) if model is not None else {}
    finally:
        sampler_rows = sampler.stop()
        first_gpu_sample = next(
            (
                row["gpus"][0]
                for row in sampler_rows
                if row.get("status") == "observed" and row.get("gpus")
            ),
            None,
        )
        if first_gpu_sample is not None:
            device_facts["driver_version"] = first_gpu_sample.get("driver_version")
        if model is not None:
            del model
        gc.collect()
        try:
            torch.cuda.synchronize()
            reset_stage_peaks(torch)
            stages.append(cuda_stage_snapshot(torch, stage="after_cleanup"))
        except Exception as exc:  # noqa: BLE001
            stages.append(
                {
                    "stage": "after_cleanup",
                    "status": "unavailable",
                    "error_type": type(exc).__name__,
                }
            )
        signal.setitimer(signal.ITIMER_REAL, 0.0)

    duration = time.monotonic() - started
    history_state["requested_allocation_bytes"] = requested_bytes
    oom_classification = _oom_classification(
        history=history_state,
        oom_sample=oom_sample,
        device_samples=sampler_rows,
        baseline_stage=stages[0] if stages else None,
    )
    failure_class = failure_classification(failure)
    exception_summary = safe_exception_summary(failure) if failure is not None else None
    result = {
        "schema": "seneca-16k-r04-embedding-memory-cell-v1",
        "authority": authorized["authority"],
        "design_subject": ACCEPTED_DESIGN_SUBJECT,
        "implementation_subject": current_commit,
        "cell_id": spec["cell_id"],
        "replicate": int(spec["replicate"]),
        "cell_spec_sha256": spec_sha,
        "effective_controls": {
            "dtype_mode": effective_spec.get("dtype_mode", "post_load_half"),
            "disable_cache": effective_spec.get("disable_cache", False),
            "attention_backend": effective_spec.get("attention_backend"),
            "batch_strategy": effective_spec.get("batch_strategy", "fixed32"),
            "profiler_characterization": effective_spec.get(
                "profiler_characterization", False
            ),
        },
        "workload_sha256": workload["workload_sha256"],
        "model_revision": workload["model"]["revision"],
        "runtime_versions": runtime_versions,
        "device_facts": device_facts,
        "stage_snapshots": stages,
        "device_samples": sampler_rows,
        "token_metrics": token_metrics,
        "cache_observation": cache_observer.summary(),
        "sdpa_observation": sdpa_observer.summary(),
        "model_facts": model_facts,
        "encode_result": {
            "status": "SUCCESS" if failure is None else "FAILED",
            "document_vector_count": len(vectors) if vectors is not None else 0,
            "query_vector_count": (
                len(query_vectors) if query_vectors is not None else 0
            ),
            "vector_dimension": len(vectors[0]) if vectors else None,
            "ordered_chunk_ids_sha256": workload["ordered_chunk_ids_sha256"],
            "vectors_sha256": vector_digest,
            "vectors_path": str(vector_output_path) if vector_digest else None,
        },
        "oom_diagnostics": {
            **history_state,
            "requested_allocation_bytes": requested_bytes,
            "oom_time_memory_sample": oom_sample,
            "classification": oom_classification,
        },
        "exception": exception_summary,
        "failure_classification": failure_class,
        "profiler_operators": profiler_operators,
        "duration_seconds": duration,
        "status": "SUCCESS" if failure is None else "FAILED",
    }
    safe = safe_cell_evidence(result, private_texts=texts)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(safe, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    complete_cell_process_claim(
        claim_path,
        duration_seconds=duration,
        result_status=(
            "SUCCESS"
            if failure_class == "NONE"
            else "OOM"
            if failure_class == "CUDA_OOM"
            else "DEADLINE"
            if failure_class == "DEADLINE"
            else "FAILED"
        ),
        evidence_path=output_path,
    )
    return safe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authority", required=True, type=Path)
    parser.add_argument("--cell-spec", required=True, type=Path)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vectors-output", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--chunk-manifest", required=True, type=Path)
    parser.add_argument("--corpus-manifest", required=True, type=Path)
    parser.add_argument("--chunks-root", required=True, type=Path)
    parser.add_argument("--embeddings-root", required=True, type=Path)
    parser.add_argument("--incident-identity", type=Path)
    parser.add_argument("--source-document-id", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_cell(
            authority_path=args.authority,
            cell_spec_path=args.cell_spec,
            workload_path=args.workload,
            output_path=args.output,
            vector_output_path=args.vectors_output,
            snapshot_path=args.snapshot,
            chunk_manifest_path=args.chunk_manifest,
            corpus_manifest_path=args.corpus_manifest,
            chunks_root=args.chunks_root,
            embeddings_root=args.embeddings_root,
            incident_identity_path=args.incident_identity,
            source_document_id=args.source_document_id,
            source_sha256=args.source_sha256,
            settings_path=args.settings,
            model_dir_arg=args.model_dir,
        )
        print(json.dumps({"status": result.get("status"), "output": str(args.output)}))
        return 0
    except PermissionError:
        print("EXECUTION_BLOCKED: separate cell authority required", file=sys.stderr)
        return 20
    except Exception as exc:  # noqa: BLE001
        print(f"CELL_FAILED: {type(exc).__name__}", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
