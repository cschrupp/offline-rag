import type { QuestionCheckCommitDraft } from "../games/questionCheck/QuestionCheckPresentation";
import type { GoldRelevance } from "../types";
import type {
  PreviewQuestionCheckResponse,
  PreviewRelevanceResponse,
  PreviewResponse,
} from "./previewTypes";

/**
 * Non-authoritative local preview interaction with per-task memory.
 * Contains zero Gold mutation API calls by construction.
 */
export type PreviewInteraction = {
  getResponse: (taskId: string) => PreviewResponse | null;
  submitQuestionCheck: (
    taskId: string,
    draft: QuestionCheckCommitDraft,
  ) => Promise<PreviewQuestionCheckResponse>;
  submitRelevance: (
    taskId: string,
    relevance: GoldRelevance,
  ) => Promise<PreviewRelevanceResponse>;
  clearTask: (taskId: string) => void;
  clearAll: () => void;
};

export type PreviewResponseMap = Readonly<
  Record<string, PreviewResponse>
>;

export function createPreviewInteraction(options: {
  getMap: () => PreviewResponseMap;
  setMap: (next: PreviewResponseMap) => void;
}): PreviewInteraction {
  return {
    getResponse(taskId) {
      return options.getMap()[taskId] ?? null;
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
      options.setMap({ ...options.getMap(), [taskId]: next });
      return next;
    },
    async submitRelevance(taskId, relevance) {
      const next: PreviewRelevanceResponse = {
        kind: "rapid_fire",
        taskId,
        relevance,
        recordedAt: new Date().toISOString(),
      };
      options.setMap({ ...options.getMap(), [taskId]: next });
      return next;
    },
    clearTask(taskId) {
      const current = { ...options.getMap() };
      delete current[taskId];
      options.setMap(current);
    },
    clearAll() {
      options.setMap({});
    },
  };
}
