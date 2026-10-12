import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  goldBootstrapOperationFailureMessage,
  managedOperationFailureMessage,
} from "../features/operations/operationErrorMessages";
import {
  ACTIVE_OPERATIONS_KEY,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import { goldProject } from "./goldLabFixtures";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  workspace,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

const PROJECT = goldProject({
  project_id: "goldproj_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  workspace_id: "ws_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
});

function authoringReadyCapabilities() {
  return {
    ...capabilities(),
    authoring: {
      enabled: true,
      ready: true,
      reason_codes: [],
      provider: "openai_compatible",
      base_url: "http://127.0.0.1:11434/v1",
      model: "qwen",
      timeout_seconds: 300,
      network_policy: "localhost_only",
      api_key_configured: true,
    },
  };
}

function failedBootstrapOp(partial: {
  operation_id: string;
  reason: string;
  message?: string;
}) {
  return operation({
    operation_id: partial.operation_id,
    kind: "gold_lab_baseline_bootstrap",
    workspace_id: PROJECT.workspace_id,
    status: "failed",
    progress_stage: "pooling",
    error: {
      code: "gold_conflict",
      message:
        partial.message ??
        "Gold Lab state conflicts with the requested operation",
      retryable: false,
      details: { reason: partial.reason },
    },
  });
}

describe("Gold bootstrap operation failure copy", () => {
  it("maps zero_reviewable_cases without leaking codes or raw message", () => {
    const op = failedBootstrapOp({
      operation_id: "wop_1",
      reason: "zero_reviewable_cases",
      message: "SENTINEL_BACKEND_MESSAGE",
    });
    const text = managedOperationFailureMessage(op);
    expect(text).toMatch(/no reviewable evidence cases/i);
    expect(text).not.toMatch(/gold_conflict/i);
    expect(text).not.toMatch(/zero_reviewable_cases/i);
    expect(text).not.toContain("SENTINEL_BACKEND_MESSAGE");
  });

  it("maps representative bootstrap reasons and unknown fallback", () => {
    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "proposal_count_exceeds_eligible_population" },
      }),
    ).toMatch(/larger than the eligible workspace population/i);

    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "publication_drift_before_commit" },
      }),
    ).toMatch(/workspace publication changed while the baseline/i);

    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "project_drift_before_commit" },
      }),
    ).toMatch(/Gold project changed while the baseline/i);

    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "staged_run_invalid" },
      }),
    ).toMatch(/could not verify the staged baseline state/i);

    expect(
      goldBootstrapOperationFailureMessage({
        code: "gold_conflict",
        details: { reason: "canonical_destination_conflict" },
      }),
    ).toMatch(/did not overwrite existing canonical state/i);

    const unknown = goldBootstrapOperationFailureMessage({
      code: "gold_conflict",
      message: "SENTINEL",
      details: { reason: "totally_unknown_internal_reason" },
    });
    expect(unknown).toMatch(/state conflicted with the requested operation/i);
    expect(unknown).not.toContain("totally_unknown_internal_reason");
    expect(unknown).not.toContain("SENTINEL");
    expect(unknown).not.toMatch(/gold_conflict/i);
  });
});

describe("operation-tray CSS layout contract", () => {
  it("uses fixed lower-right tray and drops sticky top", () => {
    const cssPath = join(
      dirname(fileURLToPath(import.meta.url)),
      "../styles/global.css",
    );
    const css = readFileSync(cssPath, "utf8");
    const match = css.match(/\.operation-tray\s*\{([^}]+)\}/g);
    expect(match).toBeTruthy();
    const blocks = match!.join("\n");
    expect(blocks).toMatch(/position:\s*fixed/);
    expect(blocks).toMatch(/bottom:/);
    expect(blocks).toMatch(/right:/);
    expect(blocks).not.toMatch(/position:\s*sticky/);
    expect(blocks).not.toMatch(/top:\s*0/);
  });
});

describe("global tray single authority and recovery", () => {
  it("shows one tray card for a remembered failed Gold bootstrap", async () => {
    rememberActiveOperation({
      operation_id: "wop_gold_fail",
      workspace_id: PROJECT.workspace_id,
      kind: "gold_lab_baseline_bootstrap",
      label: "Create baseline from workspace",
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") {
        return jsonResponse(authoringReadyCapabilities());
      }
      if (call.url === "/v1/workspaces") {
        return jsonResponse([
          workspace({ workspace_id: PROJECT.workspace_id }),
        ]);
      }
      if (call.url === `/v1/operations/wop_gold_fail`) {
        return jsonResponse(
          failedBootstrapOp({
            operation_id: "wop_gold_fail",
            reason: "zero_reviewable_cases",
            message: "SENTINEL_BACKEND_MESSAGE",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    const tray = await screen.findByTestId("operation-tray");
    expect(
      await within(tray).findByTestId("operation-progress-wop_gold_fail"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByTestId("operation-progress-wop_gold_fail"),
    ).toHaveLength(1);
    expect(
      within(tray).getByText(/no reviewable evidence cases/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("gold_conflict")).not.toBeInTheDocument();
    expect(screen.queryByText("zero_reviewable_cases")).not.toBeInTheDocument();
    expect(screen.queryByText("SENTINEL_BACKEND_MESSAGE")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    mock.restore();
  });

  it("stacks multiple remembered operations in one tray", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "wop_a",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
        {
          operation_id: "wop_b",
          workspace_id: "ws_1",
          kind: "source_remove",
          label: "Remove source",
        },
      ]),
    );
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") {
        return jsonResponse(authoringReadyCapabilities());
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/operations/wop_a") {
        return jsonResponse(
          operation({
            operation_id: "wop_a",
            status: "running",
            progress_stage: "processing",
            kind: "source_add",
          }),
        );
      }
      if (call.url === "/v1/operations/wop_b") {
        return jsonResponse(
          operation({
            operation_id: "wop_b",
            status: "running",
            progress_stage: "processing",
            kind: "source_remove",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    const tray = await screen.findByTestId("operation-tray");
    expect(screen.getAllByTestId("operation-tray")).toHaveLength(1);
    expect(
      await within(tray).findByTestId("operation-progress-wop_a"),
    ).toBeInTheDocument();
    expect(
      within(tray).getByTestId("operation-progress-wop_b"),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId(/operation-progress-/)).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
    mock.restore();
  });

  it("dismisses terminal cards without mutating server state", async () => {
    const user = userEvent.setup();
    rememberActiveOperation({
      operation_id: "wop_done",
      workspace_id: "ws_1",
      kind: "source_add",
      label: "Add sources",
    });
    const methods: string[] = [];
    const mock = installFetchMock(async (call) => {
      methods.push(`${call.method} ${call.url}`);
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") {
        return jsonResponse(authoringReadyCapabilities());
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/operations/wop_done") {
        return jsonResponse(
          operation({
            operation_id: "wop_done",
            status: "succeeded",
            progress_stage: "ready",
            kind: "source_add",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(
      await screen.findByTestId("operation-progress-wop_done"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => {
      expect(
        screen.queryByTestId("operation-progress-wop_done"),
      ).not.toBeInTheDocument();
    });
    expect(methods.some((m) => m.startsWith("DELETE "))).toBe(false);
    expect(methods.some((m) => m.startsWith("PATCH "))).toBe(false);
    mock.restore();
  });

  it("Gold bootstrap admission uses tray only (no inline duplicate)", async () => {
    const user = userEvent.setup();
    let baselinesHits = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") {
        return jsonResponse(authoringReadyCapabilities());
      }
      if (call.url === "/v1/workspaces") {
        return jsonResponse([
          workspace({ workspace_id: PROJECT.workspace_id }),
        ]);
      }
      if (call.url === `/v1/gold-lab/projects/${PROJECT.project_id}`) {
        return jsonResponse(PROJECT);
      }
      if (
        call.url === `/v1/gold-lab/projects/${PROJECT.project_id}/baselines`
      ) {
        baselinesHits += 1;
        return jsonResponse({ baselines: [] });
      }
      if (
        call.url === `/v1/gold-lab/projects/${PROJECT.project_id}/campaigns`
      ) {
        return jsonResponse({ campaigns: [] });
      }
      if (
        call.url.includes("/baseline-bootstrap") &&
        call.method === "POST"
      ) {
        return jsonResponse(
          operation({
            operation_id: "wop_boot_dup",
            kind: "gold_lab_baseline_bootstrap",
            workspace_id: PROJECT.workspace_id,
            status: "pending",
            progress_stage: "preparing",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/wop_boot_dup") {
        return jsonResponse(
          failedBootstrapOp({
            operation_id: "wop_boot_dup",
            reason: "zero_reviewable_cases",
            message: "SENTINEL_BACKEND_MESSAGE",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp(`/gold-lab/projects/${PROJECT.project_id}`);
    expect(
      await screen.findByRole("button", {
        name: "Create baseline from workspace",
      }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", {
        name: "Create baseline from workspace",
      }),
    );

    const card = await screen.findByTestId(
      "operation-progress-wop_boot_dup",
      {},
      { timeout: 4000 },
    );
    const tray = screen.getByTestId("operation-tray");
    expect(tray.contains(card)).toBe(true);
    expect(
      screen.getAllByTestId("operation-progress-wop_boot_dup"),
    ).toHaveLength(1);
    expect(
      within(tray).getByText(/no reviewable evidence cases/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("gold_conflict")).not.toBeInTheDocument();
    expect(screen.queryByText("zero_reviewable_cases")).not.toBeInTheDocument();
    expect(screen.queryByText("SENTINEL_BACKEND_MESSAGE")).not.toBeInTheDocument();
    expect(baselinesHits).toBeGreaterThan(0);
    mock.restore();
  });

  it("refresh rediscovers locator and invalidates baselines on Gold success", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "wop_boot_ok",
          workspace_id: PROJECT.workspace_id,
          kind: "gold_lab_baseline_bootstrap",
          label: "Create baseline from workspace",
        },
      ]),
    );
    let opHits = 0;
    let baselineHits = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") {
        return jsonResponse(authoringReadyCapabilities());
      }
      if (call.url === "/v1/workspaces") {
        return jsonResponse([
          workspace({ workspace_id: PROJECT.workspace_id }),
        ]);
      }
      if (call.url === `/v1/gold-lab/projects/${PROJECT.project_id}`) {
        return jsonResponse(PROJECT);
      }
      if (
        call.url === `/v1/gold-lab/projects/${PROJECT.project_id}/baselines`
      ) {
        baselineHits += 1;
        return jsonResponse({ baselines: [] });
      }
      if (
        call.url === `/v1/gold-lab/projects/${PROJECT.project_id}/campaigns`
      ) {
        return jsonResponse({ campaigns: [] });
      }
      if (call.url === "/v1/operations/wop_boot_ok") {
        opHits += 1;
        if (opHits === 1) {
          return jsonResponse(
            operation({
              operation_id: "wop_boot_ok",
              kind: "gold_lab_baseline_bootstrap",
              workspace_id: PROJECT.workspace_id,
              status: "running",
              progress_stage: "pooling",
            }),
          );
        }
        return jsonResponse(
          operation({
            operation_id: "wop_boot_ok",
            kind: "gold_lab_baseline_bootstrap",
            workspace_id: PROJECT.workspace_id,
            status: "succeeded",
            progress_stage: "ready",
            result: {
              project_id: PROJECT.project_id,
              authoring_run_id: "authorrun_ok",
              reviewable_case_count: 2,
              baseline_eligible: true,
            },
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp(`/gold-lab/projects/${PROJECT.project_id}`);
    expect(await screen.findByTestId("operation-tray")).toBeInTheDocument();
    expect(opHits).toBeGreaterThan(0);
    await waitFor(
      () => {
        expect(screen.getByText(/Baseline ready/i)).toBeInTheDocument();
      },
      { timeout: 4000 },
    );
    await waitFor(
      () => {
        expect(baselineHits).toBeGreaterThan(1);
      },
      { timeout: 4000 },
    );
    const stored = localStorage.getItem(ACTIVE_OPERATIONS_KEY) ?? "[]";
    expect(stored.includes("wop_boot_ok")).toBe(false);
    mock.restore();
  });
});
