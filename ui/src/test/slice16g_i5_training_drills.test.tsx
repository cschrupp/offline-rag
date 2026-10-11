import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
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

function assertLearnerNetwork(calls: FetchCall[]) {
  for (const call of calls) {
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Training touched forbidden path: ${call.url}`);
      }
    }
    if (
      call.method !== "GET" &&
      !call.url.includes("/health") &&
      call.url.includes("/gold-lab")
    ) {
      throw new Error(`Training non-GET Gold call: ${call.method} ${call.url}`);
    }
    if (call.headers.get("Idempotency-Key")) {
      throw new Error("Training must not create Idempotency-Key");
    }
  }
}

function installTrainingMock(packageBody = trainingPackageFixture()) {
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
            exported_case_ids: ["case_accept"],
            registered_at: "2026-03-03T00:00:00Z",
          },
        ],
      });
    }
    if (
      call.url ===
      `/v1/gold-lab/campaigns/camp_1/registrations/${DATASET_ID}/training-package`
    ) {
      return jsonResponse(packageBody);
    }
    for (const fragment of FORBIDDEN) {
      if (call.url.includes(fragment)) {
        throw new Error(`Forbidden training fetch: ${call.url}`);
      }
    }
    return jsonResponse(
      { error: { code: "not_found", message: "x" } },
      { status: 404 },
    );
  });
}

async function openTraining(user: ReturnType<typeof userEvent.setup>) {
  renderApp("/gold-lab/campaigns/camp_1/training");
  await user.click(
    await screen.findByRole("button", { name: /Use for Training/i }),
  );
  expect(await screen.findByTestId("training-workspace")).toBeInTheDocument();
}

describe("16G-I5 training drills", () => {
  it("shows empty registration guidance without auto-export", async () => {
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
      if (FORBIDDEN.some((f) => call.url.includes(f))) {
        throw new Error(`Forbidden: ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/gold-lab/campaigns/camp_1/training");
    expect(await screen.findByTestId("training-no-regs")).toHaveTextContent(
      /No registered Gold dataset is available for Training/,
    );
    expect(mock.calls.some((c) => c.url.includes("/export"))).toBe(false);
    assertLearnerNetwork(mock.calls);
    mock.restore();
  });

  it("completes learner drills with only campaign/registrations/package GETs", async () => {
    const mock = installTrainingMock();
    const user = userEvent.setup();
    const storageSet = vi.spyOn(Storage.prototype, "setItem");

    await openTraining(user);

    // Drill order: QC accept → Evidence select → Relevance recall → QC reject
    const qc = await screen.findByTestId("training-question-check");
    expect(within(qc).queryByText(/Registration-time disposition/i)).toBeNull();
    await user.click(within(qc).getByRole("button", { name: "Accept" }));
    expect(
      await within(qc).findByText(/Registration-time disposition: accept/),
    ).toBeInTheDocument();
    await user.click(within(qc).getByRole("button", { name: /Next exercise/i }));

    const evidence = await screen.findByTestId("training-evidence-select");
    expect(
      within(evidence).queryByText(/Direct evidence|Supporting evidence|Irrelevant/),
    ).toBeNull();
    await user.click(within(evidence).getByText(/Include chunk_a/i));
    await user.click(
      within(evidence).getByRole("button", { name: /Commit local response/i }),
    );
    expect(
      await within(evidence).findByTestId("training-reveal-chunk_a"),
    ).toHaveTextContent(/Direct evidence/);
    expect(
      within(evidence).getByTestId("training-reveal-chunk_b"),
    ).toHaveTextContent(/Irrelevant/);
    await user.click(
      within(evidence).getByRole("button", { name: /Next exercise/i }),
    );

    const recall = await screen.findByTestId("training-relevance-recall");
    expect(within(recall).queryByTestId("training-reveal")).toBeNull();
    await user.click(within(recall).getByLabelText(/2 — Direct evidence/i));
    await user.click(
      within(recall).getByRole("button", { name: /Commit local response/i }),
    );
    expect(await within(recall).findByTestId("training-reveal")).toHaveTextContent(
      /match|mismatch/,
    );
    await user.click(
      within(recall).getByRole("button", { name: /Next candidate/i }),
    );
    const recall2 = await screen.findByTestId("training-relevance-recall");
    await user.click(within(recall2).getByLabelText(/0 — Irrelevant/i));
    await user.click(
      within(recall2).getByRole("button", { name: /Commit local response/i }),
    );
    await user.click(
      within(recall2).getByRole("button", { name: /Finish exercise/i }),
    );

    const qcReject = await screen.findByTestId("training-question-check");
    await user.click(within(qcReject).getByRole("button", { name: "Reject" }));
    expect(
      await within(qcReject).findByText(/Registration-time disposition: reject/),
    ).toBeInTheDocument();

    assertLearnerNetwork(mock.calls);
    expect(
      mock.calls.some((c) => c.url.includes("/training-package")),
    ).toBe(true);
    expect(
      storageSet.mock.calls.some((call) =>
        String(call[0]).includes("training"),
      ),
    ).toBe(false);
    mock.restore();
  });

  it("exposes Training nav from campaign shell", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks")) {
        return jsonResponse({ campaign_id: "camp_1", tasks: [] });
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/gold-lab/campaigns/camp_1");
    expect(await screen.findByRole("link", { name: "Training" })).toHaveAttribute(
      "href",
      "/gold-lab/campaigns/camp_1/training",
    );
    mock.restore();
  });
});
