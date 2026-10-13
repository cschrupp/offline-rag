import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GoldWorkSession } from "../features/goldLab/work/GoldWorkSession";
import { goldCampaign, goldTask } from "./goldLabFixtures";
import {
  installFetchMock,
  jsonResponse,
  type FetchCall,
} from "./mockApi";
import { renderApp, renderWithProviders } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sessionStorage.clear();
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

function installWorkReads(options: {
  game: "question_check" | "rapid_fire";
  tasks: ReturnType<typeof goldTask>[];
  details: Record<string, Record<string, unknown>>;
  onPost?: (call: FetchCall) => Response | Promise<Response>;
}) {
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
      return jsonResponse({ campaign_id: "camp_1", tasks: options.tasks });
    }
    const taskMatch = call.url.match(/\/tasks\/([^/?]+)$/);
    if (taskMatch && call.method === "GET") {
      const detail = options.details[taskMatch[1]!];
      if (detail) return jsonResponse(detail);
    }
    if (
      (call.url.endsWith("/question-check") || call.url.endsWith("/relevance")) &&
      call.method === "POST"
    ) {
      if (options.onPost) return options.onPost(call);
      return jsonResponse(
        receipt({
          task_id: options.tasks[0]?.task_id ?? "t1",
          record_type:
            options.game === "question_check"
              ? "question_check"
              : "absolute_relevance",
        }),
      );
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

describe("16N-B session exit and completion", () => {
  it("B-EXIT-01: End session visible during production QC", async () => {
    const mock = installWorkReads({
      game: "question_check",
      tasks: [
        goldTask({
          task_id: "q1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
      details: { q1: questionDetail("q1") },
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=question_check&workload=until_stop&task=q1",
    );
    expect(await screen.findByTestId("end-session")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /End Question Check session/i }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-EXIT-02: End session visible during production RF", async () => {
    const mock = installWorkReads({
      game: "rapid_fire",
      tasks: [
        goldTask({
          task_id: "t1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      details: { t1: absoluteDetail("t1") },
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=rapid_fire&workload=until_stop&task=t1",
    );
    expect(await screen.findByTestId("end-session")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /End Rapid Fire session/i }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-EXIT-03/04: End session returns to campaign with zero new mutation; committed stays", async () => {
    const user = userEvent.setup();
    let posts = 0;
    const mock = installWorkReads({
      game: "rapid_fire",
      tasks: [
        goldTask({
          task_id: "t1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
        goldTask({
          task_id: "t2",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      details: {
        t1: absoluteDetail("t1"),
        t2: absoluteDetail("t2"),
      },
      onPost: () => {
        posts += 1;
        return jsonResponse(
          receipt({ task_id: "t1", record_type: "absolute_relevance" }),
        );
      },
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=rapid_fire&workload=until_stop&task=t1",
    );
    await screen.findByTestId("rapid-fire-presentation");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    await screen.findByRole("button", { name: /Correct judgment/i });
    expect(posts).toBe(1);

    await user.click(screen.getByTestId("end-session"));
    expect(await screen.findByRole("heading", { name: "Campaign" })).toBeInTheDocument();
    expect(posts).toBe(1);
    mock.restore();
  });

  it("B-EXIT-05/06: unsaved QC edit requires discard confirmation; Keep working stays", async () => {
    const user = userEvent.setup();
    let posts = 0;
    const mock = installWorkReads({
      game: "question_check",
      tasks: [
        goldTask({
          task_id: "q1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
      details: { q1: questionDetail("q1") },
      onPost: () => {
        posts += 1;
        return jsonResponse(
          receipt({ task_id: "q1", record_type: "question_check" }),
        );
      },
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=question_check&workload=until_stop&task=q1",
    );
    await screen.findByTestId("question-check-presentation");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));
    expect(screen.getByLabelText(/Effective query/i)).toBeInTheDocument();

    await user.click(screen.getByTestId("end-session"));
    expect(
      await screen.findByText(/Discard this unsaved edit and end the session/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Keep working/i }));
    expect(screen.getByLabelText(/Effective query/i)).toBeInTheDocument();
    expect(screen.getByTestId("end-session")).toBeInTheDocument();
    expect(posts).toBe(0);

    await user.click(screen.getByTestId("end-session"));
    await screen.findByText(/Discard this unsaved edit and end the session/i);
    await user.click(screen.getByRole("button", { name: /Discard and end/i }));
    expect(await screen.findByRole("heading", { name: "Campaign" })).toBeInTheDocument();
    expect(posts).toBe(0);
    mock.restore();
  });

  it("B-EXIT-07: mutation-pending cannot silently abandon via End session", async () => {
    const user = userEvent.setup();
    let resolvePost: ((value: Response) => void) | null = null;
    const mock = installWorkReads({
      game: "rapid_fire",
      tasks: [
        goldTask({
          task_id: "t1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
        goldTask({
          task_id: "t2",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      details: {
        t1: absoluteDetail("t1"),
        t2: absoluteDetail("t2"),
      },
      onPost: () =>
        new Promise<Response>((resolve) => {
          resolvePost = resolve;
        }),
    });
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="rapid_fire"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=rapid_fire&workload=until_stop&task=t1" },
    );
    await screen.findByTestId("rapid-fire-presentation");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    await waitFor(() => {
      expect(screen.getByTestId("end-session")).toBeDisabled();
    });
    expect(
      screen.getByText(/Wait for the current judgment to finish/i),
    ).toBeInTheDocument();
    resolvePost?.(
      jsonResponse(receipt({ task_id: "t1", record_type: "absolute_relevance" })),
    );
    await waitFor(() => {
      expect(screen.getByTestId("end-session")).not.toBeDisabled();
    });
    mock.restore();
  });

  it("B-EXIT-07b: ambiguous transport disables End session", async () => {
    const user = userEvent.setup();
    const mock = installWorkReads({
      game: "rapid_fire",
      tasks: [
        goldTask({
          task_id: "t1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      details: { t1: absoluteDetail("t1") },
      onPost: () => {
        throw new TypeError("network down");
      },
    });
    renderWithProviders(
      <GoldWorkSession
        campaignId="camp_1"
        game="rapid_fire"
        campaignClosed={false}
      />,
      { initialPath: "/work?game=rapid_fire&workload=until_stop&task=t1" },
    );
    await screen.findByTestId("rapid-fire-presentation");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    await waitFor(() => {
      expect(screen.getByTestId("end-session")).toBeDisabled();
    });
    expect(
      screen.getByText(/Reconcile the ambiguous judgment/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("B-END-01/02/03: exhausted bounded workload shows Session complete, not campaign complete", async () => {
    const user = userEvent.setup();
    const mock = installWorkReads({
      game: "rapid_fire",
      tasks: [
        goldTask({
          task_id: "t1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
      details: { t1: absoluteDetail("t1") },
      onPost: () =>
        jsonResponse(
          receipt({ task_id: "t1", record_type: "absolute_relevance" }),
        ),
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=rapid_fire&workload=1&task=t1",
    );
    await screen.findByTestId("rapid-fire-presentation");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    expect(await screen.findByText(/Judgment recorded/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Next task$/i }));
    expect(await screen.findByTestId("expert-session-complete")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Session complete" })).toBeInTheDocument();
    expect(
      screen.getByText(/campaign may still have more Gold work/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Return to campaign/i }),
    ).toHaveAttribute("href", "/gold-lab/campaigns/camp_1");
    expect(screen.queryByText(/Canonical Gold work is complete/i)).not.toBeInTheDocument();
    mock.restore();
  });
});
