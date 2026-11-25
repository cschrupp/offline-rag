import { Button } from "../../components/Button";
import type {
  ConversationHistoryEntry,
  IncompleteUserTurn,
} from "./conversationState";

type RecoveryProps = {
  onEdit: (question: string) => void;
  canEdit: boolean;
};

function reformulation(reason: string | null): string {
  switch (reason) {
    case "no_evidence":
      return "Try an exact term or section title from the manual. If another source covers the topic, select it before asking again.";
    case "insufficient_support":
      return "Ask about one concept or step at a time. Name the manual, edition, or section if you know it.";
    case "conflicting_evidence":
      return "Name the manual and edition that applies, or ask how the selected manuals differ on this point.";
    case "ambiguous_request":
      return "Replace words like “it” or “that” with the specific term or procedure you mean.";
    default:
      return "Narrow the question to one point that the selected sources can address.";
  }
}

function observedCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

export function AbstentionRecovery({
  entry,
  canEdit,
  onEdit,
}: RecoveryProps & { entry: ConversationHistoryEntry }) {
  const response = entry.response;
  const diagnostics = response.recovery_diagnostics;
  const isClarification = response.status === "clarification_required";
  return (
    <div className="stack conversation-recovery">
      <p className="muted">{reformulation(response.abstention_reason)}</p>
      <div>
        <Button
          type="button"
          variant="secondary"
          disabled={!canEdit}
          onClick={() => onEdit(entry.question)}
        >
          Edit question
        </Button>
      </div>
      <details>
        <summary>What happened</summary>
        <ul className="muted">
          {observedCount(diagnostics?.source_count) ? (
            <li>Sources in this request: {diagnostics.source_count}</li>
          ) : null}
          {isClarification ? <li>The search did not run.</li> : null}
          {observedCount(diagnostics?.evidence_unit_count) ? (
            <li>
              Evidence units in the assembled context: {diagnostics.evidence_unit_count}
            </li>
          ) : null}
          {typeof diagnostics?.generator_invoked === "boolean" ? (
            <li>
              {diagnostics.generator_invoked
                ? "Answer generation was attempted."
                : "Answer generation did not run."}
            </li>
          ) : null}
          {!isClarification && !observedCount(diagnostics?.evidence_unit_count) ? (
            <li>Detailed retrieval counts are unavailable for this turn.</li>
          ) : null}
          <li>Workspace revision: {response.workspace_revision}</li>
          <li>Publication snapshot: {response.snapshot_id}</li>
          {response.query_trace_id ? <li>Query trace: {response.query_trace_id}</li> : null}
        </ul>
      </details>
    </div>
  );
}

export function FailedTurnRecovery({
  turn,
  canEdit,
  onEdit,
}: RecoveryProps & { turn: IncompleteUserTurn }) {
  const failure = turn.failure;
  const code = failure?.code;
  const guidance = code === "network_error"
    ? "Check your connection before submitting again. Seneca could not confirm the outcome."
    : code?.startsWith("generation_")
      ? "Check the configured generation service before asking again."
      : failure?.retryable
        ? "Try again when the service is available."
        : "Review the error above before submitting again.";

  return (
    <div className="stack conversation-recovery">
      <p className="muted">{guidance}</p>
      <div>
        <Button
          type="button"
          variant="secondary"
          disabled={!canEdit}
          onClick={() => onEdit(turn.question)}
        >
          Edit question
        </Button>
      </div>
      <details>
        <summary>What happened</summary>
        <ul className="muted">
          <li>There is no confirmed answer for this request.</li>
          {code ? <li>Error code: {code}</li> : null}
          {failure?.traceId ? <li>Trace: {failure.traceId}</li> : null}
        </ul>
      </details>
    </div>
  );
}
