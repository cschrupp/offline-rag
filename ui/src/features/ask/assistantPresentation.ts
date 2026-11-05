import type { ConversationTurnResponse } from "../../api/types";
import { abstentionCopy, conversationGuidanceCopy } from "./abstentionCopy";

/**
 * Canonical visible plain text for an assistant conversation turn (A2-D05/D07).
 * Used for both UI rendering and client prior_turns construction.
 */
export function assistantPresentationText(
  response: Pick<
    ConversationTurnResponse,
    | "status"
    | "answer"
    | "abstention_reason"
    | "response_kind"
    | "guidance_code"
  >,
): string {
  if (
    response.response_kind === "conversation_transform" &&
    response.status === "transformed"
  ) {
    return typeof response.answer === "string" ? response.answer : "";
  }
  if (response.status === "answered") {
    return typeof response.answer === "string" ? response.answer : "";
  }
  return (
    conversationGuidanceCopy(response.guidance_code) ??
    abstentionCopy(response.abstention_reason)
  );
}

/** Unicode code-point length (matches Python ``len(str)`` / A2-D07). */
export function unicodeCharCount(text: string): number {
  return Array.from(text).length;
}
