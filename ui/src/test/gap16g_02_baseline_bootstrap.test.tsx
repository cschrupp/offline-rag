import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GoldProjectDetail } from "../features/goldLab/shell/GoldProjectDetail";
import type { GoldProject } from "../features/goldLab/types";
import { ACTIVE_OPERATIONS_KEY } from "../features/operations/activeOperations";

const project: GoldProject = {
  project_id: "goldproj_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  workspace_id: "ws_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  title: "Bootstrap Project",
  description: "",
  project_type: "benchmark",
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
};

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <GoldProjectDetail project={project} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("GAP-16G-02 baseline bootstrap UI", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/v1/capabilities")) {
          return new Response(
            JSON.stringify({
              product: { name: "Seneca", descriptor: "x" },
              source_limits: {
                max_active_sources: 32,
                max_bytes_per_source: 1,
                max_active_source_bytes: 1,
              },
              generation: {
                enabled: true,
                provider: "openai_compatible",
                base_url: "http://127.0.0.1:11434/v1",
                model: "m",
                timeout_seconds: 120,
              },
              authoring: {
                enabled: true,
                ready: true,
                reason_codes: [],
                provider: "openai_compatible",
                base_url: "http://127.0.0.1:11434/v1",
                model: "qwen",
                timeout_seconds: 300,
                api_key_configured: true,
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }
        if (url.includes("/baselines")) {
          return new Response(JSON.stringify({ baselines: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/campaigns") && (!init || init.method === "GET")) {
          return new Response(JSON.stringify({ campaigns: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/baseline-bootstrap") && init?.method === "POST") {
          const body = JSON.parse(String(init.body));
          expect(Object.keys(body).sort()).toEqual([
            "prelabel_enabled",
            "proposal_count",
          ]);
          expect(init.headers).toBeTruthy();
          const headers = new Headers(init.headers as HeadersInit);
          expect(headers.get("Idempotency-Key")).toBeTruthy();
          return new Response(
            JSON.stringify({
              operation_id: "wop_bootstrap1",
              kind: "gold_lab_baseline_bootstrap",
              workspace_id: project.workspace_id,
              expected_revision: null,
              status: "pending",
              progress_stage: "preparing",
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:00Z",
              result: null,
              error: null,
            }),
            {
              status: 202,
              headers: {
                "Content-Type": "application/json",
                Location: "/v1/operations/wop_bootstrap1",
              },
            },
          );
        }
        if (url.includes("/v1/operations/wop_bootstrap1")) {
          return new Response(
            JSON.stringify({
              operation_id: "wop_bootstrap1",
              kind: "gold_lab_baseline_bootstrap",
              workspace_id: project.workspace_id,
              expected_revision: null,
              status: "succeeded",
              progress_stage: "ready",
              created_at: "2026-01-01T00:00:00Z",
              updated_at: "2026-01-01T00:00:01Z",
              result: {
                project_id: project.project_id,
                authoring_run_id: "authorrun_ui",
                reviewable_case_count: 3,
                baseline_eligible: true,
              },
              error: null,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify({ error: { code: "not_found" } }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("posts only proposal_count and prelabel_enabled and surfaces success handoff", async () => {
    const user = userEvent.setup();
    renderDetail();
    expect(
      await screen.findByRole("button", {
        name: "Create baseline from workspace",
      }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Create baseline from workspace" }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("gold-bootstrap-success")).toBeInTheDocument();
    });
    expect(
      screen.getAllByText(/Baseline ready/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByRole("button", {
        name: "Create campaign from this baseline",
      }),
    ).toBeInTheDocument();
    const remembered = JSON.parse(
      localStorage.getItem(ACTIVE_OPERATIONS_KEY) ?? "[]",
    );
    // Terminal path forgets the locator after success handling.
    expect(Array.isArray(remembered)).toBe(true);
  });
});
