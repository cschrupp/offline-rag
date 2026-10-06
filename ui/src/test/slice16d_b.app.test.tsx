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
import type { WorkspaceQueryResponse } from "../api/types";
import {
  ASK_HISTORY_MAX,
  appendAskHistory,
  loadAskHistory,
  newHistoryEntryId,
  persistAskHistory,
  snapshotBadge,
} from "../features/ask/askHistory";
import {
  reconcileSourceSelection,
  sourceIdsForQuery,
} from "../features/ask/sourceSelection";
import { buildTextLineWindow } from "../features/ask/previewText";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function queryResponse(
  partial: Partial<WorkspaceQueryResponse> = {},
): WorkspaceQueryResponse {
  return {
    workspace_id: "ws_1",
    workspace_revision: 5,
    snapshot_id: "snap_1",
    product_mode_id: "grounded_v1",
    trace_id: "tr_1",
    status: "answered",
    answer: "Ventilation must be established first.",
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
      },
    ],
    ...partial,
  };
}

describe("Slice 16D-B source selection helpers", () => {
  it("reconciles all-selected vs explicit subset when sources change", () => {
    const a = source({ source_id: "src_a", display_name: "A.pdf" });
    const b = source({ source_id: "src_b", display_name: "B.pdf" });
    const first = reconcileSourceSelection("ws_sel", [a, b]);
    expect(first.selectedSourceIds).toEqual(["src_a", "src_b"]);

    const subset = {
      knownSourceIds: ["src_a", "src_b"],
      selectedSourceIds: ["src_a"],
    };
    sessionStorage.setItem(
      "seneca.source-selection.v1:ws_sel",
      JSON.stringify(subset),
    );
    const c = source({ source_id: "src_c", display_name: "C.pdf" });
    const afterSubset = reconcileSourceSelection("ws_sel", [a, b, c]);
    expect(afterSubset.selectedSourceIds).toEqual(["src_a"]);

    sessionStorage.setItem(
      "seneca.source-selection.v1:ws_all",
      JSON.stringify({
        knownSourceIds: ["src_a", "src_b"],
        selectedSourceIds: ["src_a", "src_b"],
      }),
    );
    const afterAll = reconcileSourceSelection("ws_all", [a, b, c]);
    expect(afterAll.selectedSourceIds).toEqual(["src_a", "src_b", "src_c"]);
  });

  it("omits source_ids only when every active source is selected", () => {
    const sources = [
      source({ source_id: "src_a" }),
      source({ source_id: "src_b" }),
    ];
    expect(sourceIdsForQuery(sources, ["src_a", "src_b"])).toBeUndefined();
    expect(sourceIdsForQuery(sources, ["src_a"])).toEqual(["src_a"]);
    expect(sourceIdsForQuery(sources, [])).toEqual([]);
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
      if (call.url === "/v1/workspaces/ws_1/query" && call.method === "POST") {
        bodies.push(JSON.parse(String(call.body)));
        return jsonResponse(queryResponse());
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("heading", { name: "Ask your sources" })).toBeInTheDocument();
    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes).toHaveLength(2);
    expect(boxes.every((box) => (box as HTMLInputElement).checked)).toBe(true);

    await user.click(boxes[0]!);
    await user.click(boxes[1]!);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Select all" }));
    await user.type(screen.getByLabelText("Question"), "What does Alpha say?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ question: "What does Alpha say?" });
    expect(bodies[0]).not.toHaveProperty("source_ids");
    mock.restore();
  });

  it("sends exact subset for Q2 and never includes prior history in the request", async () => {
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
      if (call.url === "/v1/workspaces/ws_1/query" && call.method === "POST") {
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
    await screen.findByRole("heading", { name: "Ask your sources" });
    const beta = screen.getByLabelText(/Include Beta\.pdf in next Ask/i);
    await user.click(beta);

    await user.type(screen.getByLabelText("Question"), "Question one?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("A1");

    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "Question two?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("A2");

    expect(bodies).toHaveLength(2);
    expect(bodies[0]).toEqual({
      question: "Question one?",
      source_ids: ["src_1"],
    });
    expect(bodies[1]).toEqual({
      question: "Question two?",
      source_ids: ["src_1"],
    });
    expect(JSON.stringify(bodies[1])).not.toContain("Question one");
    expect(JSON.stringify(bodies[1])).not.toContain("A1");
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
      if (call.url === "/v1/workspaces/ws_1/query" && call.method === "POST") {
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
            }),
          );
        }
        if (mode === "abstain") {
          return jsonResponse(
            queryResponse({
              status: "model_abstain",
              answer: null,
              citations: [],
            }),
          );
        }
        return jsonResponse(queryResponse());
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await screen.findByRole("heading", { name: "Ask your sources" });
    await user.type(screen.getByLabelText("Question"), "Requirements?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText(/Ventilation must be established first/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Current snapshot/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: /1 · Week02\.pdf · p\. 14/i }),
    ).toBeInTheDocument();

    mode = "insufficient";
    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "Missing?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    const insufficient = await screen.findByText(/did not find enough evidence/i);
    expect(insufficient).toBeInTheDocument();
    expect(insufficient.closest("[role='alert']")).toBeNull();

    mode = "abstain";
    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "Abstain?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText(/chose not to answer from the available evidence/i),
    ).toBeInTheDocument();

    mode = "conflict";
    await user.clear(screen.getByLabelText("Question"));
    await user.type(screen.getByLabelText("Question"), "Conflict?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText(/workspace changed while this question was running/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("loads historical citation via exact version+revision after snapshot change", async () => {
    const user = userEvent.setup();
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
      if (call.url === "/v1/workspaces/ws_1/query" && call.method === "POST") {
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
      await screen.findByLabelText("Question"),
      "Historical evidence?",
    );
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      (await screen.findAllByText(/Current snapshot/i)).length,
    ).toBeGreaterThan(0);

    currentSnapshot = "snap_2";
    revision = 6;
    await queryClient.invalidateQueries({ queryKey: ["workspace", "ws_1"] });
    await queryClient.invalidateQueries({
      queryKey: ["workspace", "ws_1", "sources"],
    });
    await waitFor(() => {
      expect(screen.getAllByText(/Historical snapshot/i).length).toBeGreaterThan(
        0,
      );
    });
    await user.click(
      screen.getByRole("button", { name: /1 · Alpha\.pdf · p\. 2/i }),
    );
    await waitFor(() => {
      expect(versionFetches.some((url) => url.includes("/versions/1/content"))).toBe(
        true,
      );
      expect(
        versionFetches.some((url) => url.includes("workspace_revision=5")),
      ).toBe(true);
    });
    expect(versionFetches.some((url) => url.includes("/versions/2/"))).toBe(false);
    mock.restore();
  });

  it("opens Sources drawer without nesting a second dialog for Add sources", async () => {
    const user = userEvent.setup();
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

    // Force narrow layout classes are CSS-only; exercise drawer controls directly.
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
