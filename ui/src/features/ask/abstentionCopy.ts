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
    default:
      return "Seneca did not provide an answer from the available evidence.";
  }
}
