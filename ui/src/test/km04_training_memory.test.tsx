import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { errorResponse, installFetchMock, jsonResponse, source, workspace } from "./mockApi";
import { renderApp } from "./render";

it("creates and practices a card in Training Mode while preserving reveal boundaries", async () => {
  const user = userEvent.setup();
  const root = "/v1/workspaces/ws_1/knowledge/training";
  const active = {
    id: "card_current", topic: "Practice tags", flashcard_question: "What does the source say?",
    exercise: "In the synthetic exercise, record an ____ tag.",
    citation: { source_id: "src_1", source_version: 2, source_display_name: "Exercise.txt", evidence_unit_id: "eu_2" },
    requires_revalidation: false, snapshot_id: "snap_1",
  };
  let cards = [{ ...active, id: "card_old", topic: "Earlier practice tags", requires_revalidation: true }];
  const mock = installFetchMock((call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1") return jsonResponse(workspace({ workspace_id: "ws_1" }));
    if (call.url === "/v1/workspaces/ws_1/sources") {
      return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [source({ source_id: "src_1" })] });
    }
    if (call.url.startsWith(root + "?")) {
      return jsonResponse({ enabled: true, cards, topics: [], aids: [], history: [] });
    }
    if (call.url === root + "/cards") {
      expect(JSON.parse(String(call.body))).toEqual({ topic: "Practice tags", source_ids: ["src_1"] });
      expect(call.headers.get("Idempotency-Key")).toBeTruthy();
      cards = [active, ...cards];
      return new Response(null, { status: 204 });
    }
    if (call.url === root + "/cards/card_current/attempts") {
      expect(JSON.parse(String(call.body))).toMatchObject({ mode: "check", answer: "orange", source_ids: ["src_1"] });
      return jsonResponse({ outcome: "matched" });
    }
    return errorResponse("not_found", "fixture route missing", 404);
  });

  try {
    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Training Mode" }));
    await user.click(screen.getByRole("button", { name: "Review workspace memory" }));
    const panel = within(screen.getByRole("region", { name: "Training memory review" }));
    await user.click(await panel.findByText("Earlier practice tags", { selector: "summary" }));
    expect(panel.getByText("Needs revalidation.")).toBeVisible();
    expect(panel.getByRole("button", { name: "Reveal source answer" })).toBeDisabled();
    await user.type(panel.getByLabelText("New card topic"), "Practice tags");
    await user.click(panel.getByRole("button", { name: "Create flashcard and recall exercise" }));
    const summary = await panel.findByText("Practice tags", { selector: "summary" });
    await user.click(summary);
    const card = within(summary.closest("details")!);
    expect(card.queryByText("In the synthetic exercise, record an orange tag.")).not.toBeInTheDocument();
    await user.type(card.getByLabelText("Missing word"), "orange");
    await user.click(card.getByRole("button", { name: "Check recall" }));
    expect(await card.findByText("Exact match. Recall demonstrated on this exercise.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Presentation view" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Training memory review" })).not.toBeInTheDocument());
  } finally {
    mock.restore();
  }
});
