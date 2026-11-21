"""Summarize exact-incident batching measurements from the scalar log."""

import json
import statistics
import sys
from pathlib import Path


def summarize(lines):
    """Keep every observed trial and compute three within-block reductions."""
    samples = {}
    parity = {}
    observations = {}
    for line in lines:
        if not line.startswith("{"):
            continue
        record = json.loads(line)
        if "bge_phase" in record:
            samples[record["bge_phase"]] = record["profile"]
        elif "assembler_total_ms" in record:
            observations[record["phase"]] = record
        elif "parity_block" in record:
            parity[record["parity_block"]] = record

    trials = {}
    for phase, obs in observations.items():
        batches = samples[phase]["batches"]
        trials[phase] = {
            "assembler_s": obs["assembler_total_ms"] / 1000,
            "scorer_s": samples[phase]["phases"]["total"]["wall_s"],
            "forward_s": sum(batch["forward"]["wall_s"] for batch in batches),
            "forward_cpu_s": sum(batch["forward"]["cpu_s"] for batch in batches),
            "batch_forward_s": [batch["forward"]["wall_s"] for batch in batches],
            "padding": sum(batch["padded_positions"] for batch in batches),
            "rss_before_mib": obs["rss_before_bytes"] / 1048576,
            "rss_after_mib": obs["rss_after_bytes"] / 1048576,
            "peak_rss_mib": obs["peak_rss_kib"] / 1024,
            "host_available_mib": obs["host_available_kib"] / 1024,
        }

    metrics = ("assembler_s", "forward_s", "forward_cpu_s")
    reductions = {
        key: [
            1 - trials[f"{block}_B"][key] / trials[f"{block}_A"][key]
            for block in range(1, 4)
            if f"{block}_A" in trials and f"{block}_B" in trials
        ]
        for key in metrics
    }
    medians = {
        key: statistics.median(values) for key, values in reductions.items() if values
    }
    complete = len(trials) == 8 and set(parity) == {0, 1, 2, 3}
    return {
        "trials": trials,
        "paired_fractional_reductions": reductions,
        "median_paired_fractional_reductions": medians,
        "parity_blocks": parity,
        "complete": complete,
        "parity_pass": complete and all(result["pass"] for result in parity.values()),
        "performance_gate": complete
        and all(medians[key] >= 0.2 for key in metrics[:2]),
    }


if __name__ == "__main__":
    log = Path(sys.argv[1]).read_text().splitlines()
    print(json.dumps(summarize(log), indent=2))
