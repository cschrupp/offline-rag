import { describe, expect, it } from "vitest";
import {
  applySessionConfig,
  caseIdsInServerOrder,
  parseSessionConfig,
  pendingTasksMatchingConfig,
} from "../features/goldLab/state/sessionConfig";

describe("16G-I1 session config", () => {
  it("accepts frozen game and workload values", () => {
    const params = new URLSearchParams(
      "game=evidence_sweep&workload=10&task=task_9",
    );
    expect(parseSessionConfig(params)).toEqual({
      game: "evidence_sweep",
      workload: "10",
      taskId: "task_9",
    });
  });

  it("maps Until stop to omitted workload and fails invalid values safely", () => {
    expect(parseSessionConfig(new URLSearchParams("game=chunk_duel"))).toEqual({
      game: "chunk_duel",
      workload: "until_stop",
      taskId: null,
    });
    expect(
      parseSessionConfig(
        new URLSearchParams("game=not_a_game&workload=continuous&task="),
      ),
    ).toEqual({
      game: "rapid_fire",
      workload: "until_stop",
      taskId: null,
    });
  });

  it("serializes until_stop without inventing workload query values", () => {
    const next = applySessionConfig(new URLSearchParams("foo=1"), {
      game: "question_check",
      workload: "until_stop",
      taskId: null,
    });
    expect(next.get("game")).toBe("question_check");
    expect(next.has("workload")).toBe(false);
    expect(next.has("task")).toBe(false);
    expect(next.get("foo")).toBe("1");
  });

  it("preserves server case/task order for complete-case grouping", () => {
    const tasks = [
      { case_id: "case_b", task_id: "t2" },
      { case_id: "case_a", task_id: "t1" },
      { case_id: "case_b", task_id: "t3" },
    ];
    expect(caseIdsInServerOrder(tasks)).toEqual(["case_b", "case_a"]);
    expect(
      pendingTasksMatchingConfig(
        [
          {
            task_id: "t2",
            case_id: "case_b",
            state: "pending",
            active: true,
          },
          {
            task_id: "t1",
            case_id: "case_a",
            state: "pending",
            active: true,
          },
          {
            task_id: "t3",
            case_id: "case_b",
            state: "completed",
            active: true,
          },
        ],
        { game: "rapid_fire", workload: "case", taskId: "t2" },
      ).map((task) => task.task_id),
    ).toEqual(["t2"]);
  });
});
