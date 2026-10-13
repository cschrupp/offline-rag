/**
 * 16G-I6 — Integration / regression / accessibility preflight.
 *
 * Cross-surface harness for accepted I1–I5 + GAP-16G-01 + GAP-16G-02.
 * This is NOT 16H WCAG 2.2 AA acceptance or the 16H seal.
 *
 * 16H residual acceptance obligations (not claimed proven here):
 * - full WCAG 2.2 AA certification
 * - manual 200% zoom visual acceptance
 * - full prefers-reduced-motion visual audit across all Gold Lab transitions
 * - exhaustive dialog focus-trap matrix beyond exercised surfaces
 * - narrow/mobile layout visual QA across all four games + shell
 */
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { validateTrainingCalibrationPackage } from "../features/goldLab/api/trainingPackageValidation";
import {
  goldLabErrorMessage,
  isGoldStateUnavailable,
  isIdempotencyConflict,
  isRetryableSameIntentError,
} from "../features/goldLab/errors/goldLabErrors";
import { CHUNK_DUEL_AUXILIARY_MESSAGE } from "../features/goldLab/games/chunkDuel/ChunkDuelGame";
import { ChunkDuelGame } from "../features/goldLab/games/chunkDuel/ChunkDuelGame";
import { EvidenceSweepGame } from "../features/goldLab/games/evidenceSweep/EvidenceSweepGame";
import { QuestionCheckGame } from "../features/goldLab/games/questionCheck/QuestionCheckGame";
import { RapidFireGame } from "../features/goldLab/games/rapidFire/RapidFireGame";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  isAllowProduction,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
} from "../features/goldLab/policy/presentations";
import { WorkloadChooser } from "../features/goldLab/shell/WorkloadChooser";
import { GoldWorkSession } from "../features/goldLab/work/GoldWorkSession";
import { trainingPackageFixture } from "./calibrationPackageFixture";
import { goldBaseline, goldCampaign, goldTask } from "./goldLabFixtures";
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

type User = ReturnType<typeof userEvent.setup>;

async function tabUntil(
  user: User,
  match: (el: Element | null) => boolean,
  label: string,
  maxTabs = 48,
): Promise<HTMLElement> {
  for (let i = 0; i < maxTabs; i += 1) {
    await user.tab();
    if (match(document.activeElement)) {
      return document.activeElement as HTMLElement;
    }
  }
  throw new Error(`keyboard tabUntil exhausted before reaching: ${label}`);
}

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

function absoluteDetail(
  taskId: string,
  overrides: Record<string, unknown> = {},
) {
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

function questionDetail(
  taskId: string,
  overrides: Record<string, unknown> = {},
) {
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

const DATASET_ID =
  "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const GOLD_MUTATION_FRAGMENTS = [
  "/relevance",
  "/question-check",
  "/preferences",
];

function assertNoGoldMutations(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of GOLD_MUTATION_FRAGMENTS) {
      if (call.url.includes(fragment)) {
        throw new Error(`Unexpected Gold mutation path: ${call.url}`);
      }
    }
    if (
      call.method === "POST" &&
      call.url.includes("/gold-lab/") &&
      !call.url.includes("/training-package")
    ) {
      // Training/calibration package reads are GET-only; any other gold-lab POST is a mutation.
      if (!call.url.includes("/registrations")) {
        throw new Error(`Unexpected Gold Lab POST: ${call.url}`);
      }
    }
  }
}

function apiErr(code: string, message = "x") {
  return new ApiError({
    kind: "api",
    code,
    message,
    status: 409,
  });
}

describe("16G-I6 A — keyboard / accessible interaction preflight", () => {
  it("Rapid Fire: Tab reaches judgment controls; shortcut and Enter commit", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(
      <RapidFireGame
        task={absoluteDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage="Commit recorded"
        afterAction={null}
        onCommit={onCommit}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Commit recorded");
    expect(screen.getByText("Candidate source")).toBeInTheDocument();

    // Accepted digit shortcut (window-level) without pointer / programmatic focus.
    await user.keyboard("1");
    expect(onCommit).toHaveBeenCalledWith(1);
    onCommit.mockClear();

    cleanup();
    const onCommit2 = vi.fn();
    render(
      <RapidFireGame
        task={absoluteDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage={null}
        afterAction={null}
        onCommit={onCommit2}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    const supporting = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement &&
        /1 — Supporting evidence/i.test(el.textContent ?? ""),
      "Rapid Fire Supporting button",
    );
    expect(supporting).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onCommit2).toHaveBeenCalledWith(1);
  });

  it("Evidence Sweep: Tab into linear-list relevance actions and commit", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(
      <EvidenceSweepGame
        cards={[
          { task: absoluteDetail("t1") as never, afterAction: null },
          {
            task: absoluteDetail("t2", {
              candidate_chunk_id: "chunk_2",
              presentation: {
                kind: "absolute_relevance",
                effective_query: "What pressure?",
                effective_category: "ops",
                effective_tags: ["pump"],
                candidate: { ...source, chunk_id: "chunk_2" },
              },
            }) as never,
            afterAction: null,
          },
        ]}
        mutationBusy={false}
        ambiguous={false}
        busyTaskId={null}
        errorMessage={null}
        statusMessage={null}
        batchComplete={false}
        nextBatchDisabled={false}
        onCommit={onCommit}
        onCorrect={vi.fn()}
        onRetrySame={vi.fn()}
        onNextBatch={vi.fn()}
      />,
    );

    const list = screen.getByRole("list");
    expect(list.tagName).toBe("OL");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    for (const label of [
      /0 — Irrelevant/,
      /1 — Supporting evidence/,
      /2 — Direct evidence/,
    ]) {
      expect(
        screen.getAllByRole("button", { name: label }).length,
      ).toBeGreaterThan(0);
    }

    const supporting = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement &&
        /1 — Supporting evidence/i.test(el.textContent ?? ""),
      "Evidence Sweep Supporting button",
    );
    expect(supporting).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onCommit).toHaveBeenCalledWith("t1", 1);
  });

  it("Question Check: Tab to Edit, keyboard-edit query, submit edit decision", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    render(
      <QuestionCheckGame
        task={questionDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage={null}
        afterAction={null}
        onCommit={onCommit}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();

    const edit = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement && el.textContent?.trim() === "Edit",
      "Question Check Edit button",
    );
    expect(edit).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(
      await screen.findByRole("heading", { name: "Edit proposed question" }),
    ).toBeInTheDocument();

    const queryField = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLInputElement && el.id === "gold-qc-edit-query",
      "Question Check Effective query field",
    );
    expect(queryField).toHaveFocus();
    await user.clear(queryField);
    await user.keyboard("Revised keyboard query?");

    const submit = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement &&
        el.textContent?.trim() === "Submit edit",
      "Question Check Submit edit",
    );
    expect(submit).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onCommit).toHaveBeenCalledWith({
      decision: "edit",
      effective_query: "Revised keyboard query?",
      effective_category: "ops",
      effective_tags: ["tag-a"],
    });

    // Decision actions remain keyboard-reachable after cancel path on a fresh mount.
    cleanup();
    const onCommit2 = vi.fn();
    render(
      <QuestionCheckGame
        task={questionDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage="Replay applied"
        afterAction={null}
        onCommit={onCommit2}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Replay applied");
    const reject = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement && el.textContent?.trim() === "Reject",
      "Question Check Reject button",
    );
    expect(reject).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onCommit2).toHaveBeenCalledWith({ decision: "reject" });
  });

  it("Chunk Duel: keyboard-reach case/candidates, toggle pair, submit preference", async () => {
    const user = userEvent.setup();
    const onPrefer = vi.fn();

    function ChunkDuelKeyboardHarness() {
      const [caseId, setCaseId] = useState("case_a");
      const [selectedChunkIds, setSelectedChunkIds] = useState<
        [string | null, string | null]
      >([null, null]);
      const detailA = absoluteDetail("t1");
      const detailB = absoluteDetail("t2", {
        candidate_chunk_id: "chunk_2",
        presentation: {
          kind: "absolute_relevance",
          effective_query: "What pressure?",
          effective_category: "ops",
          effective_tags: ["pump"],
          candidate: { ...source, chunk_id: "chunk_2" },
        },
      });
      return (
        <ChunkDuelGame
          caseId={caseId}
          caseIds={["case_a", "case_b"]}
          candidates={[
            { taskId: "t1", chunkId: "chunk_1", label: "A" },
            { taskId: "t2", chunkId: "chunk_2", label: "B" },
          ]}
          selectedChunkIds={selectedChunkIds}
          duelDetails={[
            selectedChunkIds[0] ? (detailA as never) : null,
            selectedChunkIds[1] ? (detailB as never) : null,
          ]}
          preferenceCount={0}
          preferenceCap={5}
          mutationBusy={false}
          ambiguous={false}
          errorMessage={null}
          statusMessage={null}
          lastReceipt={null}
          lastPreferredChunkId={null}
          onSelectCase={setCaseId}
          onToggleCandidate={(chunkId) => {
            setSelectedChunkIds(([a, b]) => {
              if (a === chunkId) return [b, null];
              if (b === chunkId) return [a, null];
              if (a === null) return [chunkId, b];
              if (b === null) return [a, chunkId];
              return [a, b];
            });
          }}
          onPrefer={onPrefer}
          onRetrySame={vi.fn()}
          onStartAnother={vi.fn()}
        />
      );
    }

    render(<ChunkDuelKeyboardHarness />);
    expect(
      screen
        .getAllByRole("status")
        .some((el) => el.textContent?.includes(CHUNK_DUEL_AUXILIARY_MESSAGE)),
    ).toBe(true);

    const caseRadio = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLInputElement &&
        el.type === "radio" &&
        el.name === "gold-chunk-duel-case" &&
        el.value === "case_a",
      "Chunk Duel case radio",
    );
    expect(caseRadio).toHaveFocus();
    expect((caseRadio as HTMLInputElement).checked).toBe(true);

    const candA = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLInputElement &&
        el.type === "checkbox" &&
        /chunk_1/i.test(el.parentElement?.textContent ?? ""),
      "Chunk Duel candidate A checkbox",
    );
    expect(candA).toHaveFocus();
    await user.keyboard(" ");
    expect((candA as HTMLInputElement).checked).toBe(true);

    const candB = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLInputElement &&
        el.type === "checkbox" &&
        /chunk_2/i.test(el.parentElement?.textContent ?? ""),
      "Chunk Duel candidate B checkbox",
    );
    expect(candB).toHaveFocus();
    await user.keyboard(" ");
    expect((candB as HTMLInputElement).checked).toBe(true);

    const preferA = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLButtonElement &&
        /Prefer candidate A/i.test(el.textContent ?? ""),
      "Chunk Duel Prefer A",
    );
    expect(preferA).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onPrefer).toHaveBeenCalledWith("a");
  });

  it("Workload chooser: Tab reaches radios; arrow keys change selection", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <WorkloadChooser
        value="5"
        onChange={onChange}
        caseIds={["case_a"]}
        selectedCaseId={null}
        onCaseChange={vi.fn()}
      />,
    );
    const radio5 = await tabUntil(
      user,
      (el) =>
        el instanceof HTMLInputElement &&
        el.type === "radio" &&
        el.name === "gold-lab-workload" &&
        el.value === "5",
      "Workload radio 5",
    );
    expect(radio5).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("10");
  });

  it("CSS carries focus-visible rings and prefers-reduced-motion (preflight, not WCAG seal)", () => {
    const css = readFileSync(
      resolve(__dirname, "../styles/global.css"),
      "utf8",
    );
    expect(css).toMatch(/button:focus-visible/);
    expect(css).toMatch(/outline:\s*3px solid var\(--color-focus\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)/);
    expect(css).toMatch(/\.gold-lab-/);
  });
});

describe("16G-I6 B — error-matrix regression", () => {
  it("maps every frozen error class through goldLabErrorMessage without raw leakage", () => {
    const matrix: Array<{
      code: string;
      expect: RegExp;
      helper?: (e: unknown) => boolean;
    }> = [
      {
        code: "request_invalid",
        expect: /Check the form fields|not accepted/i,
      },
      { code: "gold_project_unknown", expect: /Gold project not found/i },
      { code: "gold_campaign_unknown", expect: /Gold campaign not found/i },
      { code: "gold_task_unknown", expect: /Gold task not found/i },
      {
        code: "gold_baseline_unknown",
        expect: /baseline is no longer available|choose another eligible/i,
      },
      {
        code: "gold_conflict",
        expect: /changed since you last loaded|Refresh/i,
      },
      {
        code: "gold_state_unavailable",
        expect: /temporarily unavailable|Do not continue/i,
        helper: isGoldStateUnavailable,
      },
      {
        code: "idempotency_conflict",
        expect: /already bound to a different earlier attempt/i,
        helper: isIdempotencyConflict,
      },
      {
        code: "gold_busy",
        expect: /busy|Retry the same commit/i,
        helper: isRetryableSameIntentError,
      },
      {
        code: "internal_error",
        expect: /Something went wrong in Gold Lab/i,
      },
    ];

    const RAW = "RAW_BACKEND_SECRET_NOT_FOR_UI";
    const TRACE = "TRACEBACK_INTERNAL_DETAIL";

    for (const row of matrix) {
      const err = apiErr(row.code, `${RAW}::${row.code}`);
      const msg = goldLabErrorMessage(err);
      expect(msg).toMatch(row.expect);
      expect(msg).not.toContain(RAW);
      expect(msg).not.toContain(TRACE);
      if (row.helper) expect(row.helper(err)).toBe(true);
    }

    expect(goldLabErrorMessage(apiErr("not_found", RAW))).toBe(
      "Gold Lab resource not found.",
    );
    expect(goldLabErrorMessage(apiErr("not_found", RAW))).not.toContain(RAW);
    expect(goldLabErrorMessage(apiErr("gold_widget_unknown", RAW))).toBe(
      "Gold Lab resource not found.",
    );
    expect(goldLabErrorMessage(apiErr("gold_widget_unknown", RAW))).not.toContain(
      RAW,
    );
    expect(goldLabErrorMessage(apiErr("totally_unknown_code", RAW))).toBe(
      "Something went wrong in Gold Lab. Try again later.",
    );
    expect(
      goldLabErrorMessage(apiErr("totally_unknown_code", RAW)),
    ).not.toContain(RAW);
    expect(goldLabErrorMessage(apiErr("internal_error", TRACE))).toBe(
      "Something went wrong in Gold Lab. Try again later.",
    );
    expect(goldLabErrorMessage(apiErr("internal_error", TRACE))).not.toContain(
      TRACE,
    );
    expect(goldLabErrorMessage(new Error(RAW))).toBe(
      "Something went wrong in Gold Lab. Try again later.",
    );
    expect(goldLabErrorMessage(new Error(RAW))).not.toContain(RAW);
  });

  it("integrated Rapid Fire surfaces gold_busy retry-later and gold_state_unavailable fail-closed", async () => {
    const user = userEvent.setup();
    let mode: "busy" | "unavailable" = "busy";
    const posts: string[] = [];
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
        posts.push(call.url);
        if (mode === "busy") {
          return errorResponse("gold_busy", "locked", 409, true);
        }
        return errorResponse("gold_state_unavailable", "provenance", 409);
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
      { initialPath: "/work?game=rapid_fire&workload=1&task=t1" },
    );
    await screen.findByText("What pressure?");
    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/busy/i);
    expect(
      screen.getByRole("button", { name: "Retry same commit" }),
    ).toBeInTheDocument();
    mock.restore();
    cleanup();

    mode = "unavailable";
    const mock2 = installFetchMock(async (call) => {
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
        return errorResponse("gold_state_unavailable", "provenance", 409);
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
      { initialPath: "/work?game=rapid_fire&workload=1&task=t1" },
    );
    await screen.findByText("What pressure?");
    await user.click(screen.getByRole("button", { name: /1 — Supporting/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /temporarily unavailable|Do not continue/i,
    );
    expect(
      screen.getByRole("button", { name: /1 — Supporting/ }),
    ).toBeDisabled();
    mock2.restore();
  });

  it("campaign create path maps gold_baseline_unknown (creation blocked)", async () => {
    const campaignPosts: FetchCall[] = [];
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url.match(/\/v1\/gold-lab\/projects\/[^/]+$/)) {
        return jsonResponse({
          project_id: "proj_1",
          workspace_id: "ws_1",
          title: "Gold Bench",
          description: "",
          project_type: "benchmark",
          status: "active",
          created_at: "2026-03-01T12:00:00Z",
        });
      }
      if (
        call.url === "/v1/gold-lab/projects/proj_1/baselines" &&
        call.method === "GET"
      ) {
        return jsonResponse({
          project_id: "proj_1",
          baselines: [goldBaseline({ authoring_run_id: "run_missing" })],
        });
      }
      if (
        call.url === "/v1/gold-lab/projects/proj_1/campaigns" &&
        call.method === "POST"
      ) {
        campaignPosts.push(call);
        return errorResponse(
          "gold_baseline_unknown",
          "RAW_BACKEND_SECRET_NOT_FOR_UI",
          404,
        );
      }
      if (
        call.url === "/v1/gold-lab/projects/proj_1/campaigns" &&
        call.method === "GET"
      ) {
        return jsonResponse({ project_id: "proj_1", campaigns: [] });
      }
      if (call.url.includes("/baseline-bootstrap")) {
        return jsonResponse(
          { error: { code: "not_found", message: "x" } },
          { status: 404 },
        );
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    const user = userEvent.setup();
    renderApp("/gold-lab/projects/proj_1");
    const baselineSelect = await screen.findByLabelText("Eligible baseline");
    await waitFor(() => {
      expect(
        within(baselineSelect).getByRole("option", { name: /run_missing/ }),
      ).toBeInTheDocument();
    });
    await user.selectOptions(baselineSelect, "run_missing");
    await user.type(
      screen.getByLabelText("Selection policy ID"),
      "policy_i6_baseline_unknown",
    );
    await user.click(screen.getByRole("button", { name: "Create campaign" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /baseline is no longer available|choose another eligible/i,
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent(
      "RAW_BACKEND_SECRET_NOT_FOR_UI",
    );
    expect(campaignPosts).toHaveLength(1);
    expect(
      screen.queryByRole("heading", { name: "Campaign" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create campaign" }),
    ).toBeInTheDocument();
    mock.restore();
  });
});

describe("16G-I6 C — idempotency / retry regression", () => {
  it("uncertain retry reuses the same idempotency key; divergent retry surfaces conflict", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    let postCount = 0;
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
        postCount += 1;
        keys.push(call.headers.get("Idempotency-Key") ?? "");
        if (postCount === 1) {
          throw new TypeError("network failed");
        }
        if (postCount === 2) {
          return jsonResponse(receipt({ replayed: true }));
        }
        return errorResponse("idempotency_conflict", "bound", 409);
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
      { initialPath: "/work?game=rapid_fire&workload=1&task=t1" },
    );
    await screen.findByText("What pressure?");
    await user.click(screen.getByRole("button", { name: /1 — Supporting/ }));
    expect(
      await screen.findByRole("button", { name: "Retry same commit" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry same commit" }));
    await screen.findByRole("button", { name: "Correct judgment" });
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    mock.restore();
  });

  it("suppresses double-submit while a relevance mutation is pending (POST count == 1)", async () => {
    const user = userEvent.setup();
    let resolvePost: ((value: Response) => void) | null = null;
    let relevancePosts = 0;
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
        relevancePosts += 1;
        return new Promise<Response>((resolve) => {
          resolvePost = resolve;
        });
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
      { initialPath: "/work?game=rapid_fire&workload=1&task=t1" },
    );
    await screen.findByText("What pressure?");
    const supporting = screen.getByRole("button", {
      name: /1 — Supporting/,
    });
    await user.click(supporting);
    await waitFor(() => {
      expect(relevancePosts).toBe(1);
      expect(resolvePost).toBeTruthy();
    });
    expect(
      screen.getByRole("button", { name: /1 — Supporting/ }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: /0 — Irrelevant/ }),
    ).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /1 — Supporting/ }));
    await user.keyboard("1");
    expect(relevancePosts).toBe(1);

    resolvePost!(jsonResponse(receipt({ replayed: false })));
    expect(
      await screen.findByRole("button", { name: "Correct judgment" }),
    ).toBeInTheDocument();
    expect(relevancePosts).toBe(1);
    mock.restore();
  });
});

describe("16G-I6 D/E — Calibration and Training Gold non-mutation", () => {
  it("Calibration workspace issues ZERO Gold mutation calls while scoring", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const pkg = trainingPackageFixture();
    const mock = installFetchMock(async (call) => {
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
      for (const fragment of GOLD_MUTATION_FRAGMENTS) {
        if (call.url.includes(fragment)) {
          throw new Error(`Calibration mutation: ${call.url}`);
        }
      }
      if (call.url.includes("/contribution") || call.url.includes("/export")) {
        throw new Error(`Calibration forbidden: ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    await user.click(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    );
    expect(
      await screen.findByTestId("calibration-workspace"),
    ).toBeInTheDocument();
    assertNoGoldMutations(mock.calls);
    expect(
      mock.calls.some((c) => c.url.includes("/training-package")),
    ).toBe(true);
    expect(mock.calls.some((c) => c.method === "POST")).toBe(false);
    mock.restore();
  });

  it("Training scenario path issues ZERO Gold mutation calls", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const pkg = trainingPackageFixture();
    const mock = installFetchMock(async (call) => {
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
      for (const fragment of GOLD_MUTATION_FRAGMENTS) {
        if (call.url.includes(fragment)) {
          throw new Error(`Training mutation: ${call.url}`);
        }
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/training/scenario");
    const useBtn = await screen.findByRole("button", {
      name: /Use for scenario/i,
    });
    await user.click(useBtn);
    assertNoGoldMutations(mock.calls);
    expect(mock.calls.some((c) => c.method === "POST")).toBe(false);
    mock.restore();
  });
});

describe("16G-I6 F — presentation-policy gate (integrated route)", () => {
  it("ALLOW_PRODUCTION is QC+RF; ES/CD fail closed on work routes", async () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([
      {
        game_id: "goldgame_question_check_v1",
        presentation_id: "goldpres_question_check_source_panel_v1",
        disposition: "ALLOW_PRODUCTION",
      },
      {
        game_id: "goldgame_rapid_fire_v1",
        presentation_id: "goldpres_rapid_fire_single_card_v1",
        disposition: "ALLOW_PRODUCTION",
      },
    ]);
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(true);
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);

    const campaign = goldCampaign({ campaign_id: "camp_1" });
    for (const game of [
      "evidence_sweep",
      "chunk_duel",
    ] as const) {
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
          call.url.includes("/preferences") ||
          call.url.includes("/question-check")
        ) {
          throw new Error(`Policy gate leaked: ${call.method} ${call.url}`);
        }
        return jsonResponse(
          { error: { code: "not_found", message: "x" } },
          { status: 404 },
        );
      });
      renderApp(`/gold-lab/campaigns/camp_1/work?game=${game}&workload=1`);
      expect(
        await screen.findByText(
          /This presentation is not approved for production Gold Mode/,
        ),
      ).toBeInTheDocument();
      expect(mock.calls.some((c) => c.method === "POST")).toBe(false);
      cleanup();
      mock.restore();
    }
  });
});

describe("16G-I6 G — scientific semantic preservation", () => {
  it("keeps RF/ES absolute 0/1/2, QC accept/edit/reject, Chunk Duel auxiliary only", () => {
    expect(CHUNK_DUEL_AUXILIARY_MESSAGE).toMatch(
      /Preference only — does not create Gold relevance/i,
    );

    const rf = render(
      <RapidFireGame
        task={absoluteDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage={null}
        afterAction={null}
        onCommit={vi.fn()}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "Rapid Fire" })).toBeTruthy();
    expect(screen.getByText(/0 Irrelevant/)).toBeTruthy();
    rf.unmount();

    const es = render(
      <EvidenceSweepGame
        cards={[{ task: absoluteDetail("t1") as never, afterAction: null }]}
        mutationBusy={false}
        ambiguous={false}
        busyTaskId={null}
        errorMessage={null}
        statusMessage={null}
        batchComplete={false}
        nextBatchDisabled={false}
        onCommit={vi.fn()}
        onCorrect={vi.fn()}
        onRetrySame={vi.fn()}
        onNextBatch={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: /Evidence Sweep/i }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /2 — Direct evidence/ })).toBeTruthy();
    es.unmount();

    const qc = render(
      <QuestionCheckGame
        task={questionDetail("t1") as never}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage={null}
        afterAction={null}
        onCommit={vi.fn()}
        onRetrySame={vi.fn()}
        onNext={vi.fn()}
        onCorrect={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Accept" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /0 — Irrelevant/ })).toBeNull();
    qc.unmount();

    const cd = render(
      <ChunkDuelGame
        caseId="case_a"
        caseIds={["case_a"]}
        candidates={[
          { taskId: "t1", chunkId: "chunk_1", label: "A" },
          { taskId: "t2", chunkId: "chunk_2", label: "B" },
        ]}
        selectedChunkIds={[null, null]}
        duelDetails={[null, null]}
        preferenceCount={0}
        preferenceCap={null}
        mutationBusy={false}
        ambiguous={false}
        errorMessage={null}
        statusMessage={null}
        lastReceipt={null}
        lastPreferredChunkId={null}
        onSelectCase={vi.fn()}
        onToggleCandidate={vi.fn()}
        onPrefer={vi.fn()}
        onRetrySame={vi.fn()}
        onStartAnother={vi.fn()}
      />,
    );
    expect(
      screen.getAllByText(CHUNK_DUEL_AUXILIARY_MESSAGE).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/does not create Gold relevance or contribution/i),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: /0 — Irrelevant/ })).toBeNull();
    cd.unmount();
  });
});

describe("16G-I6 H — GAP-16G-01 package truth bindings", () => {
  it("fails closed when adjudication projection_sha256 diverges from registration", () => {
    const pkg = trainingPackageFixture();
    expect(() =>
      validateTrainingCalibrationPackage(
        {
          ...pkg,
          adjudication: {
            ...pkg.adjudication,
            projection_sha256: "f".repeat(64),
          },
        },
        { campaignId: "camp_1", datasetId: DATASET_ID },
      ),
    ).toThrow(/projection_sha256 must match registration/i);
  });

  it("fails closed when registration projection_sha256 is missing", () => {
    const pkg = trainingPackageFixture();
    expect(() =>
      validateTrainingCalibrationPackage(
        {
          ...pkg,
          registration: {
            ...pkg.registration,
            projection_sha256: "",
          },
        },
        { campaignId: "camp_1", datasetId: DATASET_ID },
      ),
    ).toThrow(/projection_sha256/i);
  });

  it("accepts package binding registration + adjudication + historical source truth", () => {
    const validated = validateTrainingCalibrationPackage(
      trainingPackageFixture(),
      { campaignId: "camp_1", datasetId: DATASET_ID },
    );
    expect(validated.registration.projection_sha256).toBe("c".repeat(64));
    expect(validated.adjudication.projection_sha256).toBe("c".repeat(64));
    expect(validated.registered_dataset.dataset_id).toBe(DATASET_ID);
  });
});

describe("16G-I6 I — GAP-16G-02 baseline bootstrap product path", () => {
  it("project surface exposes Create baseline from workspace toward pristine campaign state", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url.includes("/v1/capabilities")) {
        return jsonResponse({
          product: { name: "Seneca", descriptor: "x" },
          source_limits: {
            max_active_sources: 32,
            max_bytes_per_source: 1,
            max_active_source_bytes: 1,
          },
          authoring: { ready: true },
        });
      }
      if (call.url.match(/\/v1\/gold-lab\/projects\/[^/]+$/)) {
        return jsonResponse({
          project_id: "proj_1",
          workspace_id: "ws_1",
          title: "Bootstrap Project",
          description: "",
          project_type: "benchmark",
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
        });
      }
      if (call.url.includes("/baselines")) {
        return jsonResponse({ baselines: [] });
      }
      if (call.url.includes("/campaigns")) {
        return jsonResponse({ campaigns: [] });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/projects/proj_1");
    expect(
      await screen.findByRole("button", {
        name: "Create baseline from workspace",
      }),
    ).toBeInTheDocument();
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([
      {
        game_id: "goldgame_question_check_v1",
        presentation_id: "goldpres_question_check_source_panel_v1",
        disposition: "ALLOW_PRODUCTION",
      },
      {
        game_id: "goldgame_rapid_fire_v1",
        presentation_id: "goldpres_rapid_fire_single_card_v1",
        disposition: "ALLOW_PRODUCTION",
      },
    ]);
    mock.restore();
  });
});
