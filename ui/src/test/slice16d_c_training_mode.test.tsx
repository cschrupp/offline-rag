import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurnResponse } from "../api/types";
import { loadDesktopRailState } from "../features/ask/desktopRailState";
import { NARROW_LAYOUT_MEDIA } from "../features/ask/useNarrowLayout";
import {
  HIDDEN_REVEAL,
  withRevealPatch,
} from "../features/training/revealState";
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

describe("Slice 16D-C reveal-state helpers (Rework 1)", () => {
  it("withRevealPatch defaults missing answered turns to hidden layers (C-R1)", () => {
    const afterAnswer = withRevealPatch({}, "e1", { answer: true });
    expect(afterAnswer.e1).toEqual({
      answer: true,
      citations: false,
      evidence: false,
    });
    const afterCitations = withRevealPatch({}, "e2", { citations: true });
    expect(afterCitations.e2).toEqual({
      answer: false,
      citations: true,
      evidence: false,
    });
    const afterEvidence = withRevealPatch({}, "e3", { evidence: true });
    expect(afterEvidence.e3).toEqual({
      answer: false,
      citations: false,
      evidence: true,
    });
    expect(HIDDEN_REVEAL).toEqual({
      answer: false,
      citations: false,
      evidence: false,
    });
  });
});

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
    expect(
      screen.getByRole("button", { name: "Question bank (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Saved training drill?" }),
    ).toBeNull();

    await user.clear(composer);
    expect(composer).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Question bank (1)" }));
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

    await user.click(screen.getByRole("button", { name: "Question bank (1)" }));
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
      screen.getByRole("button", { name: "Question bank (0)" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Only for ws_1" }),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: "Question bank (0)" }));
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
      screen.getByRole("button", { name: "Question bank (1)" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Question bank (1)" }));
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

  it("pre-existing normal answer keeps independent layers on first reveal (C-R1)", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock } = workspaceHandlers({
      onTurn: () =>
        turnResponse({
          answer: "Preexisting answer.",
          answer_blocks: [
            { text: "Preexisting answer.", citation_refs: ["c1"] },
          ],
        }),
    });
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Normal first?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Preexisting answer.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Citation 1/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    expect(await screen.findByText("Answer hidden")).toBeInTheDocument();
    expect(screen.queryByText("Preexisting answer.")).toBeNull();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();

    await user.click(
      screen.getAllByRole("button", { name: "Reveal answer" })[0]!,
    );
    expect(screen.getByText("Preexisting answer.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reveal citations" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: "Reveal evidence" }),
    ).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", { name: "Hide answer" }));
    expect(screen.getByText("Answer hidden")).toBeInTheDocument();
    mock.restore();
  });

  it("first action Reveal citations does not reveal answer or evidence (C-R1)", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Cite first?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer text.");

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await screen.findByText("Answer hidden");
    await user.click(screen.getByRole("button", { name: "Reveal citations" }));

    expect(screen.getByText("Answer hidden")).toBeInTheDocument();
    expect(screen.queryByText("Answer text.")).toBeNull();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Hide citations" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getAllByRole("button", { name: "Reveal answer" })[0],
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: "Reveal evidence" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Evidence hidden")).toBeInTheDocument();
    mock.restore();
  });

  it("first action Reveal evidence does not reveal answer or citations (C-R1)", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.type(screen.getByLabelText("Ask a follow-up"), "Evidence first?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer text.");

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await screen.findByText("Answer hidden");
    await user.click(screen.getByRole("button", { name: "Reveal evidence" }));

    expect(screen.getByText("Answer hidden")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Citation 1/i })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Hide evidence" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getAllByRole("button", { name: "Reveal answer" })[0],
    ).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.getByRole("button", { name: "Reveal citations" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Evidence hidden")).toBeNull();
    mock.restore();
  });

  it("Reveal evidence on older non-active turn binds Evidence to that turn (C-R2)", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    let n = 0;
    const { mock } = workspaceHandlers({
      onTurn: () => {
        n += 1;
        if (n === 1) {
          return turnResponse({
            conversation_trace_id: "ctr_old",
            query_trace_id: "tr_old",
            snapshot_id: "snap_old",
            answer: "Older answer one.",
            answer_blocks: [
              { text: "Older answer one.", citation_refs: ["c1"] },
            ],
            citations: [
              {
                evidence_unit_id: "eu_old",
                document_id: "doc_1",
                source_chunk_id: "chunk_old",
                kind: "parent",
                section_path: ["Old"],
                page_start: 2,
                page_end: 2,
                line_start: null,
                line_end: null,
                clipped: false,
                source_id: "src_1",
                source_version: 1,
                source_display_name: "Alpha.pdf",
                citation_ref: "c1",
                excerpt: "Older excerpt.",
                excerpt_clipped: false,
              },
            ],
          });
        }
        return turnResponse({
          conversation_trace_id: "ctr_new",
          query_trace_id: "tr_new",
          snapshot_id: "snap_1",
          answer: "Newer answer two.",
          answer_blocks: [
            { text: "Newer answer two.", citation_refs: ["c1"] },
          ],
          citations: [
            {
              evidence_unit_id: "eu_new",
              document_id: "doc_1",
              source_chunk_id: "chunk_new",
              kind: "parent",
              section_path: ["New"],
              page_start: 9,
              page_end: 9,
              line_start: null,
              line_end: null,
              clipped: false,
              source_id: "src_1",
              source_version: 1,
              source_display_name: "Alpha.pdf",
              citation_ref: "c1",
              excerpt: "Newer excerpt.",
              excerpt_clipped: false,
            },
          ],
        });
      },
    });
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "Q1 older?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");
    await user.click(
      screen.getAllByRole("button", { name: "Reveal answer" })[0]!,
    );
    expect(await screen.findByText("Older answer one.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Training question"), "Q2 newer?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() =>
      expect(screen.getAllByText("Answer hidden").length).toBeGreaterThan(0),
    );
    // Newest answered turn is active; reveal its answer so both turns show controls.
    const revealAnswers = screen.getAllByRole("button", {
      name: "Reveal answer",
    });
    await user.click(revealAnswers[revealAnswers.length - 1]!);
    expect(await screen.findByText("Newer answer two.")).toBeInTheDocument();

    // Reveal evidence on the older turn (first Reveal evidence control).
    const revealEvidenceButtons = screen.getAllByRole("button", {
      name: "Reveal evidence",
    });
    expect(revealEvidenceButtons.length).toBeGreaterThanOrEqual(1);
    await user.click(revealEvidenceButtons[0]!);

    await waitFor(() => {
      expect(screen.queryByText("Evidence hidden")).toBeNull();
    });
    // Older turn's evidence context — page 2, not the newer page 9.
    expect(screen.getAllByText(/page 2/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/page 9/i)).toBeNull();
    await user.click(screen.getAllByText("Provenance")[0]!);
    expect(screen.getAllByText("ctr_old").length).toBeGreaterThan(0);
    expect(screen.getAllByText("snap_old").length).toBeGreaterThan(0);
    expect(screen.queryByText("ctr_new")).toBeNull();
    // Older turn evidence control expanded.
    const hideEvidence = screen.getAllByRole("button", {
      name: "Hide evidence",
    });
    expect(hideEvidence.length).toBeGreaterThanOrEqual(1);
    expect(hideEvidence[0]).toHaveAttribute("aria-expanded", "true");
    mock.restore();
  });

  it("historical turn Reveal evidence keeps exact snapshot provenance (C-R2)", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    let n = 0;
    const { mock } = workspaceHandlers({
      onTurn: () => {
        n += 1;
        if (n === 1) {
          return turnResponse({
            conversation_trace_id: "ctr_hist",
            query_trace_id: "tr_hist",
            snapshot_id: "snap_historical",
            workspace_revision: 4,
            answer: "Historical answer.",
            answer_blocks: [
              { text: "Historical answer.", citation_refs: ["c1"] },
            ],
            citations: [
              {
                evidence_unit_id: "eu_hist",
                document_id: "doc_1",
                source_chunk_id: "chunk_hist",
                kind: "parent",
                section_path: ["Hist"],
                page_start: 3,
                page_end: 3,
                line_start: null,
                line_end: null,
                clipped: false,
                source_id: "src_1",
                source_version: 1,
                source_display_name: "Alpha.pdf",
                citation_ref: "c1",
                excerpt: "Historical excerpt.",
                excerpt_clipped: false,
              },
            ],
          });
        }
        return turnResponse({
          conversation_trace_id: "ctr_cur",
          query_trace_id: "tr_cur",
          snapshot_id: "snap_1",
          answer: "Current answer.",
          answer_blocks: [{ text: "Current answer.", citation_refs: ["c1"] }],
        });
      },
    });
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.type(screen.getByLabelText("Training question"), "Historical Q?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer hidden");
    await user.type(screen.getByLabelText("Training question"), "Current Q?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: /Historical snapshot/i }).length,
      ).toBeGreaterThan(0),
    );

    // Reveal evidence on the historical turn via its reveal control group.
    const historicalBadge = screen.getByRole("button", {
      name: /Historical snapshot/i,
    });
    const historicalTurn = historicalBadge.closest("article");
    expect(historicalTurn).toBeTruthy();
    const revealEvidence = Array.from(
      historicalTurn!.querySelectorAll("button"),
    ).find((b) => b.textContent?.trim() === "Reveal evidence");
    expect(revealEvidence).toBeTruthy();
    await user.click(revealEvidence!);

    await waitFor(() => {
      expect(screen.queryByText("Evidence hidden")).toBeNull();
    });
    expect(screen.getAllByText(/page 3/i).length).toBeGreaterThan(0);
    const provenance = screen.getAllByText("Provenance")[0]!;
    await user.click(provenance);
    expect(screen.getAllByText("ctr_hist").length).toBeGreaterThan(0);
    expect(screen.getAllByText("snap_historical").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Historical snapshot").length,
    ).toBeGreaterThan(0);
    mock.restore();
  });
});
