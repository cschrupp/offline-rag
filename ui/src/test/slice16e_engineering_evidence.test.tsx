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
import { renderApp, renderWithProviders } from "./render";
import { installFetchMock, jsonResponse } from "./mockApi";

const here = dirname(fileURLToPath(import.meta.url));
const manifestText = readFileSync(
  join(here, "../../public/evidence/engineering-evidence-v1.json"),
  "utf8",
);
const manifestJson = JSON.parse(manifestText) as unknown;

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

describe("16E evaluation evidence UI", () => {
  it("renders evidence families with caveats and provenance", async () => {
    const user = userEvent.setup();
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(
      await screen.findByRole("heading", { name: "Retrieval quality" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Generation/i })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Performance — 14C/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Level-C end-to-end/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recovery" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Security / robustness" }),
    ).toBeInTheDocument();

    expect(screen.getAllByText(/Non-promotional/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/PILOT \/ NON-PROMOTIONAL/i).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getAllByText(/Same-model self-judge limitation/i).length,
    ).toBeGreaterThan(0);

    expect(screen.getByText("≈ 50.83 s")).toBeInTheDocument();
    expect(screen.getAllByText("Unevaluable").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);

    const summary = screen.getAllByText("View provenance")[0].closest("summary");
    expect(summary).toBeTruthy();
    await user.click(summary!);
    expect(summary!.closest("details")).toHaveAttribute("open");
    expect(
      screen.getByText("docs/pilots/slice9h_p_results.md"),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("shows security fail-closed semantics and omits forbidden claims", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(await screen.findByText("Completed")).toBeInTheDocument();
    expect(screen.getByText(/Fail — fail-closed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/required invariant was unevaluable/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Accepted")).toBeInTheDocument();
    const body = document.body.textContent ?? "";
    for (const forbidden of [
      "Security passed",
      "All attacks blocked",
      "System secure",
      "0 attacks blocked",
      "7 attacks failed",
      "7 attacks passed",
    ]) {
      expect(body).not.toContain(forbidden);
    }
    mock.restore();
  });

  it("shows recovery disabled semantics without controls", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    expect(await screen.findByText("Disabled")).toBeInTheDocument();
    expect(screen.getByText("Insufficient")).toBeInTheDocument();
    expect(
      screen.getAllByText(/Deferred \/ not authorized/i).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /enable recovery/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /run benchmark/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /run evaluation/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /promote/i })).toBeNull();
    mock.restore();
  });

  it("fails visibly without fake fallback on invalid manifest", async () => {
    const mock = installAppMocks({ manifest: "invalid" });
    renderApp("/engineering/evaluation");
    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent(/bundled evidence manifest could not be validated/i);
    expect(screen.queryByRole("heading", { name: "Retrieval quality" })).toBeNull();
    expect(screen.queryByText("0.7643")).toBeNull();
    mock.restore();
  });

  it("does not call /eval runtime APIs from Evaluation", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/evaluation");
    await screen.findByRole("heading", { name: "Retrieval quality" });
    await waitFor(() => {
      expect(
        mock.calls.some((call) => call.url.includes("/eval/")),
      ).toBe(false);
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

    const { container: naContainer } = renderWithProviders(
      <EvidenceMetric
        metric={{
          availability: "not_applicable",
          value: null,
          value_qualifier: null,
        }}
      />,
    );
    expect(naContainer.textContent).toBe("Not applicable");
  });
});

describe("16E architecture and overview", () => {
  it("renders distinct architecture sections and keeps LangGraph deferred", async () => {
    const mock = installAppMocks();
    renderApp("/engineering/architecture");
    expect(
      await screen.findByRole("heading", { name: "Product architecture" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Snapshot / data architecture" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Deployment architecture" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Deferred / not active" }),
    ).toBeInTheDocument();
    const productCard = screen
      .getByRole("heading", { name: "Product architecture" })
      .closest(".card");
    const productDiagram = productCard?.querySelector(".engineering-diagram");
    expect(productDiagram?.textContent ?? "").not.toMatch(/LangGraph/);
    const deferred = screen
      .getByRole("heading", { name: "Deferred / not active" })
      .closest(".card");
    expect(deferred?.textContent ?? "").toMatch(/LangGraph adapter/);
    mock.restore();
  });

  it("corrects Overview guidance and links Engineering", async () => {
    const mock = installAppMocks();
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Seneca" })).toBeInTheDocument();
    expect(screen.queryByText(/later phase/i)).toBeNull();
    expect(
      screen.getByText(/ask grounded questions/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Engineering evidence" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open Evaluation/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View Architecture/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "System status" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Workspaces" })).toBeInTheDocument();
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
