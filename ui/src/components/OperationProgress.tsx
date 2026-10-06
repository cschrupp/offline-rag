import { Badge } from "./Badge";
import { Button } from "./Button";
import {
  operationStatusLabel,
  progressStageLabel,
} from "../features/operations/progressLabels";
import type { Operation } from "../api/types";

type Props = {
  phase: "uploading" | "operation" | "lookup_error";
  operation?: Operation | null;
  label?: string;
  lookupError?: string;
  onDismiss?: () => void;
};

export function OperationProgress({
  phase,
  operation,
  label,
  lookupError,
  onDismiss,
}: Props) {
  if (phase === "uploading") {
    return (
      <div className="card" aria-live="polite">
        <div className="row">
          <Badge tone="busy" label="Uploading" />
          <strong>{label ?? "Uploading…"}</strong>
        </div>
        <p className="muted">
          Sending files to OfflineRAG. Durable processing starts after the
          server accepts the request.
        </p>
      </div>
    );
  }

  if (phase === "lookup_error") {
    return (
      <div className="card" aria-live="polite" data-testid="operation-lookup-error">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <div className="row">
            <Badge tone="error" label="Unavailable" />
            <strong>{label ?? "Workspace operation"}</strong>
          </div>
          {onDismiss ? (
            <Button variant="secondary" onClick={onDismiss}>
              Dismiss
            </Button>
          ) : null}
        </div>
        <p className="error-box" role="alert">
          {lookupError ??
            "Could not load this operation status. Reload the page or dismiss this notice."}
        </p>
      </div>
    );
  }

  if (!operation) return null;

  const terminal =
    operation.status === "succeeded" ||
    operation.status === "failed" ||
    operation.status === "interrupted";

  let tone: "ready" | "busy" | "error" = "busy";
  let statusText = progressStageLabel(operation.progress_stage);
  if (operation.status === "succeeded") {
    tone = "ready";
    statusText = "Ready";
  } else if (operation.status === "failed") {
    tone = "error";
    statusText = "Failed";
  } else if (operation.status === "interrupted") {
    tone = "error";
    statusText = "Interrupted";
  } else if (!operation.progress_stage) {
    statusText = operationStatusLabel(String(operation.status));
  }

  return (
    <div
      className="card"
      aria-live="polite"
      data-testid={`operation-progress-${operation.operation_id}`}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <Badge tone={tone} label={statusText} />
          <strong>{label ?? "Workspace operation"}</strong>
        </div>
        {terminal && onDismiss ? (
          <Button variant="secondary" onClick={onDismiss}>
            Dismiss
          </Button>
        ) : null}
      </div>
      <p className="muted">
        Status: {operationStatusLabel(String(operation.status))}
        {operation.progress_stage
          ? ` · ${progressStageLabel(operation.progress_stage)}`
          : ""}
      </p>
      {operation.status === "failed" && operation.error ? (
        <p className="error-box" role="alert">
          {operation.error.message}
          <span className="sr-only"> Error code: {operation.error.code}</span>
          <span
            className="muted"
            style={{ display: "block", marginTop: "0.5rem" }}
          >
            {operation.error.code}
          </span>
        </p>
      ) : null}
      {operation.status === "interrupted" ? (
        <p className="error-box" role="alert">
          Processing was interrupted. You may retry this action.
        </p>
      ) : null}
      {operation.status === "succeeded" ? (
        <p className="muted">Ready. Workspace knowledge has been updated.</p>
      ) : null}
      {!terminal ? (
        <p className="muted">
          No percentage or ETA is shown. OfflineRAG reports coarse progress
          stages only.
        </p>
      ) : null}
    </div>
  );
}
