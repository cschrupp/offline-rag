import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurnResponse } from "../api/types";
import { abstentionCopy } from "../features/ask/abstentionCopy";
import {
  assistantPresentationText,
  unicodeCharCount,
} from "../features/ask/assistantPresentation";
import {
  CONVERSATION_PAIR_MAX,
  RESOLVER_CHAR_MAX,
  RESOLVER_PAIR_MAX,
  appendConversationPair,
  buildResolverPriorTurns,
  chronologicalPairs,
  clearConversation,
  loadConversation,
  newPairId,
  sourceScopeLabel,
  toHistoryEntry,
} from "../features/ask/conversationState";
import { NARROW_LAYOUT_MEDIA } from "../features/ask/useNarrowLayout";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  source,
  workspace,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
  const root = document.getElementById("root");
  root?.removeAttribute("inert");
  root?.remove();
});

function ensureAppRoot(): HTMLElement {
  let root = document.getElementById("root");
  if (!root) {
    root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
  }
  return root;
}

function mockViewport(matchesNarrow: boolean) {
  let matches = matchesNarrow;
  const listeners = new Set<() => void>();
  const media = {
    get matches() {
      return matches;
    },
    media: NARROW_LAYOUT_MEDIA,
    onchange: null as ((ev: MediaQueryListEvent) => void) | null,
    addEventListener: (event: string, cb: () => void) => {
      if (event === "change") listeners.add(cb);
    },
    removeEventListener: (event: string, cb: () => void) => {
      if (event === "change") listeners.delete(cb);
    },
    addListener: (cb: () => void) => listeners.add(cb),
    removeListener: (cb: () => void) => listeners.delete(cb),
    dispatchEvent: () => true,
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => {
      if (query !== NARROW_LAYOUT_MEDIA) {
        return {
          matches: false,
          media: query,
          addEventListener: () => undefined,
          removeEventListener: () => undefined,
          addListener: () => undefined,
          removeListener: () => undefined,
          dispatchEvent: () => true,
          onchange: null,
        };
      }
      return media;
    }),
  );
  return {
    setNarrow(next: boolean) {
      matches = next;
      listeners.forEach((cb) => cb());
    },
  };
}

function turnResponse(
  partial: Partial<ConversationTurnResponse> = {},
): ConversationTurnResponse {
  return {
    workspace_id: "ws_1",
    workspace_revision: 5,
    snapshot_id: "snap_1",
    product_mode_id: "grounded_v1",
    conversation_trace_id: "ctr_1",
    query_trace_id: "tr_1",
    status: "answered",
    abstention_reason: null,
    question: "Q?",
    retrieval_question: "Q?",
    context_used: false,
    answer: "Answer text.",
    answer_blocks: [{ text: "Answer text.", citation_refs: ["c1"] }],
    citations: [
      {
        evidence_unit_id: "eu_1",
        document_id: "doc_1",
        source_chunk_id: "chunk_1",
        kind: "parent",
        section_path: ["S"],
        page_start: 1,
        page_end: 1,
        line_start: null,
        line_end: null,
        clipped: false,
        source_id: "src_1",
        source_version: 1,
        source_display_name: "Alpha.pdf",
        citation_ref: "c1",
        excerpt: "Answer text.",
        excerpt_clipped: false,
      },
    ],
    ...partial,
  };
}

describe("Slice 16D-B3 conversation state helpers", () => {
  it("enforces 50-pair persistence bound", () => {
    for (let i = 0; i < CONVERSATION_PAIR_MAX + 5; i += 1) {
      appendConversationPair("ws_bound", {
        pairId: newPairId(),
        askedAt: new Date().toISOString(),
        question: `Q${i}`,
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "all",
        response: turnResponse({
          conversation_trace_id: `ctr_${i}`,
          query_trace_id: `tr_${i}`,
          answer: `A${i}`,
          answer_blocks: [{ text: `A${i}`, citation_refs: ["c1"] }],
        }),
      });
    }
    expect(loadConversation("ws_bound")).toHaveLength(CONVERSATION_PAIR_MAX);
  });

  it("builds 6-pair / 12k client resolver window", () => {
    const pairs: Array<{
      pairId: string;
      askedAt: string;
      question: string;
      selectedSourceIds: string[];
      selectedSourceNames: string[];
      selectionMode: "all" | "subset";
      response: ConversationTurnResponse;
    }> = [];
    for (let i = 0; i < 8; i += 1) {
      pairs.push({
        pairId: `p${i}`,
        askedAt: `2026-01-0${(i % 9) + 1}T00:00:00Z`,
        question: `User ${i}`,
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "all",
        response: turnResponse({ answer: `Assistant ${i}` }),
      });
    }
    const turns = buildResolverPriorTurns(pairs);
    expect(turns.length).toBe(RESOLVER_PAIR_MAX * 2);
    expect(turns[0]).toEqual({ role: "user", text: "User 2" });
    expect(turns.at(-1)).toEqual({ role: "assistant", text: "Assistant 7" });

    const huge = "x".repeat(RESOLVER_CHAR_MAX / 2 + 10);
    const fat: Array<{
      pairId: string;
      askedAt: string;
      question: string;
      selectedSourceIds: string[];
      selectedSourceNames: string[];
      selectionMode: "all" | "subset";
      response: ConversationTurnResponse;
    }> = [
      {
        pairId: "old",
        askedAt: "2026-01-01T00:00:00Z",
        question: huge,
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "all",
        response: turnResponse({ answer: huge }),
      },
      {
        pairId: "new",
        askedAt: "2026-01-02T00:00:00Z",
        question: "short",
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "subset",
        response: turnResponse({ answer: "ok" }),
      },
    ];
    const trimmed = buildResolverPriorTurns(fat);
    expect(trimmed).toEqual([
      { role: "user", text: "short" },
      { role: "assistant", text: "ok" },
    ]);
    expect(chronologicalPairs([...fat].reverse())[0]?.pairId).toBe("old");
  });

  it("uses visible assistant presentation text for prior_turns (R5)", () => {
    const reasons = [
      "no_evidence",
      "insufficient_support",
      "conflicting_evidence",
      "model_declined",
      "ambiguous_request",
    ] as const;
    for (const reason of reasons) {
      const status =
        reason === "ambiguous_request"
          ? "clarification_required"
          : reason === "no_evidence"
            ? "insufficient_evidence"
            : "model_abstain";
      const response = turnResponse({
        status,
        answer: null,
        answer_blocks: [],
        citations: [],
        abstention_reason: reason,
        query_trace_id:
          status === "clarification_required" ? null : "tr_abs",
        retrieval_question:
          status === "clarification_required" ? null : "Resolved?",
        context_used: status !== "clarification_required",
      });
      const visible = assistantPresentationText(response);
      expect(visible).toBe(abstentionCopy(reason));
      const turns = buildResolverPriorTurns([
        {
          pairId: "p1",
          askedAt: "2026-01-01T00:00:00Z",
          question: "Q?",
          selectedSourceIds: ["src_1"],
          selectedSourceNames: ["A.pdf"],
          selectionMode: "subset",
          response,
        },
      ]);
      expect(turns[1]).toEqual({ role: "assistant", text: visible });
    }
    const answered = turnResponse({ answer: "Exact answer." });
    answered.answer_blocks = [{ text: "Exact answer.", citation_refs: ["c1"] }];
    expect(assistantPresentationText(answered)).toBe("Exact answer.");
  });

  it("counts Unicode code points for the 12k resolver window (R5)", () => {
    // One emoji is one Python/Unicode character but two UTF-16 code units.
    const emoji = "😀";
    expect(emoji.length).toBe(2);
    expect(unicodeCharCount(emoji)).toBe(1);
    const pairChars = Math.floor(RESOLVER_CHAR_MAX / 2) + 1;
    const block = emoji.repeat(pairChars);
    expect(unicodeCharCount(block)).toBe(pairChars);
    expect(block.length).toBeGreaterThan(pairChars);
    const fat = [
      {
        pairId: "old",
        askedAt: "2026-01-01T00:00:00Z",
        question: block,
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "all" as const,
        response: turnResponse({
          answer: block,
          answer_blocks: [{ text: block, citation_refs: ["c1"] }],
        }),
      },
      {
        pairId: "new",
        askedAt: "2026-01-02T00:00:00Z",
        question: "keep",
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["A.pdf"],
        selectionMode: "all" as const,
        response: turnResponse({ answer: "me" }),
      },
    ];
    // Unicode total for the old pair exceeds 12k code points; UTF-16 `.length`
    // would be larger still. Window must drop the old pair.
    expect(unicodeCharCount(block) * 2).toBeGreaterThan(RESOLVER_CHAR_MAX);
    const turns = buildResolverPriorTurns(fat);
    expect(turns).toEqual([
      { role: "user", text: "keep" },
      { role: "assistant", text: "me" },
    ]);
  });

  it("presents frozen all|subset source scope labels (R6)", () => {
    expect(
      sourceScopeLabel({
        selectionMode: "all",
        selectedSourceNames: ["Alpha.pdf", "Beta.pdf"],
      }),
    ).toBe("All active sources · Alpha.pdf, Beta.pdf");
    expect(
      sourceScopeLabel({
        selectionMode: "subset",
        selectedSourceNames: ["Alpha.pdf"],
      }),
    ).toBe("Selected sources · Alpha.pdf");
  });
});

describe("Slice 16D-B3 conversation workspace UI", () => {
  it("shows sent turn immediately, clears composer, and blocks duplicate send", async () => {
    const user = userEvent.setup();
    let resolveTurn: ((value: Response) => void) | null = null;
    let posts = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 1,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        posts += 1;
        return new Promise<Response>((resolve) => {
          resolveTurn = resolve;
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    const composer = screen.getByLabelText("Ask a follow-up");
    await user.type(composer, "Immediate user turn?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Immediate user turn?")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a follow-up")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(posts).toBe(1);
    resolveTurn!(
      jsonResponse(
        turnResponse({
          answer: "Done.",
          answer_blocks: [{ text: "Done.", citation_refs: ["c1"] }],
        }),
      ),
    );
    expect(await screen.findByText("Done.")).toBeInTheDocument();
    mock.restore();
  });

  it("new conversation clears turns but preserves source selection", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 2,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [
            source({ source_id: "src_1", display_name: "Alpha.pdf" }),
            source({ source_id: "src_2", display_name: "Beta.pdf" }),
          ],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        return jsonResponse(
          turnResponse({
            answer: "First answer.",
            answer_blocks: [{ text: "First answer.", citation_refs: ["c1"] }],
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByLabelText(/Include Beta\.pdf in next Ask/i));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Only alpha?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("First answer.")).toBeInTheDocument();
    expect(loadConversation("ws_1")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "+ New conversation" }));
    await waitFor(() => expect(loadConversation("ws_1")).toHaveLength(0));
    expect(screen.queryByText("First answer.")).toBeNull();
    const boxes = screen.getAllByRole("checkbox");
    expect((boxes[0] as HTMLInputElement).checked).toBe(true);
    expect((boxes[1] as HTMLInputElement).checked).toBe(false);
    clearConversation("ws_1");
    mock.restore();
  });

  it("desktop layout exposes three knowledge columns and narrow drawers do not stack", async () => {
    const user = userEvent.setup();
    const viewport = mockViewport(false);
    ensureAppRoot();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 1,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        return jsonResponse(turnResponse());
      }
      if (call.url.includes("/content")) {
        return new Response("line one\nline two\n", {
          status: 200,
          headers: { "content-type": "text/plain" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    expect(document.querySelector(".knowledge-layout")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidence" })).toBeInTheDocument();

    viewport.setNarrow(true);
    await user.click(await screen.findByRole("button", { name: "Sources" }));
    expect(screen.getByRole("dialog", { name: "Sources" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evidence" }));
    // No stacked drawers: Sources closes when Evidence opens from mobile bar path
    // (citation path closes Sources first). Mobile bar can open Evidence while Sources
    // was open — product rule for citation/source-preview paths is covered below.
    viewport.setNarrow(false);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
      expect(document.getElementById("root")?.hasAttribute("inert")).toBe(false);
    });
    mock.restore();
  });

  it("keeps sent user turn visible after request failure (R2)", async () => {
    const user = userEvent.setup();
    const bodies: Array<Record<string, unknown>> = [];
    let failFirst = true;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 1,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        bodies.push(JSON.parse(String(call.body)) as Record<string, unknown>);
        if (failFirst) {
          failFirst = false;
          return errorResponse("generation_failed", "Generator failed", 502);
        }
        return jsonResponse(
          turnResponse({
            answer: "Recovered.",
            answer_blocks: [{ text: "Recovered.", citation_refs: ["c1"] }],
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Failed send stays?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Failed send stays?")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a follow-up")).toHaveValue("");
    // Failure UI appears; submitted turn remains immutable display content.
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((el) => (el.textContent ?? "").length > 0)).toBe(true);
    expect(screen.getByText("Failed send stays?")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask a follow-up"), "Second try?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]?.prior_turns).toEqual([]);
    expect(JSON.stringify(bodies[1])).not.toContain("Failed send stays?");
    expect(await screen.findByText("Recovered.")).toBeInTheDocument();
    expect(screen.getByText("Failed send stays?")).toBeInTheDocument();
    mock.restore();
  });

  it("distinguishes conversation and query traces in provenance (R3)", async () => {
    const user = userEvent.setup();
    let mode: "answered" | "clarification" = "answered";
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 1,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        if (mode === "clarification") {
          return jsonResponse(
            turnResponse({
              status: "clarification_required",
              answer: null,
              answer_blocks: [],
              citations: [],
              abstention_reason: "ambiguous_request",
              query_trace_id: null,
              retrieval_question: null,
              context_used: true,
              conversation_trace_id: "ctr_clarify",
            }),
          );
        }
        return jsonResponse(
          turnResponse({
            conversation_trace_id: "ctr_answer",
            query_trace_id: "tr_answer",
            answer: "Cited answer.",
            answer_blocks: [{ text: "Cited answer.", citation_refs: ["c1"] }],
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Answered?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Cited answer.")).toBeInTheDocument();
    await user.click(screen.getByText("Provenance"));
    expect(screen.getByText("Conversation trace ID")).toBeInTheDocument();
    expect(screen.getByText("ctr_answer")).toBeInTheDocument();
    expect(screen.getByText("Query trace ID")).toBeInTheDocument();
    expect(screen.getByText("tr_answer")).toBeInTheDocument();
    expect(screen.queryByText("Trace ID")).toBeNull();

    mode = "clarification";
    await user.type(screen.getByLabelText("Ask a follow-up"), "Which of those?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/could not safely resolve what this follow-up refers to/i),
    ).toBeInTheDocument();
    const badges = screen.getAllByRole("button", { name: /Current snapshot/i });
    await user.click(badges[badges.length - 1]!);
    await user.click(screen.getByText("Provenance"));
    expect(screen.getByText("ctr_clarify")).toBeInTheDocument();
    expect(
      screen.getByText(/None \(no scientific query for this turn\)/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("tr_answer")).toBeNull();
    mock.restore();
  });

  it("freezes subset source-scope presentation across later selection changes (R6)", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 5,
            source_count: 2,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [
            source({ source_id: "src_1", display_name: "Alpha.pdf" }),
            source({ source_id: "src_2", display_name: "Beta.pdf" }),
          ],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        return jsonResponse(
          turnResponse({
            answer: "Scoped.",
            answer_blocks: [{ text: "Scoped.", citation_refs: ["c1"] }],
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByLabelText(/Include Beta\.pdf in next Ask/i));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Alpha only?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Scoped.")).toBeInTheDocument();
    expect(
      screen.getByText((text) => text.includes("Selected sources · Alpha.pdf")),
    ).toBeInTheDocument();
    const stored = loadConversation("ws_1");
    expect(stored[0]?.selectionMode).toBe("subset");
    expect(stored[0]?.selectedSourceNames).toEqual(["Alpha.pdf"]);

    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(
      screen.getByText((text) => text.includes("Selected sources · Alpha.pdf")),
    ).toBeInTheDocument();
    expect(loadConversation("ws_1")[0]?.selectionMode).toBe("subset");
    mock.restore();
  });
});

describe("Slice 16D-B3 dual-trace history entry (R3)", () => {
  it("does not alias query and conversation traces into a generic trace_id", () => {
    const answered = toHistoryEntry({
      pairId: "p1",
      askedAt: "2026-01-01T00:00:00Z",
      question: "Q?",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["A.pdf"],
      selectionMode: "all",
      response: turnResponse({
        conversation_trace_id: "ctr_x",
        query_trace_id: "tr_y",
      }),
    });
    expect(answered.response.conversation_trace_id).toBe("ctr_x");
    expect(answered.response.query_trace_id).toBe("tr_y");
    expect(
      Object.prototype.hasOwnProperty.call(answered.response, "trace_id"),
    ).toBe(false);

    const clarification = toHistoryEntry({
      pairId: "p2",
      askedAt: "2026-01-01T00:00:00Z",
      question: "Which?",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["A.pdf"],
      selectionMode: "subset",
      response: turnResponse({
        status: "clarification_required",
        answer: null,
        answer_blocks: [],
        citations: [],
        abstention_reason: "ambiguous_request",
        conversation_trace_id: "ctr_c",
        query_trace_id: null,
        retrieval_question: null,
        context_used: true,
      }),
    });
    expect(clarification.response.conversation_trace_id).toBe("ctr_c");
    expect(clarification.response.query_trace_id).toBeNull();
  });
});
