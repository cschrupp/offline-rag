import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScenarioWorkspace } from "../features/goldLab/training/scenario/ScenarioWorkspace";
import type {
  BlindScenarioExercise,
  ScenarioAuthority,
} from "../features/goldLab/training/types";
import type { GoldTrainingCalibrationPackage } from "../features/goldLab/types";
import { trainingPackageFixture } from "./calibrationPackageFixture";
import { goldCampaign } from "./goldLabFixtures";
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

const DATASET_ID =
  "gold_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

const FORBIDDEN = [
  "/tasks",
  "/relevance",
  "/question-check",
  "/preferences",
  "/export",
  "/contribution",
];

const source = (chunkId: string, text: string) => ({
  chunk_id: chunkId,
  document_id: "doc_1",
  document_title: "Ops Manual",
  source_name: "ops.pdf",
  section_path: ["Start"],
  page_start: 1,
  page_end: 1,
  line_start: 1,
  line_end: 2,
  content_type: "text/plain",
  text,
});

function twoScenarioPackage(): GoldTrainingCalibrationPackage {
  const base = trainingPackageFixture();
  return {
    ...base,
    registration: {
      ...base.registration,
      exported_case_ids: ["case_accept", "case_edit"],
    },
    registered_dataset: {
      ...base.registered_dataset,
      cases: [
        ...base.registered_dataset.cases,
        {
          case_id: "case_edit",
          query: "Edited pump query?",
          category: "ops",
          tags: ["valve"],
          judgments: [{ chunk_id: "chunk_c", relevance: 1 }],
        },
      ],
    },
    adjudication: {
      ...base.adjudication,
      cases: [
        base.adjudication.cases[0]!,
        {
          case_id: "case_edit",
          qc_disposition: "edit",
          proposed_query: "Original pump query?",
          proposed_category: "ops",
          proposed_tags: ["valve"],
          effective_query: "Edited pump query?",
          effective_category: "ops",
          effective_tags: ["valve"],
          question_source: source("chunk_c", "Valve note."),
          candidates: [
            {
              chunk_id: "chunk_c",
              source: source("chunk_c", "Valve note."),
            },
            {
              chunk_id: "chunk_d",
              source: source("chunk_d", "Noise."),
            },
          ],
          relevance_judgments: [
            { chunk_id: "chunk_c", relevance: 1 },
            { chunk_id: "chunk_d", relevance: 0 },
          ],
        },
        base.adjudication.cases[1]!,
      ],
    },
  };
}

function assertLearnerNetwork(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Scenario touched forbidden path: ${call.url}`);
      }
    }
    if (
      call.method !== "GET" &&
      !call.url.includes("/health") &&
      call.url.includes("/gold-lab")
    ) {
      throw new Error(`Scenario non-GET Gold call: ${call.method} ${call.url}`);
    }
  }
}

function installScenarioMock(pkg: GoldTrainingCalibrationPackage = trainingPackageFixture()) {
  const campaign = goldCampaign({ campaign_id: "camp_1" });
  return installFetchMock(async (call) => {
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
            exported_case_ids: pkg.registration.exported_case_ids,
            registered_at: "2026-03-03T00:00:00Z",
          },
        ],
      });
    }
    if (call.url.includes("/training-package")) {
      return jsonResponse(pkg);
    }
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Forbidden scenario fetch: ${call.url}`);
      }
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

const blindScenario: BlindScenarioExercise = {
  kind: "scenario_relevance_map",
  exerciseId: `goldex_${DATASET_ID}_case_accept_scenario_relevance_map_v1`,
  caseId: "case_accept",
  scenarioStem: "What pressure?",
  category: "ops",
  tags: ["pump"],
  candidates: [
    {
      chunkId: "chunk_a",
      source: source("chunk_a", "Pump pressure must remain stable."),
    },
    {
      chunkId: "chunk_b",
      source: source("chunk_b", "Unrelated cooling note."),
    },
  ],
};

const scenarioAuthority: ScenarioAuthority = {
  exerciseId: blindScenario.exerciseId,
  caseId: "case_accept",
  relevanceByChunkId: {
    chunk_a: 2,
    chunk_b: 0,
  },
};

describe("16G-I5 training scenario / debrief", () => {
  it("hides authority until scenario commit, then locks and debriefs", async () => {
    const mock = installScenarioMock();
    const user = userEvent.setup();
    const storageSet = vi.spyOn(Storage.prototype, "setItem");

    renderApp(
      `/gold-lab/campaigns/camp_1/training/scenario?dataset=${DATASET_ID}`,
    );
    const scenario = await screen.findByTestId("training-scenario");
    expect(within(scenario).getByTestId("scenario-stem")).toHaveTextContent(
      "What pressure?",
    );
    expect(
      within(scenario).queryByText(/Authority:|Registration-time/),
    ).toBeNull();
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();

    const cards = within(scenario).getAllByRole("listitem");
    await user.click(within(cards[0]!).getByLabelText(/2 — Direct evidence/i));
    await user.click(within(cards[1]!).getByLabelText(/1 — Supporting evidence/i));
    // Revise B before commit
    await user.click(within(cards[1]!).getByLabelText(/0 — Irrelevant/i));

    await user.click(
      within(scenario).getByRole("button", { name: /Commit scenario/i }),
    );

    expect(
      await screen.findByTestId("scenario-reveal-chunk_a"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("scenario-reveal-chunk_b")).toBeInTheDocument();
    const debrief = await screen.findByTestId("training-scenario-debrief");
    expect(within(debrief).getByTestId("scenario-debrief-matches")).toHaveTextContent(
      "2 / 2",
    );
    expect(
      within(debrief).getByTestId("scenario-debrief-learner-dist"),
    ).toHaveTextContent("0:1 · 1:0 · 2:1");
    expect(
      within(debrief).getByTestId("scenario-debrief-authority-dist"),
    ).toHaveTextContent("0:1 · 1:0 · 2:1");
    expect(within(debrief).getByText(/chunk_a/i)).toBeInTheDocument();
    expect(within(debrief).getAllByText(/Historical source/i).length).toBeGreaterThan(
      0,
    );

    // Locked — radios disabled
    expect(
      within(cards[0]!).getByLabelText(/2 — Direct evidence/i),
    ).toBeDisabled();

    assertLearnerNetwork(mock.calls);
    expect(
      storageSet.mock.calls.some((call) =>
        String(call[0]).toLowerCase().includes("train"),
      ),
    ).toBe(false);
    mock.restore();
  });

  it("I5-R1: ScenarioWorkspace receives no authority or resolver before commit", async () => {
    const user = userEvent.setup();
    const onCommit = vi.fn();
    const onRestart = vi.fn();
    let seenAuthority: ScenarioAuthority | undefined = undefined;
    let seenResolver: unknown = "unset";

    function Probe(props: {
      authority: ScenarioAuthority | undefined;
      committed: boolean;
    }) {
      seenAuthority = props.authority;
      seenResolver = (props as { resolveAuthorityAfterCommit?: unknown })
        .resolveAuthorityAfterCommit;
      return (
        <ScenarioWorkspace
          exercise={blindScenario}
          authority={props.authority}
          committed={props.committed}
          onCommit={onCommit}
          onRestart={onRestart}
        />
      );
    }

    const { rerender } = render(
      <Probe authority={undefined} committed={false} />,
    );

    expect(seenAuthority).toBeUndefined();
    expect(seenResolver).toBeUndefined();
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();
    expect(screen.queryByText(/Authority:/)).toBeNull();
    expect(screen.queryByTestId("scenario-reveal-chunk_a")).toBeNull();

    const scenario = screen.getByTestId("training-scenario");
    const cards = within(scenario).getAllByRole("listitem");
    await user.click(within(cards[0]!).getByLabelText(/2 — Direct evidence/i));
    await user.click(within(cards[1]!).getByLabelText(/0 — Irrelevant/i));
    await user.click(
      within(scenario).getByRole("button", { name: /Commit scenario/i }),
    );

    expect(onCommit).toHaveBeenCalledTimes(1);
    // Still blind until parent supplies exact authority after commit.
    expect(seenAuthority).toBeUndefined();
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();

    rerender(<Probe authority={scenarioAuthority} committed={true} />);
    expect(seenAuthority).toEqual(scenarioAuthority);
    expect(seenResolver).toBeUndefined();
    expect(
      await screen.findByTestId("training-scenario-debrief"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("scenario-reveal-chunk_a")).toHaveTextContent(
      /Authority: 2/,
    );
  });

  it("I5-R2: next scenario case is unavailable until current debrief completes", async () => {
    const mock = installScenarioMock(twoScenarioPackage());
    const user = userEvent.setup();

    renderApp(
      `/gold-lab/campaigns/camp_1/training/scenario?dataset=${DATASET_ID}`,
    );

    const scenario = await screen.findByTestId("training-scenario");
    expect(screen.getByText(/Scenario 1 of 2/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Next scenario case/i }),
    ).toBeNull();
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();

    const cards = within(scenario).getAllByRole("listitem");
    await user.click(within(cards[0]!).getByLabelText(/2 — Direct evidence/i));
    await user.click(within(cards[1]!).getByLabelText(/0 — Irrelevant/i));

    // Still uncommitted — next remains unavailable.
    expect(
      screen.queryByRole("button", { name: /Next scenario case/i }),
    ).toBeNull();

    await user.click(
      within(scenario).getByRole("button", { name: /Commit scenario/i }),
    );

    expect(
      await screen.findByTestId("training-scenario-debrief"),
    ).toBeInTheDocument();
    const next = await screen.findByRole("button", {
      name: /Next scenario case/i,
    });

    await user.click(next);

    const scenario2 = await screen.findByTestId("training-scenario");
    expect(screen.getByText(/Scenario 2 of 2/i)).toBeInTheDocument();
    expect(within(scenario2).getByTestId("scenario-stem")).toHaveTextContent(
      "Edited pump query?",
    );
    expect(screen.queryByTestId("training-scenario-debrief")).toBeNull();
    expect(screen.queryByText(/Authority:/)).toBeNull();
    expect(
      screen.queryByRole("button", { name: /Next scenario case/i }),
    ).toBeNull();
    expect(
      within(scenario2).getByRole("button", { name: /Commit scenario/i }),
    ).toBeInTheDocument();

    assertLearnerNetwork(mock.calls);
    mock.restore();
  });
});
