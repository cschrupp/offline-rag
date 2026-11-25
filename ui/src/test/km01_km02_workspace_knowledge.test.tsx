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
    await user.click(await view.findByText("Concept · inspection"));
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
