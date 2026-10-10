import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  validateGoldBaselineListResponse,
  validateGoldProjectListResponse,
  validateGoldTaskListResponse,
} from "../features/goldLab/api/validation";
import {
  goldBaseline,
  goldCampaign,
  goldProject,
  goldTask,
  usableWorkspace,
} from "./goldLabFixtures";
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type FetchCall,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const FORBIDDEN_SUBSTRINGS = [
  "/question-check",
  "/relevance",
  "/preferences",
  "/contribution",
  "/export",
  "/registrations",
  "/v1/gold-lab/data",
  "/training-package",
  "/data/",
];

function assertNoForbiddenCalls(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN_SUBSTRINGS) {
      expect(call.url).not.toContain(fragment);
    }
    const path = call.url.split("?")[0] ?? call.url;
    if (/\/tasks\/[^/]+$/.test(path) || /\/tasks\/[^/]+\//.test(path)) {
      throw new Error(`Unexpected task-detail or judgment path: ${call.method} ${call.url}`);
    }
  }
}

type MockState = {
  projects: ReturnType<typeof goldProject>[];
  baselinesByProject: Record<string, ReturnType<typeof goldBaseline>[]>;
  campaignsByProject: Record<string, ReturnType<typeof goldCampaign>[]>;
  campaigns: Record<string, ReturnType<typeof goldCampaign>>;
  tasksByCampaign: Record<string, ReturnType<typeof goldTask>[]>;
  workspaces: ReturnType<typeof usableWorkspace>[];
  malformedBaselines?: boolean;
  archiveConflict?: boolean;
};

function installGoldLabMocks(initial?: Partial<MockState>) {
  const state: MockState = {
    projects: initial?.projects ?? [],
    baselinesByProject: initial?.baselinesByProject ?? {},
    campaignsByProject: initial?.campaignsByProject ?? {},
    campaigns: initial?.campaigns ?? {},
    tasksByCampaign: initial?.tasksByCampaign ?? {},
    workspaces: initial?.workspaces ?? [usableWorkspace()],
    malformedBaselines: initial?.malformedBaselines ?? false,
    archiveConflict: initial?.archiveConflict ?? false,
  };

  const mock = installFetchMock(async (call) => {
    const { url, method } = call;

    if (url === "/health/ready") return jsonResponse({ status: "ready" });
    if (url === "/v1/workspaces" && method === "GET") {
      return jsonResponse(state.workspaces);
    }

    if (url === "/v1/gold-lab/projects" && method === "GET") {
      return jsonResponse({ projects: state.projects });
    }

    if (url === "/v1/gold-lab/projects" && method === "POST") {
      const body = JSON.parse(String(call.body ?? "{}")) as Record<
        string,
        unknown
      >;
      expect(body).not.toHaveProperty("project_id");
      expect(body).not.toHaveProperty("created_at");
      expect(body).not.toHaveProperty("status");
      expect(call.headers.get("Idempotency-Key")).toBeNull();
      const created = goldProject({
        project_id: `proj_${state.projects.length + 1}`,
        workspace_id: String(body.workspace_id),
        title: String(body.title),
        description: String(body.description ?? ""),
        project_type: body.project_type as "benchmark" | "improvement",
      });
      state.projects = [...state.projects, created];
      state.baselinesByProject[created.project_id] ??= [];
      state.campaignsByProject[created.project_id] ??= [];
      return jsonResponse(created, { status: 201 });
    }

    const projectMatch = url.match(/^\/v1\/gold-lab\/projects\/([^/?]+)$/);
    if (projectMatch && method === "GET") {
      const project = state.projects.find(
        (item) => item.project_id === projectMatch[1],
      );
      if (!project) {
        return errorResponse("gold_project_unknown", "missing", 404);
      }
      return jsonResponse(project);
    }

    const archiveMatch = url.match(
      /^\/v1\/gold-lab\/projects\/([^/?]+)\/archive$/,
    );
    if (archiveMatch && method === "POST") {
      expect(call.body == null || call.body === "").toBe(true);
      expect(call.headers.get("Idempotency-Key")).toBeNull();
      if (state.archiveConflict) {
        return errorResponse("gold_conflict", "already archived", 409);
      }
      const index = state.projects.findIndex(
        (item) => item.project_id === archiveMatch[1],
      );
      if (index < 0) {
        return errorResponse("gold_project_unknown", "missing", 404);
      }
      const archived = { ...state.projects[index], status: "archived" as const };
      state.projects = state.projects.map((item, i) =>
        i === index ? archived : item,
      );
      return jsonResponse(archived);
    }

    const baselinesMatch = url.match(
      /^\/v1\/gold-lab\/projects\/([^/?]+)\/baselines$/,
    );
    if (baselinesMatch && method === "GET") {
      if (state.malformedBaselines) {
        return jsonResponse({ project_id: baselinesMatch[1], baselines: null });
      }
      return jsonResponse({
        project_id: baselinesMatch[1],
        baselines: state.baselinesByProject[baselinesMatch[1]] ?? [],
      });
    }

    const campaignsListMatch = url.match(
      /^\/v1\/gold-lab\/projects\/([^/?]+)\/campaigns$/,
    );
    if (campaignsListMatch && method === "GET") {
      return jsonResponse({
        project_id: campaignsListMatch[1],
        campaigns: state.campaignsByProject[campaignsListMatch[1]] ?? [],
      });
    }

    if (campaignsListMatch && method === "POST") {
      const body = JSON.parse(String(call.body ?? "{}")) as Record<
        string,
        unknown
      >;
      expect(body).toEqual({
        baseline_authoring_run_id: body.baseline_authoring_run_id,
        selection_policy_id: body.selection_policy_id,
        selection_policy_parameters: {},
        hard_calls: [],
      });
      expect(body).not.toHaveProperty("campaign_id");
      expect(body).not.toHaveProperty("project_type");
      expect(body).not.toHaveProperty("selection_policy_fingerprint");
      expect(body).not.toHaveProperty("snapshot_id");
      expect(call.headers.get("Idempotency-Key")).toBeNull();
      const projectId = campaignsListMatch[1];
      const created = goldCampaign({
        campaign_id: `camp_${Object.keys(state.campaigns).length + 1}`,
        project_id: projectId,
        baseline_authoring_run_id: String(body.baseline_authoring_run_id),
      });
      state.campaigns[created.campaign_id] = created;
      state.campaignsByProject[projectId] = [
        ...(state.campaignsByProject[projectId] ?? []),
        created,
      ];
      state.tasksByCampaign[created.campaign_id] ??= [];
      return jsonResponse(created, { status: 201 });
    }

    const campaignMatch = url.match(/^\/v1\/gold-lab\/campaigns\/([^/?]+)$/);
    if (campaignMatch && method === "GET") {
      const campaign = state.campaigns[campaignMatch[1]];
      if (!campaign) {
        return errorResponse("gold_campaign_unknown", "missing", 404);
      }
      return jsonResponse(campaign);
    }

    const closeMatch = url.match(
      /^\/v1\/gold-lab\/campaigns\/([^/?]+)\/close$/,
    );
    if (closeMatch && method === "POST") {
      expect(call.body == null || call.body === "").toBe(true);
      expect(call.headers.get("Idempotency-Key")).toBeNull();
      const campaign = state.campaigns[closeMatch[1]];
      if (!campaign) {
        return errorResponse("gold_campaign_unknown", "missing", 404);
      }
      const closed = { ...campaign, status: "closed" as const };
      state.campaigns[closeMatch[1]] = closed;
      const list = state.campaignsByProject[closed.project_id] ?? [];
      state.campaignsByProject[closed.project_id] = list.map((item) =>
        item.campaign_id === closed.campaign_id ? closed : item,
      );
      return jsonResponse(closed);
    }

    const tasksMatch = url.match(
      /^\/v1\/gold-lab\/campaigns\/([^/?]+)\/tasks(?:\?(.*))?$/,
    );
    if (tasksMatch && method === "GET") {
      const campaignId = tasksMatch[1];
      if (url.includes(`/tasks/`)) {
        throw new Error(`Unexpected task-detail GET: ${url}`);
      }
      return jsonResponse({
        campaign_id: campaignId,
        tasks: state.tasksByCampaign[campaignId] ?? [],
      });
    }

    if (url.includes("/v1/gold-lab/")) {
      throw new Error(`Unexpected Gold Lab call: ${method} ${url}`);
    }

    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });

  return { mock, state };
}

describe("16G-I1 navigation and routing", () => {
  it("exposes Gold Lab nav and preserves existing items including mobile menu", async () => {
    const user = userEvent.setup();
    const { mock } = installGoldLabMocks();
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /^Overview$/i })).toBeTruthy();
    expect(
      within(nav).getByRole("link", { name: /^Workspaces$/i }),
    ).toBeTruthy();
    expect(within(nav).getByRole("link", { name: /^Gold Lab$/i })).toBeTruthy();
    expect(
      within(nav).getByRole("link", { name: /^Engineering$/i }),
    ).toBeTruthy();
    expect(within(nav).getByRole("link", { name: /^Settings$/i })).toBeTruthy();

    await user.click(within(nav).getByRole("link", { name: /^Gold Lab$/i }));
    expect(
      await screen.findByRole("heading", { name: "Gold Lab" }),
    ).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Menu" });
    await user.click(toggle);
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass(
      "open",
    );
    assertNoForbiddenCalls(mock.calls);
    mock.restore();
  });

  it("renders project and campaign routes and unknown Gold routes 404", async () => {
    const project = goldProject({ project_id: "proj_1" });
    const campaign = goldCampaign({
      campaign_id: "camp_1",
      project_id: "proj_1",
    });
    const { mock } = installGoldLabMocks({
      projects: [project],
      campaigns: { camp_1: campaign },
      campaignsByProject: { proj_1: [campaign] },
      baselinesByProject: { proj_1: [goldBaseline({ authoring_run_id: "run_1" })] },
      tasksByCampaign: { camp_1: [] },
    });

    renderApp("/gold-lab/projects/proj_1");
    expect(
      await screen.findByRole("heading", { name: "Gold Bench" }),
    ).toBeInTheDocument();
    mock.restore();
    cleanup();

    const again = installGoldLabMocks({
      projects: [project],
      campaigns: { camp_1: campaign },
      campaignsByProject: { proj_1: [campaign] },
      tasksByCampaign: { camp_1: [] },
    });
    renderApp("/gold-lab/campaigns/camp_1");
    expect(
      await screen.findByRole("heading", { name: "Campaign" }),
    ).toBeInTheDocument();
    again.mock.restore();
    cleanup();

    const unknown = installGoldLabMocks();
    renderApp("/gold-lab/campaigns/camp_1/work");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    assertNoForbiddenCalls(unknown.mock.calls);
    unknown.mock.restore();
  });
});

describe("16G-I1 project list and create", () => {
  it("shows empty state and distinguishes project types/status", async () => {
    const { mock } = installGoldLabMocks({
      projects: [
        goldProject({
          project_id: "p1",
          title: "Bench A",
          project_type: "benchmark",
          status: "active",
        }),
        goldProject({
          project_id: "p2",
          title: "Improve B",
          project_type: "improvement",
          status: "archived",
        }),
      ],
    });
    renderApp("/gold-lab");
    expect(await screen.findByText("Bench A")).toBeInTheDocument();
    expect(screen.getByText("Improve B")).toBeInTheDocument();
    expect(screen.getAllByText("Benchmark").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Improvement").length).toBeGreaterThan(0);
    expect(screen.getByText("Archived")).toBeInTheDocument();
    mock.restore();
    cleanup();

    const empty = installGoldLabMocks({ projects: [] });
    renderApp("/gold-lab");
    expect(
      await screen.findByRole("heading", { name: "No Gold projects yet" }),
    ).toBeInTheDocument();
    empty.mock.restore();
  });

  it("creates a project with exact payload and navigates", async () => {
    const user = userEvent.setup();
    const { mock } = installGoldLabMocks({
      workspaces: [usableWorkspace()],
      projects: [],
    });
    renderApp("/gold-lab");
    await screen.findByLabelText("Workspace");
    await user.selectOptions(screen.getByLabelText("Workspace"), "ws_1");
    await user.type(screen.getByLabelText("Title"), "New Gold");
    await user.type(screen.getByLabelText("Description"), "Desc");
    await user.click(screen.getByLabelText(/Improvement/i));
    await user.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "New Gold" }),
      ).toBeInTheDocument();
    });

    const createCall = mock.calls.find(
      (call) => call.url === "/v1/gold-lab/projects" && call.method === "POST",
    );
    expect(createCall).toBeTruthy();
    expect(JSON.parse(String(createCall?.body))).toEqual({
      workspace_id: "ws_1",
      title: "New Gold",
      description: "Desc",
      project_type: "improvement",
    });
    expect(createCall?.headers.get("Idempotency-Key")).toBeNull();
    assertNoForbiddenCalls(mock.calls);
    mock.restore();
  });

  it("surfaces create errors visibly", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([usableWorkspace()]);
      if (call.url === "/v1/gold-lab/projects" && call.method === "GET") {
        return jsonResponse({ projects: [] });
      }
      if (call.url === "/v1/gold-lab/projects" && call.method === "POST") {
        return errorResponse("request_invalid", "bad", 400);
      }
      return jsonResponse({ error: { code: "not_found", message: "x" } }, { status: 404 });
    });
    renderApp("/gold-lab");
    await user.selectOptions(await screen.findByLabelText("Workspace"), "ws_1");
    await user.type(screen.getByLabelText("Title"), "Broken");
    await user.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Check the form fields/i,
    );
    mock.restore();
  });
});

describe("16G-I1 archive, baselines, campaign create", () => {
  it("archives with confirmation and blocks new campaigns", async () => {
    const user = userEvent.setup();
    const project = goldProject({ project_id: "proj_1" });
    const { mock } = installGoldLabMocks({
      projects: [project],
      baselinesByProject: {
        proj_1: [goldBaseline({ authoring_run_id: "run_1" })],
      },
      campaignsByProject: { proj_1: [] },
    });
    renderApp("/gold-lab/projects/proj_1");
    await screen.findByRole("heading", { name: "Gold Bench" });
    await user.click(screen.getByRole("button", { name: "Archive project" }));
    const archiveDialog = screen.getByRole("alertdialog", {
      name: /Archive this Gold project/i,
    });
    await user.click(
      within(archiveDialog).getByRole("button", { name: "Archive project" }),
    );
    await waitFor(() => {
      expect(screen.getAllByText("Archived").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByText(/New campaigns cannot be created/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create campaign" }),
    ).toBeDisabled();
    const archiveCall = mock.calls.find((call) =>
      call.url.endsWith("/archive"),
    );
    expect(archiveCall?.method).toBe("POST");
    expect(archiveCall?.url).toBe("/v1/gold-lab/projects/proj_1/archive");
    mock.restore();
  });

  it("surfaces archive conflict instead of faking success", async () => {
    const user = userEvent.setup();
    const project = goldProject({ project_id: "proj_1" });
    const { mock } = installGoldLabMocks({
      projects: [project],
      baselinesByProject: {
        proj_1: [goldBaseline({ authoring_run_id: "run_1" })],
      },
      campaignsByProject: { proj_1: [] },
      archiveConflict: true,
    });
    renderApp("/gold-lab/projects/proj_1");
    await screen.findByRole("button", { name: "Archive project" });
    await user.click(screen.getByRole("button", { name: "Archive project" }));
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Archive project",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed since/i);
    expect(screen.queryByText(/^Archived$/)).not.toBeInTheDocument();
    mock.restore();
  });

  it("renders baselines, empty baseline state, and malformed failure", async () => {
    const project = goldProject({ project_id: "proj_1" });
    const { mock } = installGoldLabMocks({
      projects: [project],
      baselinesByProject: {
        proj_1: [
          goldBaseline({
            authoring_run_id: "run_1",
            corpus_name: "Ops Corpus",
            case_count: 4,
            reviewable_case_count: 3,
            chunk_set_id: "chunkset_1",
          }),
        ],
      },
      campaignsByProject: { proj_1: [] },
    });
    renderApp("/gold-lab/projects/proj_1");
    expect(await screen.findByText("Ops Corpus")).toBeInTheDocument();
    expect(screen.getAllByText(/run_1/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/chunkset_1/).length).toBeGreaterThan(0);
    expect(screen.getByText(/4 total \/ 3 reviewable/)).toBeInTheDocument();
    mock.restore();
    cleanup();

    const empty = installGoldLabMocks({
      projects: [project],
      baselinesByProject: { proj_1: [] },
      campaignsByProject: { proj_1: [] },
    });
    renderApp("/gold-lab/projects/proj_1");
    expect(
      await screen.findByRole("heading", {
        name: "No eligible pristine authoring baselines are available for this project.",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create campaign" }),
    ).toBeDisabled();
    empty.mock.restore();
    cleanup();

    const bad = installGoldLabMocks({
      projects: [project],
      campaignsByProject: { proj_1: [] },
      malformedBaselines: true,
    });
    renderApp("/gold-lab/projects/proj_1");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    bad.mock.restore();
  });

  it("creates campaign with explicit policy and empty advanced fields", async () => {
    const user = userEvent.setup();
    const project = goldProject({ project_id: "proj_1" });
    const { mock } = installGoldLabMocks({
      projects: [project],
      baselinesByProject: {
        proj_1: [goldBaseline({ authoring_run_id: "run_1" })],
      },
      campaignsByProject: { proj_1: [] },
    });
    renderApp("/gold-lab/projects/proj_1");
    const baselineSelect = await screen.findByLabelText("Eligible baseline");
    await waitFor(() => {
      expect(
        within(baselineSelect).getByRole("option", { name: /run_1/ }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(baselineSelect, "run_1");
    await user.type(
      screen.getByLabelText("Selection policy ID"),
      "my_explicit_policy",
    );
    await user.click(screen.getByRole("button", { name: "Create campaign" }));
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Campaign" }),
      ).toBeInTheDocument();
    });
    const createCall = mock.calls.find(
      (call) =>
        call.url === "/v1/gold-lab/projects/proj_1/campaigns" &&
        call.method === "POST",
    );
    expect(JSON.parse(String(createCall?.body))).toEqual({
      baseline_authoring_run_id: "run_1",
      selection_policy_id: "my_explicit_policy",
      selection_policy_parameters: {},
      hard_calls: [],
    });
    assertNoForbiddenCalls(mock.calls);
    mock.restore();
  });
});

describe("16G-I1 campaign shell, close, session, scientific boundary", () => {
  it("shows binding fields, closes with confirmation, and disables preparation", async () => {
    const user = userEvent.setup();
    const campaign = goldCampaign({
      campaign_id: "camp_1",
      project_id: "proj_1",
      corpus_name: "Ops Corpus",
      baseline_authoring_run_id: "run_1",
      snapshot_id: "snap_1",
      chunk_set_id: "chunkset_1",
      workspace_revision_at_creation: 7,
    });
    const tasks = [
      goldTask({ task_id: "t1", case_id: "case_a", state: "pending" }),
      goldTask({
        task_id: "t2",
        case_id: "case_b",
        state: "completed",
        active: true,
      }),
      goldTask({ task_id: "t3", case_id: "case_a", state: "pending" }),
    ];
    const { mock } = installGoldLabMocks({
      projects: [goldProject({ project_id: "proj_1" })],
      campaigns: { camp_1: campaign },
      campaignsByProject: { proj_1: [campaign] },
      tasksByCampaign: { camp_1: tasks },
    });
    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByText("Ops Corpus")).toBeInTheDocument();
    expect(screen.getAllByText("run_1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Open").length).toBeGreaterThan(0);
    expect(screen.queryByText(/prelabel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/retrieval rank/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/model confidence/i)).not.toBeInTheDocument();

    expect(await screen.findByText("t1")).toBeInTheDocument();
    const taskList = screen.getByRole("list");
    const taskItems = within(taskList).getAllByRole("listitem");
    expect(taskItems[0]?.textContent).toContain("t1");
    expect(taskItems[1]?.textContent).toContain("t2");
    expect(taskItems[2]?.textContent).toContain("t3");

    await user.click(screen.getByRole("button", { name: "Close campaign" }));
    expect(
      screen.getByRole("alertdialog", { name: /Close this campaign/i }),
    ).toBeInTheDocument();
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Close campaign",
      }),
    );
    await waitFor(() => {
      expect(
        screen.getByText(/new expert-session preparation is disabled/i),
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /reopen/i })).toBeNull();
    expect(screen.getByRole("button", { name: "Prepare session" })).toBeDisabled();
    expect(
      mock.calls.some(
        (call) =>
          call.url === "/v1/gold-lab/campaigns/camp_1/close" &&
          call.method === "POST",
      ),
    ).toBe(true);
    expect(
      mock.calls.some((call) => call.url.includes("/tasks/") && call.method === "GET"),
    ).toBe(false);
    assertNoForbiddenCalls(mock.calls);
    mock.restore();
  });

  it("supports game/workload selection, until-stop omission, and prepare boundary", async () => {
    const user = userEvent.setup();
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const tasks = [
      goldTask({ task_id: "t1", case_id: "case_a", state: "pending" }),
      goldTask({ task_id: "t2", case_id: "case_b", state: "pending" }),
    ];
    const { mock } = installGoldLabMocks({
      campaigns: { camp_1: campaign },
      campaignsByProject: { proj_1: [campaign] },
      tasksByCampaign: { camp_1: tasks },
    });
    renderApp("/gold-lab/campaigns/camp_1");
    await screen.findByRole("heading", { name: "Session configuration" });

    await user.click(screen.getByLabelText("Evidence Sweep"));
    await user.click(screen.getByLabelText("5"));
    await user.click(screen.getByRole("button", { name: "Prepare session" }));
    expect(
      await screen.findByText(
        /Session configuration is ready\. Expert task execution is not available in this build\./,
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByLabelText("Until stop"));
    await user.click(screen.getByLabelText("Complete case"));
    await user.selectOptions(screen.getByLabelText("Case"), "case_b");

    expect(screen.getByLabelText("Rapid Fire")).toBeInTheDocument();
    expect(screen.getByLabelText("Question Check")).toBeInTheDocument();
    expect(screen.getByLabelText("Chunk Duel")).toBeInTheDocument();
    expect(screen.getByLabelText("1")).toBeInTheDocument();
    expect(screen.getByLabelText("10")).toBeInTheDocument();
    expect(screen.getByLabelText("25")).toBeInTheDocument();

    assertNoForbiddenCalls(mock.calls);
    expect(
      mock.calls.filter((call) =>
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks"),
      ).length,
    ).toBeGreaterThan(0);
    expect(
      mock.calls.some((call) => /\/tasks\/[^/?]+$/.test(call.url.split("?")[0])),
    ).toBe(false);
    mock.restore();
  });

  it("shows truthful empty task list and no fabricated Gold data", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const { mock } = installGoldLabMocks({
      campaigns: { camp_1: campaign },
      tasksByCampaign: { camp_1: [] },
    });
    renderApp("/gold-lab/campaigns/camp_1");
    expect(
      await screen.findByRole("heading", { name: "No tasks yet." }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
    assertNoForbiddenCalls(mock.calls);
    mock.restore();
  });

  it("keeps project type, game, and workload controls labeled with alert semantics", async () => {
    const user = userEvent.setup();
    const { mock } = installGoldLabMocks({
      workspaces: [usableWorkspace()],
    });
    renderApp("/gold-lab");
    expect(await screen.findByLabelText(/Benchmark/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Improvement/i)).toBeInTheDocument();

    const campaign = goldCampaign({ campaign_id: "camp_1" });
    mock.restore();
    const next = installGoldLabMocks({
      campaigns: { camp_1: campaign },
      tasksByCampaign: {
        camp_1: [goldTask({ task_id: "t1", state: "pending" })],
      },
    });
    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByLabelText("Rapid Fire")).toBeInTheDocument();
    expect(screen.getByLabelText("Until stop")).toBeInTheDocument();
    await user.tab();
    expect(document.activeElement).not.toBe(document.body);
    next.mock.restore();
  });
});

describe("16G-I1 validation helpers", () => {
  it("fails closed on malformed product DTOs", () => {
    expect(() =>
      validateGoldProjectListResponse({ projects: [{ project_id: "x" }] }),
    ).toThrow(/missing workspace_id/i);
    expect(() =>
      validateGoldBaselineListResponse(
        { project_id: "p1", baselines: [{ authoring_run_id: "r" }] },
        "p1",
      ),
    ).toThrow(/invalid created_at|missing/i);
    expect(() =>
      validateGoldTaskListResponse(
        {
          campaign_id: "c1",
          tasks: [
            {
              task_id: "t1",
              task_kind: "absolute_relevance",
              campaign_id: "other",
              case_id: "case",
              active: true,
              state: "pending",
              candidate_chunk_id: null,
              effective_query: null,
            },
          ],
        },
        "c1",
      ),
    ).toThrow(/different campaign/i);
  });
});
