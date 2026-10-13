import type { GoldTaskSummary } from "../types";
import type { GoldGameId } from "../state/sessionConfig";

export type ExpertCampaignState = {
  qcReviewed: number;
  qcPending: number;
  relevanceCompleted: number;
  relevancePending: number;
  nextPrimaryGame: "question_check" | "rapid_fire" | null;
  primaryComplete: boolean;
  firstQcTaskId: string | null;
  firstRfTaskId: string | null;
};

/**
 * Pure UI selector over authoritative task projection.
 * Does not encode production eligibility authority.
 */
export function deriveExpertCampaignState(
  tasks: readonly GoldTaskSummary[],
): ExpertCampaignState {
  let qcReviewed = 0;
  let qcPending = 0;
  let relevanceCompleted = 0;
  let relevancePending = 0;
  let firstQcTaskId: string | null = null;
  let firstRfTaskId: string | null = null;

  for (const task of tasks) {
    if (task.task_kind === "question_check") {
      if (task.state === "completed") {
        qcReviewed += 1;
      } else if (task.state === "pending" && task.active) {
        qcPending += 1;
        if (!firstQcTaskId) firstQcTaskId = task.task_id;
      }
      continue;
    }
    if (task.task_kind === "absolute_relevance") {
      if (task.state === "completed") {
        relevanceCompleted += 1;
      } else if (task.state === "pending" && task.active) {
        relevancePending += 1;
        if (!firstRfTaskId) firstRfTaskId = task.task_id;
      }
    }
  }

  let nextPrimaryGame: ExpertCampaignState["nextPrimaryGame"] = null;
  if (qcPending > 0) {
    nextPrimaryGame = "question_check";
  } else if (relevancePending > 0) {
    nextPrimaryGame = "rapid_fire";
  }

  return {
    qcReviewed,
    qcPending,
    relevanceCompleted,
    relevancePending,
    nextPrimaryGame,
    primaryComplete: nextPrimaryGame === null,
    firstQcTaskId,
    firstRfTaskId,
  };
}

export function continueSessionGame(
  state: ExpertCampaignState,
): GoldGameId | null {
  return state.nextPrimaryGame;
}

export function continueAnchorTaskId(
  state: ExpertCampaignState,
): string | null {
  if (state.nextPrimaryGame === "question_check") {
    return state.firstQcTaskId;
  }
  if (state.nextPrimaryGame === "rapid_fire") {
    return state.firstRfTaskId;
  }
  return null;
}
