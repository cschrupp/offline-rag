import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConversationTurnResponse } from "../api/types";
import {
  conversationHasPendingTurn,
  DERIVED_CONVERSATION_WARNING,
  serializeConversationJson,
  serializeConversationMarkdown,
} from "../features/ask/conversationExport";
import type {
  ConversationHistoryEntry,
  IncompleteUserTurn,
} from "../features/ask/conversationState";
import { NARROW_LAYOUT_MEDIA } from "../features/ask/useNarrowLayout";
import {
  exportQuestionBankJson,
  exportQuestionBankMarkdown,
  filterQuestionBankSearch,
  parseQuestionBankFile,
  planQuestionBankMerge,
  QUESTION_BANK_FORMAT,
  QUESTION_BANK_VERSION,
} from "../features/training/questionBankIo";
import {
  loadTrainingPrompts,
  PROMPT_MAX,
  saveTrainingPrompt,
  type SavedTrainingPrompt,
} from "../features/training/trainingPrompts";
import {
  capabilities,
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
  const listeners = new Set<() => void>();
  const media = {
    matches: matchesNarrow,
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
        section_path: ["Employment"],
        page_start: 2,
        page_end: 2,
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
}) {
  const turnBodies: Record<string, unknown>[] = [];
  const mock = installFetchMock(async (call) => {
    if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
      return jsonResponse(
        workspace({
          workspace_id: "ws_1",
          title: "B1 Upload Smoke",
          revision: 7,
          source_count: 1,
          current_snapshot_id: "snap_1",
        }),
      );
    }
    if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
      return jsonResponse({
        sources: [source({ source_id: "src_1", display_name: "Alpha.pdf" })],
      });
    }
    if (
      call.url === "/v1/workspaces/ws_1/conversation/turn" &&
      call.method === "POST"
    ) {
      const body = JSON.parse(String(call.body ?? "{}")) as Record<
        string,
        unknown
      >;
      turnBodies.push(body);
      const custom = opts?.onTurn?.(body);
      if (custom instanceof Response) return custom;
      return jsonResponse(custom ?? turnResponse({ question: String(body.question) }));
    }
    if (call.url.startsWith("/v1/workspaces/ws_1/operations")) {
      return jsonResponse({ operations: [] });
    }
    return jsonResponse({});
  });
  return { mock, turnBodies };
}

function samplePrompts(): SavedTrainingPrompt[] {
  return [
    {
      id: "p1",
      text: "What is Carlos's last name?",
      createdAt: "2026-01-01T00:00:00.000Z",
    },
    {
      id: "p2",
      text: "Describe Machine Learning.",
      createdAt: "2026-01-02T00:00:00.000Z",
    },
  ];
}

describe("16D-C Rework 2 / A4 — Question Bank UX", () => {
  it("keeps the bank closed by default and reports count", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    saveTrainingPrompt("ws_1", "Q1");
    saveTrainingPrompt("ws_1", "Q2");
    saveTrainingPrompt("ws_1", "Q3");
    saveTrainingPrompt("ws_1", "Q4");
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));

    expect(
      screen.getByRole("button", { name: "Question bank (4)" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Search questions")).toBeNull();
    expect(screen.queryByRole("button", { name: "Q1" })).toBeNull();
    expect(document.querySelector(".training-prompt-list")).toBeNull();
    expect(document.querySelector(".question-bank-list")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Question bank (4)" }));
    expect(screen.getByLabelText("Search questions")).toBeInTheDocument();
    expect(document.querySelector(".question-bank-popover")).not.toBeNull();
    expect(document.querySelector(".question-bank-list")).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(screen.queryByLabelText("Search questions")).toBeNull();
    mock.restore();
  });

  it("filters search without mutating storage and seeds without Send", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    saveTrainingPrompt("ws_1", "Alpha question");
    saveTrainingPrompt("ws_1", "Beta question");
    const { mock, turnBodies } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.click(screen.getByRole("button", { name: "Question bank (2)" }));

    const before = loadTrainingPrompts("ws_1");
    await user.type(screen.getByLabelText("Search questions"), "beta");
    expect(screen.queryByRole("button", { name: "Alpha question" })).toBeNull();
    expect(
      screen.getByRole("button", { name: "Beta question" }),
    ).toBeInTheDocument();
    expect(loadTrainingPrompts("ws_1")).toEqual(before);

    await user.click(screen.getByRole("button", { name: "Beta question" }));
    expect(screen.getByLabelText("Training question")).toHaveValue(
      "Beta question",
    );
    expect(turnBodies).toHaveLength(0);
    mock.restore();
  });

  it("presentation mode does not permanently expand the bank", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    saveTrainingPrompt("ws_1", "Present Q");
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.click(screen.getByRole("button", { name: "Presentation view" }));
    expect(
      screen.getByRole("button", { name: "Question bank (1)" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Present Q" })).toBeNull();
    expect(loadTrainingPrompts("ws_1").map((p) => p.text)).toEqual(["Present Q"]);
    mock.restore();
  });
});

describe("16D-C Rework 2 / A4 — Question Bank IO", () => {
  it("exports JSON v1 without internal IDs and Markdown bullets", () => {
    const artifact = exportQuestionBankJson(
      samplePrompts(),
      "B1 Upload Smoke",
      "2026-10-07T20:00:00-04:00",
    );
    expect(artifact.filename).toBe(
      "seneca-question-bank-b1-upload-smoke.json",
    );
    const doc = JSON.parse(artifact.content) as Record<string, unknown>;
    expect(doc).toMatchObject({
      format: QUESTION_BANK_FORMAT,
      version: QUESTION_BANK_VERSION,
      title: "B1 Upload Smoke",
      questions: [
        { text: "What is Carlos's last name?" },
        { text: "Describe Machine Learning." },
      ],
    });
    expect(JSON.stringify(doc)).not.toContain("p1");
    expect(JSON.stringify(doc)).not.toContain("createdAt");

    const md = exportQuestionBankMarkdown(samplePrompts(), "B1 Upload Smoke");
    expect(md.filename).toBe("seneca-question-bank-b1-upload-smoke.md");
    expect(md.content).toContain("# Seneca Question Bank — B1 Upload Smoke");
    expect(md.content).toContain("- What is Carlos's last name?");
    expect(md.content).toContain("- Describe Machine Learning.");
  });

  it("parses valid JSON/Markdown and rejects bad format/version/corrupt", () => {
    const valid = parseQuestionBankFile(
      "bank.json",
      JSON.stringify({
        format: QUESTION_BANK_FORMAT,
        version: QUESTION_BANK_VERSION,
        questions: [{ text: "One" }, { text: "  " }, { text: "Two" }],
      }),
      200,
    );
    expect(valid.ok).toBe(true);
    if (valid.ok) expect(valid.questions).toEqual(["One", "  ", "Two"]);

    expect(
      parseQuestionBankFile(
        "bank.json",
        JSON.stringify({ format: "other", version: 1, questions: [] }),
        40,
      ).ok,
    ).toBe(false);
    expect(
      parseQuestionBankFile(
        "bank.json",
        JSON.stringify({
          format: QUESTION_BANK_FORMAT,
          version: 99,
          questions: [],
        }),
        40,
      ).ok,
    ).toBe(false);
    expect(parseQuestionBankFile("bank.json", "{not-json", 20).ok).toBe(false);

    const md = parseQuestionBankFile(
      "bank.md",
      `# Title\n\n- First\n- Second\n\nProse paragraph\n\n1. Numbered\n  - nested\n`,
      80,
    );
    expect(md.ok).toBe(true);
    if (md.ok) expect(md.questions).toEqual(["First", "Second"]);
  });

  it("ignores bullet-looking lines inside fenced code (A4-R1)", () => {
    const backtick = parseQuestionBankFile(
      "bank.md",
      [
        "# Bank",
        "",
        "```text",
        "- Do not import this",
        "```",
        "",
        "- Import this question?",
        "",
      ].join("\n"),
      200,
    );
    expect(backtick.ok).toBe(true);
    if (backtick.ok) {
      expect(backtick.questions).toEqual(["Import this question?"]);
      expect(backtick.questions).not.toContain("Do not import this");
    }

    const tilde = parseQuestionBankFile(
      "bank.md",
      [
        "~~~markdown",
        "- Also not a question",
        "~~~",
        "",
        "- Real question",
        "",
      ].join("\n"),
      200,
    );
    expect(tilde.ok).toBe(true);
    if (tilde.ok) {
      expect(tilde.questions).toEqual(["Real question"]);
      expect(tilde.questions).not.toContain("Also not a question");
    }

    const longer = parseQuestionBankFile(
      "bank.md",
      [
        "- Before fence",
        "````text",
        "- Inside longer fence",
        "```",
        "- Still inside (short close)",
        "````",
        "- After fence",
        "",
      ].join("\n"),
      240,
    );
    expect(longer.ok).toBe(true);
    if (longer.ok) {
      expect(longer.questions).toEqual(["Before fence", "After fence"]);
      expect(longer.questions).not.toContain("Inside longer fence");
      expect(longer.questions).not.toContain("Still inside (short close)");
    }

    const unclosed = parseQuestionBankFile(
      "bank.md",
      [
        "- Before unclosed",
        "```text",
        "- Fake after open",
        "- Also fake",
        "",
      ].join("\n"),
      160,
    );
    expect(unclosed.ok).toBe(true);
    if (unclosed.ok) {
      expect(unclosed.questions).toEqual(["Before unclosed"]);
      expect(unclosed.questions).not.toContain("Fake after open");
      expect(unclosed.questions).not.toContain("Also fake");
    }
  });

  it("requires whitespace-only close and recognizes indented fences (A4-R3)", () => {
    const infoStringFalseClose = parseQuestionBankFile(
      "bank.md",
      [
        "```text",
        "```js",
        "- Fake question inside code",
        "```",
        "- Real question?",
        "",
      ].join("\n"),
      200,
    );
    expect(infoStringFalseClose.ok).toBe(true);
    if (infoStringFalseClose.ok) {
      expect(infoStringFalseClose.questions).toEqual(["Real question?"]);
      expect(infoStringFalseClose.questions).not.toContain(
        "Fake question inside code",
      );
    }

    const indented = parseQuestionBankFile(
      "bank.md",
      [
        "   ```text",
        "- Fake question inside indented fence",
        "   ```",
        "- Real question?",
        "",
      ].join("\n"),
      200,
    );
    expect(indented.ok).toBe(true);
    if (indented.ok) {
      expect(indented.questions).toEqual(["Real question?"]);
      expect(indented.questions).not.toContain(
        "Fake question inside indented fence",
      );
    }

    const suffixedDoesNotClose = parseQuestionBankFile(
      "bank.md",
      [
        "```text",
        "```python",
        "- Still inside after suffixed marker",
        "```   ",
        "- Real after true close",
        "",
      ].join("\n"),
      220,
    );
    expect(suffixedDoesNotClose.ok).toBe(true);
    if (suffixedDoesNotClose.ok) {
      expect(suffixedDoesNotClose.questions).toEqual(["Real after true close"]);
      expect(suffixedDoesNotClose.questions).not.toContain(
        "Still inside after suffixed marker",
      );
    }
  });

  it("plans merge with duplicates, invalid, and capacity skips", () => {
    const existing = Array.from({ length: PROMPT_MAX - 1 }, (_, i) => ({
      id: `id_${i}`,
      text: `Existing ${i}`,
      createdAt: "2026-01-01T00:00:00.000Z",
    }));
    const plan = planQuestionBankMerge(existing, [
      "Existing 0",
      "  Brand new  ",
      "",
      "Another new",
      "Third new",
    ]);
    expect(plan.duplicateCount).toBe(1);
    expect(plan.invalidCount).toBe(1);
    expect(plan.newCount).toBe(1);
    expect(plan.capacitySkippedCount).toBe(2);
    expect(plan.importableTexts).toEqual(["Brand new"]);
  });

  it("search helper is presentation-only", () => {
    const prompts = samplePrompts();
    const filtered = filterQuestionBankSearch(prompts, "CARLOS");
    expect(filtered.map((p) => p.text)).toEqual(["What is Carlos's last name?"]);
    expect(prompts).toHaveLength(2);
  });

  it("import confirmation mutates only after commit; export/import make no API calls", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    saveTrainingPrompt("ws_1", "Keep me");
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    await user.click(screen.getByRole("button", { name: "Question bank (1)" }));

    const file = new File(
      [
        JSON.stringify({
          format: QUESTION_BANK_FORMAT,
          version: QUESTION_BANK_VERSION,
          questions: [
            { text: "Keep me" },
            { text: "Fresh import" },
            { text: "   " },
          ],
        }),
      ],
      "machine-learning-review.json",
      { type: "application/json" },
    );
    const input = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const callsBeforeImport = mock.calls.length;
    await user.upload(input, file);

    const dialog = await screen.findByRole("dialog", {
      name: "Import question bank",
    });
    expect(within(dialog).getByText(/3 questions found/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/1 new/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/1 duplicates/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/1 invalid/i)).toBeInTheDocument();
    expect(loadTrainingPrompts("ws_1").map((p) => p.text)).toEqual(["Keep me"]);

    await user.click(
      within(dialog).getByRole("button", { name: "Import 1 questions" }),
    );
    expect(loadTrainingPrompts("ws_1").map((p) => p.text)).toEqual([
      "Fresh import",
      "Keep me",
    ]);
    expect(mock.calls.length).toBe(callsBeforeImport);
    mock.restore();
  });
});

describe("16D-C Rework 2 / A4 — Conversation export", () => {
  const workspaceMeta = {
    workspace_id: "ws_1",
    title: "B1 Upload Smoke",
    revision: 7,
    current_snapshot_id: "snap_1",
  };

  function answeredEntry(): ConversationHistoryEntry {
    return {
      entryId: "pair_1",
      askedAt: "2026-10-07T19:00:00.000Z",
      question: "How many jobs?",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["Alpha.pdf"],
      selectionMode: "all",
      response: turnResponse({
        question: "How many jobs?",
        answer: "Three jobs. [1]",
        answer_blocks: [{ text: "Three jobs.", citation_refs: ["c1"] }],
      }),
    };
  }

  it("serializes Markdown with provenance warning and citations; JSON retains B3 fields", () => {
    const md = serializeConversationMarkdown({
      workspace: workspaceMeta,
      history: [answeredEntry()],
      incompleteTurns: [],
      exportedFromView: "training",
      exportedAt: "2026-10-07T20:00:00-04:00",
    });
    expect(md.filename).toBe("seneca-conversation-b1-upload-smoke.md");
    expect(md.content).toContain(DERIVED_CONVERSATION_WARNING.split(".")[0]!);
    expect(md.content).toContain("derived material and is not primary evidence");
    expect(md.content).toContain("How many jobs?");
    expect(md.content).toContain("Three jobs.[1]");
    expect(md.content).toContain("`Alpha.pdf`");
    expect(md.content).toContain("Version: 1");
    expect(md.content).toContain("Page: 2");
    expect(md.content).not.toContain("revealMap");

    const json = serializeConversationJson({
      workspace: workspaceMeta,
      history: [answeredEntry()],
      incompleteTurns: [],
      exportedFromView: "training",
      exportedAt: "2026-10-07T20:00:00-04:00",
    });
    expect(json.filename).toBe("seneca-conversation-b1-upload-smoke.json");
    const doc = JSON.parse(json.content) as Record<string, unknown>;
    expect(doc).toMatchObject({
      format: "seneca-conversation",
      version: 1,
      exported_from_view: "training",
      workspace: workspaceMeta,
    });
    const turns = doc.turns as Array<Record<string, unknown>>;
    expect(turns[0]).toMatchObject({
      kind: "completed",
      question: "How many jobs?",
      answer: "Three jobs. [1]",
      conversation_trace_id: "ctr_1",
      query_trace_id: "tr_1",
      snapshot_id: "snap_1",
      workspace_revision: 5,
    });
    expect(JSON.stringify(doc)).not.toContain("revealMap");
  });

  it("exports abstention/clarification/failed turns without fabricating answers", () => {
    const clarification: ConversationHistoryEntry = {
      ...answeredEntry(),
      entryId: "pair_2",
      question: "What about that?",
      response: turnResponse({
        status: "clarification_required",
        abstention_reason: "ambiguous_request",
        answer: null,
        answer_blocks: [],
        citations: [],
        query_trace_id: null,
        retrieval_question: null,
      }),
    };
    const failed: IncompleteUserTurn = {
      pairId: "fail_1",
      askedAt: "2026-10-07T19:30:00.000Z",
      question: "Broken?",
      selectedSourceIds: ["src_1"],
      selectedSourceNames: ["Alpha.pdf"],
      selectionMode: "all",
      status: "failed",
      errorMessage: "Network unavailable.",
    };
    const md = serializeConversationMarkdown({
      workspace: workspaceMeta,
      history: [clarification],
      incompleteTurns: [failed],
      exportedFromView: "normal",
    });
    expect(md.content).toContain("clarification_required");
    expect(md.content).toMatch(/could not safely resolve/i);
    expect(md.content).toContain("**Turn did not complete.**");
    expect(md.content).toContain("Network unavailable.");
    expect(md.content).not.toMatch(/Three jobs/);

    const pending: IncompleteUserTurn = { ...failed, status: "pending" };
    expect(conversationHasPendingTurn([pending])).toBe(true);
  });

  it("export controls exist in Normal and Training Mode without backend calls", async () => {
    ensureAppRoot();
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:test");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });

    expect(
      screen.getByRole("button", { name: "Export conversation" }),
    ).toBeDisabled();

    await user.type(screen.getByLabelText("Ask a follow-up"), "Normal Q?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Answer text.");
    const exportBtn = screen.getByRole("button", {
      name: "Export conversation",
    });
    expect(exportBtn).toBeEnabled();
    const callsBefore = mock.calls.length;
    await user.click(exportBtn);
    await user.click(screen.getByRole("menuitem", { name: "Export as Markdown" }));
    expect(mock.calls.length).toBe(callsBefore);
    expect(createObjectURL).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Training Mode" }));
    expect(
      screen.getByRole("button", { name: "Export conversation" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("heading", { name: "Training conversation" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Answer hidden")).toBeInTheDocument();

    const md = serializeConversationMarkdown({
      workspace: {
        workspace_id: "ws_1",
        title: "B1 Upload Smoke",
        revision: 7,
        current_snapshot_id: "snap_1",
      },
      history: [
        {
          entryId: "pair_1",
          askedAt: "2026-10-07T19:00:00.000Z",
          question: "Normal Q?",
          selectedSourceIds: ["src_1"],
          selectedSourceNames: ["Alpha.pdf"],
          selectionMode: "all",
          response: turnResponse({ question: "Normal Q?" }),
        },
      ],
      incompleteTurns: [],
      exportedFromView: "training",
    });
    expect(md.content).toContain("Answer text.");
    mock.restore();
  });
});

describe("16D-C Rework 2 / A4 — Application header", () => {
  it("keeps Seneca brand/nav and full-width header contract; Overview body stays constrained", async () => {
    ensureAppRoot();
    mockViewport(false);
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return jsonResponse({});
    });
    renderApp("/");
    const header = document.querySelector(".app-header");
    expect(header).not.toBeNull();
    const scoped = within(header as HTMLElement);
    expect(scoped.getByRole("link", { name: /Seneca/i })).toBeInTheDocument();
    expect(scoped.getByRole("link", { name: /^Overview$/i })).toBeInTheDocument();
    expect(
      scoped.getByRole("link", { name: /^Workspaces$/i }),
    ).toBeInTheDocument();
    expect(scoped.getByRole("link", { name: /Settings/i })).toBeInTheDocument();

    const headerInner = header!.querySelector(".app-header-inner");
    expect(headerInner).not.toBeNull();
    const main = document.getElementById("main-content");
    expect(main?.classList.contains("app-main")).toBe(true);
    // Overview/Settings remain on the constrained app-main shell (A4-D22).
    expect(document.querySelector(".workspace-page")).toBeNull();
    mock.restore();
  });

  it("workspace body retains A3 layout under the same header shell", async () => {
    ensureAppRoot();
    mockViewport(false);
    const { mock } = workspaceHandlers();
    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Conversation" });
    expect(document.querySelector(".workspace-page")).not.toBeNull();
    expect(document.querySelector(".app-header-inner")).not.toBeNull();
    expect(document.querySelector(".knowledge-layout")).not.toBeNull();
    mock.restore();
  });

  it("preserves mobile nav toggle", async () => {
    ensureAppRoot();
    mockViewport(true);
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return jsonResponse({});
    });
    renderApp("/");
    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-controls", "primary-navigation");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // JSDOM does not apply the 720px CSS that reveals the toggle; fireEvent
    // still exercises the AppShell open/close contract.
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass(
      "open",
    );
    mock.restore();
  });
});
