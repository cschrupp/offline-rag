import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Operation, Workspace } from "../api/types";
import { GoldLabQuickPlayPage } from "../pages/GoldLabQuickPlayPage";
import type { QuickPlayState } from "../features/goldLab/api/quickPlay";
import { GoldLabGuideRoute } from "../features/goldLab/guide/GoldLabGuide";

const workspace: Workspace = {
  workspace_id: "ws_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  title: "Field Manual",
  description: "",
  revision: 4,
  status: "active",
  current_snapshot_id: "snap_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  source_count: 3,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function state(
  status: QuickPlayState["status"],
  extra: Partial<QuickPlayState> = {},
): QuickPlayState {
  return {
    schema_version: "quick-play-state-v1",
    workspace_id: workspace.workspace_id,
    workspace_title: workspace.title,
    status,
    ...extra,
  };
}

function operation(status: Operation["status"]): Operation {
  return {
    operation_id: "wop_quickplay1",
    kind: "gold_lab_baseline_bootstrap",
    workspace_id: workspace.workspace_id,
    expected_revision: null,
    status,
    progress_stage: "proposing",
    progress: null,
    metrics: null,
    worklist: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:01:00Z",
    result: null,
    error: null,
  };
}

function renderPage(initialState: QuickPlayState, withWorkspaceParam = true) {
  let currentState = initialState;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url === "/v1/workspaces") {
        return Response.json([workspace]);
      }
      if (url.includes("/quick-play/workspaces/") && init?.method === "POST") {
        currentState = state("generating", {
          operation: {
            operation_id: "wop_quickplay1",
            status: "running",
          },
        });
        return Response.json(currentState);
      }
      if (url.includes("/quick-play/workspaces/")) {
        return Response.json(currentState);
      }
      if (url === "/v1/operations/wop_quickplay1") {
        return Response.json(operation("running"));
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
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
        initialEntries={[
          withWorkspaceParam
            ? `/gold-lab?workspace=${workspace.workspace_id}`
            : "/gold-lab",
        ]}
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

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("BETA-GAME-01 Quick Play", () => {
  it("starts first-time generation and recovers the managed operation", async () => {
    const user = userEvent.setup();
    const requests = renderPage(state("needs_generation"), false);

    await user.selectOptions(
      await screen.findByLabelText("Workspace"),
      workspace.workspace_id,
    );
    expect(
      await screen.findByRole("heading", { name: "Create an activity deck" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("complementary", { name: "How to play" })).getByText(
        /Create a small activity deck/,
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate deck" }));

    expect(await screen.findByRole("heading", { name: "Generating your activity deck" })).toBeInTheDocument();
    expect(
      within(screen.getByRole("complementary", { name: "How to play" })).getByText(
        /proposing questions and gathering candidate passages/,
      ),
    ).toBeInTheDocument();
    expect(requests.some((request) => request.init?.method === "POST")).toBe(true);
    expect((await screen.findAllByText(/proposing/i)).length).toBeGreaterThan(0);
  });

  it("explains when the workspace has no suitable source chunks", async () => {
    renderPage(state("empty_population", { reason: "no_eligible_source_chunks" }));

    expect(
      await screen.findByRole("heading", { name: "No suitable source text yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/needs published source chunks with readable text/i),
    ).toBeInTheDocument();
  });

  it("remembers the workspace so returning users can resume directly", async () => {
    localStorage.setItem(
      "offline-rag.quick-play.workspace.v1",
      workspace.workspace_id,
    );
    renderPage(
      state("playable", {
        campaign_id: "goldcamp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        available_games: [
          { game_id: "rapid_fire", label: "Rapid Fire", pending_count: 1 },
        ],
        question_check_pending: 0,
        rapid_fire_pending: 1,
        next_game: "rapid_fire",
      }),
      false,
    );

    expect(
      await screen.findByRole("link", { name: "Resume Play · Rapid Fire" }),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("complementary", { name: "How to play" })).getByText(
        /Choose an available activity/,
      ),
    ).toBeInTheDocument();
  });

  it("lets a returning expert resume the next eligible game in one action", async () => {
    const requests = renderPage(
      state("playable", {
        campaign_id: "goldcamp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        available_games: [
          { game_id: "question_check", label: "Question Check", pending_count: 2 },
          { game_id: "rapid_fire", label: "Rapid Fire", pending_count: 3 },
        ],
        question_check_pending: 2,
        rapid_fire_pending: 3,
        next_game: "question_check",
      }),
    );

    const resume = await screen.findByRole("link", {
      name: "Resume Play · Question Check",
    });
    expect(resume).toHaveAttribute(
      "href",
      "/gold-lab/campaigns/goldcamp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/work?game=question_check&return_to=quick_play&quick_play_workspace=ws_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    );
    expect(screen.getByRole("link", { name: /Rapid Fire · 3/ })).toBeInTheDocument();
    expect(requests.some((request) => request.init?.method === "POST")).toBe(false);
  });

  it("offers retry after failed generation and uses a new idempotency key", async () => {
    const user = userEvent.setup();
    const requests = renderPage(
      state("generation_failed", {
        operation: {
          operation_id: "wop_quickplay1",
          status: "failed",
          failure_summary: "Model endpoint was unreachable.",
        },
      }),
    );

    await screen.findByRole("heading", { name: "Deck generation did not finish" });
    await user.click(screen.getByRole("button", { name: "Retry generation" }));
    await screen.findByRole("heading", { name: "Generating your activity deck" });

    const retry = requests.find((request) => request.init?.method === "POST");
    expect(retry).toBeDefined();
    const headers = new Headers(retry?.init?.headers);
    expect(headers.get("Idempotency-Key")).toMatch(/^quick-play-/);
    await waitFor(() => expect(screen.getByLabelText("Workspace")).toHaveValue(workspace.workspace_id));
  });
});
