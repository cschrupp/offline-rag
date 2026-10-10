import type {
  GoldRelevance,
  QuestionCheckMutationBody,
} from "../types";

export function fingerprintGoldRelevance(params: {
  campaignId: string;
  taskId: string;
  relevance: GoldRelevance;
  gameId: string;
  presentationId: string;
}): string {
  return JSON.stringify({
    op: "gold_relevance",
    campaign_id: params.campaignId,
    task_id: params.taskId,
    relevance: params.relevance,
    game_id: params.gameId,
    presentation_id: params.presentationId,
  });
}

export function fingerprintGoldQuestionCheck(params: {
  campaignId: string;
  taskId: string;
  body: QuestionCheckMutationBody;
}): string {
  return JSON.stringify({
    op: "gold_question_check",
    campaign_id: params.campaignId,
    task_id: params.taskId,
    body: params.body,
  });
}
