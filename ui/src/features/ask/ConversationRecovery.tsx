import { Link } from "react-router-dom";
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
    case "insufficient_support":
      return "Ask about one concept or step at a time. Name the source or section if you know it.";
    case "conflicting_evidence":
      return "Name the source or version you want to use, or ask how the selected sources differ on this point.";
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
  const needsSourceReview =
    response.abstention_reason === "no_evidence" ||
    response.abstention_reason === "insufficient_support";
  return (
    <div className="stack conversation-recovery">
      {needsSourceReview ? (
        <>
          <p className="muted">
            {response.abstention_reason === "no_evidence"
              ? "Try using a term or title from a source you expect to cover the topic."
              : reformulation(response.abstention_reason)}
          </p>
          <p className="muted">
            {entry.selectionMode === "subset"
              ? "This turn searched only the sources you selected. Review that selection and include any other relevant sources."
              : "Review the sources used for this turn and check whether they cover what you asked."}
            {" "}If you have a source on the topic, add it here or{" "}
            <Link to="/workspaces">switch workspaces</Link> if you keep it elsewhere.
          </p>
        </>
      ) : (
        <p className="muted">{reformulation(response.abstention_reason)}</p>
      )}
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
  onRetry,
}: RecoveryProps & { turn: IncompleteUserTurn; onRetry?: () => void }) {
  const failure = turn.failure;
  const code = failure?.code;
  const guidance = code === "network_error"
    ? "Check your connection before submitting again. Seneca could not confirm the outcome."
    : code === "response_parse_error"
      ? "The model response did not match Seneca’s required format, so it was not used. You can retry the same request or edit the question."
      : code === "generation_timeout"
        ? "The generation service did not finish before its time limit. You can retry or edit the question."
        : code === "generation_unavailable"
          ? "Seneca could not reach the configured generation service. Check Settings, then retry if it is available."
          : code === "generation_failed"
            ? "The generation service could not complete this request. You can retry or edit the question."
      : failure?.retryable
        ? "Try again when the service is available."
        : "Edit the question before submitting it again.";

  return (
    <div className="stack conversation-recovery">
      <p className="muted">{guidance}</p>
      {onRetry && (
        <div>
          <p className="muted">
            Retry uses the original question and sources: {turn.selectedSourceNames.join(", ") || "no selected sources"}.
          </p>
          <Button type="button" variant="secondary" onClick={onRetry}>
            Retry question
          </Button>
        </div>
      )}
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
