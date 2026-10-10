import {
  eligiblePendingForGame,
  type GoldGameId,
  type GoldSessionConfig,
  type GoldWorkload,
} from "../state/sessionConfig";
import type { GoldTaskSummary } from "../types";

export type FrozenSessionWindow = {
  mode: "frozen";
  taskIds: readonly string[];
};

export type DynamicSessionWindow = {
  mode: "dynamic";
};

export type SessionWindow = FrozenSessionWindow | DynamicSessionWindow;

function workloadLimit(workload: GoldWorkload): number | null {
  if (workload === "until_stop" || workload === "case") return null;
  const n = Number(workload);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/**
 * Build the expert-work presentation cohort from the current pending list.
 * Numeric and complete-case windows are frozen at session start.
 * until_stop remains dynamic and may refresh after each commit.
 */
export function buildSessionWindow(
  tasks: GoldTaskSummary[],
  config: GoldSessionConfig,
): SessionWindow {
  const eligible = eligiblePendingForGame(tasks, config.game);

  if (config.workload === "until_stop") {
    return { mode: "dynamic" };
  }

  if (config.workload === "case") {
    const caseId =
      eligible.find((task) => task.task_id === config.taskId)?.case_id ?? null;
    if (!caseId) {
      return { mode: "frozen", taskIds: Object.freeze([]) };
    }
    const caseTasks = eligible
      .filter((task) => task.case_id === caseId)
      .map((task) => task.task_id);
    return { mode: "frozen", taskIds: Object.freeze(caseTasks) };
  }

  const limit = workloadLimit(config.workload) ?? eligible.length;
  return {
    mode: "frozen",
    taskIds: Object.freeze(eligible.slice(0, limit).map((task) => task.task_id)),
  };
}

export function resolveTaskInWindow(
  window: SessionWindow,
  pendingOrdered: GoldTaskSummary[],
  requestedTaskId: string | null,
  game: GoldGameId,
): string | null {
  const eligible = eligiblePendingForGame(pendingOrdered, game);
  const membership =
    window.mode === "frozen"
      ? window.taskIds.filter((id) =>
          eligible.some((task) => task.task_id === id),
        )
      : eligible.map((task) => task.task_id);

  if (membership.length === 0) return null;
  if (requestedTaskId && membership.includes(requestedTaskId)) {
    return requestedTaskId;
  }
  return membership[0] ?? null;
}

export function nextTaskInWindow(
  window: SessionWindow,
  pendingOrdered: GoldTaskSummary[],
  currentTaskId: string,
  game: GoldGameId,
): string | null {
  const eligible = eligiblePendingForGame(pendingOrdered, game);
  const membership =
    window.mode === "frozen"
      ? window.taskIds.filter((id) =>
          eligible.some((task) => task.task_id === id),
        )
      : eligible.map((task) => task.task_id);

  const index = membership.indexOf(currentTaskId);
  if (index < 0) {
    return membership[0] ?? null;
  }
  return membership[index + 1] ?? null;
}
