/**
 * Ephemeral Presentation Review responses (16N-A).
 * Not scientific authority; must never be treated as a Gold mutation receipt.
 */

export type PreviewQuestionCheckResponse = {
  kind: "question_check";
  taskId: string;
  decision: "accept" | "reject" | "edit";
  effective_query?: string;
  effective_category?: string | null;
  effective_tags?: string[];
  recordedAt: string;
};

export type PreviewRelevanceResponse = {
  kind: "rapid_fire";
  taskId: string;
  relevance: 0 | 1 | 2;
  recordedAt: string;
};

export type PreviewResponse =
  | PreviewQuestionCheckResponse
  | PreviewRelevanceResponse;

export const PREVIEW_LOCAL_STATUS =
  "Preview response recorded locally. Gold was not changed.";
