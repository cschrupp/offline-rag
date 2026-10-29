"""Deterministically reduce raw cell evidence into analysis records."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .contract import (
    ACCEPTED_DESIGN_SUBJECT,
    EXPECTED_MODEL_ID,
    EXPECTED_MODEL_REVISION,
    VECTOR_DIMENSION,
    VECTOR_NORM_TOLERANCE,
    FrozenItem,
    workload_digest,
)
from .contract import (
    SCHEMA as WORKLOAD_SCHEMA,
)

CELL_SCHEMA = "seneca-16k-r04-embedding-memory-cell-v1"
REQUIRED_RUNTIME_VERSIONS = ("sentence_transformers", "transformers", "torch")


def _read_json(path: Path) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    return raw, json.loads(raw)


def _vector_facts(evidence: dict[str, Any]) -> dict[str, Any]:
    result = evidence.get("encode_result", {})
    vector_path = result.get("vectors_path")
    expected_digest = result.get("vectors_sha256")
    if not isinstance(vector_path, str) or not isinstance(expected_digest, str):
        return {"available": False, "correct": False, "vectors": None}
    try:
        vector_file = Path(vector_path)
        raw = vector_file.read_bytes()
        payload = json.loads(raw)
        compact = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    except OSError, ValueError, TypeError, json.JSONDecodeError:
        return {"available": False, "correct": False, "vectors": None}
    if hashlib.sha256(compact.encode("utf-8")).hexdigest() != expected_digest:
        return {"available": False, "correct": False, "vectors": None}
    if not isinstance(payload, dict):
        return {"available": False, "correct": False, "vectors": None}
    documents = payload.get("documents")
    queries = payload.get("queries")
    vectors = [*(documents or []), *(queries or [])]
    correct = (
        isinstance(documents, list)
        and len(documents) == 32
        and isinstance(queries, list)
        and len(queries) == 16
        and all(
            isinstance(vector, list)
            and len(vector) == VECTOR_DIMENSION
            and all(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in vector
            )
            and abs(math.sqrt(sum(value * value for value in vector)) - 1.0)
            <= VECTOR_NORM_TOLERANCE
            for vector in vectors
        )
    )
    return {
        "available": True,
        "correct": correct,
        "vectors": {"documents": documents, "queries": queries},
    }


def reduce_cell_evidence(
    path: Path,
    *,
    expected_implementation_subject: str,
    expected_workload_sha256: str,
    expected_cell_spec_sha256: str | None = None,
    expected_controls: dict[str, Any] | None = None,
    expected_ordered_chunk_ids_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate a raw evidence file and derive its analysis-facing metrics."""
    raw, payload = _read_json(path)
    evidence_sha256 = hashlib.sha256(raw).hexdigest()
    if not isinstance(payload, dict):
        raise TypeError("cell evidence must be a JSON object")
    controls = payload.get("effective_controls")
    required_control_keys = {
        "dtype_mode",
        "disable_cache",
        "attention_backend",
        "batch_strategy",
        "profiler_characterization",
    }
    if not isinstance(controls, dict) or set(controls) != required_control_keys:
        raise ValueError("cell evidence treatment controls are incomplete")
    identity_valid = (
        payload.get("schema") == CELL_SCHEMA
        and payload.get("design_subject") == ACCEPTED_DESIGN_SUBJECT
        and payload.get("implementation_subject") == expected_implementation_subject
        and payload.get("workload_sha256") == expected_workload_sha256
        and payload.get("model_revision") == EXPECTED_MODEL_REVISION
        and isinstance(payload.get("cell_id"), str)
        and isinstance(payload.get("replicate"), int)
        and not isinstance(payload.get("replicate"), bool)
        and isinstance(payload.get("cell_spec_sha256"), str)
        and (
            expected_cell_spec_sha256 is None
            or payload.get("cell_spec_sha256") == expected_cell_spec_sha256
        )
        and (expected_controls is None or controls == expected_controls)
        and (
            expected_ordered_chunk_ids_sha256 is None
            or payload.get("encode_result", {}).get("ordered_chunk_ids_sha256")
            == expected_ordered_chunk_ids_sha256
        )
    )
    versions = payload.get("runtime_versions")
    is_cpu_reference = payload.get("cell_id") == "CPU_ONNX_REFERENCE"
    if is_cpu_reference:
        versions_valid = (
            isinstance(versions, dict)
            and versions.get("provider") == "CPUExecutionProvider"
            and versions.get("profile") == "cpu_onnx_fp32_v1"
        )
    else:
        versions_valid = (
            isinstance(versions, dict)
            and all(
                isinstance(versions.get(name), str) and versions[name]
                for name in REQUIRED_RUNTIME_VERSIONS
            )
            and isinstance(versions.get("cuda_build"), str)
            and bool(versions.get("cuda_build"))
        )
    device = payload.get("device_facts")
    device_identity = None
    device_valid = is_cpu_reference
    if is_cpu_reference:
        device_identity = {"device_name": "CPUExecutionProvider"}
    if isinstance(device, dict):
        device_identity = {
            "device_name": device.get("device_name"),
            "device_total_bytes": device.get("device_total_bytes"),
            "capability": device.get("capability"),
            "driver_version": device.get("driver_version"),
        }
        device_valid = (
            device.get("cuda_available") is True
            and isinstance(device_identity["device_name"], str)
            and isinstance(device_identity["device_total_bytes"], int)
            and isinstance(device_identity["capability"], list)
            and isinstance(device_identity["driver_version"], str)
        )

    stages = payload.get("stage_snapshots")
    if not isinstance(stages, list):
        stages = []
    stage_by_name = {
        stage.get("stage"): stage for stage in stages if isinstance(stage, dict)
    }
    cell_id = payload.get("cell_id")
    dtype_mode = controls.get("dtype_mode")
    if cell_id == "M2":
        target_stage_name = (
            "after_st_construction"
            if dtype_mode == "direct_fp16"
            else "after_post_load_half"
        )
    else:
        target_stage_name = "after_encode_success"
    target_stage = stage_by_name.get(target_stage_name)
    target_phase_complete = bool(
        (target_stage and target_stage.get("status") == "observed")
        or (is_cpu_reference and payload.get("status") == "SUCCESS")
    )
    before_load = stage_by_name.get("before_model_load", {})
    initial_free = before_load.get("device_free_bytes")
    used = before_load.get("device_used_bytes")
    reserved = before_load.get("reserved_bytes")
    external_used = (
        max(0, used - reserved)
        if isinstance(used, int) and isinstance(reserved, int)
        else None
    )
    target_peak = target_stage.get("peak_allocated_bytes") if target_stage else None
    load_stage_name = (
        "after_st_construction"
        if dtype_mode == "direct_fp16"
        else "after_post_load_half"
    )
    load_stage = stage_by_name.get(load_stage_name)
    load_phase_complete = bool(load_stage and load_stage.get("status") == "observed")
    load_device_peak = None
    if load_stage is not None:
        load_end = load_stage.get("monotonic_seconds") if load_stage else None
        load_start = before_load.get("monotonic_seconds")
        samples = payload.get("device_samples", [])
        used_samples = [
            int(gpu["used_mib"]) * 1024 * 1024
            for sample in samples
            if sample.get("status") == "observed"
            and isinstance(sample.get("monotonic_seconds"), (int, float))
            and isinstance(load_start, (int, float))
            and isinstance(load_end, (int, float))
            and load_start <= sample["monotonic_seconds"] <= load_end
            for gpu in sample.get("gpus", [])[:1]
            if isinstance(gpu.get("used_mib"), int)
        ]
        load_device_peak = max(used_samples, default=None)
    load_peak_allocated = load_stage.get("peak_allocated_bytes") if load_stage else None
    load_peak_reserved = load_stage.get("peak_reserved_bytes") if load_stage else None

    vector_facts = _vector_facts(payload)
    encode_result = payload.get("encode_result", {})
    success = payload.get("status") == "SUCCESS"
    oom_type = str((payload.get("exception") or {}).get("type", "")).lower()
    oom_observed = "outofmemory" in oom_type or "cudamemoryexhausted" in oom_type
    result_status = (
        "SUCCESS" if success else "OOM" if oom_observed else "NON_OOM_FAILURE"
    )
    correctness_ok = (
        vector_facts["correct"]
        and encode_result.get("document_vector_count") == 32
        and encode_result.get("query_vector_count") == 16
        and encode_result.get("vector_dimension") == VECTOR_DIMENSION
    )
    if is_cpu_reference:
        correctness_ok = (
            encode_result.get("document_vector_count") == 32
            and encode_result.get("query_vector_count") == 16
            and encode_result.get("vector_dimension") == VECTOR_DIMENSION
            and vector_facts["correct"]
        )
    full_workload_complete = bool(
        success
        and target_phase_complete
        and correctness_ok
        and (
            stage_by_name.get("after_query_parity_encode", {}).get("status")
            == "observed"
            or is_cpu_reference
        )
    )
    oom_diagnostics = payload.get("oom_diagnostics")
    oom_diagnostics = oom_diagnostics if isinstance(oom_diagnostics, dict) else {}
    snapshot = oom_diagnostics.get("classification")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    resource_evidence_valid = result_status != "OOM" or (
        oom_diagnostics.get("snapshot_written") is True
        and oom_diagnostics.get("oom_event_observed") is True
        and snapshot.get("status") in {"CLASSIFIED", "INCONCLUSIVE"}
    )
    completion_evidence_valid = result_status != "SUCCESS" or (
        target_phase_complete and full_workload_complete and correctness_ok
    )
    valid = bool(
        identity_valid
        and versions_valid
        and device_valid
        and result_status in {"SUCCESS", "OOM"}
        and resource_evidence_valid
        and completion_evidence_valid
    )
    target_peak_key = (
        "load_device_peak_bytes" if cell_id == "M2" else "target_peak_bytes"
    )
    cache_observation = payload.get("cache_observation")
    cache_observation = cache_observation if isinstance(cache_observation, dict) else {}
    config_states = (payload.get("model_facts") or {}).get("config_states", [])
    configured_cache_values = [
        item.get("use_cache")
        for item in config_states
        if isinstance(item, dict) and isinstance(item.get("use_cache"), bool)
    ]
    cache_config_known = bool(configured_cache_values)
    cache_config_enabled = any(configured_cache_values)
    cache_activation_witness = bool(
        any(
            value is True
            for value in cache_observation.get("forward_use_cache_values", [])
        )
        or cache_observation.get("dynamic_cache_construction_attempts", 0) > 0
        or cache_observation.get("cache_update_attempts", 0) > 0
        or cache_observation.get("non_null_cache_returns", 0) > 0
    )
    gate_facts = {
        "valid": valid,
        "status": result_status,
        "target_phase_complete": target_phase_complete,
        "load_phase_complete": load_phase_complete,
        "full_workload_complete": full_workload_complete,
        "correctness_ok": correctness_ok,
        "cache_config_known": cache_config_known,
        "cache_config_enabled": cache_config_enabled,
        "cache_activation_witness": cache_activation_witness,
        "effective_controls": controls,
        "token_metrics": payload.get("token_metrics"),
        "sdpa_observation": payload.get("sdpa_observation"),
    }
    return {
        "source_evidence_sha256": evidence_sha256,
        "source_path": str(path.resolve()),
        "schema": payload.get("schema"),
        "cell_id": cell_id,
        "replicate": payload.get("replicate"),
        "cell_spec_sha256": payload.get("cell_spec_sha256"),
        "effective_controls": controls,
        "implementation_subject": payload.get("implementation_subject"),
        "workload_sha256": payload.get("workload_sha256"),
        "model_revision": payload.get("model_revision"),
        "runtime_versions": versions,
        "device_identity": device_identity,
        "valid": valid,
        "validity_reasons": {
            "identity": identity_valid,
            "runtime_versions": versions_valid,
            "device_identity": device_valid,
            "resource_evidence": resource_evidence_valid,
            "completion_evidence": completion_evidence_valid,
            "result_status": result_status,
        },
        "status": result_status,
        "target_stage": target_stage_name,
        "target_phase_complete": target_phase_complete,
        "load_phase_complete": load_phase_complete,
        "full_workload_complete": full_workload_complete,
        "correctness_ok": correctness_ok,
        "initial_device_free_bytes": initial_free,
        "external_device_used_bytes": external_used,
        "target_peak_bytes": target_peak,
        "forward_peak_bytes": stage_by_name.get("after_encode_success", {}).get(
            "peak_allocated_bytes"
        ),
        "load_device_peak_bytes": load_device_peak,
        "load_peak_allocated_bytes": load_peak_allocated,
        "load_peak_reserved_bytes": load_peak_reserved,
        "target_peak_key": target_peak_key,
        "encode_wall_ms": (
            float(stage_by_name["after_encode_success"].get("wall_seconds")) * 1000.0
            if isinstance(
                stage_by_name.get("after_encode_success", {}).get("wall_seconds"),
                (int, float),
            )
            else None
        ),
        "load_wall_ms": (
            float(load_stage.get("wall_seconds")) * 1000.0
            if isinstance(load_stage, dict)
            and isinstance(load_stage.get("wall_seconds"), (int, float))
            else None
        ),
        "vectors": vector_facts["vectors"],
        "cache_observation": payload.get("cache_observation"),
        "gate_facts": gate_facts,
        "model_facts": payload.get("model_facts"),
        "token_metrics": payload.get("token_metrics"),
        "sdpa_observation": payload.get("sdpa_observation"),
    }


def effective_controls_from_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Derive the only treatment controls admitted by an exact cell spec."""
    if spec.get("cell_id") == "CPU_ONNX_REFERENCE":
        return {
            "dtype_mode": "cpu_onnx_fp32",
            "disable_cache": False,
            "attention_backend": None,
            "batch_strategy": "fixed32",
            "profiler_characterization": False,
        }
    effective = dict(spec)
    if spec.get("cell_id") == "M5":
        selected = spec.get("selected_candidate_settings")
        if not isinstance(selected, dict):
            raise ValueError("M5 cell spec lacks selected candidate controls")
        effective.update(selected)
    return {
        "dtype_mode": effective.get("dtype_mode", "post_load_half"),
        "disable_cache": effective.get("disable_cache", False),
        "attention_backend": effective.get("attention_backend"),
        "batch_strategy": effective.get("batch_strategy", "fixed32"),
        "profiler_characterization": effective.get("profiler_characterization", False),
    }


def reduce_authorized_cell_evidence(
    *,
    evidence_path: Path,
    cell_spec_path: Path,
    authority: dict[str, Any],
    workload: dict[str, Any],
) -> dict[str, Any]:
    """Bind raw evidence to its immutable authority, spec, and workload."""
    spec_bytes, spec = _read_json(cell_spec_path)
    if not isinstance(spec, dict):
        raise TypeError("cell spec must be a JSON object")
    spec_digest = hashlib.sha256(spec_bytes).hexdigest()
    cell_id = spec.get("cell_id")
    replicate = spec.get("replicate")
    hashes = authority.get("cell_spec_sha256", {})
    expected = (
        hashes.get(cell_id, {}).get(str(replicate))
        if isinstance(hashes, dict)
        else None
    )
    if expected != spec_digest:
        raise ValueError("cell spec is not bound to this authority")
    _verify_workload_manifest(workload)
    implementation = authority.get("implementation_subject")
    workload_sha = workload.get("workload_sha256")
    ordered_ids_digest = workload.get("ordered_chunk_ids_sha256")
    if not all(
        isinstance(value, str) and value
        for value in (implementation, workload_sha, ordered_ids_digest)
    ):
        raise ValueError("authority/workload identity is incomplete")
    return reduce_cell_evidence(
        evidence_path,
        expected_implementation_subject=implementation,
        expected_workload_sha256=workload_sha,
        expected_cell_spec_sha256=spec_digest,
        expected_controls=effective_controls_from_spec(spec),
        expected_ordered_chunk_ids_sha256=ordered_ids_digest,
    )


def _verify_workload_manifest(workload: dict[str, Any]) -> None:
    """Recompute frozen item and ordered-identity digests from the manifest."""
    model = workload.get("model")
    if (
        workload.get("schema") != WORKLOAD_SCHEMA
        or workload.get("accepted_design_subject") != ACCEPTED_DESIGN_SUBJECT
        or not isinstance(model, dict)
        or model.get("id") != EXPECTED_MODEL_ID
        or model.get("revision") != EXPECTED_MODEL_REVISION
        or workload.get("item_count") != 32
        or workload.get("workload_kind")
        not in {"EXACT_INCIDENT_BATCH", "INCIDENT_ADJACENT_SUBSTITUTE"}
        or workload.get("execution_authorized") is not False
    ):
        raise ValueError("workload manifest identity or execution state is invalid")
    rows = workload.get("ordered_items")
    if not isinstance(rows, list) or len(rows) != 32:
        raise ValueError("workload must contain exactly 32 ordered item records")
    items: list[FrozenItem] = []
    chunk_ids: list[str] = []
    for ordinal, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("ordinal"), int)
            or isinstance(row.get("ordinal"), bool)
            or row.get("ordinal") != ordinal
        ):
            raise ValueError("workload item order is invalid")
        item = FrozenItem(
            chunk_id=row.get("chunk_id"),
            embedding_text_sha256=row.get("embedding_text_sha256"),
            embedding_artifact_text_sha256=row.get("embedding_artifact_text_sha256"),
            query_input_sha256=row.get("query_input_sha256"),
            qwen_token_count=row.get("qwen_token_count"),
        )
        if (
            not isinstance(item.chunk_id, str)
            or not item.chunk_id
            or not isinstance(item.embedding_text_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", item.embedding_text_sha256)
            or not isinstance(item.embedding_artifact_text_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", item.embedding_artifact_text_sha256)
            or not isinstance(item.query_input_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", item.query_input_sha256)
            or not isinstance(item.qwen_token_count, int)
            or isinstance(item.qwen_token_count, bool)
            or item.qwen_token_count <= 0
        ):
            raise ValueError("workload item identity is invalid")
        items.append(item)
        chunk_ids.append(item.chunk_id)
    if len(set(chunk_ids)) != 32:
        raise ValueError("workload chunk IDs are not unique")
    expected_ordered_digest = hashlib.sha256(
        "\n".join(chunk_ids).encode("utf-8")
    ).hexdigest()
    if workload_digest(items) != workload.get("workload_sha256"):
        raise ValueError("workload item digest does not match its manifest")
    if expected_ordered_digest != workload.get("ordered_chunk_ids_sha256"):
        raise ValueError("ordered chunk identity digest does not match its manifest")
