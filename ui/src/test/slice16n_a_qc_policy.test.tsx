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
  EVIDENCE_SWEEP_PRESENTATION_ID,
  QUESTION_CHECK_GAME_ID,
  QUESTION_CHECK_PRESENTATION_ID,
  RAPID_FIRE_GAME_ID,
  RAPID_FIRE_PRESENTATION_ID,
  isAllowProduction,
} from "../features/goldLab/policy/presentations";
import { goldCampaign, goldTask } from "./goldLabFixtures";
import {
  installFetchMock,
  jsonResponse,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

const QC_ONLY_POLICY = [
  {
    game_id: "goldgame_question_check_v1",
    presentation_id: "goldpres_question_check_source_panel_v1",
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

describe("16N-A QC ALLOW_PRODUCTION policy", () => {
  it("QC-POL: exact single QC entry; RF/ES/CD remain false; storage cannot grant", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([...QC_ONLY_POLICY]);
    expect(APPROVED_PRESENTATIONS_V1).toHaveLength(1);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1[0])).toBe(true);

    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);

    localStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([RAPID_FIRE_PRESENTATION_ID, EVIDENCE_SWEEP_PRESENTATION_ID]),
    );
    sessionStorage.setItem(
      "gold-lab-allow-production",
      JSON.stringify([CHUNK_DUEL_PRESENTATION_ID]),
    );
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
  });

  it("QC-POL-07: deep-frozen entry cannot grant RF/ES/CD via runtime mutation", () => {
    const entry = APPROVED_PRESENTATIONS_V1[0];
    expect(entry).toBeDefined();
    expect(Object.isFrozen(APPROVED_PRESENTATIONS_V1)).toBe(true);
    expect(Object.isFrozen(entry)).toBe(true);

    const mutableView = entry as {
      game_id: string;
      presentation_id: string;
      disposition: string;
    };
    expect(() => {
      mutableView.game_id = RAPID_FIRE_GAME_ID;
    }).toThrow(TypeError);
    expect(() => {
      mutableView.presentation_id = RAPID_FIRE_PRESENTATION_ID;
    }).toThrow(TypeError);
    expect(() => {
      mutableView.disposition = "ALLOW_PRODUCTION";
    }).toThrow(TypeError);
    expect(() => {
      mutableView.game_id = EVIDENCE_SWEEP_GAME_ID;
      mutableView.presentation_id = EVIDENCE_SWEEP_PRESENTATION_ID;
    }).toThrow(TypeError);
    expect(() => {
      mutableView.game_id = CHUNK_DUEL_GAME_ID;
      mutableView.presentation_id = CHUNK_DUEL_PRESENTATION_ID;
    }).toThrow(TypeError);

    expect(entry.game_id).toBe(QUESTION_CHECK_GAME_ID);
    expect(entry.presentation_id).toBe(QUESTION_CHECK_PRESENTATION_ID);
    expect(entry.disposition).toBe("ALLOW_PRODUCTION");
    expect(
      isAllowProduction(QUESTION_CHECK_GAME_ID, QUESTION_CHECK_PRESENTATION_ID),
    ).toBe(true);
    expect(
      isAllowProduction(RAPID_FIRE_GAME_ID, RAPID_FIRE_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(EVIDENCE_SWEEP_GAME_ID, EVIDENCE_SWEEP_PRESENTATION_ID),
    ).toBe(false);
    expect(
      isAllowProduction(CHUNK_DUEL_GAME_ID, CHUNK_DUEL_PRESENTATION_ID),
    ).toBe(false);
  });

  it("QC-WORK: /work mounts production QC presentation and mutation path", async () => {
    const user = userEvent.setup();
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const task = goldTask({
      task_id: "qc_prod_1",
      task_kind: "question_check",
      case_id: "case_q",
      active: true,
      state: "pending",
      candidate_chunk_id: null,
    });
    let posted = false;

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
      if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/qc_prod_1") {
        return jsonResponse(questionDetail("qc_prod_1"));
      }
      if (
        call.method === "POST" &&
        call.url.endsWith("/tasks/qc_prod_1/question-check")
      ) {
        posted = true;
        return jsonResponse({
          campaign_id: "camp_1",
          record_id: "rec_1",
          judgment_id: "jud_1",
          task_id: "qc_prod_1",
          record_type: "question_check",
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

    renderApp(
      "/gold-lab/campaigns/camp_1/work?game=question_check&workload=1",
    );
    expect(
      screen.queryByText(/This presentation is not approved for production Gold Mode/),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByTestId("question-check-presentation"),
    ).toBeInTheDocument();
    expect(screen.getByText("Proposed production question?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Accept$/i }));
    expect(await screen.findByText(/Judgment recorded/i)).toBeInTheDocument();
    expect(posted).toBe(true);
    expect(
      mock.calls.some(
        (c) =>
          c.method === "POST" &&
          c.url.includes("/question-check"),
      ),
    ).toBe(true);
    mock.restore();
  });

  it("QC-WORK-03: Rapid Fire /work remains fail-closed", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks")) {
        throw new Error(`Unexpected task call behind RF policy gate: ${call.url}`);
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

  it("QC-PREV / QC-CAL: Presentation Review and Calibration remain separate", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const qcTask = goldTask({
      task_id: "qc_1",
      task_kind: "question_check",
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
      if (call.url.includes("/registrations")) {
        return jsonResponse({ campaign_id: "camp_1", registrations: [] });
      }
      if (
        call.url.startsWith("/v1/gold-lab/campaigns/camp_1/tasks?") ||
        call.url === "/v1/gold-lab/campaigns/camp_1/tasks"
      ) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [qcTask] });
      }
      if (call.url === "/v1/gold-lab/campaigns/camp_1/tasks/qc_1") {
        return jsonResponse(questionDetail("qc_1"));
      }
      if (call.method !== "GET") {
        throw new Error(`Unexpected mutation: ${call.method} ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/gold-lab/campaigns/camp_1/presentation-review");
    expect(
      await screen.findByTestId("presentation-review-page"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Preview only — responses here do not change Gold/i),
    ).toBeInTheDocument();
    await screen.findByTestId("question-check-presentation");
    expect(
      mock.calls.some((c) => c.method === "POST"),
    ).toBe(false);
    cleanup();

    renderApp("/gold-lab/campaigns/camp_1/calibration");
    expect(
      await screen.findByText(
        /No registered Gold dataset is available for calibration/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("presentation-review-page")).not.toBeInTheDocument();
    mock.restore();
  });

  it("QC-SCOPE: production work does not import PreviewInteraction", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const work = readFileSync(
      join(here, "../features/goldLab/work/GoldWorkSession.tsx"),
      "utf8",
    );
    const page = readFileSync(
      join(here, "../pages/GoldLabWorkPage.tsx"),
      "utf8",
    );
    expect(work).toContain("submitGoldQuestionCheck");
    expect(work).not.toContain("PreviewInteraction");
    expect(work).not.toContain("presentationReview");
    expect(page).not.toContain("PreviewInteraction");
    expect(page).toContain("isAllowProduction");
  });
});
