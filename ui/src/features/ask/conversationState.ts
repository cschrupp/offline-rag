import type {
  AnswerBlock,
  ConversationPriorTurn,
  ConversationTurnResponse,
  WorkspaceCitation,
} from "../../api/types";
import type { SourceSelectionMode } from "./sourceSelection";
import {
  assistantPresentationText,
  unicodeCharCount,
} from "./assistantPresentation";
import { snapshotBadge } from "./askHistory";

export type ConversationPair = {
  pairId: string;
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  /** Frozen all | subset intent at admission (A2-D11). */
  selectionMode: SourceSelectionMode;
  response: ConversationTurnResponse;
};

/** Incomplete sent user turn that is not a completed pair (A2-D10 / R2). */
export type IncompleteUserTurn = {
  pairId: string;
  /** Immutable submission-time order key (ISO). Presentation-only; not session-persisted. */
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  selectionMode: SourceSelectionMode;
  status: "pending" | "failed";
  errorMessage?: string | null;
};

/** Unified conversation thread item ordered by submission time (Rework 2). */
export type ConversationTimelineItem =
  | { kind: "completed"; askedAt: string; entry: ConversationHistoryEntry }
  | { kind: "incomplete"; askedAt: string; turn: IncompleteUserTurn };

/**
 * Merge completed pairs and incomplete/failed turns into one chronological
 * thread by immutable submission `askedAt` (not completion time).
 */
export function buildConversationTimeline(
  historyNewestFirst: ConversationHistoryEntry[],
  incompleteTurns: IncompleteUserTurn[],
): ConversationTimelineItem[] {
  const items: ConversationTimelineItem[] = [
    ...historyNewestFirst.map((entry) => ({
      kind: "completed" as const,
      askedAt: entry.askedAt,
      entry,
    })),
    ...incompleteTurns.map((turn) => ({
      kind: "incomplete" as const,
      askedAt: turn.askedAt,
      turn,
    })),
  ];
  items.sort((a, b) => {
    if (a.askedAt < b.askedAt) return -1;
    if (a.askedAt > b.askedAt) return 1;
    const aId = a.kind === "completed" ? a.entry.entryId : a.turn.pairId;
    const bId = b.kind === "completed" ? b.entry.entryId : b.turn.pairId;
    return aId < bId ? -1 : aId > bId ? 1 : 0;
  });
  return items;
}

/** Presentation view for Evidence / Claim UI — dual traces preserved. */
export type ConversationHistoryEntry = {
  entryId: string;
  askedAt: string;
  question: string;
  selectedSourceIds: string[];
  selectedSourceNames: string[];
  selectionMode: SourceSelectionMode;
  response: ConversationTurnResponse;
};

const KEY_PREFIX = "seneca.conversation.v1:";
export const CONVERSATION_PAIR_MAX = 50;
export const RESOLVER_PAIR_MAX = 6;
export const RESOLVER_CHAR_MAX = 12_000;

const VALID_STATUSES = new Set([
  "answered",
  "insufficient_evidence",
  "model_abstain",
  "clarification_required",
]);

const INSUFFICIENT_EVIDENCE_REASONS = new Set([
  "no_evidence",
  "insufficient_support",
]);
const MODEL_ABSTAIN_REASONS = new Set([
  "insufficient_support",
  "conflicting_evidence",
  "model_declined",
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

function firstReferenceCitationRefs(blocks: AnswerBlock[]): string[] {
  const ordered: string[] = [];
  const seen = new Set<string>();
  for (const block of blocks) {
    for (const ref of block.citation_refs) {
      if (seen.has(ref)) continue;
      seen.add(ref);
      ordered.push(ref);
    }
  }
  return ordered;
}

function answeredReferentialIntegrity(
  answer: string,
  blocks: AnswerBlock[],
  citations: WorkspaceCitation[],
): boolean {
  if (answer.trim().length === 0) return false;
  if (blocks.length === 0 || citations.length === 0) return false;
  const projected = blocks.map((b) => b.text).join("\n\n");
  if (answer !== projected) return false;
  const byRef = new Map<string, WorkspaceCitation>();
  for (const citation of citations) {
    if (byRef.has(citation.citation_ref)) return false;
    byRef.set(citation.citation_ref, citation);
  }
  for (const block of blocks) {
    let resolved = 0;
    for (const ref of block.citation_refs) {
      if (!byRef.has(ref)) return false;
      resolved += 1;
    }
    if (resolved < 1) return false;
  }
  const expectedRefs = firstReferenceCitationRefs(blocks);
  if (expectedRefs.length !== citations.length) return false;
  for (let i = 0; i < expectedRefs.length; i += 1) {
    if (citations[i]?.citation_ref !== expectedRefs[i]) return false;
  }
  return true;
}

function isValidAbstentionReason(
  status: string,
  reason: unknown,
): reason is string {
  if (typeof reason !== "string") return false;
  if (status === "clarification_required") {
    return reason === "ambiguous_request";
  }
  if (reason === "ambiguous_request") return false;
  if (status === "insufficient_evidence") {
    return INSUFFICIENT_EVIDENCE_REASONS.has(reason);
  }
  if (status === "model_abstain") {
    return MODEL_ABSTAIN_REASONS.has(reason);
  }
  return false;
}

function isTurnResponse(value: unknown): value is ConversationTurnResponse {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  if (
    !isNonEmptyString(row.workspace_id) ||
    typeof row.workspace_revision !== "number" ||
    !Number.isFinite(row.workspace_revision) ||
    !isNonEmptyString(row.snapshot_id) ||
    !isNonEmptyString(row.product_mode_id) ||
    !isNonEmptyString(row.conversation_trace_id) ||
    !(row.query_trace_id === null || isNonEmptyString(row.query_trace_id)) ||
    typeof row.status !== "string" ||
    !VALID_STATUSES.has(row.status) ||
    typeof row.context_used !== "boolean" ||
    !isNonEmptyString(row.question) ||
    !(row.retrieval_question === null || typeof row.retrieval_question === "string") ||
    !Array.isArray(row.citations) ||
    !row.citations.every(isCitation) ||
    !Array.isArray(row.answer_blocks)
  ) {
    return false;
  }
  if (!(typeof row.answer === "string" || row.answer === null)) {
    return false;
  }

  if (row.status === "answered") {
    if (typeof row.answer !== "string" || row.answer.trim().length === 0) {
      return false;
    }
    if (row.abstention_reason !== null) return false;
    if (!isNonEmptyString(row.query_trace_id)) return false;
    if (!isNonEmptyString(row.retrieval_question)) return false;
    if (!row.answer_blocks.every(isAnswerBlock)) return false;
    if (row.answer_blocks.length === 0) return false;
    if (row.citations.length === 0) return false;
    return answeredReferentialIntegrity(
      row.answer,
      row.answer_blocks,
      row.citations,
    );
  }

  if (row.status === "clarification_required") {
    if (row.query_trace_id !== null) return false;
    if (row.retrieval_question !== null) return false;
    if (row.answer !== null) return false;
    if (row.answer_blocks.length !== 0) return false;
    if (row.citations.length !== 0) return false;
    return isValidAbstentionReason(row.status, row.abstention_reason);
  }

  if (row.answer !== null) return false;
  if (row.answer_blocks.length !== 0) return false;
  if (row.citations.length !== 0) return false;
  if (!isNonEmptyString(row.query_trace_id)) return false;
  return isValidAbstentionReason(row.status, row.abstention_reason);
}

function isPair(value: unknown): value is ConversationPair {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    isNonEmptyString(row.pairId) &&
    isNonEmptyString(row.askedAt) &&
    typeof row.question === "string" &&
    isStringArray(row.selectedSourceIds) &&
    isStringArray(row.selectedSourceNames) &&
    (row.selectionMode === "all" || row.selectionMode === "subset") &&
    isTurnResponse(row.response)
  );
}

export function loadConversation(workspaceId: string): ConversationPair[] {
  try {
    const raw = sessionStorage.getItem(storageKey(workspaceId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      sessionStorage.removeItem(storageKey(workspaceId));
      return [];
    }
    return parsed.filter(isPair).slice(0, CONVERSATION_PAIR_MAX);
  } catch {
    try {
      sessionStorage.removeItem(storageKey(workspaceId));
    } catch {
      /* ignore */
    }
    return [];
  }
}

export function persistConversation(
  workspaceId: string,
  pairs: ConversationPair[],
): void {
  try {
    sessionStorage.setItem(
      storageKey(workspaceId),
      JSON.stringify(pairs.slice(0, CONVERSATION_PAIR_MAX)),
    );
  } catch {
    /* ignore */
  }
}

export function appendConversationPair(
  workspaceId: string,
  pair: ConversationPair,
): ConversationPair[] {
  const prior = loadConversation(workspaceId);
  const next = [pair, ...prior].slice(0, CONVERSATION_PAIR_MAX);
  persistConversation(workspaceId, next);
  return next;
}

export function clearConversation(workspaceId: string): void {
  try {
    sessionStorage.removeItem(storageKey(workspaceId));
  } catch {
    /* ignore */
  }
}

export function newPairId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `conv_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

/**
 * Deterministic resolver window (A2-D07 client SHOULD):
 * newest completed pairs win; max 6 pairs; drop oldest whole pairs for 12k
 * Unicode code points. Incomplete/failed turns are never included.
 */
export function buildResolverPriorTurns(
  pairsChronologicalOldestFirst: ConversationPair[],
): ConversationPriorTurn[] {
  const completed = pairsChronologicalOldestFirst.filter(
    (pair) =>
      typeof pair.question === "string" &&
      pair.question.trim().length > 0 &&
      pair.response != null,
  );
  let window = completed.slice(-RESOLVER_PAIR_MAX);
  const totalChars = () =>
    window.reduce((sum, pair) => {
      const user = pair.question.trim();
      const assistant = assistantPresentationText(pair.response);
      return sum + unicodeCharCount(user) + unicodeCharCount(assistant);
    }, 0);
  while (window.length > 0 && totalChars() > RESOLVER_CHAR_MAX) {
    window = window.slice(1);
  }
  const turns: ConversationPriorTurn[] = [];
  for (const pair of window) {
    turns.push({ role: "user", text: pair.question.trim() });
    turns.push({
      role: "assistant",
      text: assistantPresentationText(pair.response),
    });
  }
  return turns;
}

export function chronologicalPairs(
  newestFirst: ConversationPair[],
): ConversationPair[] {
  return [...newestFirst].reverse();
}

export function toHistoryEntry(pair: ConversationPair): ConversationHistoryEntry {
  return {
    entryId: pair.pairId,
    askedAt: pair.askedAt,
    question: pair.question,
    selectedSourceIds: pair.selectedSourceIds,
    selectedSourceNames: pair.selectedSourceNames,
    selectionMode: pair.selectionMode,
    response: pair.response,
  };
}

/** Compact frozen logical source-scope presentation (A2-D11 / R6). */
export function sourceScopeLabel(entry: {
  selectionMode: SourceSelectionMode;
  selectedSourceNames: string[];
}): string {
  const names = entry.selectedSourceNames.join(", ");
  if (entry.selectionMode === "all") {
    return names
      ? `All active sources · ${names}`
      : "All active sources";
  }
  return names ? `Selected sources · ${names}` : "Selected sources";
}

export { assistantPresentationText, snapshotBadge, unicodeCharCount };
