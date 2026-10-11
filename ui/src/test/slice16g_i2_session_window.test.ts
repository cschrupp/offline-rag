import { describe, expect, it } from "vitest";
import {
  buildSessionWindow,
  nextTaskInWindow,
  resolveTaskInWindow,
} from "../features/goldLab/work/sessionWindow";
import { goldTask } from "./goldLabFixtures";

const pending = [
  goldTask({ task_id: "A", case_id: "c1", state: "pending" }),
  goldTask({ task_id: "B", case_id: "c1", state: "pending" }),
  goldTask({ task_id: "C", case_id: "c2", state: "pending" }),
  goldTask({ task_id: "D", case_id: "c2", state: "pending" }),
  goldTask({ task_id: "E", case_id: "c3", state: "pending" }),
  goldTask({ task_id: "F", case_id: "c3", state: "pending" }),
  goldTask({ task_id: "G", case_id: "c3", state: "pending" }),
  goldTask({
    task_id: "Q",
    case_id: "c1",
    state: "pending",
    task_kind: "question_check",
  }),
];

describe("16G-I2 session window", () => {
  it("freezes numeric cohorts and does not expand after completions", () => {
    const window = buildSessionWindow(pending, {
      game: "rapid_fire",
      workload: "5",
      taskId: null,
    });
    expect(window).toEqual({
      mode: "frozen",
      taskIds: ["A", "B", "C", "D", "E"],
    });

    const afterA = pending.filter((task) => task.task_id !== "A");
    // Remaining pending includes F/G, but frozen window must ignore them.
    expect(
      nextTaskInWindow(window, afterA, "A", "rapid_fire"),
    ).toBe("B");
    expect(
      resolveTaskInWindow(window, [...afterA, goldTask({ task_id: "H" })], "F", "rapid_fire"),
    ).toBe("B");
  });

  it("freezes complete-case cohorts to the selected case only", () => {
    const window = buildSessionWindow(pending, {
      game: "rapid_fire",
      workload: "case",
      taskId: "C",
    });
    expect(window).toEqual({ mode: "frozen", taskIds: ["C", "D"] });
    expect(nextTaskInWindow(window, pending, "C", "rapid_fire")).toBe("D");
    expect(nextTaskInWindow(window, pending, "D", "rapid_fire")).toBeNull();
  });

  it("keeps until_stop dynamic over refreshed pending order", () => {
    const window = buildSessionWindow(pending, {
      game: "rapid_fire",
      workload: "until_stop",
      taskId: null,
    });
    expect(window.mode).toBe("dynamic");
    const afterA = pending.filter((task) => task.task_id !== "A");
    expect(nextTaskInWindow(window, afterA, "A", "rapid_fire")).toBe("B");
    expect(
      nextTaskInWindow(
        window,
        [
          goldTask({ task_id: "X", state: "pending" }),
          goldTask({ task_id: "Y", state: "pending" }),
        ],
        "A",
        "rapid_fire",
      ),
    ).toBe("X");
  });

  it("filters question-check game populations separately", () => {
    const window = buildSessionWindow(pending, {
      game: "question_check",
      workload: "1",
      taskId: null,
    });
    expect(window).toEqual({ mode: "frozen", taskIds: ["Q"] });
  });
});
