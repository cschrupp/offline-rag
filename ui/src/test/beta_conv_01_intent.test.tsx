import { afterEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ConversationTurnResponse } from "../api/types";
import {
  DERIVED_CONVERSATION_WARNING,
  serializeConversationJson,
  serializeConversationMarkdown,
} from "../features/ask/conversationExport";
import {
  loadConversation,
  type ConversationHistoryEntry,
} from "../features/ask/conversationState";
import { assistantPresentationText } from "../features/ask/assistantPresentation";
import { conversationGuidanceCopy } from "../features/ask/abstentionCopy";
import { AskPanel } from "../features/ask/AskPanel";

afterEach(() => sessionStorage.clear());

function response(
  partial: Partial<ConversationTurnResponse> = {},
): ConversationTurnResponse {
  return {
    workspace_id: "ws_1",
    workspace_revision: 3,
    snapshot_id: "snap_1",
    product_mode_id: "grounded_v1",
    conversation_trace_id: "trace_conv_1",
    query_trace_id: null,
    status: "transformed",
    response_kind: "conversation_transform",
    transformation_source: "prior_assistant_turn",
    abstention_reason: null,
    question: "Summarize your previous answer.",
    retrieval_question: null,
    context_used: true,
    answer: "A concise transformed answer.",
    answer_blocks: [],
    citations: [],
    ...partial,
  };
}

function entry(turnResponse: ConversationTurnResponse): ConversationHistoryEntry {
  return {
    entryId: "pair_1",
    askedAt: "2026-11-04T12:00:00Z",
    question: turnResponse.question,
    selectedSourceIds: ["src_1"],
    selectedSourceNames: ["Report.pdf"],
    selectionMode: "all",
    response: turnResponse,
  };
}

describe("BETA-CONV-01 transformed conversation records", () => {
  it("loads explicit citation-free transforms but rejects undiscriminated ones", () => {
    const transformed = response();
    const legacyAnswered = response({
      status: "answered",
      response_kind: undefined,
      transformation_source: undefined,
      query_trace_id: "trace_query_1",
      retrieval_question: "question",
      answer: "Grounded answer.",
      answer_blocks: [{ text: "Grounded answer.", citation_refs: ["c1"] }],
      citations: [
        {
          evidence_unit_id: "eu_1",
          document_id: "doc_1",
          source_chunk_id: "chunk_1",
          kind: "parent",
          section_path: [],
          page_start: null,
          page_end: null,
          line_start: null,
          line_end: null,
          clipped: false,
          source_id: "src_1",
          source_version: 1,
          source_display_name: "Report.pdf",
          citation_ref: "c1",
          excerpt: "Grounded answer.",
          excerpt_clipped: false,
        },
      ],
    });
    sessionStorage.setItem(
      "seneca.conversation.v1:ws_1",
      JSON.stringify([
        {
          pairId: "transform",
          askedAt: "2026-11-04T12:00:00Z",
          question: transformed.question,
          selectedSourceIds: [],
          selectedSourceNames: [],
          selectionMode: "all",
          response: transformed,
        },
        {
          pairId: "legacy",
          askedAt: "2026-11-04T11:00:00Z",
          question: legacyAnswered.question,
          selectedSourceIds: [],
          selectedSourceNames: [],
          selectionMode: "all",
          response: legacyAnswered,
        },
        {
          pairId: "invalid-transform",
          askedAt: "2026-11-04T10:00:00Z",
          question: "Bad transform",
          selectedSourceIds: [],
          selectedSourceNames: [],
          selectionMode: "all",
          response: { ...transformed, response_kind: undefined },
        },
      ]),
    );

    expect(loadConversation("ws_1").map((pair) => pair.pairId)).toEqual([
      "transform",
      "legacy",
    ]);
    expect(assistantPresentationText(transformed)).toBe(
      "A concise transformed answer.",
    );
  });

  it("retains application-owned planner guidance in history and exports", () => {
    const clarification = response({
      status: "clarification_required",
      response_kind: "clarification",
      transformation_source: null,
      abstention_reason: "ambiguous_request",
      guidance_code: "conversation_summary_unavailable",
      question: "Summarize this conversation.",
      context_used: false,
      answer: null,
    });
    const historyEntry = entry(clarification);
    sessionStorage.setItem(
      "seneca.conversation.v1:ws_1",
      JSON.stringify([
        {
          pairId: "planner-guidance",
          askedAt: "2026-11-04T12:00:00Z",
          question: clarification.question,
          selectedSourceIds: [],
          selectedSourceNames: [],
          selectionMode: "all",
          response: clarification,
        },
      ]),
    );

    const loaded = loadConversation("ws_1");
    const loadedEntries: ConversationHistoryEntry[] = loaded.map((pair) => ({
      entryId: pair.pairId,
      askedAt: pair.askedAt,
      question: pair.question,
      selectedSourceIds: pair.selectedSourceIds,
      selectedSourceNames: pair.selectedSourceNames,
      selectionMode: pair.selectionMode,
      response: pair.response,
    }));
    const markdown = serializeConversationMarkdown({
      workspace: {
        workspace_id: "ws_1",
        title: "Research Desk",
        revision: 3,
        current_snapshot_id: "snap_2",
      },
      history: loadedEntries,
      incompleteTurns: [],
      exportedFromView: "normal",
      exportedAt: "2026-11-04T12:00:00Z",
    }).content;
    const json = JSON.parse(
      serializeConversationJson({
        workspace: {
          workspace_id: "ws_1",
          title: "Research Desk",
          revision: 3,
          current_snapshot_id: "snap_2",
        },
        history: loadedEntries,
        incompleteTurns: [],
        exportedFromView: "normal",
        exportedAt: "2026-11-04T12:00:00Z",
      }).content,
    );

    const guidance = conversationGuidanceCopy("conversation_summary_unavailable");
    expect(loaded).toHaveLength(1);
    expect(assistantPresentationText(loaded[0].response)).toBe(guidance);
    expect(markdown).toContain(guidance);
    expect(json.turns[0].guidance_code).toBe("conversation_summary_unavailable");
    expect(json.turns[0].citations).toEqual([]);
    expect(json.turns[0].response_kind).toBe("clarification");
    expect(historyEntry.response.guidance_code).toBe("conversation_summary_unavailable");
  });

  it("exports transformed turns with provenance and no fabricated sources", () => {
    const transformed = entry(response());
    const markdown = serializeConversationMarkdown({
      workspace: {
        workspace_id: "ws_1",
        title: "Research Desk",
        revision: 3,
        current_snapshot_id: "snap_2",
      },
      history: [transformed],
      incompleteTurns: [],
      exportedFromView: "normal",
      exportedAt: "2026-11-04T12:00:00Z",
    }).content;
    const json = JSON.parse(
      serializeConversationJson({
        workspace: {
          workspace_id: "ws_1",
          title: "Research Desk",
          revision: 3,
          current_snapshot_id: "snap_2",
        },
        history: [transformed],
        incompleteTurns: [],
        exportedFromView: "normal",
        exportedAt: "2026-11-04T12:00:00Z",
      }).content,
    );

    expect(markdown).toContain(DERIVED_CONVERSATION_WARNING);
    expect(markdown).toContain("Transformed conversation text — not verified");
    expect(markdown).toContain("Transformation source:** prior assistant turn");
    expect(markdown).not.toContain("### Sources");
    expect(markdown).not.toContain("generated from cited sources.");
    expect(json.turns[0].response_kind).toBe("conversation_transform");
    expect(json.turns[0].transformation_source).toBe("prior_assistant_turn");
  });

  it("labels grounded turns in a mixed Markdown export", () => {
    const grounded = entry(
      response({
        status: "answered",
        response_kind: "grounded_answer",
        transformation_source: null,
        query_trace_id: "trace_query_1",
        retrieval_question: "What does the report say?",
        answer: "The report identifies two pumps.",
        answer_blocks: [
          { text: "The report identifies two pumps.", citation_refs: ["c1"] },
        ],
        citations: [
          {
            evidence_unit_id: "eu_1",
            document_id: "doc_1",
            source_chunk_id: "chunk_1",
            kind: "parent",
            section_path: [],
            page_start: null,
            page_end: null,
            line_start: null,
            line_end: null,
            clipped: false,
            source_id: "src_1",
            source_version: 1,
            source_display_name: "Report.pdf",
            citation_ref: "c1",
            excerpt: "The report identifies two pumps.",
            excerpt_clipped: false,
          },
        ],
      }),
    );
    const markdown = serializeConversationMarkdown({
      workspace: {
        workspace_id: "ws_1",
        title: "Research Desk",
        revision: 3,
        current_snapshot_id: "snap_2",
      },
      history: [grounded],
      incompleteTurns: [],
      exportedFromView: "normal",
      exportedAt: "2026-11-04T12:00:00Z",
    }).content;

    expect(markdown).toContain("Source-grounded answer with citations.");
    expect(markdown).toContain("### Sources");
  });

  it("renders transform text without snapshot, source scope, or citation controls", () => {
    const historyEntry = entry(response());
    render(
      <MemoryRouter>
        <AskPanel
          question=""
          onQuestionChange={() => undefined}
          onAsk={() => undefined}
          onNewConversation={() => undefined}
          askDisabled={false}
          askPending={false}
          selectedCount={1}
          totalCount={1}
          askError={null}
          conflictHint={null}
          activeEntry={historyEntry}
          history={[historyEntry]}
          incompleteTurns={[]}
          selectedEvidenceUnitId={null}
          onSelectCitation={() => undefined}
          onSelectHistory={() => undefined}
          currentSnapshotId="snap_2"
          workspaceId="ws_1"
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("A concise transformed answer.")).toBeInTheDocument();
    expect(
      screen.getByText(/not verified against selected sources/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Current snapshot")).not.toBeInTheDocument();
    expect(screen.queryByText(/Using all active sources/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /reveal citations/i })).not.toBeInTheDocument();
  });
});
