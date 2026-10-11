import { cleanup, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { goldCampaign } from "./goldLabFixtures";
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
});

function contributionDto(overrides: Record<string, unknown> = {}) {
  return {
    contract: "gold-contribution-v1",
    campaign_id: "camp_1",
    // Intentionally unusual: not equal to any naive client re-weight of counts.
    total_score: 9042,
    expert_judgments: 3,
    questions_reviewed: 2,
    cases_completed: 1,
    gold_finalized: 1,
    hard_calls_resolved: 0,
    completed_active_absolute_tasks: 3,
    total_active_absolute_tasks: 6,
    coverage_fraction: 0.5,
    total_question_tasks: 4,
    ...overrides,
  };
}

describe("16G-I4 contribution dashboard", () => {
  it("displays server total_score without recomputing and frames non-competitively", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url === "/v1/gold-lab/campaigns/camp_1/contribution") {
        expect(call.method).toBe("GET");
        return jsonResponse(contributionDto());
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/contribution");
    expect(
      await screen.findByTestId("contribution-total-score"),
    ).toHaveTextContent("9042");
    expect(screen.getByTestId("contribution-expert-judgments")).toHaveTextContent(
      "3",
    );
    expect(screen.getByTestId("contribution-coverage-counts")).toHaveTextContent(
      "3 / 6",
    );
    expect(screen.getByTestId("contribution-coverage-pct")).toHaveTextContent(
      "50%",
    );
    expect(screen.getByTestId("contribution-question-progress")).toHaveTextContent(
      "2 / 4",
    );

    const body = document.body.textContent ?? "";
    for (const forbidden of [
      "leaderboard",
      "rank",
      "streak",
      "speed score",
      "model agreement",
      "competitive",
    ]) {
      expect(body.toLowerCase()).not.toContain(forbidden);
    }

    mock.restore();
  });

  it("rejects wrong contract or campaign identity", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/contribution")) {
        return jsonResponse(
          contributionDto({ contract: "gold-contribution-v0" }),
        );
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/contribution");
    expect(
      await screen.findByText(/unexpected Gold Lab response/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("maps gold_state_unavailable safely", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/contribution")) {
        return errorResponse("gold_state_unavailable", "raw path /data/secret", 409);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/contribution");
    expect(
      await screen.findByText(/Gold Lab state is temporarily unavailable/i),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("/data/secret");
    mock.restore();
  });

  it("exposes contribution navigation from campaign shell", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [] });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1");
    expect(
      await screen.findByRole("link", { name: "Contribution" }),
    ).toHaveAttribute("href", "/gold-lab/campaigns/camp_1/contribution");
    expect(
      screen.getByRole("link", { name: "Calibration" }),
    ).toHaveAttribute("href", "/gold-lab/campaigns/camp_1/calibration");
    await waitFor(() => {
      expect(
        mock.calls.some((call) => call.url.includes("/contribution")),
      ).toBe(false);
    });
    mock.restore();
  });
});
