import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EngineeringEvidenceManifest } from "../features/engineering/evidenceTypes";
import { renderApp } from "./render";
import { installFetchMock, jsonResponse } from "./mockApi";

const here = dirname(fileURLToPath(import.meta.url));
const manifestPath = join(
  here,
  "../../public/evidence/engineering-evidence-v3.json",
);
const sourceManifest = JSON.parse(
  readFileSync(manifestPath, "utf8"),
) as EngineeringEvidenceManifest;

type MutableRecord = {
  evidence_id: string;
  presentation: Record<string, unknown>;
};
type MutableManifest = { records: MutableRecord[] };

afterEach(() => cleanup());

function installMocks(manifest: unknown = sourceManifest) {
  return installFetchMock(async ({ url, method }) => {
    if (url === "/health/ready") return jsonResponse({ status: "ready" });
    if (url === "/v1/workspaces") return jsonResponse([]);
    if (url === "/evidence/engineering-evidence-v3.json") {
      expect(method).toBe("GET");
      return jsonResponse(manifest);
    }
    if (url.includes("/eval/")) {
      throw new Error(`Unexpected scientific runtime call: ${method} ${url}`);
    }
    return jsonResponse({ error: { code: "not_found", message: "x" } }, { status: 404 });
  });
}

function record(manifest: MutableManifest, evidenceId: string): MutableRecord {
  const found = manifest.records.find((item) => item.evidence_id === evidenceId);
  if (!found) throw new Error(`Test fixture record missing: ${evidenceId}`);
  return found;
}

function factMetric(
  manifest: MutableManifest,
  evidenceId: string,
  factId: string,
  metricId: string,
): { metric: { value: number } } {
  const presentation = record(manifest, evidenceId).presentation;
  const facts = presentation.facts as Array<{
    fact_id: string;
    metrics: Array<{ metric_id: string; metric: { value: number } }>;
  }>;
  const fact = facts.find((item) => item.fact_id === factId);
  const metric = fact?.metrics.find((item) => item.metric_id === metricId);
  if (!metric) throw new Error(`Test fixture metric missing: ${evidenceId}/${factId}/${metricId}`);
  return metric;
}

describe("18D-R Engineering routes", () => {
  it.each([
    ["/engineering", "Engineering summary"],
    ["/engineering/summary", "Engineering summary"],
    ["/engineering/evidence", "Evidence"],
    ["/engineering/evaluation", "Evidence"],
    ["/engineering/architecture", "Architecture"],
  ])("renders %s at its supported destination", async (path, heading) => {
    const mock = installMocks();
    renderApp(path);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Engineering" })).toHaveTextContent(
      "SummaryArchitectureEvidence",
    );
    mock.restore();
  });

  it("links the Overview entry point to Summary and exposes deep evidence links", async () => {
    const mock = installMocks();
    renderApp("/");
    const overview = await screen.findByRole("heading", { name: "Seneca" });
    expect(overview).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Engineering" })).toHaveAttribute(
      "href",
      "/engineering/summary",
    );
    cleanup();

    renderApp("/engineering/summary");
    await screen.findByTestId("engineering-summary");
    expect(
      document.querySelector(
        'a[href="/engineering/evidence#evidence-generation.grounding-and-external-boundary"]',
      ),
    ).toBeInTheDocument();
    mock.restore();
  });
});

describe("18D-R semantic evidence projection", () => {
  it("updates retrieval, generation, capacity, and image values from the manifest", async () => {
    const fixture = structuredClone(sourceManifest) as unknown as MutableManifest;
    const retrieval = record(fixture, "performance.slice14c").presentation;
    const variants = retrieval.variants as Array<{
      variant_id: string;
      quality: { ndcg_at_10: { value: number } };
    }>;
    const hybrid = variants.find((item) => item.variant_id === "hybrid");
    if (!hybrid) throw new Error("Test fixture hybrid variant missing");
    hybrid.quality.ndcg_at_10.value = 0.321;

    factMetric(fixture, "generation.slice10e", "development-counts", "answered").metric.value = 11;
    const generation = record(fixture, "generation.slice10e").presentation;
    const prompts = generation.prompts as Array<{
      prompt_id: string;
      metrics: { answer_rate: { value: number } };
    }>;
    const prompt = prompts.find((item) => item.prompt_id === "prompt-grounded-v1");
    if (!prompt) throw new Error("Test fixture generation prompt missing");
    prompt.metrics.answer_rate.value = 0.5;

    factMetric(fixture, "capacity.large-source-envelope", "product-limit", "pdf-limit").metric.value = 1048576;
    factMetric(fixture, "release.verification", "current-cpu-image", "image-bytes").metric.value = 2097152;

    const mock = installMocks(fixture);
    renderApp("/engineering/summary");
    const summary = await screen.findByTestId("engineering-summary");
    expect(within(summary).getByText("0.321")).toBeInTheDocument();
    expect(within(summary).getByText("50.0%")).toBeInTheDocument();
    expect(within(summary).getByText("1 MiB")).toBeInTheDocument();
    expect(within(summary).getByText("2 MiB")).toBeInTheDocument();
    expect(within(summary).getByRole("heading", { name: /Seneca answered 11 of 22/ })).toBeInTheDocument();
    mock.restore();
  });

  it("fails visibly when a required semantic variant is missing", async () => {
    const fixture = structuredClone(sourceManifest) as unknown as MutableManifest;
    const variants = record(fixture, "performance.slice14c").presentation.variants as Array<{
      variant_id: string;
    }>;
    record(fixture, "performance.slice14c").presentation.variants = variants.filter(
      (item) => item.variant_id !== "hybrid",
    );
    const mock = installMocks(fixture);
    renderApp("/engineering/summary");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Required variant is missing: performance.slice14c/hybrid",
    );
    mock.restore();
  });

  it("keeps internal evidence identifiers and hash families out of the default flow", async () => {
    const mock = installMocks();
    const { container } = renderApp("/engineering/summary");
    const summary = await screen.findByTestId("engineering-summary");
    const visibleText = summary.textContent ?? "";
    expect(visibleText).not.toMatch(/engmanifest_|indicatorcatalog_|perfrun_|perfsuite_/i);
    expect(visibleText).not.toMatch(/[0-9a-f]{40,}/i);
    expect(visibleText).not.toMatch(/\b(?:Slice\s+\d|REL-\d|BETA-CONV|L[56])\b/i);
    expect(container.textContent).toContain("The Summary is the explanation; Evidence is the audit trail.");
    mock.restore();
  });
});
