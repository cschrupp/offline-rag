import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurnResponse } from "../api/types";
import { loadDesktopRailState } from "../features/ask/desktopRailState";
import { NARROW_LAYOUT_MEDIA } from "../features/ask/useNarrowLayout";
import {
  deleteTrainingPrompt,
  loadTrainingPrompts,
  saveTrainingPrompt,
  trainingPromptsStorageKey,
} from "../features/training/trainingPrompts";
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
  localStorage.clear();
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

function workspaceHandlers(opts?: {
  onTurn?: (body: Record<string, unknown>) => ConversationTurnResponse | Response;
  workspaceId?: string;
}) {
  const workspaceId = opts?.workspaceId ?? "ws_1";
  const turnBodies: Record<string, unknown>[] = [];
  const mock = installFetchMock(async (call) => {
    if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (
      call.url === `/v1/workspaces/${workspaceId}` &&
      call.method === "GET"
    ) {
      return jsonResponse(
        workspace({
          workspace_id: workspaceId,
          title: "Ask Desk",
          revision: 5,
          source_count: 1,
          status: "active",
          current_snapshot_id: "snap_1",
        }),
      );
    }
    if (call.url === `/v1/workspaces/${workspaceId}/sources`) {
      return jsonResponse({
        workspace_id: workspaceId,
        revision: 5,
        sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
      });
    }
    if (
      call.url === `/v1/workspaces/${workspaceId}/conversation/turn` &&
      call.method === "POST"
    ) {
      const body = JSON.parse(String(call.body ?? "{}")) as Record<
        string,
        unknown
      >;
      turnBodies.push(body);
      const result = opts?.onTurn?.(body) ?? turnResponse({ question: String(body.question ?? "") });
      if (result instanceof Response) return result;
      return jsonResponse(result);
    }
    return errorResponse("not_found", "x", 404);
  });
  return { mock, turnBodies };
}

describe("Slice 16D-C training prompt storage", () => {
  it("persists per workspace and isolates libraries", () => {
    saveTrainingPrompt("ws_a", "How do you size a hoseline?");
    saveTrainingPrompt("ws_b", "What is flashover?");
    expect(loadTrainingPrompts("ws_a").map((p) => p.text)).toEqual([
      "How do you size a hoseline?",
    ]);
    expect(loadTrainingPrompts("ws_b").map((p) => p.text)).toEqual([
      "What is flashover?",
    ]);
    const id = loadTrainingPrompts("ws_a")[0]!.id;
    deleteTrainingPrompt("ws_a", id);
    expect(loadTrainingPrompts("ws_a")).toEqual([]);
    expect(loadTrainingPrompts("ws_b")).toHaveLength(1);
  });

  it("fails safely on corrupt storage", () => {
    localStorage.setItem(trainingPromptsStorageKey("ws_bad"), "{not-json");
    expect(loadTrainingPrompts("ws_bad")).toEqual([]);
    localStorage.setItem(
      trainingPromptsStorageKey("ws_bad2"),
      JSON.stringify([{ id: 1, text: "x" }]),
    );
    expect(loadTrainingPrompts("ws_bad2")).toEqual([]);
  });
});

describe("Slice 16D-C Training Mode UI", () => {
  it("enters and exits Training Mode without mutating workspace or conversation", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock, turnBodies } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Normal first?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Answer text.")).toBeInTheDocument();
    const turnsBefore = turnBodies.length;

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    expect(
      screen.getByRole("button", { name: "Exit Training Mode" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Training Mode")).toBeInTheDocument();
    expect(screen.getByText("Normal first?")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Include Alpha\.pdf/i }),
    ).toBeChecked();
    expect(turnBodies.length).toBe(turnsBefore);

    await user.click(screen.getByRole("button", { name: "Exit Training Mode" }));
    expect(
      screen.getByRole("button", { name: "Training Mode" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByText("Answer text.")).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Include Alpha\.pdf/i }),
    ).toBeChecked();
    expect(turnBodies.length).toBe(turnsBefore);
    mock.restore();
  });

  it("saves, seeds, and deletes prompts without auto-send; library never enters prior_turns", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock, turnBodies } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));

    const composer = screen.getByLabelText("Training question");
    await user.type(composer, "Saved training drill?");
    await user.click(screen.getByRole("button", { name: "Save question" }));
    expect(loadTrainingPrompts("ws_1").map((p) => p.text)).toEqual([
      "Saved training drill?",
    ]);
    expect(turnBodies).toHaveLength(0);

    await user.clear(composer);
    expect(composer).toHaveValue("");
    await user.click(
      screen.getByRole("button", { name: "Saved training drill?" }),
    );
    expect(composer).toHaveValue("Saved training drill?");
    expect(turnBodies).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Answer hidden")).toBeInTheDocument();
    expect(turnBodies).toHaveLength(1);
    expect(turnBodies[0]).toMatchObject({
      question: "Saved training drill?",
    });
    const prior = turnBodies[0]!.prior_turns;
    expect(Array.isArray(prior)).toBe(true);
    expect(prior).toEqual([]);

    await user.click(
      screen.getByRole("button", {
        name: /Delete saved question: Saved training drill/i,
      }),
    );
    expect(loadTrainingPrompts("ws_1")).toEqual([]);
    expect(
      screen.queryByRole("button", { name: "Saved training drill?" }),
    ).toBeNull();
    mock.restore();
  });

  it("keeps saved prompts workspace-scoped in the Training Mode UI", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    saveTrainingPrompt("ws_1", "Only for ws_1");
    const { mock } = workspaceHandlers({ workspaceId: "ws_2" });
    renderApp("/workspaces/ws_2");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    expect(
      screen.queryByRole("button", { name: "Only for ws_1" }),
    ).toBeNull();
    expect(screen.getByText(/No saved training questions yet/i)).toBeInTheDocument();
    expect(loadTrainingPrompts("ws_1").map((p) => p.text)).toEqual([
      "Only for ws_1",
    ]);
    mock.restore();
  });

  it("uses conversation/turn with unchanged source scope and B3 prior_turns", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock, turnBodies } = workspaceHandlers({
      onTurn: (body) =>
        turnResponse({
          question: String(body.question ?? ""),
          context_used: Array.isArray(body.prior_turns)
            ? body.prior_turns.length > 0
            : false,
          answer: "Second.",
          answer_blocks: [{ text: "Second.", citation_refs: ["c1"] }],
        }),
    });
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "First drill?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");
    await user.click(
      screen.getAllByRole("button", { name: "Reveal answer" })[0]!,
    );
    expect(screen.getByText("Second.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Training question"), "Follow-up drill?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(turnBodies.length).toBe(2));
    expect(mock.calls.some((c) => c.url.includes("/conversation/turn"))).toBe(
      true,
    );
    expect(
      mock.calls.some((c) => c.url.includes("/query") && c.method === "POST"),
    ).toBe(false);
    expect(turnBodies[0]).toMatchObject({
      question: "First drill?",
      prior_turns: [],
    });
    expect(turnBodies[0]!.source_ids).toBeUndefined();
    expect(turnBodies[1]!.prior_turns).toEqual([
      { role: "user", text: "First drill?" },
      { role: "assistant", text: "Second." },
    ]);
    mock.restore();
  });

  it("progressive reveal layers stay independent; citation activation opens evidence", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "Reveal drill?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Answer hidden")).toBeInTheDocument();
    expect(screen.queryByText("Answer text.")).toBeNull();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();

    const revealButtons = screen.getAllByRole("button", {
      name: "Reveal answer",
    });
    await user.click(revealButtons[0]!);
    expect(screen.getByText("Answer text.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Reveal citations" }));
    expect(
      screen.getByRole("button", { name: /Citation 1/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide answer" }));
    expect(screen.getByText("Answer hidden")).toBeInTheDocument();
    expect(screen.queryByText("Answer text.")).toBeNull();

    await user.click(
      screen.getAllByRole("button", { name: "Reveal answer" })[0]!,
    );
    await user.click(screen.getByRole("button", { name: /Citation 1/i }));
    await waitFor(() => {
      expect(screen.queryByText("Evidence hidden")).toBeNull();
    });
    expect(screen.getByRole("button", { name: "Hide evidence" })).toBeInTheDocument();
    mock.restore();
  });

  it("non-answered outcomes keep accepted copy and omit reveal-answer", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    let mode: "clarify" | "abstain" = "clarify";
    const { mock } = workspaceHandlers({
      onTurn: () => {
        if (mode === "clarify") {
          return turnResponse({
            status: "clarification_required",
            answer: null,
            answer_blocks: [],
            citations: [],
            abstention_reason: "ambiguous_request",
            query_trace_id: null,
            retrieval_question: null,
          });
        }
        return turnResponse({
          status: "model_abstain",
          answer: null,
          answer_blocks: [],
          citations: [],
          abstention_reason: "model_declined",
          query_trace_id: null,
        });
      },
    });
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "Which one?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(/could not safely resolve what this follow-up refers to/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reveal answer" }),
    ).toBeNull();

    mode = "abstain";
    await user.type(screen.getByLabelText("Training question"), "Abstain?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(
        /did not provide an answer from the available evidence/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Reveal answer" }),
    ).toBeNull();
    mock.restore();
  });

  it("new conversation clears B3 context but keeps prompts, sources, and Training Mode", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock, turnBodies } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(
      screen.getByLabelText("Training question"),
      "Keep this prompt",
    );
    await user.click(screen.getByRole("button", { name: "Save question" }));
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");

    await user.click(screen.getByRole("button", { name: "+ New conversation" }));
    expect(screen.queryByText("Answer hidden")).toBeNull();
    expect(
      screen.getByText(/Enter a training question or select a saved question/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Keep this prompt" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Include Alpha\.pdf/i }),
    ).toBeChecked();
    expect(
      screen.getByRole("button", { name: "Exit Training Mode" }),
    ).toBeInTheDocument();
    expect(turnBodies).toHaveLength(1);
    mock.restore();
  });

  it("presentation mode toggles layout without requests and restores rail preference", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock, turnBodies } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    // Collapse Sources via desktop control and persist.
    await user.click(screen.getByRole("button", { name: "Collapse Sources" }));
    expect(loadDesktopRailState().sourcesExpanded).toBe(false);
    const turnsBefore = turnBodies.length;

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.click(screen.getByRole("button", { name: "Presentation view" }));
    const page = document.querySelector(".workspace-page");
    expect(page?.classList.contains("presentation-mode")).toBe(true);
    expect(turnBodies.length).toBe(turnsBefore);
    // Presentation must not overwrite persisted rail preference.
    expect(loadDesktopRailState().sourcesExpanded).toBe(false);

    await user.click(screen.getByRole("button", { name: "Exit presentation" }));
    expect(page?.classList.contains("presentation-mode")).toBe(false);
    expect(loadDesktopRailState().sourcesExpanded).toBe(false);
    expect(
      screen.getByRole("button", { name: "Expand Sources" }),
    ).toBeInTheDocument();
    expect(turnBodies.length).toBe(turnsBefore);
    mock.restore();
  });

  it("reveal controls are keyboard operable and hide content from the accessibility tree", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "A11y drill?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");

    const reveal = screen.getAllByRole("button", { name: "Reveal answer" })[0]!;
    reveal.focus();
    expect(reveal).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByText("Answer text.")).toBeInTheDocument();
    await user.tab();
    // Hidden answer path removes content entirely when re-hidden.
    const hide = screen.getByRole("button", { name: "Hide answer" });
    hide.focus();
    await user.keyboard("{Enter}");
    expect(screen.queryByText("Answer text.")).toBeNull();
    expect(screen.getByText("Answer hidden")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Presentation view" }));
    const exitPresent = screen.getByRole("button", {
      name: "Exit presentation",
    });
    exitPresent.focus();
    expect(exitPresent).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(
      document.querySelector(".workspace-page.presentation-mode"),
    ).toBeNull();
    mock.restore();
  });

  it("narrow layout keeps training controls usable without stacked drawers", async () => {
    ensureAppRoot();
    mockViewport(true);
    const user = userEvent.setup();
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    expect(screen.getByRole("button", { name: "Save question" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Training question"), "Narrow drill?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");
    await user.click(screen.getAllByRole("button", { name: "Reveal answer" })[0]!);
    await user.click(screen.getByRole("button", { name: "Reveal citations" }));
    await user.click(screen.getByRole("button", { name: /Citation 1/i }));
    const drawers = screen.queryAllByRole("dialog");
    expect(drawers.length).toBeLessThanOrEqual(1);
    expect(screen.getByRole("button", { name: "Hide evidence" })).toBeInTheDocument();
    // Mobile Sources/Evidence entry points remain; no second modal stack.
    expect(screen.getAllByRole("button", { name: "Sources" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "Evidence" }).length).toBeGreaterThan(0);
    mock.restore();
  });
});
