"""Evidence-derived campaign sequencing for the R04 diagnostic cells."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .contract import (
    evaluate_mechanism_pairs,
    evaluate_parity,
    evaluate_production_candidate,
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


def _cache_state(completed: list[dict[str, Any]]) -> str:
    m0 = _runs_for(completed, "M0")
    if not _three_valid_runs(m0, full_success=False):
        return "UNRESOLVED"
    facts = [item["reduced"]["gate_facts"] for item in m0]
    if not all(fact["cache_config_known"] for fact in facts):
        return "INCONCLUSIVE"
    if not any(fact["cache_config_enabled"] for fact in facts):
        return "DISABLED_BY_BASELINE"
    if any(fact["cache_activation_witness"] for fact in facts):
        m1 = _runs_for(completed, "M1")
        if not _three_valid_runs(m1, full_success=True):
            return "M1_REQUIRED_OR_FAILED"
        m1_facts = [item["reduced"]["gate_facts"] for item in m1]
        if not all(not fact["cache_config_enabled"] for fact in m1_facts):
            return "M1_FAILED_CACHE_DISABLE"
        if not all(not fact["cache_activation_witness"] for fact in m1_facts):
            return "M1_FAILED_CACHE_REMAINS_ACTIVE"
        if any(
            cell_id == "M1" for cell_id, _settings in _qualified_treatments(completed)
        ):
            return "DISABLED_BY_M1"
        return "BASELINE_CACHE_RETAINED"
    return "BASELINE_CACHE_UNACTIVATED"


def _qualified_treatments(
    completed: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    qualified: list[tuple[str, dict[str, Any]]] = []
    target_cells = {
        "M1": "target_peak_bytes",
        "M2": "load_device_peak_bytes",
        "M3_A": "target_peak_bytes",
        "M3_B": "target_peak_bytes",
        "M4": "target_peak_bytes",
    }
    references = _runs_for(completed, "M0")
    if not _three_valid_runs(references, full_success=False):
        return qualified
    reference_run = next(
        (
            item["reduced"]
            for item in references
            if item["reduced"].get("vectors") is not None
            and item["reduced"].get("correctness_ok")
        ),
        None,
    )
    if reference_run is None:
        cpu_runs = _runs_for(completed, "CPU_ONNX_REFERENCE")
        if len(cpu_runs) == 1 and cpu_runs[0]["reduced"].get("correctness_ok"):
            reference_run = cpu_runs[0]["reduced"]
    if reference_run is None:
        return qualified

    for cell_id, target_peak_key in target_cells.items():
        treatment_items = _runs_for(completed, cell_id)
        if not _three_valid_runs(treatment_items, full_success=True):
            continue
        prior_accepted = next(
            (
                settings
                for prior_cell, settings in reversed(qualified)
                if prior_cell != cell_id
            ),
            None,
        )
        baseline_items = references
        if cell_id == "M2" and any(
            prior_cell == "M1" for prior_cell, _settings in qualified
        ):
            baseline_items = _runs_for(completed, "M1")
        elif cell_id in {"M3_A", "M3_B", "M4"} and prior_accepted is not None:
            prior_cell = next(
                prior_cell
                for prior_cell, settings in reversed(qualified)
                if settings is prior_accepted
            )
            baseline_items = _runs_for(completed, prior_cell)
        baseline_runs = [item["reduced"] for item in baseline_items]
        treatment_runs = [item["reduced"] for item in treatment_items]
        if cell_id == "M2":
            baseline_runs = [
                {
                    **run,
                    "target_phase_complete": run["load_phase_complete"],
                }
                for run in baseline_runs
            ]
        mechanism = evaluate_mechanism_pairs(
            baseline_runs=baseline_runs,
            treatment_runs=treatment_runs,
            target_peak_key=target_peak_key,
        )
        parity_results = []
        try:
            for run in treatment_runs:
                parity_results.append(
                    evaluate_parity(
                        reference_documents=reference_run["vectors"]["documents"],
                        candidate_documents=run["vectors"]["documents"],
                        reference_queries=reference_run["vectors"]["queries"],
                        candidate_queries=run["vectors"]["queries"],
                    )
                )
        except KeyError, TypeError, ValueError:
            continue
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
        if candidate.get("candidate") != "QUALIFIED":
            continue
        controls = dict(treatment_runs[0]["effective_controls"])
        controls.pop("profiler_characterization", None)
        merged = dict(prior_accepted or {})
        merged.update(controls)
        qualified.append((cell_id, merged))
    return qualified


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

    baseline_items = _runs_for(completed, "M0")
    if not baseline_items:
        raise PermissionError("M0 baseline evidence is absent")
    baseline_controls = dict(baseline_items[0]["reduced"]["effective_controls"])
    baseline_controls.pop("profiler_characterization", None)
    active_controls = dict(baseline_controls)
    qualified_treatments = _qualified_treatments(completed)
    if qualified_treatments:
        active_controls.update(qualified_treatments[-1][1])

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

    if not _three_valid_runs(m2, full_success=True):
        raise PermissionError("three successful M2 cells are required")
    if cell_id == "M3_PROFILE":
        if requested_replicate != 1:
            raise PermissionError("M3 profiler characterization is one process")
        expected_controls = {
            **active_controls,
            "profiler_characterization": True,
        }
        if requested_controls != expected_controls:
            raise PermissionError("M3 profiler cell changed the accepted runtime state")
        return
    if cell_id in {"M3_A", "M3_B"}:
        profile = _runs_for(completed, "M3_PROFILE")
        if len(profile) != 1 or not profile[0]["reduced"]["valid"]:
            raise PermissionError("M3 treatment requires completed profiler evidence")
        eligible = (profile[0]["reduced"].get("sdpa_observation") or {}).get(
            "calls", []
        )
        backends = {
            backend
            for call in eligible
            for backend, is_eligible in call.get("eligible_backends", {}).items()
            if is_eligible is True and backend != "MATH"
        }
        treatments = _runs_for(completed, "M3_A") if cell_id == "M3_B" else []
        if not backends or (cell_id == "M3_B" and len(treatments) != 3):
            raise PermissionError(
                "M3 treatment is not supported by observed eligibility"
            )
        if requested_replicate != len(_runs_for(completed, cell_id)) + 1:
            raise PermissionError("M3 treatment replicates must follow evidence order")
        expected_controls = dict(active_controls)
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
        if len(profile) != 1:
            raise PermissionError("M4 requires the M3 applicability observation")
        expected_controls = dict(active_controls)
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
            settings = requested_spec.get("selected_candidate_settings")
            if not isinstance(settings, dict):
                raise PermissionError("M5 requires frozen selected candidate settings")
            eligible = _qualified_treatments(completed)
            if not eligible or eligible[-1][1] != settings:
                raise PermissionError(
                    "M5 settings do not match a raw-evidence-qualified treatment"
                )
        return
    raise PermissionError("requested campaign cell has no evidence-derived gate")
