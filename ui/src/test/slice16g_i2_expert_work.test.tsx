import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
} from "../features/goldLab/policy/presentations";
import { GoldWorkSession } from "../features/goldLab/work/GoldWorkSession";
import {
  goldCampaign,
  goldTask,
} from "./goldLabFixtures";
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type FetchCall,
} from "./mockApi";
import { renderApp, renderWithProviders } from "./render";

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

function receipt(partial: Record<string, unknown> = {}) {
  return {
    campaign_id: "camp_1",
    record_id: "rec_1",
    judgment_id: "jud_1",
    task_id: "t1",
    record_type: "absolute_relevance",
    sequence: 1,
    created_at: "2026-03-03T00:00:00Z",
    replayed: false,
    ...partial,
  };
}

const FORBIDDEN = [
  "/preferences",
  "/contribution",
  "/export",
  "/registrations",
  "/training-package",
  "/data",
];

function assertNoForbidden(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN) {
      expect(call.url).not.toContain(fragment);
    }
  }
}

describe("16G-I2 production work route policy gate", () => {
  it("refuses unapproved Rapid Fire and Question Check without task-detail GETs", async () => {
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
    expect(
      mock.calls.some((call) => /\/tasks\//.test(call.url)),
    ).toBe(false);

    cleanup();
    mock.restore();

    const mock2 = installFetchMock(async (call) => {
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
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=question_check&workload=1",
    );
    expect(
      await screen.findByText(
        /This presentation is not approved for production Gold Mode/,
      ),
    ).toBeInTheDocument();
    expect(
      mock2.calls.some((call) => call.method === "POST"),
    ).toBe(false);
    mock2.restore();
  });

  it("shows unavailable state for Evidence Sweep / Chunk Duel without mutations", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/gold-lab/campaigns/camp_1/work?game=evidence_sweep");
    expect(
      await screen.findByText(
        /This game is not available in the current Gold Lab build/,
      ),
    ).toBeInTheDocument();
    assertNoForbidden(mock.calls);
    mock.restore();
  });
});

describe("16G-I2 Rapid Fire / Question Check session (direct work session)", () => {
  it("commits Rapid Fire with exact body, ids, idempotency, and frozen cohort", async () => {
    const user = userEvent.setup();
    const tasks = [
      goldTask({ task_id: "t1", state: "pending" }),
      goldTask({ task_id: "t2", state: "pending" }),
      goldTask({ task_id: "t3", state: "pending" }),
      goldTask({ task_id: "t4", state: "pending" }),
      goldTask({ task_id: "t5", state: "pending" }),
      goldTask({ task_id: "t6", state: "pending" }),
    ];
    let pendingIds = tasks.map((task) => task.task_id);
    let detail = absoluteDetail("t1");
    let postCount = 0;

    const mock = installFetchMock(async (call) => {
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: pendingIds.map((id) =>
            goldTask({ task_id: id, state: "pending" }),
          ),
        });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        return jsonResponse({
          ...detail,
          task_id: detailMatch[1],
          current_result:
            detail.task_id === detailMatch[1] ? detail.current_result : null,
        });
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        postCount += 1;
        const body = JSON.parse(String(call.body));
        expect(body).toEqual({
          relevance: 2,
          game_id: RAPID_FIRE_GAME_ID,
          presentation_id: RAPID_FIRE_PRESENTATION_ID,
        });
        expect(body).not.toHaveProperty("supersedes_judgment_id");
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        pendingIds = pendingIds.filter((id) => id !== "t1");
        detail = {
          ...absoluteDetail("t1", {
            state: "completed",
            current_result: { kind: "absolute_relevance", relevance: 2 },
          }),
        };
        return jsonResponse(receipt({ task_id: "t1", replayed: postCount > 1 }));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="rapid_fire"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=rapid_fire&workload=5&task=t1" },
    );

    expect(await screen.findByText("What pressure?")).toBeInTheDocument();
    expect(screen.getByText(/Pump pressure must remain stable/)).toBeInTheDocument();
    expect(screen.getByText(/0 — Irrelevant/)).toBeInTheDocument();
    expect(screen.queryByText(/prelabel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/model confidence/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /2 — Direct evidence/ }));
    expect(await screen.findByText(/Judgment recorded|Previous commit/)).toBeInTheDocument();
    expect(postCount).toBe(1);

    await user.click(screen.getByRole("button", { name: "Next task" }));
    await waitFor(() => {
      expect(
        mock.calls.some(
          (call) =>
            call.url === "/v1/gold-lab/campaigns/camp_1/tasks/t2" &&
            call.method === "GET",
        ),
      ).toBe(true);
    });
    expect(
      mock.calls.some((call) => call.url.endsWith("/tasks/t6")),
    ).toBe(false);

    assertNoForbidden(mock.calls);
    mock.restore();
  });

  it("retries ambiguous Rapid Fire with the same key/body and corrects with a new key", async () => {
    const user = userEvent.setup();
    let failOnce = true;
    const keys: string[] = [];
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [goldTask({ task_id: "t1", state: "pending" })],
        });
      }
      if (call.url.endsWith("/tasks/t1") && call.method === "GET") {
        return jsonResponse(absoluteDetail("t1"));
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        keys.push(call.headers.get("Idempotency-Key") ?? "");
        if (failOnce) {
          failOnce = false;
          throw new TypeError("network down");
        }
        return jsonResponse(receipt({ replayed: keys.length > 1 }));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    // Wrap fetch throw into network_error via apiRequest - TypeError from handler
    // installFetchMock awaits handler - if handler throws, fetch rejects → network_error
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="rapid_fire"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=rapid_fire&workload=1&task=t1" },
    );
    await screen.findByText("What pressure?");
    await user.click(screen.getByRole("button", { name: /1 — Supporting/ }));
    expect(await screen.findByRole("button", { name: "Retry same commit" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry same commit" }));
    expect(
      await screen.findByRole("button", { name: "Correct judgment" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/Previous commit confirmed|Judgment recorded/).length,
    ).toBeGreaterThan(0);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);

    await user.click(screen.getByRole("button", { name: "Correct judgment" }));
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/ }));
    await waitFor(() => expect(keys.length).toBe(3));
    expect(keys[2]).not.toBe(keys[0]);
    mock.restore();
  });

  it("supports keyboard 0/1/2 for Rapid Fire", async () => {
    const user = userEvent.setup();
    const bodies: unknown[] = [];
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [goldTask({ task_id: "t1", state: "pending" })],
        });
      }
      if (call.url.endsWith("/tasks/t1") && call.method === "GET") {
        return jsonResponse(absoluteDetail("t1"));
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        bodies.push(JSON.parse(String(call.body)));
        return jsonResponse(receipt());
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="rapid_fire"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=rapid_fire&workload=1" },
    );
    await screen.findByRole("heading", { name: "Rapid Fire" });
    await user.keyboard("0");
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ relevance: 0 });
    mock.restore();
  });

  it("posts exact Question Check accept/reject/edit bodies", async () => {
    const user = userEvent.setup();
    const posts: Array<{ url: string; body: Record<string, unknown>; key: string | null }> =
      [];
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [
            goldTask({
              task_id: "q1",
              task_kind: "question_check",
              state: "pending",
            }),
          ],
        });
      }
      if (call.url.endsWith("/tasks/q1") && call.method === "GET") {
        return jsonResponse(questionDetail("q1"));
      }
      if (call.url.endsWith("/question-check") && call.method === "POST") {
        const body = JSON.parse(String(call.body)) as Record<string, unknown>;
        posts.push({
          url: call.url,
          body,
          key: call.headers.get("Idempotency-Key"),
        });
        return jsonResponse(
          receipt({
            task_id: "q1",
            record_type: "question_check",
          }),
        );
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="question_check"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=question_check&workload=1&task=q1" },
    );
    expect(await screen.findByText("Proposed question?")).toBeInTheDocument();
    expect(screen.getByText(/Ops Manual/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Accept" }));
    await screen.findByRole("button", { name: "Correct judgment" });
    expect(posts[0]?.body).toEqual({
      decision: "accept",
      game_id: QUESTION_CHECK_GAME_ID,
      presentation_id: QUESTION_CHECK_PRESENTATION_ID,
    });
    expect(posts[0]?.body).not.toHaveProperty("effective_query");
    expect(posts[0]?.key).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Correct judgment" }));
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await screen.findByRole("button", { name: "Correct judgment" });
    expect(posts[1]?.body).toEqual({
      decision: "reject",
      game_id: QUESTION_CHECK_GAME_ID,
      presentation_id: QUESTION_CHECK_PRESENTATION_ID,
    });
    expect(posts[1]?.body).not.toHaveProperty("effective_tags");
    expect(posts[1]?.key).not.toBe(posts[0]?.key);

    await user.click(screen.getByRole("button", { name: "Correct judgment" }));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const query = screen.getByLabelText("Effective query");
    await user.clear(query);
    await user.type(query, "Edited question");
    await user.click(screen.getByRole("button", { name: "Submit edit" }));
    await waitFor(() => expect(posts.length).toBe(3));
    expect(posts[2]?.body).toEqual({
      decision: "edit",
      effective_query: "Edited question",
      effective_category: "ops",
      effective_tags: ["tag-a"],
      game_id: QUESTION_CHECK_GAME_ID,
      presentation_id: QUESTION_CHECK_PRESENTATION_ID,
    });
    assertNoForbidden(mock.calls);
    mock.restore();
  });

  it("handles null Question Check source truthfully", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [
            goldTask({
              task_id: "q1",
              task_kind: "question_check",
              state: "pending",
            }),
          ],
        });
      }
      if (call.url.endsWith("/tasks/q1")) {
        return jsonResponse(
          questionDetail("q1", {
            presentation: {
              kind: "question_check",
              proposed_query: "No seed?",
              proposed_category: null,
              proposed_tags: [],
              source: null,
            },
          }),
        );
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="question_check"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=question_check&workload=1" },
    );
    expect(
      await screen.findByText(
        "No source seed is available for this question.",
      ),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("surfaces no-op edit backend failures safely", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [
            goldTask({
              task_id: "q1",
              task_kind: "question_check",
              state: "pending",
            }),
          ],
        });
      }
      if (call.url.endsWith("/tasks/q1")) {
        return jsonResponse(questionDetail("q1"));
      }
      if (call.url.endsWith("/question-check")) {
        return errorResponse("request_invalid", "question_check_edit_not_semantic", 422);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="question_check"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=question_check&workload=1" },
    );
    await screen.findByText("Proposed question?");
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getByLabelText("Effective query"), " changed");
    await user.click(screen.getByRole("button", { name: "Submit edit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Check the form fields/i,
    );
    mock.restore();
  });
});
