"""Check gate accounting without calling a model."""

import json

import pytest
from summarize import SCHEDULE, summarize


def test_all_pairs_and_failed_arms_are_retained(tmp_path):
    rows = []
    for block, order in enumerate(SCHEDULE):
        for arm in order:
            phase = f"{block}_{arm}"
            forward = 30 if arm in "AB" else 20
            rows.append(
                {
                    "bge_phase": phase,
                    "profile": {
                        "phases": {"total": {"wall_s": forward, "cpu_s": 2 * forward}},
                        "batches": [
                            {
                                "forward": {"wall_s": forward, "cpu_s": 2 * forward},
                                "padded_positions": 0,
                                "batch_size": 10,
                                "padded_width": 509,
                            }
                        ],
                    },
                }
            )
            rows.append(
                {
                    "phase": phase,
                    "start_epoch_ns": 1,
                    "end_epoch_ns": 2,
                    "assembler_total_ms": 1000 * (forward + 1),
                    "cpu_user_s": 2 * forward,
                    "cpu_system_s": 0,
                    "rss_after_bytes": 1,
                    "peak_rss_kib": 1,
                }
            )
        for arm in "BCD":
            rows.append(
                {
                    "parity_block": block,
                    "arm": arm,
                    "pass": arm != "D",
                    "max_abs_delta": 0,
                }
            )
    log = tmp_path / "measurements"
    samples = tmp_path / "samples"
    log.write_text("\n".join(map(json.dumps, rows)))
    samples.write_text("ticks=100\n")
    result = summarize(log, samples)
    assert len(result["trials"]) == 20
    assert result["comparison"]["C"]["advances"]
    assert not result["comparison"]["B"]["advances"]
    assert not result["comparison"]["D"]["advances"]
    assert result["comparison"]["D"]["gates"]["wall_magnitude"]
    assert not result["comparison"]["D"]["gates"]["parity"]
    log.write_text("\n".join(map(json.dumps, rows[2:])))
    with pytest.raises(ValueError, match="trial order"):
        summarize(log, samples)
