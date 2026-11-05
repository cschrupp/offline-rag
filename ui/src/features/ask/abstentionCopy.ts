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
      return "Seneca could not safely resolve what this follow-up refers to. Rephrase with the specific topic or terms you mean.";
    default:
      return "Seneca did not provide an answer from the available evidence.";
  }
}

export function conversationGuidanceCopy(
  code: string | null | undefined,
): string | null {
  switch (code) {
    case "conversation_summary_unavailable":
      return "I cannot summarize the entire conversation from the limited history available. Ask me to summarize my previous answer, or paste the text you want summarized.";
    case "history_coverage_unavailable":
      return "I do not have enough of the requested conversation history to do that safely. Ask about a specific available turn or paste the text.";
    case "target_missing":
      return "Tell me which text or conversation turn you want me to transform.";
    case "target_ambiguous":
    case "target_unavailable":
      return "I could not identify that exact conversation text. Specify the turn or paste the text you want me to transform.";
    case "source_reference_unavailable":
      return "I could not match that source within the sources selected for this question. Select the source or clarify its title, then try again.";
    case "unsupported_transform_options":
      return "I cannot safely apply all of those formatting or style requirements yet. Try a supported summary, rewrite, simplification, or translation request.";
    case "planner_plan_invalid":
      return "I could not safely interpret that request. Rephrase it as one clear question or one text transformation.";
    case "multi_stage_operation_unavailable":
      return "I cannot complete that combination of editing and source-verification steps in one request. Ask a source question or a text transformation separately.";
    case "operation_unavailable":
      return "I cannot perform that conversation operation yet. Ask a grounded source question or a supported text transformation.";
    default:
      return null;
  }
}
