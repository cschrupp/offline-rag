"""Evidence-derived campaign sequencing for the R04 diagnostic cells."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from .contract import (
    MATERIAL_MEMORY_FLOOR_BYTES,
    MATERIAL_MEMORY_FRACTION,
    authorized_cell_spec_hashes,
    evaluate_mechanism_pairs,
    evaluate_parity,
    evaluate_production_candidate,
    greedy_token_partitions,
)
from .evidence import effective_controls_from_spec, reduce_authorized_cell_evidence


def _load_completed_claims(
    *,
    claims_dir: Path,
    authority: dict[str, Any],
    workload: dict[str, Any],
    implementation_subject: str,
) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for claim_path in claims_dir.glob("*.json"):
        try:
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PermissionError("campaign claim ledger is corrupt") from exc
        if claim.get("status") != "COMPLETED":
            continue
        if claim.get("implementation_subject") != implementation_subject:
            raise PermissionError("prior claim implementation subject changed")
        if claim.get("workload_sha256") != workload.get("workload_sha256"):
            raise PermissionError("prior claim workload identity changed")
        evidence_path = Path(str(claim.get("evidence_path", "")))
        spec_path = Path(str(claim.get("cell_spec_path", "")))
        try:
            evidence_bytes = evidence_path.read_bytes()
        except OSError as exc:
            raise PermissionError("prior raw cell evidence is unavailable") from exc
        if hashlib.sha256(evidence_bytes).hexdigest() != claim.get("evidence_sha256"):
            raise PermissionError("prior raw cell evidence hash changed")
        if claim.get("evidence_validity") is not True:
            raise PermissionError("invalid prior evidence stops campaign progression")
        reduced = reduce_authorized_cell_evidence(
            evidence_path=evidence_path,
            cell_spec_path=spec_path,
            authority=authority,
            workload=workload,
        )
        if reduced["valid"] is not True:
            raise PermissionError("raw prior evidence is not valid")
        if claim.get("gate_facts") != reduced["gate_facts"]:
            raise PermissionError("prior claim gate facts do not match raw evidence")
        for key in ("cell_id", "replicate", "cell_spec_sha256"):
            if claim.get(key) != reduced.get(key):
                raise PermissionError("prior claim identity does not match evidence")
        completed.append({"claim": claim, "reduced": reduced})
    return completed


def _runs_for(completed: list[dict[str, Any]], cell_id: str) -> list[dict[str, Any]]:
    return sorted(
        (item for item in completed if item["claim"].get("cell_id") == cell_id),
        key=lambda item: int(item["claim"].get("replicate", 0)),
    )


def _three_valid_runs(runs: list[dict[str, Any]], *, full_success: bool) -> bool:
    if [item["claim"].get("replicate") for item in runs] != [1, 2, 3]:
        return False
    for item in runs:
        reduced = item["reduced"]
        if not reduced["valid"]:
            return False
        if full_success and not (
            reduced["status"] == "SUCCESS"
            and reduced["full_workload_complete"]
            and reduced["correctness_ok"]
        ):
            return False
        if not full_success and reduced["status"] not in {"SUCCESS", "OOM"}:
            return False
    return True


def _controls_without_profiler(run: dict[str, Any]) -> dict[str, Any]:
    controls = dict(run["reduced"]["effective_controls"])
    controls.pop("profiler_characterization", None)
    return controls


def _condition_controls(
    runs: list[dict[str, Any]], *, cell_id: str
) -> dict[str, Any] | None:
    if not runs:
        return None
    controls = _controls_without_profiler(runs[0])
    if any(_controls_without_profiler(run) != controls for run in runs):
        raise PermissionError(f"{cell_id} replicate controls are inconsistent")
    return controls


def _reference_run(completed: list[dict[str, Any]]) -> dict[str, Any] | None:
    references = _runs_for(completed, "M0")
    reference = next(
        (
            item["reduced"]
            for item in references
            if item["reduced"].get("vectors") is not None
            and item["reduced"].get("correctness_ok")
        ),
        None,
    )
    if reference is not None:
        return reference
    cpu_runs = _runs_for(completed, "CPU_ONNX_REFERENCE")
    if len(cpu_runs) == 1 and cpu_runs[0]["reduced"].get("correctness_ok"):
        return cpu_runs[0]["reduced"]
    return None


def _qualified_candidate(
    *,
    cell_id: str,
    target_peak_key: str,
    baseline_items: list[dict[str, Any]],
    treatment_items: list[dict[str, Any]],
    reference: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    if not _three_valid_runs(treatment_items, full_success=True):
        return None
    if reference is None:
        return None
    baseline_runs = [item["reduced"] for item in baseline_items]
    treatment_runs = [item["reduced"] for item in treatment_items]
    if cell_id == "M2":
        baseline_runs = [
            {**run, "target_phase_complete": run["load_phase_complete"]}
            for run in baseline_runs
        ]
    mechanism = evaluate_mechanism_pairs(
        baseline_runs=baseline_runs,
        treatment_runs=treatment_runs,
        target_peak_key=target_peak_key,
    )
    try:
        parity_results = [
            evaluate_parity(
                reference_documents=reference["vectors"]["documents"],
                candidate_documents=run["vectors"]["documents"],
                reference_queries=reference["vectors"]["queries"],
                candidate_queries=run["vectors"]["queries"],
            )
            for run in treatment_runs
        ]
    except KeyError, TypeError, ValueError:
        return None
    candidate = evaluate_production_candidate(
        mechanism=mechanism,
        baseline_runs=baseline_runs,
        treatment_runs=treatment_runs,
        parity_results=parity_results,
        other_peak_keys=(
            ("load_peak_allocated_bytes", "load_peak_reserved_bytes")
            if cell_id == "M2"
            else ()
        ),
    )
    if (
        mechanism.get("mechanism") != "SUPPORTED"
        or candidate.get("candidate") != "QUALIFIED"
    ):
        return None
    controls = _controls_without_profiler(treatment_items[0])
    return cell_id, controls


def _qualified_treatments(
    completed: list[dict[str, Any]], *, through: str = "M4"
) -> list[tuple[str, dict[str, Any]]]:
    """Derive cumulative active controls only from supported qualified cells."""
    stage_order = {"M1": 1, "M2": 2, "M3": 3, "M4": 4}
    if through not in stage_order.values() and through not in stage_order:
        raise ValueError("unknown accepted-treatment boundary")
    limit = stage_order.get(through, through)
    qualified: list[tuple[str, dict[str, Any]]] = []
    references = _runs_for(completed, "M0")
    if not _three_valid_runs(references, full_success=False):
        return qualified
    reference = _reference_run(completed)

    if limit >= stage_order["M1"]:
        m1 = _runs_for(completed, "M1")
        m1_controls = _condition_controls(m1, cell_id="M1")
        baseline_controls = _condition_controls(references, cell_id="M0")
        if (
            m1_controls is not None
            and baseline_controls is not None
            and _three_valid_runs(m1, full_success=True)
            and all(
                not run["reduced"]["gate_facts"]["cache_config_enabled"]
                and not run["reduced"]["gate_facts"]["cache_activation_witness"]
                for run in m1
            )
        ):
            accepted = _qualified_candidate(
                cell_id="M1",
                target_peak_key="target_peak_bytes",
                baseline_items=references,
                treatment_items=m1,
                reference=reference,
            )
            if accepted is not None:
                qualified.append(accepted)

    if limit >= stage_order["M2"]:
        m2 = _runs_for(completed, "M2")
        if _three_valid_runs(m2, full_success=True):
            m2_baseline = _runs_for(completed, "M1") if qualified else references
            accepted = _qualified_candidate(
                cell_id="M2",
                target_peak_key="load_device_peak_bytes",
                baseline_items=m2_baseline,
                treatment_items=m2,
                reference=reference,
            )
            if accepted is not None:
                qualified.append(accepted)

    if limit >= stage_order["M3"]:
        m3_a = _runs_for(completed, "M3_A")
        m3_b = _runs_for(completed, "M3_B")
        if m3_b and not _three_valid_runs(m3_a, full_success=True):
            raise PermissionError("M3_B cannot precede a completed M3_A condition")
        pre_m3 = _qualified_treatments(completed, through="M2")
        m3_baseline_cell = pre_m3[-1][0] if pre_m3 else "M0"
        m3_baseline = _runs_for(completed, m3_baseline_cell)
        m3_candidates = [
            candidate
            for cell_id, runs in (("M3_A", m3_a), ("M3_B", m3_b))
            if (
                candidate := _qualified_candidate(
                    cell_id=cell_id,
                    target_peak_key="target_peak_bytes",
                    baseline_items=m3_baseline,
                    treatment_items=runs,
                    reference=reference,
                )
            )
            is not None
        ]
        if len(m3_candidates) > 1:
            raise PermissionError(
                "multiple qualified M3 alternatives make ACTIVE_CONTROLS ambiguous"
            )
        qualified.extend(m3_candidates)

    if limit >= stage_order["M4"]:
        m4 = _runs_for(completed, "M4")
        if _three_valid_runs(m4, full_success=True):
            m4_baseline_cell = qualified[-1][0] if qualified else "M0"
            accepted = _qualified_candidate(
                cell_id="M4",
                target_peak_key="target_peak_bytes",
                baseline_items=_runs_for(completed, m4_baseline_cell),
                treatment_items=m4,
                reference=reference,
            )
            if accepted is not None:
                qualified.append(accepted)
    return qualified


def _active_condition(
    completed: list[dict[str, Any]], *, through: str
) -> tuple[str, dict[str, Any], list[dict[str, Any]]] | None:
    """Return the three runs matching controls accepted through one stage."""
    baseline = _runs_for(completed, "M0")
    if not _three_valid_runs(baseline, full_success=False):
        return None
    active_cell = "M0"
    active_controls = _condition_controls(baseline, cell_id="M0")
    if active_controls is None:
        return None
    accepted = _qualified_treatments(completed, through=through)
    if accepted:
        active_cell, active_controls = accepted[-1]
    active_runs = _runs_for(completed, active_cell)
    if _condition_controls(active_runs, cell_id=active_cell) != active_controls:
        raise PermissionError("ACTIVE_CONTROLS do not match their raw replicate set")
    return active_cell, active_controls, active_runs


def _cache_state(completed: list[dict[str, Any]]) -> str:
    m0 = _runs_for(completed, "M0")
    if not _three_valid_runs(m0, full_success=False):
        return "UNRESOLVED"
    facts = [item["reduced"]["gate_facts"] for item in m0]
    if not all(fact["cache_config_known"] for fact in facts):
        return "INCONCLUSIVE"
    if not any(fact["cache_config_enabled"] for fact in facts):
        return "DISABLED_BY_BASELINE"
    if not any(fact["cache_activation_witness"] for fact in facts):
        return "BASELINE_CACHE_UNACTIVATED"
    m1 = _runs_for(completed, "M1")
    if not _three_valid_runs(m1, full_success=False):
        return "M1_REQUIRED_OR_FAILED"
    if any(
        cell_id == "M1" for cell_id, _ in _qualified_treatments(completed, through="M1")
    ):
        return "DISABLED_BY_M1"
    return "BASELINE_CACHE_RETAINED"


def _m3_opening_supported(completed: list[dict[str, Any]]) -> bool:
    """Apply Amendment 001 to the accepted active-state forward evidence."""
    active = _active_condition(completed, through="M2")
    if active is None:
        return False
    _active_cell, _controls, runs = active
    if not _three_valid_runs(runs, full_success=False):
        return False
    forward_peaks = [run["reduced"].get("forward_peak_bytes") for run in runs]
    increments = [
        run["reduced"].get("forward_incremental_allocated_bytes") for run in runs
    ]
    if all(
        isinstance(peak, int)
        and not isinstance(peak, bool)
        and isinstance(increment, int)
        and not isinstance(increment, bool)
        for peak, increment in zip(forward_peaks, increments, strict=True)
    ):
        threshold = max(
            MATERIAL_MEMORY_FLOOR_BYTES,
            statistics.median(forward_peaks) * MATERIAL_MEMORY_FRACTION,
        )
        successful_forward_trigger = (
            statistics.median(increments) >= threshold
            and sum(increment >= threshold for increment in increments) >= 2
        )
        if successful_forward_trigger:
            return True
    forward_ooms = sum(
        run["reduced"]["gate_facts"].get("forward_oom_observed") is True for run in runs
    )
    return forward_ooms >= 2


def _m4_opening_supported(completed: list[dict[str, Any]]) -> bool:
    """Apply Amendment 001's token-padding applicability proxy to active state."""
    active = _active_condition(completed, through="M3")
    if active is None:
        return False
    _active_cell, _controls, runs = active
    if not _three_valid_runs(runs, full_success=False):
        return False
    token_count_lists = [
        (run["reduced"].get("token_metrics") or {}).get("token_counts") for run in runs
    ]
    if any(
        not isinstance(counts, list)
        or len(counts) != 32
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count <= 0
            for count in counts
        )
        for counts in token_count_lists
    ):
        return False
    if any(counts != token_count_lists[0] for counts in token_count_lists[1:]):
        return False
    counts = token_count_lists[0]
    partitions = greedy_token_partitions(counts)
    if partitions is None or len(partitions) <= 1:
        return False
    fixed_padded = len(counts) * max(counts)
    partitioned_padded = sum(
        len(partition) * max(counts[index] for index in partition)
        for partition in partitions
    )
    savings_fraction = (fixed_padded - partitioned_padded) / fixed_padded
    return (
        partitioned_padded < fixed_padded
        and savings_fraction >= MATERIAL_MEMORY_FRACTION
    )


def _observed_baseline_sdpa_backend(completed: list[dict[str, Any]]) -> str:
    profile = _runs_for(completed, "M3_PROFILE")
    if len(profile) != 1 or not profile[0]["reduced"].get("full_workload_complete"):
        return "UNKNOWN"
    operators = profile[0]["reduced"].get("profiler_operators")
    if not isinstance(operators, list):
        return "UNKNOWN"

    operator_backend_markers = {
        "FLASH_ATTENTION": ("_scaled_dot_product_flash_attention",),
        "EFFICIENT_ATTENTION": ("_scaled_dot_product_efficient_attention",),
        "CUDNN_ATTENTION": ("_scaled_dot_product_cudnn_attention",),
        "MATH": (
            "_scaled_dot_product_attention_math",
            "_scaled_dot_product_math_attention",
        ),
    }
    observed = {
        backend
        for operator in operators
        if isinstance(operator, str)
        for backend, markers in operator_backend_markers.items()
        if any(marker in operator for marker in markers)
    }
    return next(iter(observed)) if len(observed) == 1 else "UNKNOWN"


def _eligible_sdpa_backends(completed: list[dict[str, Any]]) -> set[str]:
    profile = _runs_for(completed, "M3_PROFILE")
    if len(profile) != 1 or not profile[0]["reduced"].get("full_workload_complete"):
        return set()
    baseline_backend = _observed_baseline_sdpa_backend(completed)
    if baseline_backend == "UNKNOWN":
        return set()

    calls = (profile[0]["reduced"].get("sdpa_observation") or {}).get("calls", [])
    if not calls:
        return set()
    eligible_by_call = [
        {
            backend
            for backend, eligible in call.get("eligible_backends", {}).items()
            if eligible is True
        }
        for call in calls
    ]
    if any(not backends for backends in eligible_by_call):
        return set()
    eligible_for_all_calls = set.intersection(*eligible_by_call)
    return eligible_for_all_calls - {baseline_backend}


def _has_authorized_replicates(
    authority: dict[str, Any], *, cell_id: str, replicate_count: int
) -> bool:
    """Return whether every required replicate has a valid exact spec hash."""
    return all(
        authorized_cell_spec_hashes(authority, cell_id=cell_id, replicate=replicate)
        for replicate in range(1, replicate_count + 1)
    )


def _m3_treatment_completed(
    completed: list[dict[str, Any]], authority: dict[str, Any]
) -> bool:
    if not _m3_opening_supported(completed):
        return True
    profile = _runs_for(completed, "M3_PROFILE")
    if len(profile) != 1 or not profile[0]["reduced"].get("full_workload_complete"):
        return False
    if _observed_baseline_sdpa_backend(completed) == "UNKNOWN":
        return False
    eligible = _eligible_sdpa_backends(completed)
    if not eligible:
        return True
    if not _has_authorized_replicates(authority, cell_id="M3_A", replicate_count=3):
        return False
    m3_a = _runs_for(completed, "M3_A")
    if not _three_valid_runs(m3_a, full_success=True):
        return False
    selected_a = m3_a[0]["reduced"]["effective_controls"].get("attention_backend")
    remaining = eligible - {selected_a}
    if not remaining:
        return True
    if not _has_authorized_replicates(authority, cell_id="M3_B", replicate_count=3):
        return False
    m3_b = _runs_for(completed, "M3_B")
    if not _three_valid_runs(m3_b, full_success=True):
        return False
    selected_b = m3_b[0]["reduced"]["effective_controls"].get("attention_backend")
    return selected_b in remaining


def authorize_cell_start(
    *,
    claims_dir: Path,
    requested_replicate: int,
    requested_spec: dict[str, Any],
    authority: dict[str, Any],
    workload: dict[str, Any],
    implementation_subject: str,
) -> None:
    """Fail closed unless raw completed evidence satisfies the next gate."""
    completed = _load_completed_claims(
        claims_dir=claims_dir,
        authority=authority,
        workload=workload,
        implementation_subject=implementation_subject,
    )
    cell_id = requested_spec.get("cell_id")
    m0 = _runs_for(completed, "M0")
    if _runs_for(completed, "M5") and cell_id != "M5":
        raise PermissionError("campaign stops after the M5 confirmation sequence")
    requested_controls = effective_controls_from_spec(requested_spec)
    prior_same_cell = _runs_for(completed, str(cell_id))
    if (
        prior_same_cell
        and requested_controls != prior_same_cell[0]["reduced"]["effective_controls"]
    ):
        raise PermissionError("replicate controls differ within one cell condition")
    if cell_id == "M0":
        if any(item["claim"].get("cell_id") != "M0" for item in completed):
            raise PermissionError(
                "M0 baseline sequence cannot resume after a treatment"
            )
        if requested_replicate != len(m0) + 1:
            raise PermissionError("M0 replicates must follow evidence order")
        return
    if cell_id == "M1":
        if not _three_valid_runs(m0, full_success=False):
            raise PermissionError("three valid M0 cells are required before M1")
        m1 = _runs_for(completed, "M1")
        if requested_replicate != len(m1) + 1:
            raise PermissionError("M1 replicates must follow evidence order")
        facts = [item["reduced"]["gate_facts"] for item in m0]
        if not all(fact["cache_config_known"] for fact in facts):
            raise PermissionError("M0 cache configuration is inconclusive")
        if not any(
            fact["cache_config_enabled"] and fact["cache_activation_witness"]
            for fact in facts
        ):
            raise PermissionError("M1 is not applicable from M0 evidence")
        return

    if cell_id == "CPU_ONNX_REFERENCE":
        if not _three_valid_runs(m0, full_success=False) or not any(
            item["reduced"]["status"] == "OOM" for item in m0
        ):
            raise PermissionError("CPU reference requires valid M0 CUDA OOM evidence")
        return

    cache_state = _cache_state(completed)
    if cache_state not in {
        "DISABLED_BY_BASELINE",
        "DISABLED_BY_M1",
        "BASELINE_CACHE_RETAINED",
        "BASELINE_CACHE_UNACTIVATED",
    }:
        raise PermissionError("accepted cache state is not derivable from raw evidence")

    active_before_m2 = _active_condition(completed, through="M1")
    if active_before_m2 is None:
        raise PermissionError("M0 active controls are not derivable")
    _active_cell, active_controls, _active_runs = active_before_m2

    m2 = _runs_for(completed, "M2")
    if cell_id == "M2":
        if requested_replicate != len(m2) + 1:
            raise PermissionError("M2 replicates must follow evidence order")
        if requested_replicate == 1 and not _three_valid_runs(m0, full_success=False):
            raise PermissionError("M2 requires three valid baseline cells")
        expected_controls = dict(active_controls)
        expected_controls["dtype_mode"] = "direct_fp16"
        expected_controls["profiler_characterization"] = False
        if requested_controls != expected_controls:
            raise PermissionError(
                "M2 controls do not preserve the accepted prior state"
            )
        return

    if not _three_valid_runs(m2, full_success=False):
        raise PermissionError("three valid M2 cells are required before later stages")
    if cell_id == "M3_PROFILE":
        if not _m3_opening_supported(completed):
            raise PermissionError(
                "M3 applicability is not supported by active-state forward evidence"
            )
        if requested_replicate != 1:
            raise PermissionError("M3 profiler characterization is one process")
        active_before_m3 = _active_condition(completed, through="M2")
        if active_before_m3 is None:
            raise PermissionError("M3 active controls are not derivable")
        _active_cell, active_controls, _active_runs = active_before_m3
        expected_controls = {
            **active_controls,
            "profiler_characterization": True,
        }
        if requested_controls != expected_controls:
            raise PermissionError("M3 profiler cell changed the accepted runtime state")
        return
    if cell_id in {"M3_A", "M3_B"}:
        profile = _runs_for(completed, "M3_PROFILE")
        if (
            not _m3_opening_supported(completed)
            or len(profile) != 1
            or not profile[0]["reduced"].get("full_workload_complete")
        ):
            raise PermissionError("M3 treatment requires completed profiler evidence")
        if _observed_baseline_sdpa_backend(completed) == "UNKNOWN":
            raise PermissionError("BASELINE_ATTENTION_BACKEND_UNRESOLVED")
        backends = _eligible_sdpa_backends(completed)
        treatments = _runs_for(completed, "M3_A") if cell_id == "M3_B" else []
        if not backends or (
            cell_id == "M3_B" and not _three_valid_runs(treatments, full_success=True)
        ):
            raise PermissionError(
                "M3 treatment is not supported by observed eligibility"
            )
        if cell_id == "M3_B":
            selected_a = treatments[0]["reduced"]["effective_controls"].get(
                "attention_backend"
            )
            backends.discard(selected_a)
            if not backends:
                raise PermissionError("M3_B has no second eligible backend")
        if requested_replicate != len(_runs_for(completed, cell_id)) + 1:
            raise PermissionError("M3 treatment replicates must follow evidence order")
        active_before_m3 = _active_condition(completed, through="M2")
        if active_before_m3 is None:
            raise PermissionError("M3 active controls are not derivable")
        _active_cell, expected_controls, _active_runs = active_before_m3
        if requested_controls.get("attention_backend") not in backends:
            raise PermissionError("M3 backend is not supported by observed eligibility")
        expected_controls["attention_backend"] = requested_controls["attention_backend"]
        expected_controls["profiler_characterization"] = False
        if requested_controls != expected_controls:
            raise PermissionError(
                "M3 treatment changes more than its attention backend"
            )
        return
    if cell_id == "M4":
        profile = _runs_for(completed, "M3_PROFILE")
        if not _m4_opening_supported(completed):
            raise PermissionError(
                "M4 is not opened by the frozen token-budget evidence"
            )
        if not _m3_treatment_completed(completed, authority):
            raise PermissionError("M4 requires the opened M3 path to be resolved")
        if _m3_opening_supported(completed) and len(profile) != 1:
            raise PermissionError("M4 requires the M3 applicability observation")
        active_before_m4 = _active_condition(completed, through="M3")
        if active_before_m4 is None:
            raise PermissionError("M4 active controls are not derivable")
        _active_cell, expected_controls, _active_runs = active_before_m4
        expected_controls["batch_strategy"] = "m4_partitions"
        expected_controls["profiler_characterization"] = False
        if requested_controls != expected_controls:
            raise PermissionError("M4 changes more than the frozen token partitions")
        return
    if cell_id == "M5":
        m5 = _runs_for(completed, "M5")
        if requested_replicate != len(m5) + 1:
            raise PermissionError("M5 replicates must follow evidence order")
        if requested_replicate == 1:
            if not _m3_treatment_completed(completed, authority):
                raise PermissionError("M5 requires the opened M3 path to be resolved")
            if _m4_opening_supported(completed) and not _three_valid_runs(
                _runs_for(completed, "M4"), full_success=True
            ):
                raise PermissionError("M5 requires the opened M4 path to be resolved")
            settings = requested_spec.get("selected_candidate_settings")
            if not isinstance(settings, dict):
                raise PermissionError("M5 requires frozen selected candidate settings")
            eligible = _qualified_treatments(completed, through="M4")
            if not eligible:
                raise PermissionError(
                    "M5 is not applicable without a qualified treatment"
                )
            if eligible[-1][1] != settings:
                raise PermissionError(
                    "M5 settings do not match final evidence-derived ACTIVE_CONTROLS"
                )
        return
    raise PermissionError("requested campaign cell has no evidence-derived gate")
