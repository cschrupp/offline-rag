import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { trainingPackageFixture } from "./calibrationPackageFixture";
import { goldCampaign } from "./goldLabFixtures";
import {
  installFetchMock,
  jsonResponse,
  type FetchCall,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const DATASET_ID =
  "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const FORBIDDEN = [
  "/tasks",
  "/relevance",
  "/question-check",
  "/preferences",
  "/export",
  "/contribution",
];

function assertLearnerNetwork(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Scenario touched forbidden path: ${call.url}`);
      }
    }
    if (
      call.method !== "GET" &&
      !call.url.includes("/health") &&
      call.url.includes("/gold-lab")
    ) {
      throw new Error(`Scenario non-GET Gold call: ${call.method} ${call.url}`);
    }
  }
}

function installScenarioMock() {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  const pkg = trainingPackageFixture();
  return installFetchMock(async (call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces") return jsonResponse([]);
    if (call.url === "/v1/gold-lab/campaigns/camp_1") {
      return jsonResponse(campaign);
    }
    if (call.url === "/v1/gold-lab/campaigns/camp_1/registrations") {
      return jsonResponse({
        campaign_id: "camp_1",
        registrations: [
          {
            dataset_id: DATASET_ID,
            dataset_path: `datasets/${DATASET_ID}`,
            baseline_sha256: "b".repeat(64),
            projection_sha256: "c".repeat(64),
            exported_case_ids: ["case_accept"],
            registered_at: "2026-03-03T00:00:00Z",
          },
        ],
      });
    }
    if (call.url.includes("/training-package")) {
      return jsonResponse(pkg);
    }
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Forbidden scenario fetch: ${call.url}`);
      }
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

describe("16G-I5 training scenario / debrief", () => {
  it("hides authority until scenario commit, then locks and debriefs", async () => {
    const mock = installScenarioMock();
    const user = userEvent.setup();
    const storageSet = vi.spyOn(Storage.prototype, "setItem");

    renderApp(
      `/gold-lab/campaigns/camp_1/training/scenario?dataset=${DATASET_ID}`,
    );
    const scenario = await screen.findByTestId("training-scenario");
    expect(within(scenario).getByTestId("scenario-stem")).toHaveTextContent(
      "What pressure?",
    );
    expect(
      within(scenario).queryByText(/Authority:|Registration-time/),
    ).toBeNull();
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();

    const cards = within(scenario).getAllByRole("listitem");
    await user.click(within(cards[0]!).getByLabelText(/2 — Direct evidence/i));
    await user.click(within(cards[1]!).getByLabelText(/1 — Supporting evidence/i));
    // Revise B before commit
    await user.click(within(cards[1]!).getByLabelText(/0 — Irrelevant/i));

    await user.click(
      within(scenario).getByRole("button", { name: /Commit scenario/i }),
    );

    expect(
      await screen.findByTestId("scenario-reveal-chunk_a"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("scenario-reveal-chunk_b")).toBeInTheDocument();
    const debrief = await screen.findByTestId("training-scenario-debrief");
    expect(within(debrief).getByTestId("scenario-debrief-matches")).toHaveTextContent(
      "2 / 2",
    );
    expect(
      within(debrief).getByTestId("scenario-debrief-learner-dist"),
    ).toHaveTextContent("0:1 · 1:0 · 2:1");
    expect(
      within(debrief).getByTestId("scenario-debrief-authority-dist"),
    ).toHaveTextContent("0:1 · 1:0 · 2:1");
    expect(within(debrief).getByText(/chunk_a/i)).toBeInTheDocument();
    expect(within(debrief).getAllByText(/Historical source/i).length).toBeGreaterThan(
      0,
    );

    // Locked — radios disabled
    expect(
      within(cards[0]!).getByLabelText(/2 — Direct evidence/i),
    ).toBeDisabled();

    assertLearnerNetwork(mock.calls);
    expect(
      storageSet.mock.calls.some((call) =>
        String(call[0]).toLowerCase().includes("train"),
      ),
    ).toBe(false);
    mock.restore();
  });
});
