import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { errorResponse, installFetchMock, jsonResponse, source, workspace } from "./mockApi";
import { renderApp } from "./render";

it("inspects recalled knowledge, corrects it and forgets it through the workspace panel", async () => {
  const user = userEvent.setup();
  const initial = {
    id: "concept_1", category: "semantic", origin: "source_grounded",
    revision: 1, topic: "inspection", text: "Historical inspection discussion.",
    parent_id: null, relation: null, history: [],
    provenance: { snapshot_id: "snap_old", workspace_revision: 1, citations: [] },
  };
  let records = [initial];
  const knowledge = "/v1/workspaces/ws_1/knowledge";
  const mock = installFetchMock((call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1") return jsonResponse(workspace({ workspace_id: "ws_1" }));
    if (call.url === "/v1/workspaces/ws_1/sources") {
      return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [source({ source_id: "src_1" })] });
    }
    if (call.url.startsWith(knowledge + "?")) return jsonResponse({ enabled: true, records, summaries: [] });
    if (call.url === knowledge + "/records/concept_1" && call.method === "PATCH") {
      const input = JSON.parse(String(call.body));
      expect(input.revision).toBe(records[0].revision);
      records = input.text === null ? [] : [{ ...initial, origin: "user_provided", revision: 2, text: input.text }];
      return new Response(null, { status: 204 });
    }
    return errorResponse("not_found", "x", 404);
  });

  try {
    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Knowledge" }));
    const panel = screen.getByRole("region", { name: "Workspace knowledge" });
    const view = within(panel);
    await user.type(view.getByLabelText("Find a topic"), "inspection");
    await user.click(view.getByRole("button", { name: "Find" }));
    await user.click(await view.findByText("Concept · inspection", { selector: "summary" }));
    await user.click(view.getByText("Source provenance"));
    expect(view.getByText("Historical publication")).toBeVisible();
    await user.click(view.getByRole("button", { name: "Correct" }));
    await user.clear(view.getByLabelText("Correction"));
    await user.type(view.getByLabelText("Correction"), "My correction");
    await user.click(view.getByRole("button", { name: "Save" }));
    expect(await view.findByText("Learner · Revision 2")).toBeVisible();
    await user.click(view.getByRole("button", { name: "Forget" }));
    await user.click(view.getByRole("button", { name: "Confirm forget" }));
    expect(await view.findByText("No matching knowledge yet.")).toBeVisible();
    expect(mock.calls.some((call) => call.url === knowledge + "?topic=inspection")).toBe(true);
    expect(mock.calls.some((call) => call.url.endsWith("/conversation/turn"))).toBe(false);
  } finally {
    mock.restore();
  }
});

it("shows learning-history recall in chat without persisting it or using it for factual follow-ups", async () => {
  const user = userEvent.setup();
  const memoryQuestion = "What did I learn about forcible entry?";
  const remembered = "Saved discussion about inspection.";
  const submitted: { question: string; prior_turns: unknown[] }[] = [];
  const mock = installFetchMock((call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1") return jsonResponse(workspace({ workspace_id: "ws_1" }));
    if (call.url === "/v1/workspaces/ws_1/sources") {
      return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [source({ source_id: "src_1" })] });
    }
    if (call.url.endsWith("/conversation/turn")) {
      const input = JSON.parse(String(call.body));
      submitted.push(input);
      if (input.question === memoryQuestion) {
        return jsonResponse({
          workspace_id: "ws_1", workspace_revision: 1, snapshot_id: "snap_1",
          product_mode_id: "knowledge_recall_v1", conversation_trace_id: "memory_fixture",
          status: "answered", answer: remembered, answer_origin: "conversation",
          memory_recall: true, query_trace_id: null, retrieval_question: null,
          context_used: false, question: memoryQuestion, abstention_reason: null,
          answer_blocks: [], citations: [],
        });
      }
      return errorResponse("generation_timeout", "Generation timed out.", 504, true);
    }
    return errorResponse("not_found", "x", 404);
  });
  try {
    renderApp("/workspaces/ws_1");
    const composer = await screen.findByLabelText("Ask a follow-up");
    await user.type(composer, memoryQuestion);
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(remembered)).toBeVisible();
    expect(screen.getByText(/From workspace learning history/)).toBeVisible();
    expect(Object.values(sessionStorage).join(" ")).not.toContain(remembered);
    await user.type(composer, "What does the current source say?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Generation timed out.")).toBeVisible();
    expect(submitted[1].prior_turns).toEqual([]);
  } finally {
    mock.restore();
    sessionStorage.clear();
  }
});
