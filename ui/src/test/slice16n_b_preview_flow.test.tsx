import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
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

function questionDetail(taskId: string, overrides: Record<string, unknown> = {}) {
  return {
    task_id: taskId,
    task_kind: "question_check",
    campaign_id: "camp_1",
    case_id: `case_${taskId}`,
    active: true,
    state: "pending",
    candidate_chunk_id: null,
    effective_query: null,
    presentation: {
      kind: "question_check",
      proposed_query: `Proposed ${taskId}?`,
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
    case_id: `case_${taskId}`,
    active: true,
    state: "pending",
    candidate_chunk_id: "chunk_1",
    effective_query: `Query ${taskId}?`,
    presentation: {
      kind: "absolute_relevance",
      effective_query: `Query ${taskId}?`,
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

function installPreviewReads(options: {
  qcTasks?: ReturnType<typeof goldTask>[];
  arTasks?: ReturnType<typeof goldTask>[];
}) {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  const qcTasks = options.qcTasks ?? [];
  const arTasks = options.arTasks ?? [];
  const details = new Map<string, Record<string, unknown>>();
  for (const t of qcTasks) {
    details.set(t.task_id, questionDetail(t.task_id));
  }
  for (const t of arTasks) {
    details.set(t.task_id, absoluteDetail(t.task_id));
  }

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
    const taskMatch = call.url.match(/\/tasks\/([^/?]+)$/);
    if (taskMatch) {
      const id = taskMatch[1]!;
      const detail = details.get(id);
      if (!detail) {
        return jsonResponse(
          { error: { code: "not_found", message: "missing" } },
          { status: 404 },
        );
      }
      return jsonResponse(detail);
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

describe("16N-B Presentation Review finite flow", () => {
  it("B-PREV-01: QC preview Q1→…→QN→END never wraps to Q1", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      qcTasks: [
        goldTask({
          task_id: "qc_1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
        goldTask({
          task_id: "qc_2",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    expect(await screen.findByText("Proposed qc_1?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByText("Proposed qc_2?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByTestId("qc-preview-complete")).toBeInTheDocument();
    expect(screen.getByText(/You reviewed 2 of 2 presentations/i)).toBeInTheDocument();
    expect(screen.queryByText("Proposed qc_1?")).not.toBeInTheDocument();
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-02: RF preview R1→…→RN→END never wraps", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      arTasks: [
        goldTask({
          task_id: "ar_1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
        goldTask({
          task_id: "ar_2",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    expect(await screen.findByText("Query ar_1?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByText("Query ar_2?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /1 — Supporting evidence/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByTestId("rf-preview-complete")).toBeInTheDocument();
    expect(screen.queryByText("Query ar_1?")).not.toBeInTheDocument();
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-03: Previous from first does not wrap", async () => {
    const mock = installPreviewReads({
      qcTasks: [
        goldTask({
          task_id: "qc_1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
        goldTask({
          task_id: "qc_2",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByText("Proposed qc_1?");
    const prev = screen.getByRole("button", { name: /Previous preview task/i });
    expect(prev).toBeDisabled();
    mock.restore();
  });

  it("B-PREV-04/06: per-task QC responses survive navigation; change replaces only current", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      qcTasks: [
        goldTask({
          task_id: "qc_1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
        goldTask({
          task_id: "qc_2",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByText("Proposed qc_1?");
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /accept/i,
    );
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    await screen.findByText("Proposed qc_2?");
    await user.click(screen.getByRole("button", { name: /^Edit$/i }));
    await user.clear(screen.getByLabelText(/Effective query/i));
    await user.type(screen.getByLabelText(/Effective query/i), "Edited Q2?");
    await user.click(screen.getByRole("button", { name: /Submit edit/i }));
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /edit/i,
    );

    await user.click(screen.getByRole("button", { name: /Previous preview task/i }));
    expect(await screen.findByText("Proposed qc_1?")).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /accept/i,
    );

    await user.click(
      screen.getByRole("button", { name: /Change preview response/i }),
    );
    await user.click(screen.getByRole("button", { name: /^Reject$/i }));
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /reject/i,
    );

    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByText("Proposed qc_2?")).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      /edit/i,
    );
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-05: per-task RF responses survive Previous/Next", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      arTasks: [
        goldTask({
          task_id: "ar_1",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
        goldTask({
          task_id: "ar_2",
          task_kind: "absolute_relevance",
          active: true,
          state: "pending",
        }),
      ],
    });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    await screen.findByText("Query ar_1?");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    await screen.findByText("Query ar_2?");
    await user.click(
      screen.getByRole("button", { name: /2 — Direct evidence/i }),
    );
    await user.click(screen.getByRole("button", { name: /Previous preview task/i }));
    expect(await screen.findByText("Query ar_1?")).toBeInTheDocument();
    expect(screen.getByTestId("preview-response-summary")).toHaveTextContent(
      "0",
    );
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-07: Restart preview clears ephemeral map and returns to first", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      qcTasks: [
        goldTask({
          task_id: "qc_1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByText("Proposed qc_1?");
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    await user.click(screen.getByRole("button", { name: /^Next preview task$/i }));
    expect(await screen.findByTestId("qc-preview-complete")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Restart preview$/i }));
    expect(await screen.findByText("Proposed qc_1?")).toBeInTheDocument();
    expect(
      screen.queryByText(/Preview response recorded locally/i),
    ).not.toBeInTheDocument();
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-08: no preview POST/mutation occurs", async () => {
    const user = userEvent.setup();
    const mock = installPreviewReads({
      qcTasks: [
        goldTask({
          task_id: "qc_1",
          task_kind: "question_check",
          active: true,
          state: "pending",
          candidate_chunk_id: null,
        }),
      ],
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    await screen.findByText("Proposed qc_1?");
    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-09: Preview stale-detail gate remains fail-closed", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks?") || call.url.endsWith("/tasks")) {
        return jsonResponse({
          campaign_id: "camp_1",
          tasks: [
            goldTask({
              task_id: "qc_stale",
              task_kind: "question_check",
              active: true,
              state: "pending",
              candidate_chunk_id: null,
            }),
          ],
        });
      }
      if (call.url.endsWith("/tasks/qc_stale")) {
        return jsonResponse(
          questionDetail("qc_stale", { active: false, state: "completed" }),
        );
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    expect(await screen.findByTestId("qc-preview-stale")).toBeInTheDocument();
    assertNoGoldMutationPosts(mock.calls);
    mock.restore();
  });

  it("B-PREV-10: RF empty-state copy does not say QC presentation must be approved", async () => {
    const mock = installPreviewReads({ arTasks: [] });
    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    const empty = await screen.findByTestId("rf-preview-unavailable");
    expect(empty).toHaveTextContent(/No active Rapid Fire tasks are available yet/i);
    expect(empty).toHaveTextContent(
      /after a real Question Check Accept or Edit/i,
    );
    expect(empty.textContent ?? "").not.toMatch(/Approve the Question Check presentation/i);
    expect(empty.textContent ?? "").not.toMatch(/ALLOW_PRODUCTION|policy/i);
    expect(
      screen.getByRole("link", { name: /Return to campaign/i }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("presentationReview subtree still has no mutation client imports", () => {
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
    ];
    for (const name of files) {
      const text = readFileSync(join(root, name), "utf8");
      for (const token of forbidden) {
        expect(text, `${name} must not contain ${token}`).not.toContain(token);
      }
    }
  });
});
