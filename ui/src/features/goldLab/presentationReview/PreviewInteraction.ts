import type { QuestionCheckCommitDraft } from "../games/questionCheck/QuestionCheckPresentation";
import type { GoldRelevance } from "../types";
import type {
  PreviewQuestionCheckResponse,
  PreviewRelevanceResponse,
  PreviewResponse,
} from "./previewTypes";

/**
 * Non-authoritative local preview interaction.
 * Contains zero Gold mutation API calls by construction.
 */
export type PreviewInteraction = {
  readonly response: PreviewResponse | null;
  submitQuestionCheck: (
    taskId: string,
    draft: QuestionCheckCommitDraft,
  ) => Promise<PreviewQuestionCheckResponse>;
  submitRelevance: (
    taskId: string,
    relevance: GoldRelevance,
  ) => Promise<PreviewRelevanceResponse>;
  clear: () => void;
};

export function createPreviewInteraction(options: {
  getResponse: () => PreviewResponse | null;
  setResponse: (next: PreviewResponse | null) => void;
}): PreviewInteraction {
  return {
    get response() {
      return options.getResponse();
    },
    async submitQuestionCheck(taskId, draft) {
      const recordedAt = new Date().toISOString();
      const next: PreviewQuestionCheckResponse =
        draft.decision === "edit"
          ? {
              kind: "question_check",
              taskId,
              decision: "edit",
              effective_query: draft.effective_query,
              effective_category: draft.effective_category,
              effective_tags: draft.effective_tags,
              recordedAt,
            }
          : {
              kind: "question_check",
              taskId,
              decision: draft.decision,
              recordedAt,
            };
      options.setResponse(next);
      return next;
    },
    async submitRelevance(taskId, relevance) {
      const next: PreviewRelevanceResponse = {
        kind: "rapid_fire",
        taskId,
        relevance,
        recordedAt: new Date().toISOString(),
      };
      options.setResponse(next);
      return next;
    },
    clear() {
      options.setResponse(null);
    },
  };
}
