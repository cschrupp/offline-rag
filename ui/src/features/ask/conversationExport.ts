/** Conversation Markdown/JSON export serializers (Amendment A4). */

import type {
  AnswerBlock,
  ConversationTurnResponse,
  WorkspaceCitation,
} from "../../api/types";
import type { DownloadArtifact } from "../../lib/downloadFile";
import { buildExportFilename } from "../../lib/safeFilename";
import { assistantPresentationText } from "./assistantPresentation";
import {
  buildConversationTimeline,
  type ConversationHistoryEntry,
  type IncompleteUserTurn,
} from "./conversationState";

export const CONVERSATION_FORMAT = "seneca-conversation";
export const CONVERSATION_VERSION = 1;

export const DERIVED_CONVERSATION_WARNING =
  "Derived Seneca conversation. Assistant responses in this document were generated from cited sources. This document is derived material and is not primary evidence.";

export type ConversationExportWorkspace = {
  workspace_id: string;
  title: string;
  revision: number;
  current_snapshot_id: string | null;
};

export type ConversationExportView = "normal" | "training";

export type ConversationExportInput = {
  workspace: ConversationExportWorkspace;
  history: ConversationHistoryEntry[];
  incompleteTurns: IncompleteUserTurn[];
  exportedFromView: ConversationExportView;
  exportedAt?: string;
};

function citationLocatorDetails(citation: WorkspaceCitation): string[] {
  const detail: string[] = [`- Version: ${citation.source_version}`];
  if (citation.page_start != null || citation.page_end != null) {
    const start = citation.page_start ?? citation.page_end;
    const end = citation.page_end ?? citation.page_start;
    detail.push(
      start === end ? `- Page: ${start}` : `- Page: ${start}-${end}`,
    );
  }
  if (citation.line_start != null || citation.line_end != null) {
    const start = citation.line_start ?? citation.line_end;
    const end = citation.line_end ?? citation.line_start;
    detail.push(
      start === end ? `- Line: ${start}` : `- Line: ${start}-${end}`,
    );
  }
  if (citation.section_path.length > 0) {
    detail.push(`- Section: ${citation.section_path.join(" / ")}`);
  }
  return detail;
}

function formatAnswerWithMarkers(
  blocks: AnswerBlock[],
  citations: WorkspaceCitation[],
): { answerMarkdown: string; sourcesMarkdown: string } {
  const refToIndex = new Map<string, number>();
  citations.forEach((citation, index) => {
    if (!refToIndex.has(citation.citation_ref)) {
      refToIndex.set(citation.citation_ref, index + 1);
    }
  });

  const answerParts = blocks.map((block) => {
    const markers = block.citation_refs
      .map((ref) => refToIndex.get(ref))
      .filter((n): n is number => typeof n === "number")
      .map((n) => `[${n}]`)
      .join("");
    return `${block.text}${markers}`;
  });

  const sourcesLines: string[] = [];
  citations.forEach((citation, index) => {
    sourcesLines.push(`${index + 1}. \`${citation.source_display_name}\``);
    for (const line of citationLocatorDetails(citation)) {
      sourcesLines.push(`   ${line}`);
    }
  });

  return {
    answerMarkdown: answerParts.join("\n\n"),
    sourcesMarkdown: sourcesLines.join("\n"),
  };
}

function statusHeading(status: string): string {
  switch (status) {
    case "answered":
      return "answered";
    case "clarification_required":
      return "clarification_required";
    case "insufficient_evidence":
      return "insufficient_evidence";
    case "model_abstain":
      return "model_abstain";
    default:
      return status;
  }
}

export function conversationHasPendingTurn(
  incompleteTurns: IncompleteUserTurn[],
): boolean {
  return incompleteTurns.some((turn) => turn.status === "pending");
}

export function serializeConversationMarkdown(
  input: ConversationExportInput,
): DownloadArtifact {
  const exportedAt = input.exportedAt ?? new Date().toISOString();
  const timeline = buildConversationTimeline(
    input.history,
    input.incompleteTurns.filter((turn) => turn.status !== "pending"),
  );

  const parts: string[] = [
    `# Seneca Conversation — ${input.workspace.title}`,
    "",
    `Exported: ${exportedAt}`,
    "",
    `> **Derived Seneca conversation.**`,
    `> Assistant responses in this document were generated from cited sources.`,
    `> This document is derived material and is not primary evidence.`,
    "",
  ];

  let turnNumber = 0;
  for (const item of timeline) {
    turnNumber += 1;
    parts.push(`## Turn ${turnNumber}`, "");
    if (item.kind === "incomplete") {
      parts.push("### User", "", item.turn.question, "", "### Seneca", "");
      parts.push("**Turn did not complete.**", "");
      if (item.turn.errorMessage) {
        parts.push(item.turn.errorMessage, "");
      }
      continue;
    }

    const entry = item.entry;
    const response = entry.response;
    parts.push("### User", "", entry.question, "", "### Seneca", "");

    if (response.status === "answered") {
      const { answerMarkdown, sourcesMarkdown } = formatAnswerWithMarkers(
        response.answer_blocks,
        response.citations,
      );
      parts.push(answerMarkdown || response.answer || "", "");
      if (sourcesMarkdown) {
        parts.push("### Sources", "", sourcesMarkdown, "");
      }
    } else {
      parts.push(`**Status:** ${statusHeading(String(response.status))}`, "");
      parts.push(assistantPresentationText(response), "");
    }
  }

  return {
    filename: buildExportFilename("conversation", input.workspace.title, "md"),
    mimeType: "text/markdown;charset=utf-8",
    content: `${parts.join("\n").trimEnd()}\n`,
  };
}

function completedTurnJson(entry: ConversationHistoryEntry) {
  const response: ConversationTurnResponse = entry.response;
  return {
    kind: "completed" as const,
    asked_at: entry.askedAt,
    question: entry.question,
    selection_mode: entry.selectionMode,
    selected_source_ids: entry.selectedSourceIds,
    selected_source_names: entry.selectedSourceNames,
    status: response.status,
    abstention_reason: response.abstention_reason,
    answer: response.answer,
    answer_blocks: response.answer_blocks,
    citations: response.citations,
    workspace_revision: response.workspace_revision,
    snapshot_id: response.snapshot_id,
    conversation_trace_id: response.conversation_trace_id,
    query_trace_id: response.query_trace_id,
    retrieval_question: response.retrieval_question,
    context_used: response.context_used,
  };
}

function failedTurnJson(turn: IncompleteUserTurn) {
  return {
    kind: "failed" as const,
    asked_at: turn.askedAt,
    question: turn.question,
    selection_mode: turn.selectionMode,
    selected_source_ids: turn.selectedSourceIds,
    selected_source_names: turn.selectedSourceNames,
    error_message: turn.errorMessage ?? "This turn did not complete.",
  };
}

export function serializeConversationJson(
  input: ConversationExportInput,
): DownloadArtifact {
  const exportedAt = input.exportedAt ?? new Date().toISOString();
  const timeline = buildConversationTimeline(
    input.history,
    input.incompleteTurns.filter((turn) => turn.status !== "pending"),
  );

  const turns = timeline.map((item) =>
    item.kind === "completed"
      ? completedTurnJson(item.entry)
      : failedTurnJson(item.turn),
  );

  const doc = {
    format: CONVERSATION_FORMAT,
    version: CONVERSATION_VERSION,
    exported_at: exportedAt,
    workspace: {
      workspace_id: input.workspace.workspace_id,
      title: input.workspace.title,
      revision: input.workspace.revision,
      current_snapshot_id: input.workspace.current_snapshot_id,
    },
    exported_from_view: input.exportedFromView,
    turns,
  };

  return {
    filename: buildExportFilename(
      "conversation",
      input.workspace.title,
      "json",
    ),
    mimeType: "application/json;charset=utf-8",
    content: `${JSON.stringify(doc, null, 2)}\n`,
  };
}
