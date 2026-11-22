"""Summarize the bounded Stage 1 measurements without dropping attempts."""

import json
import sys
from pathlib import Path
from statistics import median

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines()]
print(f"Assembler calls started: {sum('start' in row for row in rows)}")
for workload in ("Recipes", "Rich"):
    records = {
        (row["block"], row["arm"]): row
        for row in rows
        if row.get("workload") == workload and "completed" in row
    }
    parity = [row for row in rows if row.get("workload") == workload and "parity_block" in row]
    print(f"\n{workload}: {len(records)}/8 completed, {len(parity)}/4 parity pairs")
    for block in range(1, 4):
        if (block, "A") in records and (block, "B") in records:
            print(block, *(
                (arm, round(row["assembler_s"], 3), round(row["cpu_s"], 3),
                 round(row["scorer_s"], 3), round(sum(row["forward_s"]), 3))
                for arm in ("A", "B") if (row := records[block, arm])
            ))
    if len(records) != 8 or len(parity) != 4:
        print("INCOMPLETE")
        continue
    passed = all(row["numerical"] and row["identity"] for row in parity)
    print(f"Parity: {passed}; max absolute logit delta: {max(abs(d) for p in parity for d in p['logit_deltas']):.8g}")
    changes = {}
    for key in ("assembler_s", "forward_s", "cpu_s"):
        values = []
        for block in range(1, 4):
            baseline = records[block, "A"][key]
            sorted_eight = records[block, "B"][key]
            if key == "forward_s":
                baseline, sorted_eight = sum(baseline), sum(sorted_eight)
            values.append(100 * (baseline - sorted_eight) / baseline)
        changes[key] = median(values)
        print(f"{key} paired median reduction: {changes[key]:.2f}%")
    print("Performance screen:", changes["assembler_s"] >= 20 and changes["forward_s"] >= 20 and changes["cpu_s"] >= -5)
