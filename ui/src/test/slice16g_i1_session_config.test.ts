import { describe, expect, it } from "vitest";
import {
  applySessionConfig,
  caseIdsInServerOrder,
  eligiblePendingForGame,
  parseSessionConfig,
  pendingTasksMatchingConfig,
  taskKindForGame,
} from "../features/goldLab/state/sessionConfig";

const mixedTasks = [
  {
    task_id: "qc1",
    case_id: "case_q",
    state: "pending",
    active: true,
    task_kind: "question_check",
  },
  {
    task_id: "ar1",
    case_id: "case_a",
    state: "pending",
    active: true,
    task_kind: "absolute_relevance",
  },
  {
    task_id: "ar2",
    case_id: "case_b",
    state: "pending",
    active: true,
    task_kind: "absolute_relevance",
  },
  {
    task_id: "qc2",
    case_id: "case_q",
    state: "pending",
    active: true,
    task_kind: "question_check",
  },
  {
    task_id: "ar3",
    case_id: "case_a",
    state: "completed",
    active: true,
    task_kind: "absolute_relevance",
  },
];

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

  it("maps each frozen game to its sealed task_kind", () => {
    expect(taskKindForGame("rapid_fire")).toBe("absolute_relevance");
    expect(taskKindForGame("evidence_sweep")).toBe("absolute_relevance");
    expect(taskKindForGame("chunk_duel")).toBe("absolute_relevance");
    expect(taskKindForGame("question_check")).toBe("question_check");
  });

  it("filters mixed-kind pending populations per game without reordering", () => {
    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "rapid_fire",
        workload: "until_stop",
        taskId: null,
      }).map((task) => task.task_id),
    ).toEqual(["ar1", "ar2"]);

    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "evidence_sweep",
        workload: "1",
        taskId: null,
      }).map((task) => task.task_id),
    ).toEqual(["ar1"]);

    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "chunk_duel",
        workload: "until_stop",
        taskId: null,
      }).map((task) => task.task_id),
    ).toEqual(["ar1", "ar2"]);

    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "question_check",
        workload: "until_stop",
        taskId: null,
      }).map((task) => task.task_id),
    ).toEqual(["qc1", "qc2"]);
  });

  it("drives complete-case grouping from game-eligible pending tasks only", () => {
    const rapidEligible = eligiblePendingForGame(mixedTasks, "rapid_fire");
    expect(caseIdsInServerOrder(rapidEligible)).toEqual(["case_a", "case_b"]);

    const questionEligible = eligiblePendingForGame(
      mixedTasks,
      "question_check",
    );
    expect(caseIdsInServerOrder(questionEligible)).toEqual(["case_q"]);

    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "rapid_fire",
        workload: "case",
        taskId: "ar1",
      }).map((task) => task.task_id),
    ).toEqual(["ar1"]);

    expect(
      pendingTasksMatchingConfig(mixedTasks, {
        game: "question_check",
        workload: "case",
        taskId: "ar1",
      }),
    ).toEqual([]);
  });
});
