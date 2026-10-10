import { describe, expect, it } from "vitest";
import {
  EVIDENCE_SWEEP_BATCH_SIZE,
  buildSessionWindow,
  nextBatchTaskIds,
  orderedWindowTaskIds,
} from "../features/goldLab/work/sessionWindow";
import type { GoldTaskSummary } from "../features/goldLab/types";

function task(id: string, caseId = "case_a"): GoldTaskSummary {
  return {
    task_id: id,
    task_kind: "absolute_relevance",
    campaign_id: "camp_1",
    case_id: caseId,
    active: true,
    state: "pending",
    candidate_chunk_id: `chunk_${id}`,
    effective_query: "q",
  };
}

describe("16G-I3 Evidence Sweep batch helpers", () => {
  it("caps batches at 5 and preserves server order", () => {
    expect(EVIDENCE_SWEEP_BATCH_SIZE).toBe(5);
    const tasks = Array.from({ length: 12 }, (_, i) => task(`t${i + 1}`));
    const window = buildSessionWindow(tasks, {
      game: "evidence_sweep",
      workload: "10",
      taskId: null,
    });
    expect(window.mode).toBe("frozen");
    if (window.mode !== "frozen") return;
    expect(window.taskIds).toEqual([
      "t1",
      "t2",
      "t3",
      "t4",
      "t5",
      "t6",
      "t7",
      "t8",
      "t9",
      "t10",
    ]);
    const ordered = orderedWindowTaskIds(window, tasks, "evidence_sweep");
    const batch1 = nextBatchTaskIds(ordered, new Set());
    expect(batch1).toEqual(["t1", "t2", "t3", "t4", "t5"]);
    const batch2 = nextBatchTaskIds(ordered, new Set(batch1));
    expect(batch2).toEqual(["t6", "t7", "t8", "t9", "t10"]);
    expect(batch2).not.toContain("t11");
  });

  it("keeps frozen case cohort and dynamic until_stop behavior", () => {
    const tasks = [
      task("a1", "case_a"),
      task("a2", "case_a"),
      task("b1", "case_b"),
    ];
    const caseWindow = buildSessionWindow(tasks, {
      game: "evidence_sweep",
      workload: "case",
      taskId: "a1",
    });
    expect(caseWindow).toEqual({
      mode: "frozen",
      taskIds: Object.freeze(["a1", "a2"]),
    });

    const dynamic = buildSessionWindow(tasks, {
      game: "evidence_sweep",
      workload: "until_stop",
      taskId: null,
    });
    expect(dynamic).toEqual({ mode: "dynamic" });
    const ordered = orderedWindowTaskIds(dynamic, tasks, "evidence_sweep");
    expect(ordered).toEqual(["a1", "a2", "b1"]);
  });
});
