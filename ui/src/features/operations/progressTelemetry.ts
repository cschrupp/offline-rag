import type { OperationProgressTelemetry } from "../../api/types";

const STEP_LABELS: Record<string, string> = {
  parsing_documents: "Reading documents",
  chunking_documents: "Preparing searchable passages",
  embedding_chunks: "Building semantic search index",
  materializing_dense_index: "Finalizing semantic search index",
  analyzing_lexical_chunks: "Building keyword search index",
  materializing_lexical_index: "Finalizing keyword search index",
  proposing_questions: "Proposing candidate questions",
  pooling_cases: "Pooling evidence",
  prelabeling_candidates: "Reviewing candidate evidence",
  publishing: "Publishing",
  finalizing: "Finalizing",
};

const UNIT_LABELS: Record<string, string> = {
  documents: "documents",
  chunks: "chunks",
  questions: "questions",
  cases: "cases",
  candidates: "candidates",
  model_calls: "model calls",
};

export function progressStepLabel(step: string | null | undefined): string {
  if (!step) return "Working";
  return STEP_LABELS[step] ?? "Working";
}

export function progressUnitLabel(unit: string | null | undefined): string {
  if (!unit) return "";
  return UNIT_LABELS[unit] ?? unit;
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const rem = s % 60;
  if (hours > 0) return `${hours}h ${minutes}m ${rem}s`;
  if (minutes > 0) return `${minutes}m ${rem}s`;
  return `${rem}s`;
}

export function progressPercent(
  progress: OperationProgressTelemetry | null | undefined,
): number | null {
  if (!progress || progress.total == null || progress.total <= 0) return null;
  const raw = Math.floor((progress.current * 100) / progress.total);
  return Math.max(0, Math.min(100, raw));
}

export function approximateEtaSeconds(params: {
  progress: OperationProgressTelemetry | null | undefined;
  nowMs: number;
}): number | null {
  const { progress, nowMs } = params;
  if (!progress || progress.total == null || progress.total <= 0) return null;
  if (progress.current <= 0 || progress.current >= progress.total) return null;
  const started = Date.parse(progress.started_at);
  if (!Number.isFinite(started)) return null;
  const elapsed = (nowMs - started) / 1000;
  if (elapsed < 10) return null;
  const rate = progress.current / elapsed;
  if (!(rate > 0)) return null;
  const remaining = (progress.total - progress.current) / rate;
  if (!(remaining > 0) || !Number.isFinite(remaining)) return null;
  return remaining;
}

export function parseTimestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}
