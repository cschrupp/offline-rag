import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Workspace } from "../api/types";
import type { QuickPlayState } from "../features/goldLab/api/quickPlay";
import { GoldLabGuideRoute } from "../features/goldLab/guide/GoldLabGuide";
import { GoldLabQuickPlayPage } from "../pages/GoldLabQuickPlayPage";

const workspaceA: Workspace = {
  workspace_id: "ws_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  title: "Field Manual",
  description: "",
  revision: 3,
  status: "active",
  current_snapshot_id: "snap_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  source_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const workspaceB: Workspace = {
  ...workspaceA,
  workspace_id: "ws_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  title: "Maintenance Notes",
  current_snapshot_id: "snap_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
};

function playableState(
  workspace: Workspace,
  campaignId: string,
): QuickPlayState {
  return {
    schema_version: "quick-play-state-v1",
    workspace_id: workspace.workspace_id,
    workspace_title: workspace.title,
    status: "playable",
    campaign_id: campaignId,
    available_games: [
      { game_id: "question_check", label: "Question Check", pending_count: 2 },
      { game_id: "rapid_fire", label: "Rapid Fire", pending_count: 5 },
    ],
    question_check_pending: 2,
    rapid_fire_pending: 5,
    next_game: "question_check",
  };
}

function contribution(campaignId: string, totalScore: number) {
  return {
    contract: "gold-contribution-v1",
    campaign_id: campaignId,
    total_score: totalScore,
    expert_judgments: 5,
    questions_reviewed: 2,
    cases_completed: 1,
    gold_finalized: 0,
    hard_calls_resolved: 0,
    completed_active_absolute_tasks: 3,
    total_active_absolute_tasks: 8,
    coverage_fraction: 0.375,
    total_question_tasks: 4,
  };
}

function renderQuickPlay({
  scoreA = 42,
  failContributionOnce = false,
  holdWorkspaceB = false,
  onWorkspaceBRequested,
}: {
  scoreA?: number;
  failContributionOnce?: boolean;
  holdWorkspaceB?: boolean;
  onWorkspaceBRequested?: (release: () => void) => void;
} = {}) {
  const requests: string[] = [];
  let contributionAttempts = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      requests.push(url);
      if (url === "/v1/workspaces") return Response.json([workspaceA, workspaceB]);
      if (url.includes(`/quick-play/workspaces/${workspaceA.workspace_id}`)) {
        return Response.json(playableState(workspaceA, "campaign_a"));
      }
      if (url.includes(`/quick-play/workspaces/${workspaceB.workspace_id}`)) {
        if (holdWorkspaceB) {
          return new Promise<Response>((resolve) => {
            onWorkspaceBRequested?.(() =>
              resolve(Response.json(playableState(workspaceB, "campaign_b"))),
            );
          });
        }
        return Response.json(playableState(workspaceB, "campaign_b"));
      }
      if (url === "/v1/gold-lab/campaigns/campaign_a/contribution") {
        contributionAttempts += 1;
        if (failContributionOnce && contributionAttempts === 1) {
          return Response.json({ message: "temporarily unavailable" }, { status: 503 });
        }
        return Response.json(contribution("campaign_a", scoreA));
      }
      if (url === "/v1/gold-lab/campaigns/campaign_b/contribution") {
        return Response.json(contribution("campaign_b", 17));
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[`/gold-lab?workspace=${workspaceA.workspace_id}`]}
      >
        <Routes>
          <Route element={<GoldLabGuideRoute />}>
            <Route path="/gold-lab" element={<GoldLabQuickPlayPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return requests;
}

function contributionRail() {
  return within(screen.getByRole("complementary", { name: "Contribution" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("BETA-GAME-02B Quick Play presentation", () => {
  it("loads authoritative contribution for the selected campaign only", async () => {
    const requests = renderQuickPlay();
    const user = userEvent.setup();

    expect(await contributionRail().findByText("42")).toBeInTheDocument();
    expect(contributionRail().getByText("Current campaign contribution")).toBeInTheDocument();
    expect(contributionRail().getByText("Evidence judgments completed")).toBeInTheDocument();

    await user.selectOptions(
      screen.getByLabelText("Workspace"),
      workspaceB.workspace_id,
    );

    expect(await contributionRail().findByText("17")).toBeInTheDocument();
    expect(contributionRail().queryByText("42")).not.toBeInTheDocument();
    expect(
      requests.some((url) => url.endsWith("/campaigns/campaign_a/contribution")),
    ).toBe(true);
    expect(
      requests.some((url) => url.endsWith("/campaigns/campaign_b/contribution")),
    ).toBe(true);
  });

  it("clears the previous score immediately while a newly selected workspace loads", async () => {
    const user = userEvent.setup();
    let releaseWorkspaceB: () => void = () => undefined;
    renderQuickPlay({
      holdWorkspaceB: true,
      onWorkspaceBRequested: (release) => {
        releaseWorkspaceB = release;
      },
    });

    expect(await contributionRail().findByText("42")).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Workspace"),
      workspaceB.workspace_id,
    );
    expect(contributionRail().queryByText("42")).not.toBeInTheDocument();
    expect(contributionRail().getByText("No current deck contribution yet.")).toBeInTheDocument();

    releaseWorkspaceB();
    expect(await contributionRail().findByText("17")).toBeInTheDocument();
  });

  it("renders game-specific cards with server-provided pending counts", async () => {
    renderQuickPlay();

    const questionCard = await screen.findByRole("article", {
      name: /Question Check/,
    });
    const rapidCard = screen.getByRole("article", { name: /Rapid Fire/ });
    expect(within(questionCard).getByText("2 questions remaining")).toBeInTheDocument();
    expect(within(rapidCard).getByText("5 evidence judgments available")).toBeInTheDocument();
    expect(
      within(questionCard).getByRole("link", { name: "Resume Play · Question Check" }),
    ).toHaveAttribute("href", expect.stringContaining("game=question_check"));
  });

  it("shows a server-returned zero contribution without blocking play", async () => {
    renderQuickPlay({ scoreA: 0 });

    expect(await contributionRail().findByText("0", { selector: ".quick-play-contribution-score" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resume Play · Question Check" })).toBeInTheDocument();
  });

  it("keeps games usable when contribution loading fails and supports retry", async () => {
    const user = userEvent.setup();
    renderQuickPlay({ failContributionOnce: true });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resume Play · Question Check" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry contribution" }));
    expect(await contributionRail().findByText("42")).toBeInTheDocument();
  });

  it("allows both desktop rails to collapse independently and remembers them", async () => {
    const user = userEvent.setup();
    renderQuickPlay();

    await user.click(screen.getByRole("button", { name: "Collapse Contribution" }));
    await user.click(screen.getByRole("button", { name: "Collapse How to play" }));

    expect(screen.getByRole("button", { name: "Expand Contribution" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByRole("button", { name: "Expand How to play" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(localStorage.getItem("offline-rag.gold-lab.quick-play-contribution-rail-expanded.v1")).toBe("false");
    expect(localStorage.getItem("offline-rag.gold-lab.guide-rail-expanded.v1")).toBe("false");
  });

  it("persists the mobile contribution and guide disclosure preferences", async () => {
    const user = userEvent.setup();
    renderQuickPlay();

    const contributionDisclosure = screen.getByRole("button", {
      name: "Your contribution",
    });
    await user.click(contributionDisclosure);
    expect(contributionDisclosure).toHaveAttribute("aria-expanded", "true");

    const guideDisclosure = screen.getByText("How to play", {
      selector: "summary",
    });
    await user.click(guideDisclosure);
    expect(guideDisclosure.closest("details")).toHaveAttribute("open");
    expect(
      localStorage.getItem("offline-rag.gold-lab.mobile-contribution-expanded.v1"),
    ).toBe("true");
    expect(
      localStorage.getItem("offline-rag.gold-lab.mobile-guide-expanded.v1"),
    ).toBe("true");
  });

  it("keeps the current deck contribution unavailable without a campaign", async () => {
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        requests.push(url);
        if (url === "/v1/workspaces") return Response.json([workspaceA]);
        if (url.includes("/quick-play/workspaces/")) {
          return Response.json({
            schema_version: "quick-play-state-v1",
            workspace_id: workspaceA.workspace_id,
            workspace_title: workspaceA.title,
            status: "needs_generation",
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/gold-lab?workspace=${workspaceA.workspace_id}`]}>
          <Routes>
            <Route element={<GoldLabGuideRoute />}>
              <Route path="/gold-lab" element={<GoldLabQuickPlayPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await contributionRail().findByText("No current deck contribution yet.")).toBeInTheDocument();
    await waitFor(() => expect(requests.some((url) => url.includes("/contribution"))).toBe(false));
  });
});
