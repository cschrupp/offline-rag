import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "./render";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  source,
  workspace,
} from "./mockApi";
import type { ConversationTurnResponse } from "../api/types";
import {
  ASK_HISTORY_MAX,
  appendAskHistory,
  loadAskHistory,
  newHistoryEntryId,
  persistAskHistory,
  snapshotBadge,
} from "../features/ask/askHistory";
import { loadConversation } from "../features/ask/conversationState";
import {
  reconcileSourceSelection,
  selectAllSources,
  setSourceSelected,
  sourceIdsForQuery,
} from "../features/ask/sourceSelection";
import { buildTextLineWindow } from "../features/ask/previewText";
import { NARROW_LAYOUT_MEDIA } from "../features/ask/useNarrowLayout";

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

function expectRootNotInert() {
  expect(ensureAppRoot().hasAttribute("inert")).toBe(false);
}

/** Drive `useNarrowLayout` via the same 960px media query the CSS uses. */
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

function queryResponse(
  partial: Partial<ConversationTurnResponse> & { trace_id?: string } = {},
): ConversationTurnResponse {
  const { trace_id: legacyTrace, ...rest } = partial;
  const base: ConversationTurnResponse = {
    workspace_id: "ws_1",
    workspace_revision: 5,
    snapshot_id: "snap_1",
    product_mode_id: "grounded_v1",
    conversation_trace_id: "ctr_1",
    query_trace_id: legacyTrace ?? "tr_1",
    status: "answered",
    question: "What does Alpha say?",
    retrieval_question: "What does Alpha say?",
    context_used: false,
    answer: "Ventilation must be established first.",
    answer_blocks: [
      {
        text: "Ventilation must be established first.",
        citation_refs: ["c1"],
      },
    ],
    abstention_reason: null,
    citations: [
      {
        evidence_unit_id: "eu_1",
        document_id: "doc_1",
        source_chunk_id: "chunk_1",
        kind: "parent",
        section_path: ["Safety"],
        page_start: 14,
        page_end: 14,
        line_start: 10,
        line_end: 12,
        clipped: false,
        source_id: "src_1",
        source_version: 1,
        source_display_name: "Week02.pdf",
        citation_ref: "c1",
        excerpt: "Ventilation must be established first.",
        excerpt_clipped: false,
      },
    ],
  };
  const merged = { ...base, ...rest };
  if (legacyTrace) {
    merged.query_trace_id = legacyTrace;
  }
  if (
    typeof rest.answer === "string" &&
    rest.answer_blocks === undefined &&
    (rest.status === undefined || rest.status === "answered")
  ) {
    merged.answer_blocks = [
      { text: rest.answer, citation_refs: ["c1"] },
    ];
  }
  // Test helper also exposes legacy trace_id for askHistory unit fixtures.
  return {
    ...merged,
    trace_id: merged.query_trace_id ?? merged.conversation_trace_id,
  } as ConversationTurnResponse & { trace_id: string };
}

describe("Slice 16D-B source selection helpers", () => {
  it("EMPTY workspace then first source selects under mode=all", () => {
    const empty = reconcileSourceSelection("ws_empty", []);
    expect(empty).toEqual({
      knownSourceIds: [],
      selectedSourceIds: [],
      mode: "all",
    });
    const first = source({ source_id: "src_1", display_name: "First.pdf" });
    const after = reconcileSourceSelection("ws_empty", [first]);
    expect(after.mode).toBe("all");
    expect(after.selectedSourceIds).toEqual(["src_1"]);
  });

  it("mode=all auto-selects newly added sources; mode=subset does not", () => {
    const a = source({ source_id: "src_a", display_name: "A.pdf" });
    const b = source({ source_id: "src_b", display_name: "B.pdf" });
    const first = reconcileSourceSelection("ws_sel", [a, b]);
    expect(first.mode).toBe("all");
    expect(first.selectedSourceIds).toEqual(["src_a", "src_b"]);

    const c = source({ source_id: "src_c", display_name: "C.pdf" });
    const afterAll = reconcileSourceSelection("ws_sel", [a, b, c]);
    expect(afterAll.mode).toBe("all");
    expect(afterAll.selectedSourceIds).toEqual(["src_a", "src_b", "src_c"]);

    const subset = setSourceSelected("ws_sel", [a, b, c], "src_b", false);
    expect(subset.mode).toBe("subset");
    expect(subset.selectedSourceIds).toEqual(["src_a", "src_c"]);

    const d = source({ source_id: "src_d", display_name: "D.pdf" });
    const afterSubset = reconcileSourceSelection("ws_sel", [a, b, c, d]);
    expect(afterSubset.mode).toBe("subset");
    expect(afterSubset.selectedSourceIds).toEqual(["src_a", "src_c"]);
  });

  it("explicit zero-source subset stays zero when a source later appears", () => {
    const a = source({ source_id: "src_a" });
    reconcileSourceSelection("ws_zero", [a]);
    const zero = setSourceSelected("ws_zero", [a], "src_a", false);
    expect(zero).toEqual({
      knownSourceIds: ["src_a"],
      selectedSourceIds: [],
      mode: "subset",
    });
    const gone = reconcileSourceSelection("ws_zero", []);
    expect(gone.mode).toBe("subset");
    expect(gone.selectedSourceIds).toEqual([]);
    const b = source({ source_id: "src_b" });
    const reappeared = reconcileSourceSelection("ws_zero", [b]);
    expect(reappeared.mode).toBe("subset");
    expect(reappeared.selectedSourceIds).toEqual([]);
  });

  it("Select all restores follow-all; removed sources leave selected IDs", () => {
    const a = source({ source_id: "src_a" });
    const b = source({ source_id: "src_b" });
    reconcileSourceSelection("ws_all", [a, b]);
    setSourceSelected("ws_all", [a, b], "src_a", false);
    const restored = selectAllSources("ws_all", [a, b]);
    expect(restored.mode).toBe("all");
    expect(restored.selectedSourceIds).toEqual(["src_a", "src_b"]);

    const afterRemove = reconcileSourceSelection("ws_all", [b]);
    expect(afterRemove.mode).toBe("all");
    expect(afterRemove.selectedSourceIds).toEqual(["src_b"]);
    expect(afterRemove.knownSourceIds).toEqual(["src_b"]);
  });

  it("migrates legacy shapes and keeps selection per workspace", () => {
    sessionStorage.setItem(
      "seneca.source-selection.v1:ws_legacy_empty",
      JSON.stringify({ knownSourceIds: [], selectedSourceIds: [] }),
    );
    const migratedEmpty = reconcileSourceSelection("ws_legacy_empty", []);
    expect(migratedEmpty.mode).toBe("all");

    sessionStorage.setItem(
      "seneca.source-selection.v1:ws_legacy_subset",
      JSON.stringify({
        knownSourceIds: ["src_a", "src_b"],
        selectedSourceIds: ["src_a"],
      }),
    );
    const a = source({ source_id: "src_a" });
    const b = source({ source_id: "src_b" });
    const c = source({ source_id: "src_c" });
    const migratedSubset = reconcileSourceSelection("ws_legacy_subset", [
      a,
      b,
      c,
    ]);
    expect(migratedSubset.mode).toBe("subset");
    expect(migratedSubset.selectedSourceIds).toEqual(["src_a"]);

    reconcileSourceSelection("ws_a", [a]);
    reconcileSourceSelection("ws_b", [b]);
    setSourceSelected("ws_a", [a], "src_a", false);
    expect(reconcileSourceSelection("ws_b", [b]).selectedSourceIds).toEqual([
      "src_b",
    ]);
    expect(reconcileSourceSelection("ws_a", [a]).mode).toBe("subset");
  });

  it("omits source_ids only for mode=all with every known source selected", () => {
    const sources = [
      source({ source_id: "src_a" }),
      source({ source_id: "src_b" }),
    ];
    expect(sourceIdsForQuery(sources, ["src_a", "src_b"], "all")).toBeUndefined();
    expect(sourceIdsForQuery(sources, ["src_a"], "all")).toEqual(["src_a"]);
    expect(sourceIdsForQuery(sources, ["src_a", "src_b"], "subset")).toEqual([
      "src_a",
      "src_b",
    ]);
    expect(sourceIdsForQuery(sources, ["src_a"], "subset")).toEqual(["src_a"]);
    expect(sourceIdsForQuery(sources, [], "subset")).toEqual([]);
  });
});

describe("Slice 16D-B ask history helpers", () => {
  it("bounds history, discards malformed data, and never stores source bytes", () => {
    const base = queryResponse();
    for (let i = 0; i < ASK_HISTORY_MAX + 3; i += 1) {
      appendAskHistory("ws_hist", {
        entryId: newHistoryEntryId(),
        askedAt: new Date().toISOString(),
        question: `Q${i}`,
        selectedSourceIds: ["src_1"],
        selectedSourceNames: ["Week02.pdf"],
        response: { ...base, trace_id: `tr_${i}` },
      });
    }
    const loaded = loadAskHistory("ws_hist");
    expect(loaded).toHaveLength(ASK_HISTORY_MAX);
    expect(JSON.stringify(loaded)).not.toMatch(/VERSION_ONE_BYTES/);

    persistAskHistory("ws_bad", [{ bogus: true } as never]);
    expect(loadAskHistory("ws_bad")).toEqual([]);
    expect(snapshotBadge("snap_1", "snap_1")).toBe("current");
    expect(snapshotBadge("snap_1", "snap_2")).toBe("historical");
    expect(snapshotBadge("snap_1", null)).toBe("historical");
  });

  it("discards malformed session history entries that would crash Ask rendering", () => {
    const valid = {
      entryId: "e_ok",
      askedAt: "2026-01-01T00:00:00Z",
      question: "Valid?",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["Alpha.pdf"],
      response: queryResponse({ trace_id: "tr_ok" }),
    };
    const answerObject = {
      ...valid,
      entryId: "e_bad_answer",
      response: {
        ...queryResponse(),
        status: "answered",
        answer: { text: "not a string" },
      },
    };
    const badSelectedIds = {
      ...valid,
      entryId: "e_bad_ids",
      selectedSourceIds: ["src_1", 2],
    };
    const badCitation = {
      ...valid,
      entryId: "e_bad_cite",
      response: {
        ...queryResponse(),
        citations: [
          {
            evidence_unit_id: "eu_1",
            source_id: "src_1",
            source_version: 1,
            // missing presentation fields
          },
        ],
      },
    };
    const badStatus = {
      ...valid,
      entryId: "e_bad_status",
      response: { ...queryResponse(), status: "hallucinated" },
    };

    sessionStorage.setItem(
      "seneca.ask-history.v2:ws_malformed",
      JSON.stringify([
        answerObject,
        badSelectedIds,
        badCitation,
        badStatus,
        valid,
      ]),
    );
    expect(loadAskHistory("ws_malformed")).toEqual([valid]);
  });

  it("builds cited text windows with line highlighting", () => {
    const text = Array.from({ length: 40 }, (_, i) => `line ${i + 1}`).join(
      "\n",
    );
    const windowed = buildTextLineWindow(text, 10, 12);
    expect(windowed.hasExactLocation).toBe(true);
    expect(windowed.lines.some((line) => line.cited && line.lineNumber === 10)).toBe(
      true,
    );
    expect(windowed.lines.every((line) => line.lineNumber >= 1)).toBe(true);
  });
});

describe("Slice 16D-B Ask & Evidence workspace", () => {
  it("selects all sources, disables Ask at zero, and omits source_ids when all selected", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
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
        bodies.push(JSON.parse(String(call.body)));
        return jsonResponse(queryResponse());
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("heading", { name: "Conversation" })).toBeInTheDocument();
    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes.every((box) => (box as HTMLInputElement).checked)).toBe(true);

    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Select all" }));
    await user.type(screen.getByLabelText("Ask a follow-up"), "What does Alpha say?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({
      question: "What does Alpha say?",
      prior_turns: [],
    });
    expect(bodies[0]).not.toHaveProperty("source_ids");
    mock.restore();
  });

  it("mode=subset always sends explicit source_ids even when all known sources are checked", async () => {
    const user = userEvent.setup();
    const bodies: Array<Record<string, unknown>> = [];
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
        bodies.push(JSON.parse(String(call.body)) as Record<string, unknown>);
        return jsonResponse(
          queryResponse({ trace_id: `tr_${bodies.length}`, answer: `A${bodies.length}` }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    const beta = screen.getByLabelText(/Include Beta\.pdf in next Ask/i);
    // Enter subset, then re-check every currently known source.
    await user.click(beta);
    await user.click(beta);
    await user.type(screen.getByLabelText("Ask a follow-up"), "Subset all visible?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({
      question: "Subset all visible?",
      source_ids: ["src_1", "src_2"],
      prior_turns: [],
    });

    await user.click(screen.getByRole("button", { name: "Select all" }));
    await user.clear(screen.getByLabelText("Ask a follow-up"));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Follow all again?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toEqual({
      question: "Follow all again?",
      prior_turns: [
        { role: "user", text: "Subset all visible?" },
        { role: "assistant", text: "A1" },
      ],
    });
    expect(bodies[1]).not.toHaveProperty("source_ids");
    mock.restore();
  });

  it("history records the submitted Ask scope even if sources refetch while pending", async () => {
    const user = userEvent.setup();
    let resolveQuery: ((value: Response) => void) | null = null;
    let sourceList = [
      source({ source_id: "src_1", display_name: "Alpha.pdf" }),
      source({ source_id: "src_2", display_name: "Beta.pdf" }),
    ];
    let revision = 5;
    const bodies: Array<Record<string, unknown>> = [];
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision,
            source_count: sourceList.length,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: sourceList,
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        bodies.push(JSON.parse(String(call.body)) as Record<string, unknown>);
        return new Promise<Response>((resolve) => {
          resolveQuery = resolve;
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    const { queryClient } = renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByLabelText(/Include Beta\.pdf in next Ask/i));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Pending scope?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({
      question: "Pending scope?",
      source_ids: ["src_1"],
      prior_turns: [],
    });

    // Mid-flight UI refresh must not rewrite the submitted history scope.
    sourceList = [
      source({ source_id: "src_2", display_name: "Beta.pdf" }),
      source({ source_id: "src_3", display_name: "Gamma.pdf" }),
    ];
    revision = 6;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await queryClient.invalidateQueries({
      queryKey: ["workspace", "ws_1", "sources"],
    });
    await screen.findByRole("button", { name: "Gamma.pdf" });

    resolveQuery!(
      jsonResponse(
        queryResponse({
          answer: "Scoped answer",
          trace_id: "tr_pending",
        }),
      ),
    );
    expect(await screen.findByText("Scoped answer")).toBeInTheDocument();
    expect(
      screen.getByText((text) => text.includes("Selected sources · Alpha.pdf")),
    ).toBeInTheDocument();
    const stored = loadConversation("ws_1");
    expect(stored[0]?.selectedSourceIds).toEqual(["src_1"]);
    expect(stored[0]?.selectedSourceNames).toEqual(["Alpha.pdf"]);
    expect(stored[0]?.question).toBe("Pending scope?");
    mock.restore();
  });

  it("sends exact subset for Q2 with bounded prior completed pairs", async () => {
    const user = userEvent.setup();
    const bodies: Array<Record<string, unknown>> = [];
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
        bodies.push(JSON.parse(String(call.body)) as Record<string, unknown>);
        return jsonResponse(
          queryResponse({
            answer: bodies.length === 1 ? "A1" : "A2",
            trace_id: `tr_${bodies.length}`,
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    const beta = screen.getByLabelText(/Include Beta\.pdf in next Ask/i);
    await user.click(beta);

    await user.type(screen.getByLabelText("Ask a follow-up"), "Question one?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("A1");

    await user.clear(screen.getByLabelText("Ask a follow-up"));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Question two?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("A2");

    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toEqual({
      question: "Question one?",
      source_ids: ["src_1"],
      prior_turns: [],
    });
    expect(bodies[1]).toEqual({
      question: "Question two?",
      source_ids: ["src_1"],
      prior_turns: [
        { role: "user", text: "Question one?" },
        { role: "assistant", text: "A1" },
      ],
    });
    mock.restore();
  });

  it("renders answered, abstention, and conflict retry guidance", async () => {
    const user = userEvent.setup();
    let mode: "answered" | "insufficient" | "abstain" | "conflict" = "answered";
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
        if (mode === "conflict") {
          return errorResponse(
            "workspace_conflict",
            "Workspace revision or state conflict",
            409,
          );
        }
        if (mode === "insufficient") {
          return jsonResponse(
            queryResponse({
              status: "insufficient_evidence",
              answer: null,
              citations: [],
              answer_blocks: [],
              abstention_reason: "no_evidence",
            }),
          );
        }
        if (mode === "abstain") {
          return jsonResponse(
            queryResponse({
              status: "model_abstain",
              answer: null,
              citations: [],
              answer_blocks: [],
              abstention_reason: "model_declined",
            }),
          );
        }
        return jsonResponse(queryResponse());
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Requirements?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/Ventilation must be established first/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Current snapshot/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: /Citation 1: Week02\.pdf/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Evidence used/i)).toBeNull();

    mode = "insufficient";
    await user.clear(screen.getByLabelText("Ask a follow-up"));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Missing?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const insufficient = await screen.findByText(
      /did not find usable evidence in the selected sources/i,
    );
    expect(insufficient).toBeInTheDocument();
    expect(insufficient.closest("[role='alert']")).toBeNull();

    mode = "abstain";
    await user.clear(screen.getByLabelText("Ask a follow-up"));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Abstain?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(
        /did not provide an answer from the available evidence/i,
      ),
    ).toBeInTheDocument();

    mode = "conflict";
    await user.clear(screen.getByLabelText("Ask a follow-up"));
    await user.type(screen.getByLabelText("Ask a follow-up"), "Conflict?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/workspace changed while this question was running/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("derives citation Current/Historical from workspace snapshot without re-click", async () => {
    const user = userEvent.setup();
    mockViewport(false);
    let currentSnapshot = "snap_1";
    let revision = 5;
    const versionFetches: string[] = [];
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision,
            source_count: 1,
            status: "active",
            current_snapshot_id: currentSnapshot,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: [
            source({
              source_id: "src_1",
              display_name: "Alpha.pdf",
              version: currentSnapshot === "snap_1" ? 1 : 2,
            }),
          ],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        return jsonResponse(
          queryResponse({
            workspace_revision: 5,
            snapshot_id: "snap_1",
            citations: [
              {
                evidence_unit_id: "eu_1",
                document_id: "doc_1",
                source_chunk_id: "chunk_1",
                kind: "parent",
                section_path: [],
                page_start: 2,
                page_end: 2,
                line_start: null,
                line_end: null,
                clipped: false,
                source_id: "src_1",
                source_version: 1,
                source_display_name: "Alpha.pdf",
                citation_ref: "c1",
                excerpt: "Alpha excerpt",
                excerpt_clipped: false,
              },
            ],
          }),
        );
      }
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        versionFetches.push(call.url);
        return new Response("VERSION_ONE_BYTES", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    const { queryClient } = renderApp("/workspaces/ws_1");
    await user.type(
      await screen.findByLabelText("Ask a follow-up"),
      "Historical evidence?",
    );
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      (await screen.findAllByText(/Current snapshot/i)).length,
    ).toBeGreaterThan(0);
    await waitFor(() => {
      expect(versionFetches.some((url) => url.includes("/versions/1/content"))).toBe(
        true,
      );
      expect(
        versionFetches.some((url) => url.includes("workspace_revision=5")),
      ).toBe(true);
    });
    expect(await screen.findByText("VERSION_ONE_BYTES")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    currentSnapshot = "snap_2";
    revision = 6;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await queryClient.invalidateQueries({
      queryKey: ["workspace", "ws_1", "sources"],
    });
    // Without re-clicking the citation: answer, provenance, and SourcePreview
    // all flip to Historical while pinned bytes stay on v1 / revision 5.
    await waitFor(() => {
      expect(screen.getAllByText(/Historical snapshot/i).length).toBeGreaterThan(
        0,
      );
    });
    expect(screen.queryByText(/Current snapshot/i)).not.toBeInTheDocument();
    expect(screen.getByText("VERSION_ONE_BYTES")).toBeInTheDocument();
    expect(versionFetches.some((url) => url.includes("/versions/2/"))).toBe(false);
    mock.restore();
  });

  it("rebinds direct current-source preview after replace; clears when removed", async () => {
    const user = userEvent.setup();
    mockViewport(false);
    let revision = 5;
    let active: ReturnType<typeof source> | null = source({
      source_id: "src_1",
      display_name: "Alpha.pdf",
      version: 1,
    });
    const versionFetches: string[] = [];
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision,
            source_count: active ? 1 : 0,
            status: active ? "active" : "empty",
            current_snapshot_id: active ? `snap_${active.version}` : null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: active ? [active] : [],
        });
      }
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        versionFetches.push(call.url);
        const version = call.url.includes("/versions/2/") ? "TWO" : "ONE";
        return new Response(`VERSION_${version}_BYTES`, {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    const { queryClient } = renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Alpha.pdf" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(versionFetches.some((url) => url.includes("/versions/1/content"))).toBe(
        true,
      );
    });
    expect(await screen.findByText("VERSION_ONE_BYTES")).toBeInTheDocument();
    expect(screen.getAllByText(/Current snapshot/i).length).toBeGreaterThan(0);

    active = source({
      source_id: "src_1",
      display_name: "Alpha.pdf",
      version: 2,
    });
    revision = 6;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await queryClient.invalidateQueries({
      queryKey: ["workspace", "ws_1", "sources"],
    });
    await waitFor(() => {
      expect(versionFetches.some((url) => url.includes("/versions/2/content"))).toBe(
        true,
      );
      expect(
        versionFetches.some((url) => url.includes("workspace_revision=6")),
      ).toBe(true);
    });
    expect(await screen.findByText("VERSION_TWO_BYTES")).toBeInTheDocument();
    expect(
      within(screen.getByRole("heading", { name: "Evidence" }).closest("section")!).getByText(
        /^Version 2$/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("VERSION_ONE_BYTES")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Current snapshot/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Historical snapshot/i)).not.toBeInTheDocument();

    active = null;
    revision = 7;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await queryClient.invalidateQueries({
      queryKey: ["workspace", "ws_1", "sources"],
    });
    await waitFor(() => {
      expect(screen.queryByText("VERSION_TWO_BYTES")).not.toBeInTheDocument();
      expect(
        screen.getByText(
          /Ask a question or choose a source to inspect its evidence/i,
        ),
      ).toBeInTheDocument();
    });
    mock.restore();
  });

  it("shows query provenance for citations and hides it for direct source preview", async () => {
    const user = userEvent.setup();
    mockViewport(false);
    let currentSnapshot = "snap_1";
    let revision = 5;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision,
            source_count: 1,
            status: "active",
            current_snapshot_id: currentSnapshot,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/conversation/turn" && call.method === "POST") {
        return jsonResponse(
          queryResponse({
            snapshot_id: "snap_1",
            workspace_revision: 5,
            trace_id: "tr_query_1",
          }),
        );
      }
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        return new Response("PREVIEW_BYTES", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    const { queryClient } = renderApp("/workspaces/ws_1");
    await user.type(await screen.findByLabelText("Ask a follow-up"), "Provenance?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/Ventilation must be established first/i),
    ).toBeInTheDocument();

    const evidence = screen
      .getByRole("heading", { name: "Evidence" })
      .closest("section")!;
    await user.click(within(evidence).getByText("Provenance"));
    expect(within(evidence).getByText("tr_query_1")).toBeInTheDocument();
    expect(within(evidence).getByText("snap_1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Alpha.pdf" }));
    await screen.findByText("PREVIEW_BYTES");
    const evidenceAfter = screen
      .getByRole("heading", { name: "Evidence" })
      .closest("section")!;
    await user.click(within(evidenceAfter).getByText("Provenance"));
    expect(within(evidenceAfter).queryByText("tr_query_1")).not.toBeInTheDocument();
    expect(within(evidenceAfter).queryByText("snap_1")).not.toBeInTheDocument();
    expect(
      within(evidenceAfter).getAllByText("Current snapshot").length,
    ).toBeGreaterThan(0);
    expect(within(evidenceAfter).queryByText("Historical snapshot")).not.toBeInTheDocument();

    // Historical answer card + current-source preview must not contradict in Evidence.
    currentSnapshot = "snap_2";
    revision = 6;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await waitFor(() => {
      expect(screen.getAllByText(/Historical snapshot/i).length).toBeGreaterThan(0);
    });
    await user.click(screen.getByRole("button", { name: "Alpha.pdf" }));
    const evidenceCurrent = screen
      .getByRole("heading", { name: "Evidence" })
      .closest("section")!;
    await user.click(within(evidenceCurrent).getByText("Provenance"));
    expect(
      within(evidenceCurrent).getAllByText("Current snapshot").length,
    ).toBeGreaterThan(0);
    expect(
      within(evidenceCurrent).queryByText("Historical snapshot"),
    ).not.toBeInTheDocument();
    expect(within(evidenceCurrent).queryByText("tr_query_1")).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /Citation 1: Week02\.pdf/i }),
    );
    const evidenceCite = screen
      .getByRole("heading", { name: "Evidence" })
      .closest("section")!;
    await user.click(within(evidenceCite).getByText("Provenance"));
    expect(within(evidenceCite).getByText("tr_query_1")).toBeInTheDocument();
    expect(within(evidenceCite).getByText("snap_1")).toBeInTheDocument();
    mock.restore();
  });

  it("desktop citation and source preview never mount Evidence drawer dialogs", async () => {
    const user = userEvent.setup();
    mockViewport(false);
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
        return jsonResponse(queryResponse());
      }
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        return new Response("BYTES", {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Alpha.pdf" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expectRootNotInert();

    await user.type(screen.getByLabelText("Ask a follow-up"), "Cite?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await user.click(
      await screen.findByRole("button", { name: /Citation 1: Week02\.pdf/i }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expectRootNotInert();
    mock.restore();
  });

  it("mobile Sources → source preview closes Sources then opens one Evidence drawer", async () => {
    const user = userEvent.setup();
    ensureAppRoot();
    mockViewport(true);
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
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        return new Response("BYTES", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const sourcesBtn = await screen.findByRole("button", { name: "Sources" });
    await user.click(sourcesBtn);
    const sourcesDrawer = await screen.findByRole("dialog", { name: "Sources" });
    await user.click(within(sourcesDrawer).getByRole("button", { name: "Alpha.pdf" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Sources" })).not.toBeInTheDocument();
    });
    const evidenceDrawer = await screen.findByRole("dialog", { name: "Evidence" });
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(within(evidenceDrawer).getByText("Alpha.pdf")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expectRootNotInert();
    mock.restore();
  });

  it("mobile citation opens exactly one Evidence drawer; desktop transition closes it", async () => {
    const user = userEvent.setup();
    ensureAppRoot();
    const viewport = mockViewport(true);
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
        return jsonResponse(queryResponse());
      }
      if (call.url.includes("/versions/") && call.url.includes("/content")) {
        return new Response("BYTES", {
          status: 200,
          headers: { "Content-Type": "application/pdf" },
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.type(await screen.findByLabelText("Ask a follow-up"), "Cite mobile?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(screen.queryByRole("dialog", { name: "Evidence" })).not.toBeInTheDocument();
    await user.click(
      await screen.findByRole("button", { name: /Citation 1: Week02\.pdf/i }),
    );
    expect(await screen.findByRole("dialog", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);

    viewport.setNarrow(false);
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
    expectRootNotInert();
    mock.restore();
  });

  it("opens Sources drawer without nesting a second dialog for Add sources", async () => {
    const user = userEvent.setup();
    mockViewport(true);
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Ask Desk",
            revision: 1,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Sources" }));
    const drawer = await screen.findByRole("dialog", { name: "Sources" });
    const addButtons = within(drawer).getAllByRole("button", {
      name: "+ Add sources",
    });
    await user.click(addButtons[0]!);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Sources" })).not.toBeInTheDocument();
    });
    expect(
      await screen.findByRole("dialog", { name: /add sources/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    mock.restore();
  });
});
