import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { validateTrainingCalibrationPackage } from "../features/goldLab/api/trainingPackageValidation";
import { trainingPackageFixture } from "./calibrationPackageFixture";
import { goldCampaign } from "./goldLabFixtures";
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

const DATASET_ID =
  "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const FORBIDDEN_CALIBRATION = [
  "/relevance",
  "/question-check",
  "/preferences",
  "/export",
  "/tasks",
];

function assertNoMutationOrTasks(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN_CALIBRATION) {
      if (call.url.includes(fragment)) {
        throw new Error(`Calibration called forbidden path: ${call.url}`);
      }
    }
    if (call.method !== "GET" && !call.url.includes("/health")) {
      throw new Error(`Calibration issued non-GET: ${call.method} ${call.url}`);
    }
  }
}

function installCalibrationMock(options?: {
  packageBody?: unknown;
  registrations?: unknown[];
  contributionShouldThrow?: boolean;
}) {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  const pkg = options?.packageBody ?? trainingPackageFixture();
  const registrations =
    options?.registrations ??
    [
      {
        dataset_id: DATASET_ID,
        dataset_path: `datasets/${DATASET_ID}`,
        baseline_sha256: "b".repeat(64),
        projection_sha256: "c".repeat(64),
        exported_case_ids: ["case_accept"],
        registered_at: "2026-03-03T00:00:00Z",
      },
    ];

  return installFetchMock(async (call) => {
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces") return jsonResponse([]);
    if (call.url === "/v1/gold-lab/campaigns/camp_1") {
      return jsonResponse(campaign);
    }
    if (call.url === "/v1/gold-lab/campaigns/camp_1/registrations") {
      return jsonResponse({ campaign_id: "camp_1", registrations });
    }
    if (
      call.url ===
      `/v1/gold-lab/campaigns/camp_1/registrations/${DATASET_ID}/training-package`
    ) {
      return jsonResponse(pkg);
    }
    if (call.url.includes("/contribution")) {
      if (options?.contributionShouldThrow) {
        throw new Error("Calibration must not call contribution");
      }
      return jsonResponse({ error: { code: "not_found", message: "x" } }, { status: 404 });
    }
    for (const fragment of FORBIDDEN_CALIBRATION) {
      if (call.url.includes(fragment)) {
        throw new Error(`Forbidden calibration fetch: ${call.url}`);
      }
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

describe("16G-I4 calibration surface", () => {
  it("shows empty registration guidance without auto-export", async () => {
    const mock = installCalibrationMock({ registrations: [] });
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    expect(
      await screen.findByTestId("calibration-no-regs"),
    ).toHaveTextContent(/No registered Gold dataset is available for calibration/);
    expect(
      mock.calls.some((call) => call.url.includes("/export")),
    ).toBe(false);
    assertNoMutationOrTasks(mock.calls);
    mock.restore();
  });

  it("loads package by dataset_id and never uses dataset_path or tasks", async () => {
    const mock = installCalibrationMock();
    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    expect(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Use for calibration/i }));
    expect(await screen.findByTestId("calibration-workspace")).toBeInTheDocument();

    const packageCalls = mock.calls.filter((call) =>
      call.url.includes("/training-package"),
    );
    expect(packageCalls).toHaveLength(1);
    expect(packageCalls[0]?.url).toContain(DATASET_ID);
    expect(packageCalls[0]?.url).not.toContain("datasets/");
    assertNoMutationOrTasks(mock.calls);
    mock.restore();
  });

  it("rejects packages with forbidden enrichment fields", () => {
    expect(() =>
      validateTrainingCalibrationPackage(
        {
          ...trainingPackageFixture(),
          adjudication: {
            projection_sha256: "c".repeat(64),
            cases: [
              {
                ...trainingPackageFixture().adjudication.cases[0],
                prelabel: { grade: 2 },
              },
            ],
          },
        },
        { campaignId: "camp_1", datasetId: DATASET_ID },
      ),
    ).toThrow(/forbidden field/i);
  });

  it("rejects GoldDataset relevance 0 and incoherent reject rows", () => {
    expect(() =>
      validateTrainingCalibrationPackage(
        {
          ...trainingPackageFixture(),
          registered_dataset: {
            ...trainingPackageFixture().registered_dataset,
            cases: [
              {
                case_id: "case_accept",
                query: "q",
                category: null,
                tags: [],
                judgments: [{ chunk_id: "chunk_a", relevance: 0 as 1 }],
              },
            ],
          },
        },
        { campaignId: "camp_1", datasetId: DATASET_ID },
      ),
    ).toThrow(/1 or 2/);

    expect(() =>
      validateTrainingCalibrationPackage(
        {
          ...trainingPackageFixture(),
          adjudication: {
            projection_sha256: "c".repeat(64),
            cases: [
              {
                ...trainingPackageFixture().adjudication.cases[1],
                effective_query: "should be null",
              },
            ],
          },
        },
        { campaignId: "camp_1", datasetId: DATASET_ID },
      ),
    ).toThrow(/reject effective_query/);
  });

  it("runs Rapid Fire locally with blindness then reveal, zero Gold POSTs", async () => {
    const mock = installCalibrationMock({ contributionShouldThrow: true });
    const user = userEvent.setup();
    const downloads: string[] = [];
    vi.stubGlobal(
      "URL",
      {
        ...URL,
        createObjectURL: () => "blob:cal",
        revokeObjectURL: () => undefined,
      } as unknown as typeof URL,
    );
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        downloads.push(this.download);
      });

    renderApp("/gold-lab/campaigns/camp_1/calibration");
    await user.click(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Calibrate Rapid Fire/i }),
    );

    const game = await screen.findByTestId("calibration-rapid-fire");
    expect(within(game).queryByTestId("calibration-reveal")).toBeNull();
    expect(within(game).queryByText(/Registration-time relevance/i)).toBeNull();

    await user.click(within(game).getByLabelText(/2 — Direct evidence/i));
    await user.click(
      within(game).getByRole("button", { name: /Commit local response/i }),
    );
    expect(await within(game).findByTestId("calibration-reveal")).toHaveTextContent(
      /Registration-time relevance: 2/,
    );
    await user.click(within(game).getByRole("button", { name: /Next|Finish/i }));

    // Second absolute item (chunk_b, authority 0)
    const game2 = await screen.findByTestId("calibration-rapid-fire");
    await user.click(within(game2).getByLabelText(/0 — Irrelevant/i));
    await user.click(
      within(game2).getByRole("button", { name: /Commit local response/i }),
    );
    await user.click(
      within(game2).getByRole("button", { name: /Finish items/i }),
    );

    expect(
      await screen.findByTestId("calibration-session-complete"),
    ).toHaveTextContent(/Completed/);
    await user.click(
      screen.getByRole("button", { name: /Download calibration evidence/i }),
    );
    await waitFor(() => expect(downloads.length).toBe(1));
    expect(downloads[0]).toContain("gold-calibration-");
    expect(downloads[0]).toContain("goldpres_rapid_fire_single_card_v1");

    assertNoMutationOrTasks(mock.calls);
    expect(
      mock.calls.some((call) => call.url.includes("/contribution")),
    ).toBe(false);
    expect(
      screen.getByText(/Calibration evidence is review input only/i),
    ).toBeInTheDocument();

    clickSpy.mockRestore();
    mock.restore();
  });

  it("Question Check includes reject locally without POST", async () => {
    const mock = installCalibrationMock();
    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    await user.click(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Calibrate Question Check/i }),
    );
    const game = await screen.findByTestId("calibration-question-check");
    expect(within(game).queryByTestId("calibration-reveal")).toBeNull();
    await user.click(within(game).getByRole("button", { name: "Accept" }));
    expect(await within(game).findByTestId("calibration-reveal")).toHaveTextContent(
      /Registration-time disposition: accept/,
    );
    await user.click(within(game).getByRole("button", { name: /Next/i }));

    const rejectGame = await screen.findByTestId("calibration-question-check");
    await user.click(within(rejectGame).getByRole("button", { name: "Reject" }));
    expect(
      await within(rejectGame).findByTestId("calibration-reveal"),
    ).toHaveTextContent(/Registration-time disposition: reject/);

    assertNoMutationOrTasks(mock.calls);
    mock.restore();
  });

  it("Chunk Duel keeps auxiliary framing and never claims correctness", async () => {
    const mock = installCalibrationMock();
    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    await user.click(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Calibrate Chunk Duel/i }),
    );
    const game = await screen.findByTestId("calibration-chunk-duel");
    expect(game).toHaveTextContent(/Preference only — does not create Gold relevance/);
    await user.click(within(game).getByRole("button", { name: "Prefer A" }));
    await user.click(
      within(game).getByRole("button", { name: /Commit local preference/i }),
    );
    const reveal = await within(game).findByTestId("calibration-reveal");
    expect(reveal).toHaveTextContent(/not pairwise preference truth/i);
    expect(reveal.textContent?.toLowerCase()).not.toContain("correct");
    expect(reveal.textContent?.toLowerCase()).not.toContain("incorrect");
    expect(reveal.textContent?.toLowerCase()).not.toContain("agreement");
    assertNoMutationOrTasks(mock.calls);
    mock.restore();
  });

  it("fail-closes when package is gold_state_unavailable", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/registrations") && !call.url.includes("training-package")) {
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
        return errorResponse("gold_state_unavailable", "hidden", 409);
      }
      if (FORBIDDEN_CALIBRATION.some((f) => call.url.includes(f))) {
        throw new Error(`Forbidden: ${call.url}`);
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
      await screen.findByText(/Gold Lab state is temporarily unavailable/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("calibration-workspace")).toBeNull();
    mock.restore();
  });

  it("does not register training routes", async () => {
    const mock = installCalibrationMock({ registrations: [] });
    renderApp("/gold-lab/campaigns/camp_1/training");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    cleanup();
    renderApp("/training/scenario");
    expect(
      await screen.findByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("Evidence Sweep batches at most 5 and stays local", async () => {
    const manyCandidates = Array.from({ length: 6 }, (_, index) => ({
      chunk_id: `chunk_${index}`,
      source: {
        chunk_id: `chunk_${index}`,
        document_id: "doc_1",
        document_title: "Ops",
        source_name: "ops.pdf",
        section_path: [],
        page_start: null,
        page_end: null,
        line_start: null,
        line_end: null,
        content_type: "text/plain",
        text: `Evidence ${index}`,
      },
    }));
    const pkg = trainingPackageFixture({
      adjudication: {
        projection_sha256: "c".repeat(64),
        cases: [
          {
            case_id: "case_accept",
            qc_disposition: "accept",
            proposed_query: "What pressure?",
            proposed_category: "ops",
            proposed_tags: ["pump"],
            effective_query: "What pressure?",
            effective_category: "ops",
            effective_tags: ["pump"],
            question_source: manyCandidates[0]!.source,
            candidates: manyCandidates,
            relevance_judgments: manyCandidates.map((c, index) => ({
              chunk_id: c.chunk_id,
              relevance: index === 0 ? 2 : 0,
            })),
          },
        ],
      },
      registered_dataset: {
        schema_version: "offline-rag-gold-v1",
        dataset_id: DATASET_ID,
        chunk_set_id: "chunkset_1",
        corpus_id: "corpus_1",
        corpus_name: "Ops Corpus",
        cases: [
          {
            case_id: "case_accept",
            query: "What pressure?",
            category: "ops",
            tags: ["pump"],
            judgments: [{ chunk_id: "chunk_0", relevance: 2 }],
          },
        ],
      },
    });
    const mock = installCalibrationMock({ packageBody: pkg });
    const user = userEvent.setup();
    renderApp("/gold-lab/campaigns/camp_1/calibration");
    await user.click(
      await screen.findByRole("button", { name: /Use for calibration/i }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Calibrate Evidence Sweep/i }),
    );
    const sweep = await screen.findByTestId("calibration-evidence-sweep");
    expect(within(sweep).getAllByRole("listitem")).toHaveLength(5);
    assertNoMutationOrTasks(mock.calls);
    mock.restore();
  });
});
