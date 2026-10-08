import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvidenceMetric } from "../features/engineering/EvidenceMetric";
import {
  validateEngineeringEvidenceManifest,
} from "../features/engineering/evidenceClient";
import type { EngineeringEvidenceManifest } from "../features/engineering/evidenceTypes";
import { renderApp, renderWithProviders } from "./render";
import { installFetchMock, jsonResponse } from "./mockApi";

const here = dirname(fileURLToPath(import.meta.url));
const globalCss = readFileSync(join(here, "../styles/global.css"), "utf8");
const manifestText = readFileSync(
  join(here, "../../public/evidence/engineering-evidence-v1.json"),
  "utf8",
);
const manifestJson = JSON.parse(manifestText) as EngineeringEvidenceManifest;

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

function installAppMocks(options?: {
  manifest?: unknown | "missing" | "invalid";
}) {
  const mode = options?.manifest ?? manifestJson;
  return installFetchMock(async ({ url, method }) => {
    if (url === "/health/ready") return jsonResponse({ status: "ready" });
    if (url === "/v1/workspaces") return jsonResponse([]);
    if (url === "/evidence/engineering-evidence-v1.json") {
      expect(method).toBe("GET");
      if (mode === "missing") {
        return new Response("missing", { status: 404 });
      }
      if (mode === "invalid") {
        return jsonResponse({ contract: "wrong" });
      }
      return jsonResponse(mode);
    }
    if (url.startsWith("/eval/") || url.includes("/eval/")) {
      throw new Error(`Unexpected scientific runtime call: ${method} ${url}`);
    }
    return jsonResponse({ error: { code: "not_found", message: "x" } }, { status: 404 });
  });
}

describe("16E routing and shell", () => {
  it("exposes Engineering nav and preserves Overview/Workspaces/Settings", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /^Overview$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Workspaces$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Engineering$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Settings$/i })).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: /^Engineering$/i }));
    expect(
      await screen.findByRole("heading", { name: "Engineering evidence" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Engineering" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /^Architecture$/i }));
    expect(
      await screen.findByRole("heading", { name: "Architecture" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /^Overview$/i }));
    expect(await screen.findByRole("heading", { name: "Seneca" })).toBeInTheDocument();
    mock.restore();
  });

  it("keeps mobile menu functional with Engineering present", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/");
    const toggle = await screen.findByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-controls", "primary-navigation");
    await user.click(toggle);
    expect(screen.getByRole("navigation", { name: "Primary" })).toHaveClass("open");
    expect(screen.getByRole("link", { name: /^Engineering$/i })).toBeInTheDocument();
    mock.restore();
  });
});

describe("16E presentation tokens and architecture", () => {
  it("uses defined tokens for Engineering nav/active states and no legacy dark pre diagrams", () => {
    expect(globalCss).toContain(".engineering-subnav a");
    expect(globalCss).toContain("color: var(--navy)");
    expect(globalCss).toContain("background: var(--slate)");
    expect(globalCss).toContain("color: var(--white)");
    expect(globalCss).not.toMatch(/var\(--ink\)/);
    expect(globalCss).not.toMatch(/var\(--line\)/);
    expect(globalCss).not.toContain(".engineering-diagram");
  });

  it("renders architecture flows instead of ASCII pre blocks", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/architecture");
    expect(
      await screen.findByTestId("product-architecture-flow"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("snapshot-architecture-flow")).toBeInTheDocument();
    expect(screen.getByTestId("deployment-architecture-flow")).toBeInTheDocument();
    expect(document.querySelector("pre.engineering-diagram")).toBeNull();
    expect(
      screen.getByRole("heading", { name: "Deferred / not active" }),
    ).toBeInTheDocument();
    const product = screen.getByTestId("product-architecture-flow");
    expect(product.textContent ?? "").not.toMatch(/LangGraph/);
    const deferred = screen
      .getByRole("heading", { name: "Deferred / not active" })
      .closest(".card");
    expect(deferred?.textContent ?? "").toMatch(/LangGraph adapter/);
    mock.restore();
  });
});

describe("16E evaluation evidence UI", () => {
  it("renders evidence families with plain-language limits and no foreground manifest id", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(
      await screen.findByRole("heading", { name: "Retrieval quality" }),
    ).toBeInTheDocument();
    const pageHeader = document.querySelector(".engineering-page-header");
    expect(pageHeader?.textContent ?? "").toMatch(/Static accepted evidence/i);
    expect(pageHeader?.textContent ?? "").toMatch(/No live benchmark execution/i);
    expect(pageHeader?.textContent ?? "").not.toMatch(/engmanifest_/i);
    expect(
      screen.getAllByText(/does not authorize a configuration change/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /Generation/i })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Performance — 14C/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recovery" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Security / robustness" }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("keeps retrieval chart A–F order, 0–1 domain, and chart/table parity", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    const chart = await screen.findByTestId("metric-bar-chart");
    expect(chart).toHaveTextContent(/0\.0 → 1\.0/);
    const rows = within(chart).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-arm-id"))).toEqual([
      "A",
      "B",
      "C",
      "D",
      "E",
      "F",
    ]);
    const fill = rows[0].querySelector(".engineering-bar-fill");
    expect(fill?.getAttribute("data-bar-ratio")).toBeTruthy();
    const ratio = Number(fill?.getAttribute("data-bar-ratio"));
    expect(ratio).toBeGreaterThan(0);
    expect(ratio).toBeLessThanOrEqual(1);

    const retrievalDetails = screen.getAllByText("View detailed metrics")[0];
    await user.click(retrievalDetails);
    const table = await screen.findByTestId("retrieval-metrics-table");
    const firstNd = within(table).getAllByRole("row")[1];
    expect(within(firstNd).getByRole("cell", { name: "0.7643" })).toBeInTheDocument();
    expect(within(rows[0]).getByText("0.7643")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Population/i), "human-16");
    await waitFor(() => {
      expect(within(screen.getByTestId("metric-bar-chart")).getByText("0.7477")).toBeInTheDocument();
    });
    const details = retrievalDetails.closest("details");
    if (details && !details.open) {
      await user.click(retrievalDetails);
    }
    await waitFor(() => {
      expect(
        within(screen.getByTestId("retrieval-metrics-table")).getByText("0.7477"),
      ).toBeInTheDocument();
    });
    mock.restore();
  });

  it("keeps 14C quality and latency separate and derived from manifest", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(await screen.findByTestId("performance-14c-panels")).toBeInTheDocument();
    expect(screen.getByTestId("performance-14c-quality")).toBeInTheDocument();
    expect(screen.getByTestId("performance-14c-latency")).toBeInTheDocument();
    expect(screen.queryByTestId("security-bar-chart")).toBeNull();
    const panels = screen.getByTestId("performance-14c-panels");
    expect(panels.textContent ?? "").not.toMatch(/\bwinner\b/i);
    expect(panels.textContent ?? "").not.toMatch(/best configuration/i);

    const qualityPanel = screen.getByTestId("performance-14c-quality");
    expect(within(qualityPanel).getByText(/0\.7905068212751879/)).toBeInTheDocument();
    const latencyPanel = screen.getByTestId("performance-14c-latency");
    expect(within(latencyPanel).getByText(/5\.617130434024148/)).toBeInTheDocument();

    await user.click(screen.getAllByText("View detailed metrics")[1]);
    const qTable = await screen.findByTestId("performance-14c-quality-table");
    expect(within(qTable).getByText(/0\.7905068212751879/)).toBeInTheDocument();
    mock.restore();
  });

  it("shows security fail-closed flow separate from harness acceptance", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    const flow = await screen.findByTestId("security-status-flow");
    expect(within(flow).getByText("Completed")).toBeInTheDocument();
    expect(within(flow).getByText(/Fail — fail-closed/i)).toBeInTheDocument();
    expect(within(flow).getByText(/Unevaluable/i)).toBeInTheDocument();
    expect(within(flow).getByText("Accepted")).toBeInTheDocument();
    expect(within(flow).getByText(/fails closed by contract/i)).toBeInTheDocument();
    const body = document.body.textContent ?? "";
    for (const forbidden of [
      "Security passed",
      "All attacks blocked",
      "System secure",
      "0 attacks blocked",
      "7 attacks failed",
    ]) {
      expect(body).not.toContain(forbidden);
    }
    mock.restore();
  });

  it("shows recovery disabled semantics without controls", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    const flow = await screen.findByTestId("recovery-status-flow");
    expect(within(flow).getByText("Disabled")).toBeInTheDocument();
    expect(within(flow).getByText("Insufficient")).toBeInTheDocument();
    expect(within(flow).getByText(/Deferred \/ not authorized/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /enable recovery/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /run benchmark/i })).toBeNull();
    mock.restore();
  });

  it("keeps provenance with manifest/source hashes and unevaluable textual states", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(await screen.findByText("≈ 50.83 s")).toBeInTheDocument();
    expect(screen.getAllByText("Unevaluable").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);

    const summary = screen.getAllByText("View provenance")[0].closest("summary");
    expect(summary).toBeTruthy();
    await user.click(summary!);
    const provenance = summary!.closest("details");
    expect(provenance).toHaveAttribute("open");
    expect(
      within(provenance as HTMLElement).getByText(manifestJson.manifest_id),
    ).toBeInTheDocument();
    expect(
      within(provenance as HTMLElement).getByText(
        "docs/pilots/slice9h_p_results.md",
      ),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("fails visibly without fake fallback on invalid manifest", async () => {
    const mock = installAppMocks({ manifest: "invalid" });
    renderApp("/engineering/evaluation");
    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(/bundled evidence manifest could not be validated/i);
    expect(screen.queryByRole("heading", { name: "Retrieval quality" })).toBeNull();
    mock.restore();
  });

  it("does not call /eval runtime APIs from Evaluation", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    await screen.findByRole("heading", { name: "Retrieval quality" });
    await waitFor(() => {
      expect(mock.calls.some((call) => call.url.includes("/eval/"))).toBe(false);
    });
    expect(
      mock.calls.some((call) => call.url === "/evidence/engineering-evidence-v1.json"),
    ).toBe(true);
    mock.restore();
  });
});

describe("16E metric rendering", () => {
  it("keeps measured zero numeric and never zeros unevaluable", () => {
    const { container: zeroContainer } = renderWithProviders(
      <EvidenceMetric
        metric={{ availability: "measured", value: 0, value_qualifier: "exact" }}
      />,
    );
    expect(zeroContainer.textContent).toBe("0");

    const { container: unevalContainer } = renderWithProviders(
      <EvidenceMetric
        metric={{ availability: "unevaluable", value: null, value_qualifier: null }}
      />,
    );
    expect(unevalContainer.textContent).toBe("Unevaluable");
    expect(unevalContainer.textContent).not.toBe("0");
  });
});

describe("16E overview", () => {
  it("corrects Overview guidance and links Engineering", async () => {
    const mock = installAppMocks();
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Seneca" })).toBeInTheDocument();
    expect(screen.queryByText(/later phase/i)).toBeNull();
    expect(screen.getByText(/ask grounded questions/i)).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Engineering evidence" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Evaluation/i })).toBeInTheDocument();
    mock.restore();
  });
});

describe("16E manifest validation", () => {
  it("accepts the committed manifest contract", () => {
    const validated = validateEngineeringEvidenceManifest(manifestJson);
    expect(validated.contract).toBe("seneca-engineering-evidence-manifest-v1");
    expect(validated.records.length).toBe(6);
  });
});
