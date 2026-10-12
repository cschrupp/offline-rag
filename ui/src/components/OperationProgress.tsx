import { useEffect, useState } from "react";
import { Badge } from "./Badge";
import { Button } from "./Button";
import { managedOperationFailureMessage } from "../features/operations/operationErrorMessages";
import {
  operationStatusLabel,
  progressStageLabel,
} from "../features/operations/progressLabels";
import {
  formatElapsed,
  parseTimestampMs,
  progressPercent,
  progressStepLabel,
  progressUnitLabel,
} from "../features/operations/progressTelemetry";
import type { Operation } from "../api/types";

type Props = {
  phase: "uploading" | "operation" | "lookup_error";
  operation?: Operation | null;
  label?: string;
  lookupError?: string;
  onDismiss?: () => void;
  /** Optional kind-aware success copy; overrides the default workspace text. */
  successMessage?: string;
};

function defaultSuccessMessage(operation: Operation): string {
  if (operation.kind === "gold_lab_baseline_bootstrap") {
    return "Baseline ready.";
  }
  return "Ready. Workspace knowledge has been updated.";
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function OperationProgress({
  phase,
  operation,
  label,
  lookupError,
  onDismiss,
  successMessage,
}: Props) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (phase !== "operation" || !operation) return;
    const terminal =
      operation.status === "succeeded" ||
      operation.status === "failed" ||
      operation.status === "interrupted";
    if (terminal) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [phase, operation]);

  if (phase === "uploading") {
    return (
      <div className="card" aria-live="polite">
        <div className="row">
          <Badge tone="busy" label="Uploading" />
          <strong>{label ?? "Uploading…"}</strong>
        </div>
        <p className="muted">
          Sending files to Seneca. Durable processing starts after the server
          accepts the request.
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
            <strong>{label ?? "Operation"}</strong>
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

  const kind = String(operation.kind);
  const progress = operation.progress ?? null;
  let tone: "ready" | "busy" | "error" = "busy";
  let statusText = progress
    ? progressStepLabel(progress.step)
    : progressStageLabel(operation.progress_stage, kind);
  if (operation.status === "succeeded") {
    tone = "ready";
    statusText = "Ready";
  } else if (operation.status === "failed") {
    tone = "error";
    statusText = "Failed";
  } else if (operation.status === "interrupted") {
    tone = "error";
    statusText = "Interrupted";
  } else if (!operation.progress_stage && !progress) {
    statusText = operationStatusLabel(String(operation.status));
  }

  const percent = progressPercent(progress);
  const createdMs = parseTimestampMs(operation.created_at);
  const elapsedSeconds =
    !terminal && createdMs != null ? (nowMs - createdMs) / 1000 : null;

  return (
    <div
      className="card"
      aria-live="polite"
      data-testid={`operation-progress-${operation.operation_id}`}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <Badge tone={tone} label={statusText} />
          <strong>{label ?? "Operation"}</strong>
        </div>
        {terminal && onDismiss ? (
          <Button variant="secondary" onClick={onDismiss}>
            Dismiss
          </Button>
        ) : null}
      </div>
      <p className="muted">
        Status: {operationStatusLabel(String(operation.status))}
        {progress
          ? ` · ${progressStepLabel(progress.step)}`
          : operation.progress_stage
            ? ` · ${progressStageLabel(operation.progress_stage, kind)}`
            : ""}
      </p>
      {!terminal && progress && percent != null && progress.total != null ? (
        <div className="stack" style={{ gap: "0.35rem" }}>
          <p className="muted" style={{ margin: 0 }}>
            {formatCount(progress.current)} / {formatCount(progress.total)}
            {progressUnitLabel(progress.unit)
              ? ` ${progressUnitLabel(progress.unit)}`
              : ""}{" "}
            · {percent}%
          </p>
          <progress
            value={progress.current}
            max={progress.total}
            aria-label={`${progressStepLabel(progress.step)} ${percent} percent`}
          />
        </div>
      ) : null}
      {!terminal && progress && percent == null ? (
        <p className="muted" style={{ margin: 0 }}>
          {progressStepLabel(progress.step)}…
        </p>
      ) : null}
      {!terminal && elapsedSeconds != null ? (
        <p className="muted" style={{ margin: 0 }}>
          Elapsed {formatElapsed(elapsedSeconds)}
        </p>
      ) : null}
      {operation.status === "failed" && operation.error ? (
        <p className="error-box" role="alert">
          {managedOperationFailureMessage(operation)}
        </p>
      ) : null}
      {operation.status === "interrupted" ? (
        <p className="error-box" role="alert">
          Processing was interrupted. You may retry this action.
        </p>
      ) : null}
      {operation.status === "succeeded" ? (
        <p className="muted">
          {successMessage ?? defaultSuccessMessage(operation)}
        </p>
      ) : null}
    </div>
  );
}
