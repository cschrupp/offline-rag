import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  APPROVED_PRESENTATIONS_V1,
} from "../features/goldLab/policy/approvedPresentations.v1";
import {
  CHUNK_DUEL_GAME_ID,
  CHUNK_DUEL_PRESENTATION_ID,
  EVIDENCE_SWEEP_GAME_ID,
  EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID,
  EVIDENCE_SWEEP_PRESENTATION_ID,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
  isAllowProduction,
} from "../features/goldLab/policy/presentations";
import { goldCampaign, goldTask } from "./goldLabFixtures";
import { installFetchMock, jsonResponse } from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

const QC_RF_POLICY = [
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
] as const;

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

function absoluteDetail(taskId: string) {
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
  };
}

function questionDetail(taskId: string) {
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
      proposed_query: "Proposed production question?",
      proposed_category: "ops",
      proposed_tags: ["tag-a"],
      source,
    },
    current_result: null,
  };
}

describe("16N-A RF ALLOW_PRODUCTION policy", () => {
  it("RF-POL: exact QC+RF entries; ES/CD false; deep freeze; storage cannot grant", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([...QC_RF_POLICY]);
    expect(APPROVED_PRESENTATIONS_V1).toHaveLength(2);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[0])).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[1])).toBe(true);

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
    expect(
      isAllowProduction(
        EVIDENCE_SWEEP_GAME_ID,
        EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID,
      ),
    ).toBe(false);

    localStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([
        EVIDENCE_SWEEP_PRESENTATION_ID,
        CHUNK_DUEL_PRESENTATION_ID,
      ]),
    );
    sessionStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([EVIDENCE_SWEEP_LINEAR_LIST_PRESENTATION_ID]),
    );
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);
  });

  it("RF-POL-09: runtime mutation cannot retarget frozen entries", () => {
    for (const entry of APPROVED_PRESENTATIONS_V1) {
      expect(Object.isFrozen(entry)).toBe(true);
      const mutableView = entry as {
        game_id: string;
        presentation_id: string;
        disposition: string;
      };
      expect(() => {
        mutableView.game_id = EVIDENCE_SWEEP_GAME_ID;
      }).toThrow(TypeError);
      expect(() => {
        mutableView.presentation_id = EVIDENCE_SWEEP_PRESENTATION_ID;
      }).toThrow(TypeError);
      expect(() => {
        mutableView.game_id = CHUNK_DUEL_GAME_ID;
        mutableView.presentation_id = CHUNK_DUEL_PRESENTATION_ID;
      }).toThrow(TypeError);
    }
    expect(APPROVED_PRESENTATIONS_V1[0]?.game_id).toBe(QUESTION_CHECK_GAME_ID);
    expect(APPROVED_PRESENTATIONS_V1[1]?.game_id).toBe(RAPID_FIRE_GAME_ID);
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);
  });

  it("RF-WORK-02/03: /work mounts production RF and POSTs /relevance", async () => {
    const user = userEvent.setup();
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const task = goldTask({
      task_id: "ar_prod_1",
      task_kind: "absolute_relevance",
      active: true,
      state: "pending",
    });
    let relevanceBody: unknown = null;

    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [task] });
      }
      if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/ar_prod_1") {
        return jsonResponse(absoluteDetail("ar_prod_1"));
      }
      if (
        call.method === "POST" &&
        call.url.endsWith("/tasks/ar_prod_1/relevance")
      ) {
        relevanceBody = JSON.parse(String(call.body));
        return jsonResponse({
          campaign_id: "camp_1",
          record_id: "rec_rf_1",
          judgment_id: "jud_rf_1",
          task_id: "ar_prod_1",
          record_type: "absolute_relevance",
          sequence: 1,
          created_at: "2026-03-01T00:00:00Z",
          replayed: false,
        });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/work?game=rapid_fire&workload=1");
    expect(
      screen.queryByText(
        /This presentation is not approved for production Gold Mode/,
      ),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByTestId("rapid-fire-presentation"),
    ).toBeInTheDocument();
    expect(screen.getByText("What pressure?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /0 — Irrelevant/i }));
    expect(await screen.findByText(/Judgment recorded/i)).toBeInTheDocument();
    expect(relevanceBody).toEqual({
      relevance: 0,
      game_id: RAPID_FIRE_GAME_ID,
      presentation_id: RAPID_FIRE_PRESENTATION_ID,
    });
    mock.restore();
  });

  it("RF-WORK-01: Question Check /work still mounts production QC", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const task = goldTask({
      task_id: "qc_1",
      task_kind: "question_check",
      case_id: "case_q",
      active: true,
      state: "pending",
      candidate_chunk_id: null,
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [task] });
      }
      if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/qc_1") {
        return jsonResponse(questionDetail("qc_1"));
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
      await screen.findByTestId("question-check-presentation"),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("RF-WORK-04/05: Evidence Sweep and Chunk Duel remain blocked", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    for (const game of ["evidence_sweep", "chunk_duel"] as const) {
      const mock = installFetchMock(async (call) => {
        if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
        if (call.url === "/v1/workspaces") return jsonResponse([]);
        if (call.url === "/v1/gold-lab/campaigns/camp_1") {
          return jsonResponse(campaign);
        }
        if (call.url.includes("/tasks") || call.url.includes("/preferences")) {
          throw new Error(`Policy gate leaked: ${call.url}`);
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
      cleanup();
      mock.restore();
    }
  });

  it("RF-PREV / RF-CAL / RF-SCOPE: preview non-mutating; calibration separate; no PreviewInteraction in production", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const arTask = goldTask({
      task_id: "ar_1",
      task_kind: "absolute_relevance",
      active: true,
      state: "pending",
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/registrations")) {
        return jsonResponse({ campaign_id: "camp_1", registrations: [] });
      }
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [arTask] });
      }
      if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/ar_1") {
        return jsonResponse(absoluteDetail("ar_1"));
      }
      if (call.method !== "GET") {
        throw new Error(`Unexpected mutation: ${call.method} ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp(
      "/gold-lab/campaigns/camp_1/presentation-review?presentation=rapid_fire",
    );
    expect(
      await screen.findByTestId("rapid-fire-presentation"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Preview only — responses here do not change Gold/i),
    ).toBeInTheDocument();
    expect(mock.calls.some((c) => c.method === "POST")).toBe(false);
    cleanup();

    renderApp("/gold-lab/campaigns/camp_1/calibration");
    expect(
      await screen.findByText(
        /No registered Gold dataset is available for calibration/i,
      ),
    ).toBeInTheDocument();
    mock.restore();

    const here = dirname(fileURLToPath(import.meta.url));
    const work = readFileSync(
      join(here, "../features/goldLab/work/GoldWorkSession.tsx"),
      "utf8",
    );
    expect(work).toContain("submitGoldRelevance");
    expect(work).not.toContain("PreviewInteraction");
  });
});
