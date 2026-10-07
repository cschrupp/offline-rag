import type { ConversationTurnResponse } from "../../api/types";
import { abstentionCopy } from "./abstentionCopy";

/**
 * Canonical visible plain text for an assistant conversation turn (A2-D05/D07).
 * Used for both UI rendering and client prior_turns construction.
 */
export function assistantPresentationText(
  response: Pick<ConversationTurnResponse, "status" | "answer" | "abstention_reason">,
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
