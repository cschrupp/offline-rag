"""Summarize every Rich batching trial and evaluate the frozen gates."""

import argparse
import csv
import datetime as dt
import json
import statistics
from itertools import pairwise
from pathlib import Path

SCHEDULE = ("ABCD", "ABDC", "BCAD", "CDBA", "DACB")
ENDPOINTS = ("forward_s", "assembler_s", "assembler_cpu_s")


def read_samples(path):
    header, *lines = path.read_text().splitlines()
    ticks = int(header.split("=")[1])
    samples = []
    for line in lines:
        stamp, *fields = line.split()
        ns = int(dt.datetime.fromisoformat(stamp).timestamp() * 1e9)
        samples.append((ns, dict(field.split("=", 1) for field in fields)))
    return ticks, samples


def sampled_resources(window, ticks):
    rates = [
        sum(int(second[k]) - int(first[k]) for k in ("user_jiffies", "system_jiffies"))
        / ticks
        / ((end - start) / 1e9)
        for (start, first), (end, second) in pairwise(window)
    ]
    return {
        "samples": len(window),
        "sampled_peak_cpu_cores": max(rates, default=None),
        "sampled_peak_rss_kib": max(
            (int(row["rss_kib"]) for _, row in window), default=None
        ),
        "sampled_min_available_kib": min(
            (int(row["MemAvailable_kib"]) for _, row in window), default=None
        ),
        "sampled_swap_free_kib": sorted(
            {int(row["SwapFree_kib"]) for _, row in window}
        ),
    }


def summarize(log, samples):
    raw = [
        json.loads(line)
        for line in log.read_text().splitlines()
        if line.startswith("{")
    ]
    scorers = {row["bge_phase"]: row["profile"] for row in raw if "bge_phase" in row}
    observations = [row for row in raw if "assembler_total_ms" in row]
    parity = [row for row in raw if "parity_block" in row]
    expected = [
        f"{block}_{arm}" for block, order in enumerate(SCHEDULE) for arm in order
    ]
    if [row["phase"] for row in observations] != expected:
        raise ValueError("incomplete or unexpected trial order")
    if [(row["parity_block"], row["arm"]) for row in parity] != [
        (block, arm) for block in range(len(SCHEDULE)) for arm in "BCD"
    ]:
        raise ValueError("incomplete or unexpected parity observations")

    ticks, sample_data = read_samples(samples)
    trials = {}
    for row in observations:
        phase = row["phase"]
        profile = scorers[phase]
        batches = profile["batches"]
        window = [
            (ns, v)
            for ns, v in sample_data
            if row["start_epoch_ns"] <= ns <= row["end_epoch_ns"]
        ]
        trials[phase] = {
            "assembler_s": row["assembler_total_ms"] / 1000,
            "assembler_cpu_s": row["cpu_user_s"] + row["cpu_system_s"],
            "scorer_s": profile["phases"]["total"]["wall_s"],
            "scorer_cpu_s": profile["phases"]["total"]["cpu_s"],
            "forward_s": sum(b["forward"]["wall_s"] for b in batches),
            "forward_cpu_s": sum(b["forward"]["cpu_s"] for b in batches),
            "padding": sum(b["padded_positions"] for b in batches),
            "batch_shapes": [[b["batch_size"], b["padded_width"]] for b in batches],
            "batch_forward_s": [b["forward"]["wall_s"] for b in batches],
            "end_rss_mib": row["rss_after_bytes"] / 1048576,
            "high_water_rss_mib": row["peak_rss_kib"] / 1024,
            "resources": sampled_resources(window, ticks),
        }
    comparison = {}
    for arm in "BCD":
        reductions = {
            k: [
                1 - trials[f"{block}_{arm}"][k] / trials[f"{block}_A"][k]
                for block in range(1, 5)
            ]
            for k in ENDPOINTS
        }
        medians = {key: statistics.median(values) for key, values in reductions.items()}
        positives = {
            key: sum(value > 0 for value in values)
            for key, values in reductions.items()
        }
        checks = [row for row in parity if row["arm"] == arm]
        gates = {
            "wall_magnitude": all(medians[k] >= 0.20 for k in ENDPOINTS[:2]),
            "positive_pairs": all(positives[k] >= 3 for k in ENDPOINTS[:2]),
            "cpu_budget": medians["assembler_cpu_s"] >= -0.05,
            "parity": all(row["pass"] for row in checks),
        }
        comparison[arm] = {
            "paired_reductions": reductions,
            "median_reductions": medians,
            "positive_pairs": positives,
            "max_abs_logit_delta": max(row["max_abs_delta"] for row in checks),
            "gates": gates,
            "advances": all(gates.values()),
        }
    return {
        "schedule": SCHEDULE,
        "trials": trials,
        "parity": parity,
        "comparison": comparison,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path)
    parser.add_argument("samples", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = summarize(args.measurements, args.samples)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "SUMMARY.json").write_text(json.dumps(result, indent=2) + "\n")
    with (args.output / "PAIRED.csv").open("w") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(("arm", "block", "endpoint", "reduction_pct"))
        for arm, stats in result["comparison"].items():
            for key, values in stats["paired_reductions"].items():
                for block, value in enumerate(values, 1):
                    writer.writerow((arm, block, key, 100 * value))


if __name__ == "__main__":
    main()
