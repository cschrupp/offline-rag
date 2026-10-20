#!/usr/bin/env python3
"""Regenerate D1 frozen analysis from sealed A1/A2/B evidence only.

Authority: S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001
No model calls. No new scientific cells.
"""

from __future__ import annotations

import json
import math
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/16k_d_dense_cuda/d1"
REWORK_AUTH = "S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001"
EXEC_AUTH = "S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001"
MATRIX_PARENT = "0ecf2f74e4d283f59ab932abbdaee6ebb821a5ac"
TOOLING_SUBJECT = "433725952c15a2feed4b65986d03e254d08d1568"
EXECUTION_HEAD = "177620a3440c310759775dbf303420b80df7a05c"
SEALED_EVIDENCE_TIP = "4326586fe0ce3b7ca4c40ded743272d72ba53036"

D1B_CELL = {1: "F1", 14: "S1", 17: "F2", 13: "S2", 4: "D1", 6: "D2"}


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _load(name: str) -> dict[str, Any]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry, strict=True))
    return 1.0 - (6.0 * d2) / (n * (n * n - 1))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0.0 or deny == 0.0:
        return None
    return num / (denx * deny)


def _walls(evidence: dict[str, Any]) -> list[float]:
    return [float(b["encode_ms"]) for b in evidence.get("batches") or []]


def _residual_stats(batches: list[dict[str, Any]]) -> dict[str, Any]:
    residuals = [
        float(b["wall_minus_device_ms"])
        for b in batches
        if b.get("wall_minus_device_ms") is not None
        and b.get("encode_cuda_device_status") == "observed"
    ]
    return {
        "n": len(residuals),
        "mean_ms": statistics.fmean(residuals) if residuals else None,
        "stdev_ms": statistics.pstdev(residuals) if len(residuals) > 1 else None,
        "min_ms": min(residuals) if residuals else None,
        "max_ms": max(residuals) if residuals else None,
        "abs_mean_ms": statistics.fmean(abs(x) for x in residuals) if residuals else None,
    }


def _wall_device_pearson(batches: list[dict[str, Any]]) -> float | None:
    pairs = [
        (float(b["encode_ms"]), float(b["encode_cuda_device_ms"]))
        for b in batches
        if b.get("encode_cuda_device_status") == "observed"
        and b.get("encode_cuda_device_ms") is not None
    ]
    if not pairs:
        return None
    return _pearson([p[0] for p in pairs], [p[1] for p in pairs])


def _shape_corrs(batches: list[dict[str, Any]]) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for field in (
        "max_sequence_length",
        "aggregate_input_tokens",
        "padded_token_workload",
        "padding_fraction",
    ):
        xs: list[float] = []
        ys: list[float] = []
        for b in batches:
            if b.get("encode_ms") is None or b.get(field) is None:
                continue
            xs.append(float(b["encode_ms"]))
            ys.append(float(b[field]))
        out[field] = _pearson(xs, ys)
    return out


def _assoc_numeric(
    batches: list[dict[str, Any]], extractor
) -> dict[str, Any]:
    xs: list[float] = []
    ys: list[float] = []
    for b in batches:
        y = extractor(b)
        if y is None or b.get("encode_ms") is None:
            continue
        xs.append(float(b["encode_ms"]))
        ys.append(float(y))
    return {
        "n": len(xs),
        "pearson_with_encode_ms": _pearson(xs, ys),
        "y_mean": statistics.fmean(ys) if ys else None,
        "y_stdev": statistics.pstdev(ys) if len(ys) > 1 else None,
        "y_min": min(ys) if ys else None,
        "y_max": max(ys) if ys else None,
    }


def _assoc_categorical(
    batches: list[dict[str, Any]], extractor
) -> dict[str, Any]:
    groups: dict[str, list[float]] = defaultdict(list)
    for b in batches:
        key = extractor(b)
        if key is None or b.get("encode_ms") is None:
            continue
        groups[str(key)].append(float(b["encode_ms"]))
    summary = {
        k: {
            "n": len(v),
            "encode_ms_mean": statistics.fmean(v),
            "encode_ms_stdev": statistics.pstdev(v) if len(v) > 1 else 0.0,
            "encode_ms_min": min(v),
            "encode_ms_max": max(v),
        }
        for k, v in sorted(groups.items())
    }
    return {"n_batches": sum(len(v) for v in groups.values()), "by_value": summary}


def _system_state_associations(batches: list[dict[str, Any]]) -> dict[str, Any]:
    def cpu(field: str):
        return lambda b: (b.get("process_cpu_delta") or {}).get(field)

    def alloc(field: str):
        def _f(b: dict[str, Any]) -> float | None:
            a = b.get("cuda_allocator_after") or {}
            if a.get("status") != "observed":
                return None
            val = a.get(field)
            return float(val) if val is not None else None

        return _f

    def gpu(field: str):
        def _f(b: dict[str, Any]) -> float | None:
            sample = (b.get("gpu_external_after") or {}).get("sample")
            if not sample:
                return None
            val = sample.get(field)
            return float(val) if isinstance(val, (int, float)) else None

        return _f

    def gpu_cat(field: str):
        def _f(b: dict[str, Any]) -> str | None:
            sample = (b.get("gpu_external_after") or {}).get("sample")
            if not sample:
                return None
            val = sample.get(field)
            return None if val is None else str(val)

        return _f

    return {
        "cpu_user_time_s": _assoc_numeric(batches, cpu("user_time_s")),
        "cpu_system_time_s": _assoc_numeric(batches, cpu("system_time_s")),
        "cpu_time_s": _assoc_numeric(batches, cpu("cpu_time_s")),
        "voluntary_context_switches": _assoc_numeric(
            batches, cpu("voluntary_context_switches")
        ),
        "involuntary_context_switches": _assoc_numeric(
            batches, cpu("involuntary_context_switches")
        ),
        "allocator_allocated_bytes": _assoc_numeric(batches, alloc("allocated_bytes")),
        "allocator_reserved_bytes": _assoc_numeric(batches, alloc("reserved_bytes")),
        "allocator_peak_allocated_bytes": _assoc_numeric(
            batches, alloc("peak_allocated_bytes")
        ),
        "clock_graphics_mhz": _assoc_numeric(batches, gpu("clock_graphics_mhz")),
        "clock_sm_mhz": _assoc_numeric(batches, gpu("clock_sm_mhz")),
        "clock_memory_mhz": _assoc_numeric(batches, gpu("clock_memory_mhz")),
        "power_draw_w": _assoc_numeric(batches, gpu("power_draw_w")),
        "temperature_c": _assoc_numeric(batches, gpu("temperature_c")),
        "utilization_gpu_pct": _assoc_numeric(batches, gpu("utilization_gpu_pct")),
        "pstate": _assoc_categorical(batches, gpu_cat("pstate")),
        "throttle_sw_power_cap": _assoc_categorical(
            batches, gpu_cat("throttle_sw_power_cap")
        ),
        "throttle_hw_thermal_slowdown": _assoc_categorical(
            batches, gpu_cat("throttle_hw_thermal_slowdown")
        ),
        "throttle_sw_thermal_slowdown": _assoc_categorical(
            batches, gpu_cat("throttle_sw_thermal_slowdown")
        ),
        "throttle_hw_slowdown": _assoc_categorical(
            batches, gpu_cat("throttle_hw_slowdown")
        ),
    }


def _system_state_rows(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for b in batches:
        cpu = b.get("process_cpu_delta") or {}
        alloc = b.get("cuda_allocator_after") or {}
        gpu = (b.get("gpu_external_after") or {}).get("sample") or {}
        rows.append(
            {
                "batch_index": b.get("batch_index"),
                "encode_ms": b.get("encode_ms"),
                "encode_cuda_device_ms": b.get("encode_cuda_device_ms"),
                "wall_minus_device_ms": b.get("wall_minus_device_ms"),
                "cpu_user_time_s": cpu.get("user_time_s"),
                "cpu_system_time_s": cpu.get("system_time_s"),
                "cpu_time_s": cpu.get("cpu_time_s"),
                "voluntary_context_switches": cpu.get("voluntary_context_switches"),
                "involuntary_context_switches": cpu.get(
                    "involuntary_context_switches"
                ),
                "allocator_allocated_bytes": alloc.get("allocated_bytes"),
                "allocator_reserved_bytes": alloc.get("reserved_bytes"),
                "allocator_peak_allocated_bytes": alloc.get("peak_allocated_bytes"),
                "allocator_status": alloc.get("status"),
                "temperature_c": gpu.get("temperature_c"),
                "power_draw_w": gpu.get("power_draw_w"),
                "clock_sm_mhz": gpu.get("clock_sm_mhz"),
                "clock_graphics_mhz": gpu.get("clock_graphics_mhz"),
                "clock_memory_mhz": gpu.get("clock_memory_mhz"),
                "pstate": gpu.get("pstate"),
                "throttle_sw_power_cap": gpu.get("throttle_sw_power_cap"),
                "throttle_hw_thermal_slowdown": gpu.get(
                    "throttle_hw_thermal_slowdown"
                ),
                "throttle_sw_thermal_slowdown": gpu.get(
                    "throttle_sw_thermal_slowdown"
                ),
                "throttle_hw_slowdown": gpu.get("throttle_hw_slowdown"),
            }
        )
    return rows


def _batch_stats(encodes: list[dict[str, Any]], idx: int) -> dict[str, Any]:
    walls = [
        float(e["measurement"]["encode_ms"])
        for e in encodes
        if int(e["batch_index"]) == idx
    ]
    devices = [
        float(e["measurement"]["encode_cuda_device_ms"])
        for e in encodes
        if int(e["batch_index"]) == idx
        and e["measurement"].get("encode_cuda_device_status") == "observed"
        and e["measurement"].get("encode_cuda_device_ms") is not None
    ]
    return {
        "cell": D1B_CELL[idx],
        "batch_index": idx,
        "n": len(walls),
        "wall_ms_mean": statistics.fmean(walls) if walls else None,
        "wall_ms_stdev": statistics.pstdev(walls) if len(walls) > 1 else 0.0,
        "wall_ms_min": min(walls) if walls else None,
        "wall_ms_max": max(walls) if walls else None,
        "device_ms_mean": statistics.fmean(devices) if devices else None,
        "device_ms_stdev": statistics.pstdev(devices) if len(devices) > 1 else 0.0,
    }


def main() -> int:
    a1 = _load("d1_a1.json")
    a2 = _load("d1_a2.json")
    b = _load("d1_b.json")
    d0_clean = json.loads(
        (
            ROOT / "docs/evidence/16k_d_dense_cuda/d0_baseline_32e52024df47.json"
        ).read_text(encoding="utf-8")
    )
    d0_hist = json.loads(
        (
            ROOT / "docs/evidence/16k_d_dense_cuda/d0_baseline_33a031b6a1bb.json"
        ).read_text(encoding="utf-8")
    )

    for label, cell in (("a1", a1), ("a2", a2), ("b", b)):
        if cell.get("status") != "CELL_VALID":
            print(f"ERROR: sealed {label} not CELL_VALID", file=sys.stderr)
            return 2
        if cell.get("execution_head") != EXECUTION_HEAD:
            print(f"ERROR: sealed {label} execution_head mismatch", file=sys.stderr)
            return 3
    if b.get("encode_count") != 36:
        print("ERROR: sealed B encode_count != 36", file=sys.stderr)
        return 4

    a1w, a2w = _walls(a1), _walls(a2)
    d0c, d0h = _walls(d0_clean), _walls(d0_hist)
    a1b = {int(x["batch_index"]): x for x in a1["batches"]}
    a2b = {int(x["batch_index"]): x for x in a2["batches"]}

    encodes = b["encodes"]
    dispersion = {str(i): _batch_stats(encodes, i) for i in D1B_CELL}
    s1, s14 = _batch_stats(encodes, 1), _batch_stats(encodes, 14)
    s17, s13 = _batch_stats(encodes, 17), _batch_stats(encodes, 13)
    s4, s6 = _batch_stats(encodes, 4), _batch_stats(encodes, 6)

    paired = {
        "pair_1_14": {
            "fast": s1,
            "slow": s14,
            "wall_mean_ratio_slow_over_fast": (
                (s14["wall_ms_mean"] / s1["wall_ms_mean"]) if s1["wall_ms_mean"] else None
            ),
            "a1_wall_ms": {
                1: (a1b.get(1) or {}).get("encode_ms"),
                14: (a1b.get(14) or {}).get("encode_ms"),
            },
            "a2_wall_ms": {
                1: (a2b.get(1) or {}).get("encode_ms"),
                14: (a2b.get(14) or {}).get("encode_ms"),
            },
        },
        "pair_17_13": {
            "fast": s17,
            "slow": s13,
            "wall_mean_ratio_slow_over_fast": (
                (s13["wall_ms_mean"] / s17["wall_ms_mean"])
                if s17["wall_ms_mean"]
                else None
            ),
            "a1_wall_ms": {
                17: (a1b.get(17) or {}).get("encode_ms"),
                13: (a1b.get(13) or {}).get("encode_ms"),
            },
            "a2_wall_ms": {
                17: (a2b.get(17) or {}).get("encode_ms"),
                13: (a2b.get(13) or {}).get("encode_ms"),
            },
        },
        "discordant_4_6": {
            "batch_4": s4,
            "batch_6": s6,
            "a1_wall_ms": {
                4: (a1b.get(4) or {}).get("encode_ms"),
                6: (a1b.get(6) or {}).get("encode_ms"),
            },
            "a2_wall_ms": {
                4: (a2b.get(4) or {}).get("encode_ms"),
                6: (a2b.get(6) or {}).get("encode_ms"),
            },
        },
    }

    # Power-cap co-occurrence with slow vs fast in A1 (>30s vs <15s)
    def power_cap_split(batches: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {
            "slow_gt_30s": Counter(),
            "fast_lt_15s": Counter(),
            "mid": Counter(),
        }
        for bch in batches:
            sample = (bch.get("gpu_external_after") or {}).get("sample") or {}
            cap = str(sample.get("throttle_sw_power_cap") or "unknown")
            ms = float(bch["encode_ms"])
            if ms > 30000:
                counts["slow_gt_30s"][cap] += 1
            elif ms < 15000:
                counts["fast_lt_15s"][cap] += 1
            else:
                counts["mid"][cap] += 1
        return {k: dict(v) for k, v in counts.items()}

    assoc_a1 = _system_state_associations(a1["batches"])
    assoc_a2 = _system_state_associations(a2["batches"])

    hypothesis_disposition = {
        "deterministic_batch_content_shape_effect": {
            "status": "disfavored",
            "rationale": (
                "Full-run A1/A2 latency ranks are highly reproducible, but D1-B "
                "replay of the same identities collapses historical fast/slow gaps "
                "(1↔14 ratio ≈ 0.96; 17↔13 ratio ≈ 1.01). Simple shape correlations "
                "in A1 are moderate-to-weak (max seq ≈ 0.46; aggregate tokens ≈ 0.30; "
                "padded workload ≈ 0.36; padding fraction ≈ 0)."
            ),
        },
        "gpu_device_execution": {
            "status": "supported_as_locus_of_latency",
            "rationale": (
                "A1/A2 wall↔CUDA-device Pearson ≈ 1.0; wall−device residuals are "
                "hundreds of ms while slow batches last tens of seconds. The latency "
                "explosion is represented in device elapsed time, not host-only wait."
            ),
        },
        "host_scheduling_synchronization": {
            "status": "disfavored_as_primary",
            "rationale": (
                "Near-identity of wall and device times implies host/WSL scheduling "
                "outside CUDA work cannot account for the tens-of-seconds stall regime."
            ),
        },
        "power_clock_thermal_state": {
            "status": "not_established",
            "rationale": (
                "SM-clock correlation with latency is weak (~0.27 A1); power draw is "
                "approximately uncorrelated; software power-cap is Active on both fast "
                "and slow batches; no thermal-throttle Active observations in A1/A2. "
                "Temperature associations exist but are confounded with run progression."
            ),
        },
        "allocator_runtime_state": {
            "status": "not_established_as_simple_culprit",
            "rationale": (
                "Allocated bytes are nearly invariant; reserved/peak correlations with "
                "latency are weak (~0.22–0.23 in A1). No clear allocator threshold "
                "separates fast vs slow regimes."
            ),
        },
        "state_history_dependent_gpu_model_execution": {
            "status": "leading_unresolved_class",
            "rationale": (
                "Same batch identities are slow in fresh full-index traversals yet "
                "~5 s in controlled one-model targeted replay. Combined with "
                "device-time co-location of stalls, this favors a process/run-history "
                "dependent GPU/model execution phenomenon over immutable content cost."
            ),
        },
        "unresolved_mixture": {
            "status": "open",
            "rationale": (
                "D1 does not isolate a single ultimate GPU root cause; residual "
                "mixture among runtime/history effects remains possible."
            ),
        },
    }

    scientific_conclusion = {
        "execution_validity": "VALID",
        "summary": (
            "D1 execution is valid. Deterministic full-run latency structure is "
            "confirmed. Intrinsic batch-content/shape explanation is materially "
            "disfavored. Host-only delay is materially disfavored. Simple "
            "allocator/clock/thermal explanations are not established. "
            "State/history-dependent GPU/model execution remains the leading "
            "unresolved class."
        ),
        "d2_comparisons_scientifically_eligible": True,
        "d2_eligibility_conditions": [
            "Treatments must use controlled repeated-run design.",
            "Process/run history must be controlled; do not interpret a single lucky run.",
            "Lane remains BF16 / CUDA / batch-32 / SDPA unless a later AUTH changes it.",
            "D1 wall times remain attribution-only and are not §9.4 confirmation runs.",
        ],
        "no_causal_claim_from_correlation_alone": True,
        "no_production_policy_change": True,
    }

    analysis = {
        "authority": EXEC_AUTH,
        "analysis_rework_authority": REWORK_AUTH,
        "analysis_contract": "d1-frozen-analysis-v2",
        "sealed_execution_head": EXECUTION_HEAD,
        "sealed_evidence_tip": SEALED_EVIDENCE_TIP,
        "analysis_regenerated_at_head": _git_sha(),
        "recorded_at": _utc_now(),
        "matrix_parent": MATRIX_PARENT,
        "matrix_document": "docs/slice16k_d_d1_scientific_matrix_freeze.md",
        "accepted_tooling_subject": TOOLING_SUBJECT,
        "attribution_only_not_section_9_4_gate": True,
        "status": "ANALYSIS_COMPLETE",
        "phase": "analyze",
        "source_cells": {
            "a1": "docs/evidence/16k_d_dense_cuda/d1/d1_a1.json",
            "a2": "docs/evidence/16k_d_dense_cuda/d1/d1_a2.json",
            "b": "docs/evidence/16k_d_dense_cuda/d1/d1_b.json",
            "note": "Derived solely from sealed CELL_VALID evidence; no new encodes.",
        },
        "validity": {
            "a1": a1.get("status"),
            "a2": a2.get("status"),
            "b": b.get("status"),
            "b_encode_count": b.get("encode_count"),
        },
        "a1_a2_batch_rank_spearman": _spearman(a1w, a2w),
        "a1_vs_d0_clean_rank_spearman": _spearman(a1w, d0c),
        "a1_vs_d0_historical_rank_spearman": _spearman(a1w, d0h),
        "a2_vs_d0_clean_rank_spearman": _spearman(a2w, d0c),
        "a2_vs_d0_historical_rank_spearman": _spearman(a2w, d0h),
        "wall_vs_device_pearson_a1": _wall_device_pearson(a1["batches"]),
        "wall_vs_device_pearson_a2": _wall_device_pearson(a2["batches"]),
        "wall_minus_device_residual_a1": _residual_stats(a1["batches"]),
        "wall_minus_device_residual_a2": _residual_stats(a2["batches"]),
        "latency_shape_pearson_a1": _shape_corrs(a1["batches"]),
        "latency_shape_pearson_a2": _shape_corrs(a2["batches"]),
        "d1b_within_batch_dispersion": dispersion,
        "paired_comparisons": paired,
        "system_state_associations_a1": assoc_a1,
        "system_state_associations_a2": assoc_a2,
        "system_state_rows_a1": _system_state_rows(a1["batches"]),
        "system_state_rows_a2": _system_state_rows(a2["batches"]),
        "power_cap_cooccurrence_a1": power_cap_split(a1["batches"]),
        "power_cap_cooccurrence_a2": power_cap_split(a2["batches"]),
        "hypothesis_disposition": hypothesis_disposition,
        "scientific_conclusion": scientific_conclusion,
        "decision_boundary_targets": [
            "deterministic batch/content/shape effect",
            "GPU/device execution",
            "host/scheduling/synchronization",
            "power/clock/thermal state",
            "allocator/runtime state",
            "unresolved mixture",
        ],
        "interpretation_limits": [
            "No causal claim solely from correlation.",
            "D1-A/B wall times are attribution-only; not §9.4 10/12-minute gates.",
            "D1 does not promote or modify production policy.",
            "Temperature/run-order confounding prevents thermal causal claims.",
        ],
    }

    out = EVIDENCE / "d1_analysis.json"
    out.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE {out}")
    print(
        json.dumps(
            {
                "a1_a2_spearman": analysis["a1_a2_batch_rank_spearman"],
                "wall_device_a1": analysis["wall_vs_device_pearson_a1"],
                "pair_1_14": paired["pair_1_14"]["wall_mean_ratio_slow_over_fast"],
                "pair_17_13": paired["pair_17_13"]["wall_mean_ratio_slow_over_fast"],
                "d2_eligible": scientific_conclusion[
                    "d2_comparisons_scientifically_eligible"
                ],
                "leading_class": hypothesis_disposition[
                    "state_history_dependent_gpu_model_execution"
                ]["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
