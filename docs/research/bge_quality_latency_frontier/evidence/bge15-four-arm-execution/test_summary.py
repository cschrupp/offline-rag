"""Guard schedule, paired contrasts and exact scope without inference."""

import json
import math

import pytest
from summarize import SCHEDULE, summarize


def test_schedule_contrasts_and_failed_batching_parity(tmp_path):
    wall = {"A": 100, "B": 75, "C": 50, "D": 40}
    rows = [{"publication_validated": True}]
    for block, order in enumerate(SCHEDULE):
        for arm in order:
            phase = f"{block}_{arm}"
            seconds = wall[arm]
            rows.extend(
                [
                    {
                        "bge_phase": phase,
                        "profile": {
                            "phases": {
                                "total": {"wall_s": seconds, "cpu_s": 2 * seconds}
                            },
                            "batches": [
                                {
                                    "forward": {
                                        "wall_s": seconds,
                                        "cpu_s": 2 * seconds,
                                    },
                                    "batch_size": 15,
                                    "padded_width": 400,
                                    "padded_positions": 0,
                                }
                            ],
                        },
                    },
                    {
                        "phase": phase,
                        "assembler_total_ms": seconds * 1000,
                        "cpu_user_s": seconds,
                        "cpu_system_s": 0,
                        "start_epoch_ns": 1,
                        "end_epoch_ns": 2,
                        "rss_after_bytes": 1,
                        "peak_rss_kib": 1,
                    },
                ]
            )
        for pair in ("CA", "DB"):
            rows.append(
                {
                    "parity_block": block,
                    "pair": pair,
                    "pass": pair == "CA",
                    "max_abs_delta": 1e-6,
                }
            )
        for pair in ("BA", "DC"):
            rows.append(
                {"depth_block": block, "pair": pair, "fused_prefix_matches": True}
            )
    trace = tmp_path / "trace"
    samples = tmp_path / "samples"
    trace.write_text("\n".join(map(json.dumps, rows)))
    samples.write_text("ticks=100\n")
    summary = summarize(trace, samples)
    assert len(summary["trials"]) == 20
    assert summary["comparison"]["CA"]["performance_gate_vs_A"]
    assert summary["comparison"]["DA"]["performance_gate_vs_A"]
    assert not summary["batching_parity"]["DB"]["passed"]
    assert summary["comparison"]["DB"]["median_reductions"][
        "assembler_s"
    ] == pytest.approx(1 - 40 / 75)
    assert summary["median_log_assembler_interaction"] == pytest.approx(
        math.log((40 / 75) / (50 / 100))
    )
    rows[-1]["fused_prefix_matches"] = False
    trace.write_text("\n".join(map(json.dumps, rows)))
    with pytest.raises(ValueError, match="depth observations"):
        summarize(trace, samples)
