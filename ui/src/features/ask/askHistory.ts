import type { WorkspaceQueryResponse } from "../../api/types";

export type AskHistoryEntry = {
  entryId: string;
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  response: WorkspaceQueryResponse;
};

const KEY_PREFIX = "seneca.ask-history.v1:";
export const ASK_HISTORY_MAX = 25;

function storageKey(workspaceId: string): string {
  return `${KEY_PREFIX}${workspaceId}`;
}

function isCitation(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.evidence_unit_id === "string" &&
    typeof row.source_id === "string" &&
    typeof row.source_version === "number"
  );
}

function isResponse(value: unknown): value is WorkspaceQueryResponse {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.workspace_id === "string" &&
    typeof row.workspace_revision === "number" &&
    typeof row.snapshot_id === "string" &&
    typeof row.trace_id === "string" &&
    typeof row.status === "string" &&
    Array.isArray(row.citations) &&
    row.citations.every(isCitation)
  );
}

function isEntry(value: unknown): value is AskHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    typeof row.entryId === "string" &&
    typeof row.askedAt === "string" &&
    typeof row.question === "string" &&
    Array.isArray(row.selectedSourceIds) &&
    Array.isArray(row.selectedSourceNames) &&
    isResponse(row.response)
  );
}

export function loadAskHistory(workspaceId: string): AskHistoryEntry[] {
  try {
    const raw = sessionStorage.getItem(storageKey(workspaceId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      sessionStorage.removeItem(storageKey(workspaceId));
      return [];
    }
    const entries = parsed.filter(isEntry).slice(0, ASK_HISTORY_MAX);
    return entries;
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
