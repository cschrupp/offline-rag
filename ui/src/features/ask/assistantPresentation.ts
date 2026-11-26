import type { ConversationTurnResponse } from "../../api/types";
import { abstentionCopy } from "./abstentionCopy";

/**
 * Canonical visible plain text for an assistant conversation turn (A2-D05/D07).
 * Used for both UI rendering and client prior_turns construction.
 */
export function assistantPresentationText(
  response: Pick<
    ConversationTurnResponse,
    "status" | "answer" | "abstention_reason"
  >,
): string {
  if (response.status === "answered") {
    return typeof response.answer === "string" ? response.answer : "";
  }
  return abstentionCopy(response.abstention_reason);
}

/** Unicode code-point length (matches Python ``len(str)`` / A2-D07). */
export function unicodeCharCount(text: string): number {
  return Array.from(text).length;
}

export function technicalFailureMessage(code: string | undefined): string | null {
  switch (code) {
    case "response_parse_error":
      return "Seneca could not turn the model’s response into a reliable answer.";
    case "generation_timeout":
      return "The model did not finish in time.";
    case "generation_unavailable":
      return "Seneca could not use the configured generation service.";
    case "generation_failed":
      return "The generation service could not complete this question.";
    default:
      return null;
  }
}
