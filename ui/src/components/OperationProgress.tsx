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
import { formatBytes } from "../features/workspaces/format";
import type {
  Operation,
  OperationMetrics,
  OperationStageDurations,
  OperationWorklistDocument,
} from "../api/types";

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

function formatRate(value: number): string {
  return value >= 10 ? value.toFixed(0) : value.toFixed(1);
}

function terminalElapsedSeconds(operation: Operation): number | null {
  const created = parseTimestampMs(operation.created_at);
  const updated = parseTimestampMs(operation.updated_at);
  if (created == null || updated == null || updated < created) return null;
  return (updated - created) / 1000;
}

function activeDocumentMessage(
  documents: OperationWorklistDocument[],
  step: string | null | undefined,
): string | null {
  if (documents.length === 0) return null;

  const action =
    step === "parsing_documents"
      ? "Reading"
      : step === "chunking_documents"
        ? "Preparing passages for"
        : step === "embedding_chunks"
          ? "Embedding passages from"
          : step === "materializing_dense_index"
            ? "Finalizing semantic search for"
            : step === "analyzing_lexical_chunks" ||
                step === "materializing_lexical_index"
              ? "Updating keyword search for"
              : "Processing";

  if (documents.length === 1) {
    return `${action} ${documents[0]!.display_name}`;
  }
  if (step === "embedding_chunks") {
    return `Embedding passages across ${formatCount(documents.length)} documents`;
  }
  return `${action} ${formatCount(documents.length)} documents`;
}

function documentPhaseLabel(phase: string): string {
  switch (phase) {
    case "pending":
      return "Pending";
    case "parsing":
      return "Reading";
    case "parsed":
      return "Read";
    case "chunking":
      return "Preparing passages";
    case "chunked":
      return "Passages prepared";
    case "indexing":
      return "Indexing";
    case "indexed":
      return "Indexed";
    case "removed":
      return "Removed";
    case "failed":
      return "Failed";
    case "requires_ocr":
      return "OCR required";
    default:
      return "Processing";
  }
}

function terminalDocumentCount(
  worklist: Operation["worklist"],
): number | null {
  if (!worklist) return null;
  if (worklist.completed_count != null) return worklist.completed_count;
  return worklist.documents.filter((document) =>
    ["indexed", "removed", "failed", "requires_ocr"].includes(document.phase),
  ).length;
}

function remainingDocumentCount(worklist: Operation["worklist"]): number | null {
  if (!worklist) return null;
  if (worklist.remaining_count != null) return worklist.remaining_count;
  const completed = terminalDocumentCount(worklist);
  return completed == null ? null : worklist.total_document_count - completed;
}

function metricRows(metrics: OperationMetrics): Array<[string, number | string]> {
  const rows: Array<[string, number | string]> = [];
  const values: Array<[string, number | null | undefined]> = [
    ["Requested documents", metrics.requested_document_count],
    ["Sources before", metrics.pre_active_source_count],
    ["Sources after", metrics.post_active_source_count],
    ["Uploaded raw bytes", metrics.uploaded_raw_bytes],
    ["Searchable documents", metrics.parsed_searchable_document_count],
    ["Searchable passages", metrics.child_chunk_count],
    ["Oversized passages", metrics.oversized_unsplittable_count],
    ["Parsed artifacts generated", metrics.parsed_artifacts_generated],
    ["Parsed artifacts reused", metrics.parsed_artifacts_reused],
    ["Passage sets generated", metrics.chunk_artifacts_generated],
    ["Passage sets reused", metrics.chunk_artifacts_reused],
    ["Generated embeddings", metrics.embeddings_generated],
    ["Reused embeddings", metrics.embeddings_reused],
    ["Failed embeddings", metrics.embeddings_failed],
    ["Model input throughput", metrics.model_input_tokens_per_sec],
  ];
  for (const [label, value] of values) {
    if (value != null) rows.push([label, value]);
  }
  if (metrics.uploaded_raw_bytes != null) {
    const index = rows.findIndex(([label]) => label === "Uploaded raw bytes");
    if (index >= 0) rows[index] = ["Uploaded raw bytes", formatBytes(metrics.uploaded_raw_bytes)];
  }
  if (metrics.model_input_tokens_per_sec != null) {
    const index = rows.findIndex(([label]) => label === "Model input throughput");
    if (index >= 0) {
      rows[index] = [
        "Model input throughput",
        `${formatRate(metrics.model_input_tokens_per_sec)} tokens/s`,
      ];
    }
  }
  return rows;
}

function durationRows(durations: OperationStageDurations): Array<[string, number]> {
  const labels: Array<[string, keyof OperationStageDurations]> = [
    ["Parsing", "parsing_ms"],
    ["Chunking", "chunking_ms"],
    ["Dense generation", "dense_generation_ms"],
    ["Dense materialization", "dense_materialization_ms"],
    ["Keyword indexing", "lexical_ms"],
    ["Publication", "publication_ms"],
    ["Finalization", "finalization_ms"],
    ["Total", "total_ms"],
  ];
  return labels.flatMap(([label, key]) => {
    const value = durations[key];
    return value == null ? [] : [[label, value] as [string, number]];
  });
}

function successfulSourceSummary(operation: Operation): string[] {
  if (operation.kind !== "source_add" && operation.kind !== "source_replace") {
    return [];
  }
  const metrics = operation.metrics;
  if (!metrics) return [];

  const summary: string[] = [];
  if (metrics.post_active_source_count != null) {
    const count = metrics.post_active_source_count;
    summary.push(`${formatCount(count)} ${count === 1 ? "source" : "sources"} ready`);
  }
  if (metrics.child_chunk_count != null) {
    summary.push(`${formatCount(metrics.child_chunk_count)} searchable passages`);
  }
  return summary;
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
  const elapsedSeconds = terminal
    ? terminalElapsedSeconds(operation)
    : createdMs != null
      ? (nowMs - createdMs) / 1000
      : null;
  const worklist = operation.worklist ?? null;
  const completedDocuments = terminalDocumentCount(worklist);
  const remainingDocuments = remainingDocumentCount(worklist);
  const activeMessage = activeDocumentMessage(
    worklist?.active_documents ?? [],
    progress?.step,
  );
  const metrics = operation.metrics ?? null;
  const denseExecution = metrics?.dense_execution ?? null;
  const executionDevice = denseExecution?.device?.trim();
  const deviceLabel = executionDevice
    ? executionDevice.toLowerCase() === "cuda"
      ? "CUDA"
      : executionDevice.toLowerCase() === "cpu"
        ? "CPU"
        : executionDevice
    : null;
  const generated = metrics?.embeddings_generated;
  const reused = metrics?.embeddings_reused;
  const compactEmbeddingCounts =
    generated != null || reused != null
      ? `Generated ${generated == null ? "—" : formatCount(generated)} · Reused ${reused == null ? "—" : formatCount(reused)} embeddings`
      : null;
  const throughput = metrics?.generated_chunks_per_sec;
  const sourceSummary = successfulSourceSummary(operation);
  const requiresOcrDocuments =
    worklist?.documents.filter((document) => document.phase === "requires_ocr") ?? [];
  const failedDocuments =
    worklist?.documents.filter((document) => document.phase === "failed") ?? [];

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
      {activeMessage ? (
        <p className="muted" data-testid="operation-active-documents">
          {activeMessage}
        </p>
      ) : null}
      {worklist && completedDocuments != null ? (
        <p className="muted" data-testid="operation-document-counts">
          {formatCount(completedDocuments)} / {formatCount(worklist.total_document_count)} documents complete
          {remainingDocuments != null
            ? ` · ${formatCount(remainingDocuments)} remaining`
            : ""}
        </p>
      ) : null}
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
      {deviceLabel ? (
        <p className="muted" data-testid="operation-execution-device">
          Execution device: {deviceLabel}
        </p>
      ) : null}
      {!terminal && compactEmbeddingCounts ? (
        <p className="muted" data-testid="operation-embedding-counts">
          {compactEmbeddingCounts}
        </p>
      ) : null}
      {!terminal && throughput != null && Number.isFinite(throughput) && throughput > 0 ? (
        <p className="muted" data-testid="operation-throughput">
          {formatRate(throughput)} new passages/s
        </p>
      ) : null}
      {operation.status === "failed" && operation.error ? (
        <p className="error-box" role="alert">
          {managedOperationFailureMessage(operation)}
        </p>
      ) : null}
      {operation.status === "failed" && requiresOcrDocuments.length > 0 ? (
        <p className="error-box" role="alert" data-testid="operation-ocr-failure">
          OCR is required to read: {requiresOcrDocuments
            .map((document) => document.display_name)
            .join(", ")}.
        </p>
      ) : null}
      {operation.status === "failed" && failedDocuments.length > 0 ? (
        <p className="error-box" role="alert" data-testid="operation-failed-documents">
          Could not process: {failedDocuments
            .map((document) => document.display_name)
            .join(", ")}.
        </p>
      ) : null}
      {operation.status === "interrupted" ? (
        <p className="error-box" role="alert">
          Processing was interrupted. You may retry this action.
        </p>
      ) : null}
      {operation.status === "succeeded" ? (
        <div className="stack" data-testid="operation-success-summary">
          {successMessage ? (
            <p className="muted">{successMessage}</p>
          ) : sourceSummary.length > 0 ? (
            <>
              <p className="muted" style={{ margin: 0 }}>
                {sourceSummary.join(" · ")}
              </p>
              {compactEmbeddingCounts ? (
                <p className="muted" style={{ margin: 0 }}>
                  {compactEmbeddingCounts}
                </p>
              ) : null}
              {elapsedSeconds != null ? (
                <p className="muted" style={{ margin: 0 }}>
                  Completed in {formatElapsed(elapsedSeconds)}
                </p>
              ) : null}
            </>
          ) : (
            <p className="muted">{defaultSuccessMessage(operation)}</p>
          )}
        </div>
      ) : null}
      {worklist ? (
        <details className="operation-worklist" data-testid="operation-worklist">
          <summary>
            Worklist · {remainingDocuments == null
              ? `${formatCount(worklist.total_document_count)} documents`
              : `${formatCount(remainingDocuments)} remaining of ${formatCount(worklist.total_document_count)}`}
          </summary>
          <ul>
            {worklist.documents.map((document) => (
              <li key={document.document_id}>
                <strong>{document.display_name}</strong> · {documentPhaseLabel(document.phase)}
                {document.child_chunk_count != null
                  ? ` · ${formatCount(document.child_chunk_count)} passages`
                  : ""}
                {document.embeddings_generated != null
                  ? ` · ${formatCount(document.embeddings_generated)} generated`
                  : ""}
                {document.embeddings_reused != null
                  ? ` · ${formatCount(document.embeddings_reused)} reused`
                  : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {metrics ? (
        <details className="operation-details" data-testid="operation-details">
          <summary>Details</summary>
          {metricRows(metrics).length > 0 ? (
            <dl>
              {metricRows(metrics).map(([name, value]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{typeof value === "number" ? formatCount(value) : value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {denseExecution ? (
            <dl>
              {(
                [
                  ["Device", denseExecution.device],
                  ["Data type", denseExecution.dtype],
                  ["Batch size", denseExecution.batch_size],
                  ["Attention backend", denseExecution.attention_backend],
                  ["Embedding dimension", denseExecution.embedding_dimension],
                  ["Profile", denseExecution.profile_id],
                  ["Representation", denseExecution.representation_id],
                  ["Backend", denseExecution.backend],
                  ["Provider", denseExecution.provider],
                  ["Resolved precision", denseExecution.resolved_precision],
                ] as Array<[string, string | number | null | undefined]>
              )
                .filter(([, value]) => value != null)
                .map(([name, value]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
            </dl>
          ) : null}
          {metrics.stage_durations ? (
            <dl>
              {durationRows(metrics.stage_durations).map(([name, milliseconds]) => (
                <div key={name}>
                  <dt>{name} duration</dt>
                  <dd>{formatElapsed(milliseconds / 1000)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {metrics.lexical ? (
            <dl>
              {(
                [
                  ["Searchable units contract", metrics.lexical.searchable_units_contract],
                  ["Chunk-set passages", metrics.lexical.chunk_set_child_count],
                  ["Zero-term excluded", metrics.lexical.zero_term_excluded_count],
                  ["Eligible passages", metrics.lexical.eligible_child_count],
                  ["Indexed passages", metrics.lexical.indexed_child_count],
                ] as Array<[string, string | number | null | undefined]>
              )
                .filter(([, value]) => value != null)
                .map(([name, value]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
            </dl>
          ) : null}
        </details>
      ) : null}
    </div>
  );
}
