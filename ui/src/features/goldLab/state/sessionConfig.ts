export const GOLD_GAMES = [
  "rapid_fire",
  "evidence_sweep",
  "question_check",
  "chunk_duel",
] as const;

export type GoldGameId = (typeof GOLD_GAMES)[number];

export const GOLD_WORKLOAD_NUMERIC = ["1", "5", "10", "25"] as const;
export type GoldWorkloadNumeric = (typeof GOLD_WORKLOAD_NUMERIC)[number];

export type GoldWorkload =
  | GoldWorkloadNumeric
  | "case"
  | "until_stop";

export type GoldSessionConfig = {
  game: GoldGameId;
  workload: GoldWorkload;
  taskId: string | null;
};

export type GoldTaskKind = "question_check" | "absolute_relevance";

export const DEFAULT_SESSION_CONFIG: GoldSessionConfig = {
  game: "rapid_fire",
  workload: "until_stop",
  taskId: null,
};

const GAME_SET = new Set<string>(GOLD_GAMES);
const WORKLOAD_URL_SET = new Set<string>([
  ...GOLD_WORKLOAD_NUMERIC,
  "case",
]);

/** Presentation-only mapping from frozen game identity to sealed task_kind. */
export function taskKindForGame(game: GoldGameId): GoldTaskKind {
  return game === "question_check" ? "question_check" : "absolute_relevance";
}

export function parseSessionConfig(
  searchParams: URLSearchParams,
): GoldSessionConfig {
  const rawGame = searchParams.get("game");
  const game =
    rawGame && GAME_SET.has(rawGame)
      ? (rawGame as GoldGameId)
      : DEFAULT_SESSION_CONFIG.game;

  const rawWorkload = searchParams.get("workload");
  let workload: GoldWorkload;
  if (rawWorkload === null) {
    workload = "until_stop";
  } else if (WORKLOAD_URL_SET.has(rawWorkload)) {
    workload = rawWorkload as Exclude<GoldWorkload, "until_stop">;
  } else {
    workload = DEFAULT_SESSION_CONFIG.workload;
  }

  const rawTask = searchParams.get("task");
  const taskId =
    typeof rawTask === "string" && rawTask.trim().length > 0
      ? rawTask
      : null;

  return { game, workload, taskId };
}

export function applySessionConfig(
  searchParams: URLSearchParams,
  config: GoldSessionConfig,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set("game", config.game);
  if (config.workload === "until_stop") {
    next.delete("workload");
  } else {
    next.set("workload", config.workload);
  }
  if (config.taskId && config.taskId.trim()) {
    next.set("task", config.taskId);
  } else {
    next.delete("task");
  }
  return next;
}

export function sessionConfigEquals(
  a: GoldSessionConfig,
  b: GoldSessionConfig,
): boolean {
  return (
    a.game === b.game && a.workload === b.workload && a.taskId === b.taskId
  );
}

export function caseIdsInServerOrder(
  tasks: Array<{ case_id: string; task_id: string }>,
): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const task of tasks) {
    if (!seen.has(task.case_id)) {
      seen.add(task.case_id);
      ordered.push(task.case_id);
    }
  }
  return ordered;
}

export function anchorTaskForCase(
  tasks: Array<{ case_id: string; task_id: string }>,
  caseId: string,
): string | null {
  for (const task of tasks) {
    if (task.case_id === caseId) {
      return task.task_id;
    }
  }
  return null;
}

export function caseIdForTask(
  tasks: Array<{ case_id: string; task_id: string }>,
  taskId: string | null,
): string | null {
  if (!taskId) return null;
  for (const task of tasks) {
    if (task.task_id === taskId) {
      return task.case_id;
    }
  }
  return null;
}

type SessionTask = {
  task_id: string;
  case_id: string;
  state: string;
  active: boolean;
  task_kind: string;
};

/** Pending+active tasks whose sealed kind matches the selected game. */
export function eligiblePendingForGame(
  tasks: SessionTask[],
  game: GoldGameId,
): SessionTask[] {
  const kind = taskKindForGame(game);
  return tasks.filter(
    (task) =>
      task.state === "pending" &&
      task.active &&
      task.task_kind === kind,
  );
}

export function pendingTasksMatchingConfig(
  tasks: SessionTask[],
  config: GoldSessionConfig,
): SessionTask[] {
  const pending = eligiblePendingForGame(tasks, config.game);
  if (config.workload === "until_stop") {
    return pending;
  }
  if (config.workload === "case") {
    const caseId = caseIdForTask(pending, config.taskId);
    if (!caseId) return [];
    return pending.filter((task) => task.case_id === caseId);
  }
  const limit = Number(config.workload);
  if (!Number.isFinite(limit) || limit <= 0) {
    return pending;
  }
  return pending.slice(0, limit);
}
