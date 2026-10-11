import type {
  GoldPreferenceMutationBody,
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

export function fingerprintGoldPreference(params: {
  campaignId: string;
  body: GoldPreferenceMutationBody;
}): string {
  return JSON.stringify({
    op: "auxiliary_preference",
    campaign_id: params.campaignId,
    case_id: params.body.case_id,
    preferred_chunk_id: params.body.preferred_chunk_id,
    other_chunk_id: params.body.other_chunk_id,
    game_id: params.body.game_id,
    presentation_id: params.body.presentation_id,
  });
}
