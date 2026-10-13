import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import { deriveExpertCampaignState } from "../features/goldLab/shell/deriveExpertCampaignState";
import {
  GOLD_GUIDE_DISMISSED_KEY,
} from "../features/goldLab/shell/goldGuideStorage";
import { goldCampaign, goldTask } from "./goldLabFixtures";
import { installFetchMock, jsonResponse } from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
});

function installCampaignTasks(tasks: ReturnType<typeof goldTask>[]) {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  return installFetchMock(async (call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces") return jsonResponse([]);
    if (call.url === "/v1/gold-lab/campaigns/camp_1") {
      return jsonResponse(campaign);
    }
    if (
      call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
      call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
    ) {
      return jsonResponse({ campaign_id: "camp_1", tasks });
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

describe("16N-B expert-first campaign", () => {
  it("B-CAM-01: main campaign surface exposes Continue Gold work", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_1",
        task_kind: "question_check",
        active: true,
        state: "pending",
        candidate_chunk_id: null,
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByTestId("gold-continue-action")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Continue Gold work/i }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-CAM-02: QC pending takes precedence over active RF for Continue", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_1",
        task_kind: "question_check",
        active: true,
        state: "pending",
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "ar_1",
        task_kind: "absolute_relevance",
        active: true,
        state: "pending",
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    expect(
      await screen.findByRole("button", {
        name: /Continue Gold work — Review questions/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /Continue Gold work — Judge evidence/i,
      }),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("B-CAM-03: with QC exhausted and active AR pending, Continue selects Rapid Fire", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_done",
        task_kind: "question_check",
        active: false,
        state: "completed",
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "ar_1",
        task_kind: "absolute_relevance",
        active: true,
        state: "pending",
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    expect(
      await screen.findByRole("button", {
        name: /Continue Gold work — Judge evidence/i,
      }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-CAM-04: with neither primary queue active, shows resting state not dead Continue", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_done",
        task_kind: "question_check",
        active: false,
        state: "completed",
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "ar_inactive",
        task_kind: "absolute_relevance",
        active: false,
        state: "pending",
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByTestId("gold-continue-resting")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Continue Gold work/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Canonical Gold work is complete for now/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-CAM-05 / B-CAM-06: four cards in frozen order; ES/CD locked", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_1",
        task_kind: "question_check",
        active: true,
        state: "pending",
        candidate_chunk_id: null,
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    const cards = await screen.findByTestId("gold-work-cards");
    const articles = within(cards).getAllByRole("article");
    expect(articles.map((el) => el.getAttribute("data-testid"))).toEqual([
      "gold-work-card-question_check",
      "gold-work-card-rapid_fire",
      "gold-work-card-evidence_sweep",
      "gold-work-card-chunk_duel",
    ]);
    expect(screen.getByTestId("gold-work-card-evidence_sweep-locked")).toBeInTheDocument();
    expect(screen.getByTestId("gold-work-card-chunk_duel-locked")).toBeInTheDocument();
    expect(
      within(screen.getByTestId("gold-work-card-evidence_sweep")).queryByRole(
        "button",
      ),
    ).toBeNull();
    expect(
      within(screen.getByTestId("gold-work-card-chunk_duel")).queryByRole(
        "button",
      ),
    ).toBeNull();
    mock.restore();
  });

  it("B-CAM-07: raw workload/task diagnostics are under Advanced only", async () => {
    const user = userEvent.setup();
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_raw_1",
        task_kind: "question_check",
        active: true,
        state: "pending",
        candidate_chunk_id: null,
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    await screen.findByTestId("gold-continue-action");
    const cards = screen.getByTestId("gold-work-cards");
    expect(within(cards).queryByText("qc_raw_1")).not.toBeInTheDocument();
    expect(within(cards).queryByText("Workload discovery")).not.toBeInTheDocument();

    const advanced = screen.getByTestId("campaign-advanced");
    expect((advanced as HTMLDetailsElement).open).toBe(false);
    expect(within(advanced).getByText("Workload discovery")).toBeInTheDocument();
    await user.click(within(advanced).getByText("Advanced"));
    expect((advanced as HTMLDetailsElement).open).toBe(true);
    expect(within(advanced).getByText("qc_raw_1")).toBeInTheDocument();
    mock.restore();
  });

  it("B-CAM-08: Close campaign de-emphasized under Advanced; confirm still available", async () => {
    const user = userEvent.setup();
    const mock = installCampaignTasks([]);
    renderApp("/gold-lab/campaigns/camp_1");
    await screen.findByTestId("gold-workflow-progress");
    const advanced = screen.getByTestId("campaign-advanced");
    expect((advanced as HTMLDetailsElement).open).toBe(false);
    expect(
      within(advanced).getByRole("button", { name: /^Close campaign$/i }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("gold-work-cards")).queryByRole("button", {
        name: /^Close campaign$/i,
      }),
    ).not.toBeInTheDocument();

    await user.click(within(advanced).getByText("Advanced"));
    await user.click(
      within(advanced).getByRole("button", { name: /^Close campaign$/i }),
    );
    expect(
      await screen.findByText(/Closing is permanent/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-PROG-01/02/03: workflow counts QC and active AR only", () => {
    const state = deriveExpertCampaignState([
      goldTask({
        task_id: "qc_done",
        task_kind: "question_check",
        state: "completed",
        active: false,
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "qc_pend",
        task_kind: "question_check",
        state: "pending",
        active: true,
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "ar_done",
        task_kind: "absolute_relevance",
        state: "completed",
        active: false,
      }),
      goldTask({
        task_id: "ar_ready",
        task_kind: "absolute_relevance",
        state: "pending",
        active: true,
      }),
      goldTask({
        task_id: "ar_inactive",
        task_kind: "absolute_relevance",
        state: "pending",
        active: false,
      }),
    ]);
    expect(state.qcReviewed).toBe(1);
    expect(state.qcPending).toBe(1);
    expect(state.relevanceCompleted).toBe(1);
    expect(state.relevancePending).toBe(1);
    expect(state.nextPrimaryGame).toBe("question_check");
    expect(state.primaryComplete).toBe(false);
  });

  it("B-PROG renders human workflow ladder copy", async () => {
    const mock = installCampaignTasks([
      goldTask({
        task_id: "qc_done",
        task_kind: "question_check",
        state: "completed",
        active: false,
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "qc_pend",
        task_kind: "question_check",
        state: "pending",
        active: true,
        candidate_chunk_id: null,
      }),
      goldTask({
        task_id: "ar_done",
        task_kind: "absolute_relevance",
        state: "completed",
        active: false,
      }),
      goldTask({
        task_id: "ar_ready",
        task_kind: "absolute_relevance",
        state: "pending",
        active: true,
      }),
      goldTask({
        task_id: "ar_inactive",
        task_kind: "absolute_relevance",
        state: "pending",
        active: false,
      }),
    ]);
    renderApp("/gold-lab/campaigns/camp_1");
    const progress = await screen.findByTestId("gold-workflow-progress");
    await waitFor(() => {
      expect(progress).toHaveTextContent("1 reviewed · 1 remaining");
      expect(progress).toHaveTextContent("1 judged · 1 ready");
    });
    mock.restore();
  });

  it("B-GUIDE-01/02/03: Guide opens first visit; dismiss uses sessionStorage only", async () => {
    const user = userEvent.setup();
    const mock = installCampaignTasks([]);
    expect(sessionStorage.getItem(GOLD_GUIDE_DISMISSED_KEY)).toBeNull();
    expect(localStorage.getItem(GOLD_GUIDE_DISMISSED_KEY)).toBeNull();

    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByTestId("gold-guide")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: /Dismiss Gold Guide for this browser session/i,
      }),
    );
    expect(screen.queryByTestId("gold-guide")).not.toBeInTheDocument();
    expect(sessionStorage.getItem(GOLD_GUIDE_DISMISSED_KEY)).toBe("1");
    expect(localStorage.getItem(GOLD_GUIDE_DISMISSED_KEY)).toBeNull();

    cleanup();
    renderApp("/gold-lab/campaigns/camp_1");
    await screen.findByTestId("gold-workflow-progress");
    expect(screen.queryByTestId("gold-guide")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Show Gold Guide/i }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-POL-01/02: APPROVED_PRESENTATIONS_V1 remains exact QC+RF", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([
      {
        game_id: "goldgame_question_check_v1",
        presentation_id: "goldpres_question_check_source_panel_v1",
        disposition: "ALLOW_PRODUCTION",
      },
      {
        game_id: "goldgame_rapid_fire_v1",
        presentation_id: "goldpres_rapid_fire_single_card_v1",
        disposition: "ALLOW_PRODUCTION",
      },
    ]);
    const here = dirname(fileURLToPath(import.meta.url));
    const text = readFileSync(
      join(here, "../features/goldLab/policy/approvedPresentations.v1.ts"),
      "utf8",
    );
    expect(text).toContain("ALLOW_PRODUCTION");
    expect(text).not.toMatch(/evidence_sweep[\s\S]*ALLOW_PRODUCTION/);
    expect(text).not.toMatch(/chunk_duel[\s\S]*ALLOW_PRODUCTION/);
  });
});
