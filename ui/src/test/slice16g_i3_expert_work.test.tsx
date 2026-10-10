import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
} from "../features/goldLab/policy/presentations";
import { CHUNK_DUEL_AUXILIARY_MESSAGE } from "../features/goldLab/games/chunkDuel/ChunkDuelGame";
import { ChunkDuelWorkSession } from "../features/goldLab/work/ChunkDuelWorkSession";
import { EvidenceSweepWorkSession } from "../features/goldLab/work/EvidenceSweepWorkSession";
import { goldCampaign, goldTask } from "./goldLabFixtures";
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

function source(chunkId: string, text: string) {
  return {
    chunk_id: chunkId,
    document_id: "doc_1",
    document_title: "Ops Manual",
    source_name: "ops.pdf",
    section_path: ["Start"],
    page_start: 2,
    page_end: 2,
    line_start: 1,
    line_end: 4,
    content_type: "text/plain",
    text,
  };
}

function absoluteDetail(
  taskId: string,
  chunkId: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    task_id: taskId,
    task_kind: "absolute_relevance",
    campaign_id: "camp_1",
    case_id: "case_a",
    active: true,
    state: "pending",
    candidate_chunk_id: chunkId,
    effective_query: "What pressure?",
    presentation: {
      kind: "absolute_relevance",
      effective_query: "What pressure?",
      effective_category: "ops",
      effective_tags: ["pump"],
      candidate: source(chunkId, `Text for ${chunkId}`),
    },
    current_result: null,
    ...overrides,
  };
}

function relevanceReceipt(taskId: string, partial: Record<string, unknown> = {}) {
  return {
    campaign_id: "camp_1",
    record_id: `rec_${taskId}`,
    judgment_id: `jud_${taskId}`,
    task_id: taskId,
    record_type: "absolute_relevance",
    sequence: 1,
    created_at: "2026-03-03T00:00:00Z",
    replayed: false,
    ...partial,
  };
}

function preferenceReceipt(partial: Record<string, unknown> = {}) {
  return {
    campaign_id: "camp_1",
    record_id: "rec_pref_1",
    judgment_id: "jud_pref_1",
    task_id: "aux_pref_server_1",
    record_type: "auxiliary_preference",
    sequence: 3,
    created_at: "2026-03-03T00:00:00Z",
    replayed: false,
    ...partial,
  };
}

describe("16G-I3 production work route policy gate", () => {
  it("denies Evidence Sweep and Chunk Duel before task/detail/mutation calls", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    for (const game of ["evidence_sweep", "chunk_duel"] as const) {
      const mock = installFetchMock(async (call) => {
        if (call.url === "/health/ready") {
          return jsonResponse({ status: "ready" });
        }
        if (call.url === "/v1/workspaces") return jsonResponse([]);
        if (call.url === "/v1/gold-lab/campaigns/camp_1") {
          return jsonResponse(campaign);
        }
        if (
          call.url.includes("/tasks") ||
          call.url.includes("/relevance") ||
          call.url.includes("/preferences")
        ) {
          throw new Error(`Unexpected call behind policy gate: ${call.url}`);
        }
        return jsonResponse(
          { error: { code: "not_found", message: "x" } },
          { status: 404 },
        );
      });
      renderApp(`/gold-lab/campaigns/camp_1/work?game=${game}&workload=5`);
      expect(
        await screen.findByText(
          /This presentation is not approved for production Gold Mode/,
        ),
      ).toBeInTheDocument();
      expect(mock.calls.some((call) => call.url.includes("/tasks"))).toBe(
        false,
      );
      expect(mock.calls.some((call) => call.method === "POST")).toBe(false);
      cleanup();
      mock.restore();
    }
  });
});

describe("16G-I3 Evidence Sweep session", () => {
  it("commits one POST per candidate with exact body and latches the batch", async () => {
    const user = userEvent.setup();
    const taskIds = ["t1", "t2", "t3", "t4", "t5", "t6"];
    let pendingIds = [...taskIds];
    const details = new Map(
      taskIds.map((id) => [id, absoluteDetail(id, `chunk_${id}`)]),
    );
    const posts: FetchCall[] = [];

    const mock = installFetchMock(async (call) => {
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: pendingIds.map((id) =>
            goldTask({
              task_id: id,
              state: "pending",
              candidate_chunk_id: `chunk_${id}`,
            }),
          ),
        });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        const id = detailMatch[1]!;
        return jsonResponse(details.get(id) ?? absoluteDetail(id, `chunk_${id}`));
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        posts.push(call);
        const taskMatch = call.url.match(/\/tasks\/([^/]+)\/relevance/);
        const taskId = taskMatch?.[1];
        if (!taskId) {
          throw new Error(`Missing task id in relevance URL: ${call.url}`);
        }
        const body = JSON.parse(String(call.body));
        expect(body).toEqual({
          relevance: expect.any(Number),
          game_id: EVIDENCE_SWEEP_GAME_ID,
          presentation_id: EVIDENCE_SWEEP_PRESENTATION_ID,
        });
        expect(body).not.toHaveProperty("case_id");
        expect(body).not.toHaveProperty("candidate_chunk_id");
        expect(body).not.toHaveProperty("rank");
        expect(body).not.toHaveProperty("score");
        expect(body).not.toHaveProperty("supersedes_judgment_id");
        expect(body).not.toHaveProperty("batch_id");
        pendingIds = pendingIds.filter((id) => id !== taskId);
        details.set(
          taskId,
          absoluteDetail(taskId, `chunk_${taskId}`, {
            state: "completed",
            current_result: {
              kind: "absolute_relevance",
              relevance: body.relevance,
            },
          }),
        );
        return jsonResponse(relevanceReceipt(taskId));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <EvidenceSweepWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/gold-lab/campaigns/camp_1/work?game=evidence_sweep&workload=10" },
    );

    expect(await screen.findByRole("heading", { name: "Evidence Sweep" })).toBeInTheDocument();
    const cards = await screen.findAllByRole("listitem");
    expect(cards).toHaveLength(5);
    expect(document.querySelector('[data-task-id="t6"]')).toBeNull();

    // Commit first card; pending refresh removes t1 but latch keeps it rendered.
    const firstCard = document.querySelector(
      '[data-task-id="t1"]',
    ) as HTMLElement;
    expect(firstCard).toBeTruthy();
    await user.click(
      within(firstCard).getByRole("button", { name: /0 — Irrelevant/ }),
    );
    expect(
      await within(firstCard).findByText(/Judgment recorded/),
    ).toBeInTheDocument();
    expect(
      within(firstCard).getByText(/Current recorded relevance: 0/),
    ).toBeInTheDocument();
    expect(document.querySelector('[data-task-id="t1"]')).toBeTruthy();
    expect(document.querySelector('[data-task-id="t6"]')).toBeNull();

    // Partial: other cards still pending and actionable.
    const secondCard = document.querySelector(
      '[data-task-id="t2"]',
    ) as HTMLElement;
    await user.click(
      within(secondCard).getByRole("button", {
        name: /2 — Direct evidence/,
      }),
    );
    await within(secondCard).findByText(/Judgment recorded/);
    expect(posts).toHaveLength(2);
    expect(posts[0]!.url).toContain("/tasks/t1/relevance");
    expect(posts[1]!.url).toContain("/tasks/t2/relevance");

    // Blindness: no rank/score/model leakage in rendered text.
    expect(screen.queryByText(/rank/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/prelabel/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/rerank/i)).not.toBeInTheDocument();

    // Next batch disabled until all five resolve.
    expect(screen.queryByRole("button", { name: "Next batch" })).toBeNull();

    for (const id of ["t3", "t4", "t5"]) {
      const card = document.querySelector(
        `[data-task-id="${id}"]`,
      ) as HTMLElement;
      await user.click(
        within(card).getByRole("button", {
          name: /1 — Supporting evidence/,
        }),
      );
      await within(card).findByText(/Judgment recorded/);
    }

    await user.click(screen.getByRole("button", { name: "Next batch" }));
    await waitFor(() => {
      expect(document.querySelector('[data-task-id="t6"]')).toBeTruthy();
    });
    expect(document.querySelector('[data-task-id="t1"]')).toBeNull();
    expect(posts).toHaveLength(5);

    mock.restore();
  });

  it("correction uses a new key on the same latched task", async () => {
    const user = userEvent.setup();
    let pendingIds = ["t1", "t2"];
    let detail = absoluteDetail("t1", "chunk_1");
    const keys: string[] = [];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: pendingIds.map((id) =>
            goldTask({ task_id: id, candidate_chunk_id: `chunk_${id}` }),
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
          candidate_chunk_id: `chunk_${detailMatch[1]}`,
          presentation: {
            ...detail.presentation,
            candidate: source(
              `chunk_${detailMatch[1]}`,
              `Text ${detailMatch[1]}`,
            ),
          },
          current_result:
            detailMatch[1] === "t1" ? detail.current_result : null,
        });
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        keys.push(String(call.headers.get("Idempotency-Key")));
        const body = JSON.parse(String(call.body));
        pendingIds = pendingIds.filter((id) => id !== "t1");
        detail = absoluteDetail("t1", "chunk_1", {
          state: "completed",
          current_result: {
            kind: "absolute_relevance",
            relevance: body.relevance,
          },
        });
        return jsonResponse(relevanceReceipt("t1"));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <EvidenceSweepWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=evidence_sweep&workload=5" },
    );

    await screen.findByRole("heading", { name: "Evidence Sweep" });
    const li = await waitFor(() => {
      const el = document.querySelector('[data-task-id="t1"]');
      if (!(el instanceof HTMLElement)) throw new Error("missing t1 card");
      return el;
    });
    await user.click(
      within(li).getByRole("button", { name: /2 — Direct evidence/ }),
    );
    await within(li).findByText(/Judgment recorded/);
    await user.click(
      within(li).getByRole("button", { name: "Correct judgment" }),
    );
    await user.click(
      within(li).getByRole("button", { name: /1 — Supporting evidence/ }),
    );
    await within(li).findByText(/Judgment recorded/);
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toEqual(keys[1]);
    expect(
      mock.calls.filter((call) => call.url.endsWith("/relevance")),
    ).toHaveLength(2);
    mock.restore();
  });

  it("blocks further mutation on gold_state_unavailable", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [goldTask({ task_id: "t1", candidate_chunk_id: "chunk_1" })],
        });
      }
      if (/\/tasks\/t1$/.test(call.url) && call.method === "GET") {
        return jsonResponse(absoluteDetail("t1", "chunk_1"));
      }
      if (call.url.endsWith("/relevance") && call.method === "POST") {
        return errorResponse("gold_state_unavailable", "provenance", 409);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <EvidenceSweepWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=evidence_sweep&workload=1" },
    );

    await screen.findByRole("heading", { name: "Evidence Sweep" });
    const li = await waitFor(() => {
      const el = document.querySelector('[data-task-id="t1"]');
      if (!(el instanceof HTMLElement)) throw new Error("missing t1 card");
      return el;
    });
    await user.click(
      within(li).getByRole("button", { name: /0 — Irrelevant/ }),
    );
    expect(
      await screen.findByText(/Do not continue with this action until state can be trusted/),
    ).toBeInTheDocument();
    const postsBefore = mock.calls.filter((call) =>
      call.url.endsWith("/relevance"),
    ).length;
    await user.click(
      within(li).getByRole("button", { name: /1 — Supporting evidence/ }),
    );
    expect(
      mock.calls.filter((call) => call.url.endsWith("/relevance")),
    ).toHaveLength(postsBefore);
    mock.restore();
  });
});

describe("16G-I3 Chunk Duel session", () => {
  it("posts exact preference DTO, never relevance, and keeps auxiliary framing", async () => {
    const user = userEvent.setup();
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
      goldTask({
        task_id: "t3",
        case_id: "case_b",
        candidate_chunk_id: "chunk_c",
      }),
    ];
    const posts: FetchCall[] = [];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        expect(call.url).not.toContain("state=pending");
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        const id = detailMatch[1]!;
        const summary = tasks.find((task) => task.task_id === id)!;
        return jsonResponse(
          absoluteDetail(id, summary.candidate_chunk_id!, {
            case_id: summary.case_id,
          }),
        );
      }
      if (call.url.endsWith("/preferences") && call.method === "POST") {
        posts.push(call);
        const body = JSON.parse(String(call.body));
        expect(body).toEqual({
          case_id: "case_a",
          preferred_chunk_id: "chunk_a",
          other_chunk_id: "chunk_b",
          game_id: CHUNK_DUEL_GAME_ID,
          presentation_id: CHUNK_DUEL_PRESENTATION_ID,
        });
        expect(body).not.toHaveProperty("task_id");
        expect(body).not.toHaveProperty("relevance");
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        return jsonResponse(preferenceReceipt());
      }
      if (call.url.includes("/relevance")) {
        throw new Error("Chunk Duel must not POST relevance");
      }
      if (call.url.includes("/contribution")) {
        throw new Error("Chunk Duel must not touch contribution");
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=5" },
    );

    expect(
      await screen.findByRole("heading", { name: "Chunk Duel" }),
    ).toBeInTheDocument();
    const banners = screen.getAllByText(CHUNK_DUEL_AUXILIARY_MESSAGE);
    expect(banners.length).toBeGreaterThanOrEqual(2);

    const checkboxes = await screen.findAllByRole("checkbox");
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);
    await screen.findByRole("heading", { name: "Candidate A" });
    await user.click(
      screen.getByRole("button", { name: "Prefer candidate A" }),
    );
    expect(await screen.findByText("Preference recorded.")).toBeInTheDocument();
    expect(screen.getAllByText(CHUNK_DUEL_AUXILIARY_MESSAGE).length).toBeGreaterThanOrEqual(
      2,
    );
    expect(posts).toHaveLength(1);
    expect(
      mock.calls.some((call) => call.url.includes("/relevance")),
    ).toBe(false);
    expect(
      mock.calls.some((call) => call.url.includes("/contribution")),
    ).toBe(false);
    mock.restore();
  });

  it("shows no duel when a case has fewer than two distinct candidates", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [
            goldTask({
              task_id: "t1",
              case_id: "case_lonely",
              candidate_chunk_id: "chunk_only",
            }),
          ],
        });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=until_stop" },
    );

    expect(
      await screen.findByText("No duel available for this case."),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("retries ambiguous preference with the same frozen key and body", async () => {
    const user = userEvent.setup();
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
    ];
    let attempts = 0;
    const keys: string[] = [];
    const bodies: unknown[] = [];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        const id = detailMatch[1]!;
        const summary = tasks.find((task) => task.task_id === id)!;
        return jsonResponse(
          absoluteDetail(id, summary.candidate_chunk_id!, {
            case_id: summary.case_id,
          }),
        );
      }
      if (call.url.endsWith("/preferences") && call.method === "POST") {
        attempts += 1;
        keys.push(String(call.headers.get("Idempotency-Key")));
        bodies.push(JSON.parse(String(call.body)));
        if (attempts === 1) {
          throw new TypeError("network down");
        }
        return jsonResponse(preferenceReceipt({ replayed: true }));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=5" },
    );

    const checkboxes = await screen.findAllByRole("checkbox");
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);
    await user.click(
      await screen.findByRole("button", { name: "Prefer candidate B" }),
    );
    expect(
      await screen.findByRole("button", { name: "Retry same commit" }),
    ).toBeInTheDocument();
    // Pair edits locked while ambiguous: checkboxes disabled.
    expect(screen.getAllByRole("checkbox")[0]).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry same commit" }));
    await screen.findByText("Preference recorded.");
    expect(keys).toHaveLength(2);
    expect(keys[0]).toEqual(keys[1]);
    expect(bodies[0]).toEqual(bodies[1]);
    mock.restore();
  });

  it("blocks a second preference POST after idempotency_conflict", async () => {
    const user = userEvent.setup();
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
    ];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        const id = detailMatch[1]!;
        const summary = tasks.find((task) => task.task_id === id)!;
        return jsonResponse(
          absoluteDetail(id, summary.candidate_chunk_id!, {
            case_id: summary.case_id,
          }),
        );
      }
      if (call.url.endsWith("/preferences") && call.method === "POST") {
        return errorResponse("idempotency_conflict", "bound", 409);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=5" },
    );

    const checkboxes = await screen.findAllByRole("checkbox");
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);
    await user.click(
      await screen.findByRole("button", { name: "Prefer candidate A" }),
    );
    expect(
      await screen.findByText(/already bound to a different earlier attempt/),
    ).toBeInTheDocument();
    const postsBefore = mock.calls.filter((call) =>
      call.url.endsWith("/preferences"),
    ).length;
    await user.click(
      screen.getByRole("button", { name: "Prefer candidate B" }),
    );
    expect(
      mock.calls.filter((call) => call.url.endsWith("/preferences")),
    ).toHaveLength(postsBefore);
    mock.restore();
  });

  it("counts replayed=true confirmation toward workload=1 and blocks another POST", async () => {
    const user = userEvent.setup();
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
    ];
    let attempts = 0;

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      const detailMatch = call.url.match(
        /^\/v1\/gold-lab\/campaigns\/camp_1\/tasks\/([^/?]+)$/,
      );
      if (detailMatch && call.method === "GET") {
        const id = detailMatch[1]!;
        const summary = tasks.find((task) => task.task_id === id)!;
        return jsonResponse(
          absoluteDetail(id, summary.candidate_chunk_id!, {
            case_id: summary.case_id,
          }),
        );
      }
      if (call.url.endsWith("/preferences") && call.method === "POST") {
        attempts += 1;
        if (attempts === 1) {
          throw new TypeError("network down");
        }
        return jsonResponse(preferenceReceipt({ replayed: true }));
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=1" },
    );

    const checkboxes = await screen.findAllByRole("checkbox");
    await user.click(checkboxes[0]!);
    await user.click(checkboxes[1]!);
    await user.click(
      await screen.findByRole("button", { name: "Prefer candidate A" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Retry same commit" }),
    );
    expect(await screen.findByText("Preference recorded.")).toBeInTheDocument();
    expect(
      screen.getByText(/Session preference cap: 1 \/ 1/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Compare another pair" }),
    ).toBeNull();

    const postsAfterConfirm = mock.calls.filter((call) =>
      call.url.endsWith("/preferences"),
    ).length;
    expect(postsAfterConfirm).toBe(2);

    // Cap reached: preference controls must not issue another POST.
    const preferButtons = screen.queryAllByRole("button", {
      name: /Prefer candidate/,
    });
    for (const button of preferButtons) {
      expect(button).toBeDisabled();
    }
    expect(
      mock.calls.filter((call) => call.url.endsWith("/preferences")),
    ).toHaveLength(postsAfterConfirm);
    mock.restore();
  });

  it("locks workload=case to the valid anchored case only", async () => {
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
      goldTask({
        task_id: "t3",
        case_id: "case_b",
        candidate_chunk_id: "chunk_c",
      }),
      goldTask({
        task_id: "t4",
        case_id: "case_b",
        candidate_chunk_id: "chunk_d",
      }),
    ];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      if (/\/tasks\/[^/?]+$/.test(call.url) && call.method === "GET") {
        throw new Error(`Unexpected detail fetch: ${call.url}`);
      }
      if (call.url.endsWith("/preferences")) {
        throw new Error("Unexpected preference POST");
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=case&task=t3" },
    );

    expect(await screen.findByRole("radio", { name: "case_b" })).toBeChecked();
    expect(screen.queryByRole("radio", { name: "case_a" })).toBeNull();
    expect(
      screen.queryByText("No cases are available from the current task list."),
    ).toBeNull();
    mock.restore();
  });

  it("fail-closes workload=case when the task anchor is invalid", async () => {
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
      goldTask({
        task_id: "t3",
        case_id: "case_b",
        candidate_chunk_id: "chunk_c",
      }),
    ];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      if (/\/tasks\/[^/?]+$/.test(call.url) && call.method === "GET") {
        throw new Error(`Unexpected detail fetch behind fail-closed case: ${call.url}`);
      }
      if (call.url.endsWith("/preferences") && call.method === "POST") {
        throw new Error("Unexpected preference POST behind fail-closed case");
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=case&task=missing_task" },
    );

    expect(
      await screen.findByText("No cases are available from the current task list."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(
      mock.calls.some(
        (call) =>
          call.method === "GET" &&
          /\/tasks\/[^/?]+$/.test(call.url) &&
          !call.url.includes("?"),
      ),
    ).toBe(false);
    expect(
      mock.calls.some((call) => call.url.endsWith("/preferences")),
    ).toBe(false);
    mock.restore();
  });

  it("fail-closes workload=case when the task anchor is missing", async () => {
    const tasks = [
      goldTask({
        task_id: "t1",
        case_id: "case_a",
        candidate_chunk_id: "chunk_a",
      }),
      goldTask({
        task_id: "t2",
        case_id: "case_a",
        candidate_chunk_id: "chunk_b",
      }),
    ];

    const mock = installFetchMock(async (call) => {
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks });
      }
      if (/\/tasks\/[^/?]+$/.test(call.url) && call.method === "GET") {
        throw new Error(`Unexpected detail fetch: ${call.url}`);
      }
      if (call.url.endsWith("/preferences")) {
        throw new Error("Unexpected preference POST");
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderWithProviders(
      <ChunkDuelWorkSession campaignId="camp_1" campaignClosed={false} />,
      { initialPath: "/?game=chunk_duel&workload=case" },
    );

    expect(
      await screen.findByText("No cases are available from the current task list."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "case_a" })).toBeNull();
    expect(
      mock.calls.some((call) => call.url.endsWith("/preferences")),
    ).toBe(false);
    mock.restore();
  });
});
