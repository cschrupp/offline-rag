export function abstentionCopy(reason: string | null | undefined): string {
  switch (reason) {
    case "no_evidence":
      return "Seneca did not find usable evidence in the selected sources for this question.";
    case "insufficient_support":
      return "The available evidence was not strong enough to support an answer.";
    case "conflicting_evidence":
      return "The selected evidence conflicts materially, so Seneca did not provide an answer.";
    case "model_declined":
      return "Seneca did not provide an answer from the available evidence.";
    case "ambiguous_request":
      return "Seneca could not safely resolve what this follow-up refers to. Rephrase with the specific topic or terms you mean. To transform an earlier answer, use Summarize, Simplify or Translate under that answer.";
    case "conversation_response_truncated":
      return "This transformation was cut off, so Seneca discarded it. Try a shorter target answer.";
    case "conversation_response_unavailable":
      return "Seneca could not produce a complete transformation. The conversation was not changed.";
    default:
      return "Seneca did not provide an answer from the available evidence.";
  }
}
