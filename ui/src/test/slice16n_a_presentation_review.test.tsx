import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  APPROVED_PRESENTATIONS_V1,
} from "../features/goldLab/policy/approvedPresentations.v1";
import { goldCampaign, goldTask } from "./goldLabFixtures";
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

const source = {
  chunk_id: "chunk_1",
  document_id: "doc_1",
  document_title: "Ops Manual",
  source_name: "ops.pdf",
  section_path: ["Start"],
  page_start: 2,
  page_end: 2,
  line_start: 1,
  line_end: 4,
  content_type: "text/plain",
  text: "Pump pressure must remain stable.",
};

function questionDetail(taskId: string, overrides: Record<string, unknown> = {}) {
  return {
    task_id: taskId,
    task_kind: "question_check",
    campaign_id: "camp_1",
    case_id: "case_q",
    active: true,
    state: "pending",
    candidate_chunk_id: null,
    effective_query: null,
    presentation: {
      kind: "question_check",
      proposed_query: "Proposed question?",
      proposed_category: "ops",
      proposed_tags: ["tag-a"],
      source,
    },
    current_result: null,
    ...overrides,
  };
}

function absoluteDetail(taskId: string, overrides: Record<string, unknown> = {}) {
  return {
    task_id: taskId,
    task_kind: "absolute_relevance",
    campaign_id: "camp_1",
    case_id: "case_a",
    active: true,
    state: "pending",
    candidate_chunk_id: "chunk_1",
    effective_query: "What pressure?",
    presentation: {
      kind: "absolute_relevance",
      effective_query: "What pressure?",
      effective_category: "ops",
      effective_tags: ["pump"],
      candidate: source,
    },
    current_result: null,
    ...overrides,
  };
}

function assertNoGoldMutationPosts(calls: FetchCall[]) {
  for (const call of calls) {
    if (call.method === "GET" || call.method === "HEAD") continue;
    if (call.url === "/health/ready") continue;
    expect(call.method).not.toMatch(/POST|PUT|PATCH|DELETE/i);
    expect(call.url).not.toMatch(
      /question-check|\/relevance|\/preference|\/contribution|\/export/,
    );
  }
}

function installCampaignReads(options: {
  qcTasks?: ReturnType<typeof goldTask>[];
  arTasks?: ReturnType<typeof goldTask>[];
  qcDetail?: Record<string, unknown> | null;
  arDetail?: Record<string, unknown> | null;
}) {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  const qcTasks =
    options.qcTasks ??
    [
      goldTask({
        task_id: "qc_1",
        task_kind: "question_check",
        case_id: "case_q",
        active: true,
        state: "pending",
        candidate_chunk_id: null,
      }),
    ];
  const arTasks = options.arTasks ?? [];

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
      const url = new URL(call.url, "http://local.test");
      const kind = url.searchParams.get("kind");
      if (kind === "question_check") {
        return jsonResponse({ campaign_id: "camp_1", tasks: qcTasks });
      }
      if (kind === "absolute_relevance") {
        return jsonResponse({ campaign_id: "camp_1", tasks: arTasks });
      }
      return jsonResponse({
        campaign_id: "camp_1",
        tasks: [...qcTasks, ...arTasks],
      });
    }
    if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/qc_1") {
      if (options.qcDetail === null) {
        return jsonResponse(
          { error: { code: "not_found", message: "missing" } },
          { status: 404 },
        );
      }
      return jsonResponse(options.qcDetail ?? questionDetail("qc_1"));
    }
    if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/ar_1") {
      if (options.arDetail === null) {
        return jsonResponse(
          { error: { code: "not_found", message: "missing" } },
          { status: 404 },
        );
      }
      return jsonResponse(options.arDetail ?? absoluteDetail("ar_1"));
    }
    if (call.method !== "GET") {
      throw new Error(`Unexpected mutation during preview: ${call.method} ${call.url}`);
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

describe("16N-A Presentation Review", () => {
  it("keeps Advanced collapsed and links Presentation review underneath", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({});
    renderApp("/gold-lab/campaigns/camp_1");

    const advanced = await screen.findByTestId("campaign-advanced");
    expect(advanced).toBeInstanceOf(HTMLDetailsElement);
    expect((advanced as HTMLDetailsElement).open).toBe(false);

    await user.click(within(advanced).getByText("Advanced"));
    expect((advanced as HTMLDetailsElement).open).toBe(true);
    expect(
      await screen.findByRole("link", { name: /Open presentation review/i }),
    ).toHaveAttribute(
      "href",
      "/gold-lab/campaigns/camp_1/presentation-review",
    );
    mock.restore();
  });

  it("loads dedicated presentation-review route with QC real task detail", async () => {
    const mock = installCampaignReads({});
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");

    expect(
      await screen.findByTestId("presentation-review-page"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Preview only — responses here do not change Gold/i),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("question-check-presentation"),
    ).toBeInTheDocument();
    expect(screen.getByText("Proposed question?")).toBeInTheDocument();
    expect(
      mock.calls.some((c) => c.url.includes("/tasks?") && c.url.includes("question_check")),
    ).toBe(true);
    expect(
      mock.calls.some((c) => c.url.endsWith("/tasks/qc_1")),
    ).toBe(true);
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("records QC Accept/Edit/Reject locally with zero mutation POSTs", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({});
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("question-check-presentation");

    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    expect(
      await screen.findByText(/Preview response recorded locally/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /accept/i,
    );
    assertNoGoldMutationPosts(mock.calls);

    await user.click(
      screen.getByRole("button", { name: /Change preview response/i }),
    );
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));
    await user.clear(screen.getByLabelText(/Effective query/i));
    await user.type(screen.getByLabelText(/Effective query/i), "Edited query?");
    await user.click(screen.getByRole("button", { name: /Submit edit/i }));
    expect(
      await screen.findByText(/Preview response recorded locally/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /edit/i,
    );
    assertNoGoldMutationPosts(mock.calls);

    await user.click(
      screen.getByRole("button", { name: /Change preview response/i }),
    );
    await user.click(screen.getByRole("button", { name: /^Reject$/i }));
    expect(
      await screen.findByText(/Preview response recorded locally/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /reject/i,
    );
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("shows Rapid Fire prerequisite when no active AR tasks exist", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({ arTasks: [] });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    expect(
      await screen.findByTestId("rf-preview-unavailable"),
    ).toHaveTextContent(/Rapid Fire preview is not available yet/i);
    expect(
      mock.calls.some((c) => c.url.includes("absolute_relevance")),
    ).toBe(true);
    expect(
      mock.calls.some((c) => /\/tasks\/ar_/.test(c.url)),
    ).toBe(false);
    assertNoGoldMutationPosts(mock.calls);

    // Switching from QC default also works via button.
    cleanup();
    mock.restore();
    const mock2 = installCampaignReads({ arTasks: [] });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("qc-preview-session");
    await user.click(screen.getByRole("button", { name: /^Rapid Fire$/i }));
    expect(
      await screen.findByTestId("rf-preview-unavailable"),
    ).toBeInTheDocument();
    mock2.restore();
  });

  it("renders Rapid Fire from real active AR detail and records local 0/1/2", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({
      arTasks: [
        goldTask({
          task_id: "ar_1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      arDetail: absoluteDetail("ar_1"),
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    expect(
      await screen.findByTestId("rapid-fire-presentation"),
    ).toBeInTheDocument();
    expect(screen.getByText("What pressure?")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /0 — Irrelevant/i }),
    );
    expect(
      await screen.findByText(/Preview response recorded locally/i),
    ).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      "0",
    );
    assertNoGoldMutationPosts(mock.calls);

    await user.click(
      screen.getByRole("button", { name: /Change preview response/i }),
    );
    await user.click(
      screen.getByRole("button", { name: /1 — Supporting evidence/i }),
    );
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      "1",
    );
    await user.click(
      screen.getByRole("button", { name: /Change preview response/i }),
    );
    await user.click(
      screen.getByRole("button", { name: /2 — Direct evidence/i }),
    );
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      "2",
    );
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("loses preview response state on remount", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({});
    const first = renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("question-check-presentation");
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    expect(
      await screen.findByText(/Preview response recorded locally/i),
    ).toBeInTheDocument();
    first.unmount();
    cleanup();

    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("question-check-presentation");
    expect(
      screen.queryByText(/Preview response recorded locally/i),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("preserves unapproved /work refusal for Rapid Fire after QC-only policy", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks")) {
        throw new Error(`Unexpected task call behind policy gate: ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/work?game=rapid_fire&workload=1");
    expect(
      await screen.findByText(
        /This presentation is not approved for production Gold Mode/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("rapid-fire-presentation")).not.toBeInTheDocument();
    mock.restore();
  });

  it("keeps QC-only APPROVED_PRESENTATIONS_V1 and calibration separate", async () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([
      {
        game_id: "goldgame_question_check_v1",
        presentation_id: "goldpres_question_check_source_panel_v1",
        disposition: "ALLOW_PRODUCTION",
      },
    ]);

    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/registrations")) {
        return jsonResponse({ campaign_id: "camp_1", registrations: [] });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    expect(
      await screen.findByText(/No registered Gold dataset is available for calibration/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("presentation-review-page")).not.toBeInTheDocument();
    mock.restore();
  });

  it("presentationReview subtree has no mutation client imports", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const root = join(here, "../features/goldLab/presentationReview");
    const files = [
      "PresentationReviewWorkspace.tsx",
      "QuestionCheckPreviewSession.tsx",
      "RapidFirePreviewSession.tsx",
      "PreviewInteraction.ts",
      "previewTypes.ts",
      "previewEligibility.ts",
    ];
    const forbidden = [
      "submitGoldQuestionCheck",
      "submitGoldRelevance",
      "submitGoldPreference",
      "GoldMutationReceipt",
      'from "../api/client"',
      'from "../../api/client"',
      'from "../api/client.ts"',
    ];
    for (const name of files) {
      const text = readFileSync(join(root, name), "utf8");
      for (const token of forbidden) {
        expect(text, `${name} must not contain ${token}`).not.toContain(token);
      }
      expect(text).not.toMatch(/method:\s*["']POST["']/);
    }
    const page = readFileSync(
      join(here, "../pages/GoldLabPresentationReviewPage.tsx"),
      "utf8",
    );
    expect(page).toContain('from "../features/goldLab/api/readClient"');
    expect(page).not.toContain("submitGold");
  });

  it("F001: preview after-action never uses durable Gold judgment wording", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({});
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("question-check-presentation");
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    expect(
      await screen.findByText(/Preview response recorded locally\. Gold was not changed\./i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Judgment recorded\.?/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Previous commit confirmed\.?/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Correct judgment/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Change preview response/i }),
    ).toBeInTheDocument();
    mock.restore();
    cleanup();

    const mockRf = installCampaignReads({
      arTasks: [
        goldTask({
          task_id: "ar_1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      arDetail: absoluteDetail("ar_1"),
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    await screen.findByTestId("rapid-fire-presentation");
    await user.click(
      screen.getByRole("button", { name: /0 — Irrelevant/i }),
    );
    expect(
      await screen.findByText(/Preview response recorded locally\. Gold was not changed\./i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Judgment recorded\.?/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Previous commit confirmed\.?/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Correct judgment/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Change preview response/i }),
    ).toBeInTheDocument();
    mockRf.restore();
  });

  it("F002: fails closed when QC detail is completed or inactive", async () => {
    const mockCompleted = installCampaignReads({
      qcDetail: questionDetail("qc_1", {
        active: true,
        state: "completed",
        current_result: {
          kind: "question_check",
          decision: "accept",
          effective_query: "Proposed question?",
          effective_category: "ops",
          effective_tags: ["tag-a"],
        },
      }),
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    expect(await screen.findByTestId("qc-preview-stale")).toBeInTheDocument();
    expect(
      screen.queryByTestId("question-check-presentation"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Accept$/i }),
    ).not.toBeInTheDocument();
    mockCompleted.restore();
    cleanup();

    const mockInactive = installCampaignReads({
      qcDetail: questionDetail("qc_1", {
        active: false,
        state: "pending",
      }),
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    expect(await screen.findByTestId("qc-preview-stale")).toBeInTheDocument();
    expect(
      screen.queryByTestId("question-check-presentation"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Accept$/i }),
    ).not.toBeInTheDocument();
    mockInactive.restore();
  });

  it("F002: fails closed when RF detail is completed after pending list", async () => {
    const mock = installCampaignReads({
      arTasks: [
        goldTask({
          task_id: "ar_1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      arDetail: absoluteDetail("ar_1", {
        active: true,
        state: "completed",
        current_result: {
          kind: "absolute_relevance",
          relevance: 2,
        },
      }),
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    expect(await screen.findByTestId("rf-preview-stale")).toBeInTheDocument();
    expect(
      screen.queryByTestId("rapid-fire-presentation"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /0 — Irrelevant/i }),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("F003: presentation selector uses button-group pressed semantics", async () => {
    const user = userEvent.setup();
    const mock = installCampaignReads({ arTasks: [] });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByTestId("qc-preview-session");

    const group = screen.getByRole("group", {
      name: /Presentation review targets/i,
    });
    expect(group).not.toHaveAttribute("role", "tablist");
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();

    const qc = screen.getByRole("button", { name: /^Question Check$/i });
    const rf = screen.getByRole("button", { name: /^Rapid Fire$/i });
    expect(qc).toHaveAttribute("aria-pressed", "true");
    expect(rf).toHaveAttribute("aria-pressed", "false");
    expect(qc).not.toHaveAttribute("aria-selected");
    expect(rf).not.toHaveAttribute("aria-selected");

    await user.click(rf);
    expect(await screen.findByTestId("rf-preview-unavailable")).toBeInTheDocument();
    expect(qc).toHaveAttribute("aria-pressed", "false");
    expect(rf).toHaveAttribute("aria-pressed", "true");

    await user.keyboard("{Tab}");
    mock.restore();
  });
});
