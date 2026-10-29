"""Pure contract helpers for the R04 embedding-memory campaign.

This module deliberately imports no model, tokenizer, PyTorch, or CUDA package.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from typing import Any

IMPLEMENTATION_AUTHORITY = (
    "S16-K-R04-EMBEDDING-MEMORY-DIAGNOSTIC-HARNESS-IMPLEMENTATION-AUTH-001"
)
ACCEPTED_DESIGN_SUBJECT = "beecfd56fb5c085fabcca0131f0af7e67923836f"
IMPLEMENTATION_BASE = "e078c56c94eef63e00d4b347f057f89b71da7f0b"
SCHEMA = "seneca-16k-r04-embedding-memory-workload-v1"
PARITY_CONTRACT = "d2-retrieval-parity-v1"
RAW_QUERY_V1 = "raw-query-v1"
MODEL_QUERY_PROMPT_V1 = "model-query-prompt-v1"
EXPECTED_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EXPECTED_MODEL_REVISION = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
EXPECTED_BATCH_SIZE = 32
MAX_ITEMS = 32
MAX_CUDA_CELLS = 22
MAX_CPU_REFERENCE_PROCESSES = 1
MAX_TOTAL_PROCESSES = 23
MAX_VALID_REPLICATES = 3
MAX_CELL_SECONDS = 15 * 60
MAX_CAMPAIGN_SECONDS = 4 * 60 * 60
PAIR_HEADROOM_TOLERANCE_BYTES = 256 * 1024 * 1024
PAIR_EXTERNAL_USAGE_TOLERANCE_BYTES = 256 * 1024 * 1024
MATERIAL_MEMORY_FLOOR_BYTES = 256 * 1024 * 1024
MATERIAL_MEMORY_FRACTION = 0.05
MAX_OTHER_PEAK_REGRESSION_BYTES = 256 * 1024 * 1024
MAX_LATENCY_REGRESSION_FRACTION = 0.10
VECTOR_DIMENSION = 1024
VECTOR_NORM_TOLERANCE = 1e-4
MEDIAN_VECTOR_COSINE_MIN = 0.999
MIN_VECTOR_COSINE_MIN = 0.995
MEAN_TOP10_OVERLAP_MIN = 0.95
MIN_TOP10_OVERLAP_MIN = 0.80
TOP1_AGREEMENT_MIN = 15
TOP1_QUERY_COUNT = 16
TOPK = 10
MIB = 1024 * 1024

CUDA_CELL_CAPS = {
    "M0": 3,
    "M1": 3,
    "M2": 3,
    "M3_PROFILE": 1,
    "M3_A": 3,
    "M3_B": 3,
    "M4": 3,
    "M5": 3,
}


@dataclass(frozen=True)
class FrozenItem:
    """Non-sensitive identity for one exact embedding input."""

    chunk_id: str
    embedding_text_sha256: str
    qwen_token_count: int
    embedding_artifact_text_sha256: str | None = None
    query_input_sha256: str | None = None


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def workload_digest(items: list[FrozenItem]) -> str:
    """Hash ordered item identities without retaining text or token IDs."""
    payload = [
        {
            "chunk_id": item.chunk_id,
            "embedding_text_sha256": item.embedding_text_sha256,
            "embedding_artifact_text_sha256": item.embedding_artifact_text_sha256,
            "query_input_sha256": item.query_input_sha256,
            "qwen_token_count": item.qwen_token_count,
        }
        for item in items
    ]
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def build_workload_manifest(
    *,
    items: list[FrozenItem],
    workload_kind: str,
    source_document_id: str,
    source_sha256: str,
    corpus_id: str,
    chunk_set_id: str,
    embedding_config_hash: str,
    query_text_contract: str = RAW_QUERY_V1,
    workspace_identity: dict[str, Any] | None = None,
    model_id: str = EXPECTED_MODEL_ID,
    model_revision: str = EXPECTED_MODEL_REVISION,
    reused_count: int,
    desired_count: int,
) -> dict[str, Any]:
    if len(items) != MAX_ITEMS:
        raise ValueError(f"workload must contain exactly {MAX_ITEMS} items")
    if workload_kind not in {"EXACT_INCIDENT_BATCH", "INCIDENT_ADJACENT_SUBSTITUTE"}:
        raise ValueError("unsupported workload_kind")
    if len({item.chunk_id for item in items}) != MAX_ITEMS:
        raise ValueError("workload chunk IDs must be unique")
    for item in items:
        if len(item.embedding_text_sha256) != 64:
            raise ValueError("embedding text digest must be SHA-256 hex")
        if item.qwen_token_count <= 0:
            raise ValueError("Qwen token counts must be positive")
    return {
        "schema": SCHEMA,
        "authority": IMPLEMENTATION_AUTHORITY,
        "accepted_design_subject": ACCEPTED_DESIGN_SUBJECT,
        "workload_kind": workload_kind,
        "source": {
            "document_id": source_document_id,
            "content_sha256": source_sha256,
        },
        "workspace": workspace_identity,
        "corpus_id": corpus_id,
        "chunk_set_id": chunk_set_id,
        "embedding_config_hash": embedding_config_hash,
        "query_text_contract": query_text_contract,
        "model": {"id": model_id, "revision": model_revision},
        "item_count": MAX_ITEMS,
        "configured_batch_size": EXPECTED_BATCH_SIZE,
        "reconstructed_reused_count": reused_count,
        "reconstructed_desired_count": desired_count,
        "ordered_items": [
            {
                "ordinal": ordinal,
                "chunk_id": item.chunk_id,
                "embedding_text_sha256": item.embedding_text_sha256,
                "embedding_artifact_text_sha256": item.embedding_artifact_text_sha256,
                "query_input_sha256": item.query_input_sha256,
                "qwen_token_count": item.qwen_token_count,
            }
            for ordinal, item in enumerate(items)
        ],
        "ordered_chunk_ids_sha256": hashlib.sha256(
            "\n".join(item.chunk_id for item in items).encode("utf-8")
        ).hexdigest(),
        "workload_sha256": workload_digest(items),
        "token_summary": token_summary([item.qwen_token_count for item in items]),
        "execution_authorized": False,
    }


def token_summary(token_counts: list[int]) -> dict[str, int]:
    if not token_counts:
        raise ValueError("token_counts must not be empty")
    ordered = sorted(token_counts)
    # Nearest-rank p95, deterministic for the 32-item frozen set.
    p95_rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "count": len(ordered),
        "sum": sum(ordered),
        "min": ordered[0],
        "median": int(statistics.median(ordered)),
        "p95": ordered[p95_rank - 1],
        "max": ordered[-1],
        "padded_tokens_batch32": len(ordered) * ordered[-1],
        "padding_tokens_batch32": len(ordered) * ordered[-1] - sum(ordered),
    }


def greedy_token_partitions(token_counts: list[int]) -> list[list[int]] | None:
    """Greedy ordered batches under the frozen M4 padded-token budget."""
    if len(token_counts) != MAX_ITEMS or any(count <= 0 for count in token_counts):
        raise ValueError("M4 requires exactly 32 positive token counts")
    budget = EXPECTED_BATCH_SIZE * token_summary(token_counts)["p95"]
    if max(token_counts) > budget:
        return None
    partitions: list[list[int]] = []
    current: list[int] = []
    current_max = 0
    for index, count in enumerate(token_counts):
        next_max = max(current_max, count)
        if current and (
            len(current) >= EXPECTED_BATCH_SIZE
            or (len(current) + 1) * next_max > budget
        ):
            partitions.append(current)
            current = []
            current_max = 0
            next_max = count
        current.append(index)
        current_max = next_max
    if current:
        partitions.append(current)
    return partitions


def enforce_cell_budget(records: list[dict[str, Any]]) -> dict[str, int]:
    """Validate planned/executed cell and process counts without side effects."""
    cuda_cells = 0
    cpu_reference_cells = 0
    counts: dict[str, int] = {}
    total_duration = 0.0
    for record in records:
        cell = str(record.get("cell_id", ""))
        duration = record.get("duration_seconds", 0.0)
        if not isinstance(duration, (int, float)) or duration < 0:
            raise ValueError("cell duration must be a non-negative number")
        if duration > MAX_CELL_SECONDS:
            raise ValueError("15-minute per-cell ceiling exceeded")
        total_duration += float(duration)
        if cell == "CPU_ONNX_REFERENCE":
            cpu_reference_cells += 1
            continue
        if cell not in CUDA_CELL_CAPS:
            raise ValueError(f"unknown cell ID: {cell}")
        counts[cell] = counts.get(cell, 0) + 1
        if counts[cell] > CUDA_CELL_CAPS[cell]:
            raise ValueError(f"cell cap exceeded for {cell}")
        cuda_cells += 1
    if cuda_cells > MAX_CUDA_CELLS:
        raise ValueError("22-cell CUDA campaign cap exceeded")
    if cpu_reference_cells > MAX_CPU_REFERENCE_PROCESSES:
        raise ValueError("CPU ONNX reference process cap exceeded")
    if cuda_cells + cpu_reference_cells > MAX_TOTAL_PROCESSES:
        raise ValueError("23 total model-process execution cap exceeded")
    if total_duration > MAX_CAMPAIGN_SECONDS:
        raise ValueError("four-hour total campaign ceiling exceeded")
    return {
        "cuda_cells": cuda_cells,
        "cpu_onnx_reference_processes": cpu_reference_cells,
        "total_processes": cuda_cells + cpu_reference_cells,
        "cumulative_duration_seconds": int(total_duration),
    }


def classify_oom_diagnostics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Apply the accepted independent OOM-resource diagnostic rules."""
    if metrics.get("oom_observed") is not True:
        return {
            "status": "NOT_APPLICABLE",
            "flags": [],
            "missing_metrics": [],
            "owner_attribution": "NOT_APPLICABLE",
        }
    requested = metrics.get("requested_bytes")
    free = metrics.get("oom_time_free_bytes")
    allocated = metrics.get("allocated_bytes")
    reserved = metrics.get("reserved_bytes")
    device_used = metrics.get("device_used_bytes")
    total = metrics.get("device_total_bytes")
    reusable = metrics.get("snapshot_reusable_bytes")
    largest = metrics.get("snapshot_largest_reusable_block_bytes")
    inactive_split = metrics.get("snapshot_inactive_split_bytes")
    snapshot_complete = metrics.get("snapshot_complete") is True
    snapshot_has_oom = metrics.get("snapshot_oom_event") is True
    snapshot_request = metrics.get("snapshot_oom_requested_bytes")
    process_rows = metrics.get("processes")

    missing: list[str] = []
    for key, value in (
        ("requested_bytes", requested),
        ("oom_time_free_bytes", free),
        ("allocated_bytes", allocated),
        ("reserved_bytes", reserved),
        ("device_used_bytes", device_used),
        ("device_total_bytes", total),
    ):
        if not isinstance(value, int) or value < 0:
            missing.append(key)
    if (
        metrics.get("oom_sample_delay_ms") is None
        or metrics.get("oom_sample_delay_ms", 1) > 250
    ):
        missing.append("valid_oom_time_sample")
    if not snapshot_complete or not snapshot_has_oom:
        missing.append("complete_snapshot_with_oom_event")
    if not isinstance(requested, int) or not isinstance(snapshot_request, int):
        missing.append("snapshot_oom_request_size")
    elif snapshot_request != requested:
        missing.append("snapshot_oom_request_match")
    for key, value in (
        ("snapshot_reusable_bytes", reusable),
        ("snapshot_largest_reusable_block_bytes", largest),
        ("snapshot_inactive_split_bytes", inactive_split),
    ):
        if not isinstance(value, int) or value < 0:
            missing.append(key)
    if not isinstance(process_rows, list):
        missing.append("paired_device_process_observation")
    if missing:
        return {
            "status": "INCONCLUSIVE",
            "flags": [],
            "missing_metrics": sorted(set(missing)),
            "owner_attribution": "NOT_OBSERVABLE",
        }

    requested = int(requested)
    free = int(free)
    allocated = int(allocated)
    reserved = int(reserved)
    device_used = int(device_used)
    total = int(total)
    reusable = int(reusable or 0)
    largest = int(largest or 0)
    inactive_split = int(inactive_split or 0)
    gap = max(0, device_used - reserved)
    gap_threshold = max(512 * MIB, int(0.10 * total))
    split_threshold = max(256 * MIB, int(0.20 * reserved))
    guard = 256 * MIB

    fragmentation = (
        snapshot_complete
        and snapshot_has_oom
        and reusable >= requested
        and largest < requested
        and inactive_split >= split_threshold
    )
    flags: list[str] = []
    if free + reusable < requested:
        flags.append("INSUFFICIENT_DEVICE_HEADROOM")
    if (
        allocated + requested > total - gap - guard
        and free + reusable < requested
        and not fragmentation
    ):
        flags.append("PYTORCH_LIVE_WORKING_SET_PRESSURE")
    if fragmentation:
        flags.append("ALLOCATOR_FRAGMENTATION_SUPPORTED")
    else:
        flags.append("ALLOCATOR_FRAGMENTATION_NOT_ESTABLISHED")

    visible_other = sum(
        int(row.get("used_bytes", int(row.get("used_mib", 0)) * MIB))
        for row in process_rows
        if row.get("owner_class") == "OTHER_VISIBLE_PROCESS"
    )
    visible_owner_support = (
        metrics.get("process_owners_observable") is True
        and visible_other >= gap_threshold
        and free < requested + guard
    )
    external_pressure = free < requested + guard and (
        visible_owner_support
        or (
            gap >= gap_threshold
            and (
                bool(metrics.get("gap_present_at_baseline"))
                or int(metrics.get("gap_growth_bytes", 0)) >= gap_threshold
            )
            and isinstance(metrics.get("reserved_change_bytes"), int)
            and int(metrics["reserved_change_bytes"]) < guard
        )
    )
    if external_pressure:
        flags.append("EXTERNAL_OR_NON_PYTORCH_MEMORY_PRESSURE_SUPPORTED")
    elif (
        metrics.get("paired_device_observation_valid") is True
        and metrics.get("process_observation_valid") is True
    ):
        flags.append("EXTERNAL_PRESSURE_NOT_ESTABLISHED")
    else:
        return {
            "status": "INCONCLUSIVE",
            "flags": flags,
            "missing_metrics": ["paired_device_observation_valid"],
            "owner_attribution": "NOT_OBSERVABLE",
        }

    owner = "OTHER_VISIBLE_PROCESS" if visible_owner_support else "NOT_OBSERVABLE"
    return {
        "status": "CLASSIFIED",
        "flags": flags,
        "missing_metrics": [],
        "requested_bytes": requested,
        "oom_time_free_bytes": free,
        "allocator_reusable_bytes": reusable,
        "allocator_largest_reusable_block_bytes": largest,
        "allocator_inactive_split_bytes": inactive_split,
        "device_gap_bytes": gap,
        "owner_attribution": owner,
    }


def evaluate_mechanism_pairs(
    *,
    baseline_runs: list[dict[str, Any]],
    treatment_runs: list[dict[str, Any]],
    target_peak_key: str,
) -> dict[str, Any]:
    """Compare three paired runs using frozen completeness/headroom thresholds."""
    if len(baseline_runs) != 3 or len(treatment_runs) != 3:
        return {"mechanism": "INCONCLUSIVE", "reason": "three_pairs_required"}
    reductions: list[int] = []
    pair_results: list[dict[str, Any]] = []
    for baseline, treatment in zip(baseline_runs, treatment_runs, strict=True):
        if (
            baseline.get("target_phase_complete") is not True
            or treatment.get("target_phase_complete") is not True
        ):
            return {
                "mechanism": "INCONCLUSIVE",
                "reason": "right_censored_target_phase",
                "pair_results": pair_results,
            }
        if baseline.get("valid") is not True or treatment.get("valid") is not True:
            return {
                "mechanism": "INCONCLUSIVE",
                "reason": "invalid_pair",
                "pair_results": pair_results,
            }
        initial_baseline = baseline.get("initial_device_free_bytes")
        initial_treatment = treatment.get("initial_device_free_bytes")
        external_baseline = baseline.get("external_device_used_bytes")
        external_treatment = treatment.get("external_device_used_bytes")
        if not all(
            isinstance(value, int)
            for value in (
                initial_baseline,
                initial_treatment,
                external_baseline,
                external_treatment,
            )
        ):
            return {"mechanism": "INCONCLUSIVE", "reason": "pair_metrics_missing"}
        if abs(initial_baseline - initial_treatment) > PAIR_HEADROOM_TOLERANCE_BYTES:
            return {"mechanism": "INCONCLUSIVE", "reason": "pair_headroom_mismatch"}
        if (
            abs(external_baseline - external_treatment)
            > PAIR_EXTERNAL_USAGE_TOLERANCE_BYTES
        ):
            return {
                "mechanism": "INCONCLUSIVE",
                "reason": "pair_external_usage_mismatch",
            }
        baseline_peak = baseline.get(target_peak_key)
        treatment_peak = treatment.get(target_peak_key)
        if not isinstance(baseline_peak, int) or not isinstance(treatment_peak, int):
            return {"mechanism": "INCONCLUSIVE", "reason": "target_peak_missing"}
        reduction = baseline_peak - treatment_peak
        reductions.append(reduction)
        pair_results.append(
            {
                "baseline_peak_bytes": baseline_peak,
                "treatment_peak_bytes": treatment_peak,
                "reduction_bytes": reduction,
                "material_threshold_bytes": max(
                    MATERIAL_MEMORY_FLOOR_BYTES,
                    int(baseline_peak * MATERIAL_MEMORY_FRACTION),
                ),
            }
        )
    thresholds = [row["material_threshold_bytes"] for row in pair_results]
    supported = (
        statistics.median(reductions) >= statistics.median(thresholds)
        and sum(
            reduction >= threshold
            for reduction, threshold in zip(reductions, thresholds, strict=True)
        )
        >= 2
    )
    return {
        "mechanism": "SUPPORTED" if supported else "FALSIFIED",
        "median_reduction_bytes": statistics.median(reductions),
        "direction_pairs": sum(value > 0 for value in reductions),
        "pair_results": pair_results,
    }


def evaluate_production_candidate(
    *,
    mechanism: dict[str, Any],
    baseline_runs: list[dict[str, Any]],
    treatment_runs: list[dict[str, Any]],
    parity_results: list[dict[str, Any]],
    other_peak_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Apply repeatability, parity, resource, peak-regression and latency gates."""
    if len(baseline_runs) != 3 or len(treatment_runs) != 3 or len(parity_results) != 3:
        return {"candidate": "INCONCLUSIVE", "reason": "three_runs_required"}
    if any(
        run.get("full_workload_complete") is not True or run.get("status") != "SUCCESS"
        for run in treatment_runs
    ):
        return {
            "candidate": "REJECTED_RESOURCE",
            "reason": "treatment_incomplete_or_failed",
        }
    if any(run.get("valid") is not True for run in treatment_runs):
        return {
            "candidate": "INCONCLUSIVE",
            "reason": "invalid_treatment_evidence",
        }
    if any(run.get("correctness_ok") is not True for run in treatment_runs):
        return {
            "candidate": "REJECTED_CORRECTNESS",
            "reason": "correctness_gate_failed",
        }
    if any(result.get("passed") is not True for result in parity_results):
        return {"candidate": "REJECTED_PARITY", "reason": "parity_gate_failed"}
    if (
        mechanism.get("mechanism") != "SUPPORTED"
        or len(mechanism.get("pair_results", [])) != 3
    ):
        return {
            "candidate": "INCONCLUSIVE",
            "reason": "three_comparable_mechanism_pairs_required",
            "mechanism": mechanism.get("mechanism"),
        }

    if any(
        run.get("valid") is not True or run.get("target_phase_complete") is not True
        for run in baseline_runs
    ):
        return {
            "candidate": "INCONCLUSIVE",
            "reason": "baseline_target_phase_not_comparable",
        }

    for baseline, treatment in zip(baseline_runs, treatment_runs, strict=True):
        for key in other_peak_keys:
            before, after = baseline.get(key), treatment.get(key)
            if not isinstance(before, int) or not isinstance(after, int):
                return {"candidate": "INCONCLUSIVE", "reason": f"missing_{key}"}
            if after - before > MAX_OTHER_PEAK_REGRESSION_BYTES:
                return {
                    "candidate": "REJECTED_RESOURCE",
                    "reason": f"other_peak_regressed:{key}",
                }
    baseline_latency = [run.get("encode_wall_ms") for run in baseline_runs]
    treatment_latency = [run.get("encode_wall_ms") for run in treatment_runs]
    if any(
        not isinstance(value, (int, float)) or value <= 0
        for value in baseline_latency + treatment_latency
    ):
        return {"candidate": "INCONCLUSIVE", "reason": "latency_missing"}
    baseline_median = statistics.median(baseline_latency)
    treatment_median = statistics.median(treatment_latency)
    latency_regression = treatment_median / baseline_median - 1.0
    if latency_regression > MAX_LATENCY_REGRESSION_FRACTION:
        return {
            "candidate": "REJECTED_PERFORMANCE",
            "reason": "median_latency_regression_over_10_percent",
            "median_latency_regression_fraction": latency_regression,
        }
    return {
        "candidate": "QUALIFIED",
        "reason": "all_frozen_candidate_gates_passed",
        "median_latency_regression_fraction": latency_regression,
    }


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("vectors must have matching non-empty dimensions")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("zero-norm vector")
    return dot / (left_norm * right_norm)


def evaluate_parity(
    *,
    reference_documents: list[list[float]],
    candidate_documents: list[list[float]],
    reference_queries: list[list[float]],
    candidate_queries: list[list[float]],
) -> dict[str, Any]:
    """Evaluate frozen vector and exact-workload retrieval gates."""
    vectors = (
        reference_documents,
        candidate_documents,
        reference_queries,
        candidate_queries,
    )
    if [len(part) for part in vectors] != [32, 32, 16, 16]:
        raise ValueError("parity requires 32 passage and 16 query vectors per path")
    if any(len(vector) != VECTOR_DIMENSION for part in vectors for vector in part):
        raise ValueError("all parity vectors must have dimension 1024")
    if any(
        not math.isfinite(value)
        for part in vectors
        for vector in part
        for value in vector
    ):
        raise ValueError("parity vectors must contain only finite values")

    all_vectors = vectors
    norm_errors = [
        abs(math.sqrt(sum(value * value for value in vector)) - 1.0)
        for part in all_vectors
        for vector in part
    ]
    document_cosines = [
        _cosine(reference, candidate)
        for reference, candidate in zip(
            reference_documents, candidate_documents, strict=True
        )
    ]
    query_cosines = [
        _cosine(reference, candidate)
        for reference, candidate in zip(
            reference_queries, candidate_queries, strict=True
        )
    ]

    def ranking(query: list[float], documents: list[list[float]]) -> list[int]:
        return sorted(
            range(len(documents)),
            key=lambda index: (
                -sum(a * b for a, b in zip(query, documents[index], strict=True)),
                index,
            ),
        )[:TOPK]

    overlaps: list[float] = []
    top1_agreement = 0
    for index, (ref_query, cand_query) in enumerate(
        zip(reference_queries, candidate_queries, strict=True)
    ):
        ref_rank = ranking(ref_query, reference_documents)
        cand_rank = ranking(cand_query, candidate_documents)
        overlaps.append(len(set(ref_rank) & set(cand_rank)) / TOPK)
        if ref_rank[0] == cand_rank[0]:
            top1_agreement += 1

    metrics = {
        "parity_contract": PARITY_CONTRACT,
        "maximum_vector_norm_error": max(norm_errors),
        "median_document_vector_cosine": statistics.median(document_cosines),
        "min_document_vector_cosine": min(document_cosines),
        "median_query_vector_cosine": statistics.median(query_cosines),
        "min_query_vector_cosine": min(query_cosines),
        "mean_top10_set_overlap": statistics.mean(overlaps),
        "min_top10_set_overlap": min(overlaps),
        "top1_agreement": top1_agreement,
        "top1_query_count": TOP1_QUERY_COUNT,
    }
    metrics["passed"] = (
        metrics["maximum_vector_norm_error"] <= VECTOR_NORM_TOLERANCE
        and metrics["median_document_vector_cosine"] >= MEDIAN_VECTOR_COSINE_MIN
        and metrics["min_document_vector_cosine"] >= MIN_VECTOR_COSINE_MIN
        and metrics["median_query_vector_cosine"] >= MEDIAN_VECTOR_COSINE_MIN
        and metrics["min_query_vector_cosine"] >= MIN_VECTOR_COSINE_MIN
        and metrics["mean_top10_set_overlap"] >= MEAN_TOP10_OVERLAP_MIN
        and metrics["min_top10_set_overlap"] >= MIN_TOP10_OVERLAP_MIN
        and top1_agreement >= TOP1_AGREEMENT_MIN
    )
    return metrics


def safe_exception_summary(exc: BaseException) -> dict[str, str]:
    """Emit exception type only; messages can contain private input text."""
    return {"type": type(exc).__name__, "message": "REDACTED"}
