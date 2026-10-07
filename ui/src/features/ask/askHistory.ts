import type {
  AnswerBlock,
  WorkspaceCitation,
  WorkspaceQueryResponse,
} from "../../api/types";

export type AskHistoryEntry = {
  entryId: string;
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  response: WorkspaceQueryResponse;
};

/** Bumped for V2 claim-linked history; legacy B1 entries are not remapped. */
const KEY_PREFIX = "seneca.ask-history.v2:";
export const ASK_HISTORY_MAX = 25;

const VALID_STATUSES = new Set([
  "answered",
  "insufficient_evidence",
  "model_abstain",
]);

function storageKey(workspaceId: string): string {
  return `${KEY_PREFIX}${workspaceId}`;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNullableFiniteNumber(value: unknown): boolean {
  return (
    value === null || (typeof value === "number" && Number.isFinite(value))
  );
}

function isCitation(value: unknown): value is WorkspaceCitation {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    isNonEmptyString(row.evidence_unit_id) &&
    isNonEmptyString(row.document_id) &&
    isNonEmptyString(row.source_chunk_id) &&
    typeof row.kind === "string" &&
    isStringArray(row.section_path) &&
    isNullableFiniteNumber(row.page_start) &&
    isNullableFiniteNumber(row.page_end) &&
    isNullableFiniteNumber(row.line_start) &&
    isNullableFiniteNumber(row.line_end) &&
    typeof row.clipped === "boolean" &&
    isNonEmptyString(row.source_id) &&
    typeof row.source_version === "number" &&
    Number.isFinite(row.source_version) &&
    row.source_version > 0 &&
    typeof row.source_display_name === "string" &&
    isNonEmptyString(row.citation_ref) &&
    typeof row.excerpt === "string" &&
    typeof row.excerpt_clipped === "boolean"
  );
}

function isAnswerBlock(value: unknown): value is AnswerBlock {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.text === "string" &&
    row.text.trim().length > 0 &&
    isStringArray(row.citation_refs) &&
    row.citation_refs.length > 0
  );
}

function isResponse(value: unknown): value is WorkspaceQueryResponse {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  if (
    !isNonEmptyString(row.workspace_id) ||
    typeof row.workspace_revision !== "number" ||
    !Number.isFinite(row.workspace_revision) ||
    !isNonEmptyString(row.snapshot_id) ||
    !isNonEmptyString(row.product_mode_id) ||
    !isNonEmptyString(row.trace_id) ||
    typeof row.status !== "string" ||
    !VALID_STATUSES.has(row.status) ||
    !Array.isArray(row.citations) ||
    !row.citations.every(isCitation) ||
    !Array.isArray(row.answer_blocks)
  ) {
    return false;
  }
  if (!(typeof row.answer === "string" || row.answer === null)) {
    return false;
  }
  if (
    !(
      row.abstention_reason === null ||
      typeof row.abstention_reason === "string"
    )
  ) {
    return false;
  }
  if (row.status === "answered") {
    if (typeof row.answer !== "string") return false;
    if (!row.answer_blocks.every(isAnswerBlock)) return false;
    if (row.answer_blocks.length === 0) return false;
    if (row.citations.length === 0) return false;
    if (row.abstention_reason !== null) return false;
  } else {
    if (row.answer !== null) return false;
    if (row.answer_blocks.length !== 0) return false;
    if (row.citations.length !== 0) return false;
    if (typeof row.abstention_reason !== "string") return false;
  }
  return true;
}

function isEntry(value: unknown): value is AskHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    isNonEmptyString(row.entryId) &&
    isNonEmptyString(row.askedAt) &&
    typeof row.question === "string" &&
    isStringArray(row.selectedSourceIds) &&
    isStringArray(row.selectedSourceNames) &&
    isResponse(row.response)
  );
}

/**
 * Load session-local Ask history.
 * Malformed whole payloads are removed. Individual malformed entries are
 * dropped; remaining valid entries are kept (deterministic filter).
 */
export function loadAskHistory(workspaceId: string): AskHistoryEntry[] {
  try {
    const raw = sessionStorage.getItem(storageKey(workspaceId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      sessionStorage.removeItem(storageKey(workspaceId));
      return [];
    }
    return parsed.filter(isEntry).slice(0, ASK_HISTORY_MAX);
  } catch {
    try {
      sessionStorage.removeItem(storageKey(workspaceId));
    } catch {
      /* ignore */
    }
    return [];
  }
}

export function persistAskHistory(
  workspaceId: string,
  entries: AskHistoryEntry[],
): void {
  try {
    sessionStorage.setItem(
      storageKey(workspaceId),
      JSON.stringify(entries.slice(0, ASK_HISTORY_MAX)),
    );
  } catch {
    /* ignore */
  }
}

export function appendAskHistory(
  workspaceId: string,
  entry: AskHistoryEntry,
): AskHistoryEntry[] {
  const prior = loadAskHistory(workspaceId);
  const next = [entry, ...prior].slice(0, ASK_HISTORY_MAX);
  persistAskHistory(workspaceId, next);
  return next;
}

export function newHistoryEntryId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `ask_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function snapshotBadge(
  entrySnapshotId: string,
  currentSnapshotId: string | null,
): "current" | "historical" {
  if (
    currentSnapshotId != null &&
    entrySnapshotId === currentSnapshotId
  ) {
    return "current";
  }
  return "historical";
}
