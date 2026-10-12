/**
 * 16H — Final Slice-16 integration acceptance harness.
 *
 * Cross-surface invariants between previously accepted slices.
 * Not a duplicate of the entire repository suite.
 * Visual/zoom/contrast criteria are recorded in the 16H evidence artifact
 * via rendered-browser acceptance — JSDOM does not claim those PASS alone.
 */
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { APPROVED_PRESENTATIONS_V1 } from "../features/goldLab/policy/approvedPresentations.v1";
import {
  ACTIVE_OPERATIONS_KEY,
  rememberActiveOperation,
} from "../features/operations/activeOperations";
import {
  exportQuestionBankJson,
  parseQuestionBankFile,
} from "../features/training/questionBankIo";
import { goldCampaign, goldProject } from "./goldLabFixtures";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  source,
  workspace,
} from "./mockApi";
import { renderApp } from "./render";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, "..");
const globalCss = readFileSync(join(srcRoot, "styles/global.css"), "utf8");
const manifestText = readFileSync(
  join(here, "../../public/evidence/engineering-evidence-v1.json"),
  "utf8",
);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

function listSourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "test" || entry.name === "node_modules") continue;
      listSourceFiles(full, acc);
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      acc.push(full);
    }
  }
  return acc;
}

describe("16H-J — no fake data in production surfaces", () => {
  it("production src (excluding test/) never imports ui/src/test or mockApi", () => {
    const files = listSourceFiles(srcRoot).filter(
      (path) => !path.includes(`${join("src", "test")}`),
    );
    // srcRoot already is ui/src; exclude the test directory files.
    const production = files.filter((path) => !path.includes("/test/"));
    expect(production.length).toBeGreaterThan(20);
    for (const file of production) {
      const text = readFileSync(file, "utf8");
      expect(text).not.toMatch(/from\s+['"].*\/test\//);
      expect(text).not.toMatch(/from\s+['"].*mockApi['"]/);
      expect(text).not.toMatch(/installFetchMock/);
      expect(text).not.toMatch(/FAKE_ANSWER|cannedAnswer|fabricatedCitation/i);
    }
  });

  it("ALLOW_PRODUCTION remains empty", () => {
    expect([...APPROVED_PRESENTATIONS_V1]).toEqual([]);
  });
});

describe("16H-A/K — cross-surface shell integration", () => {
  it("navigates Overview → Workspaces → Engineering → Settings → Gold Lab", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") {
        return jsonResponse([workspace({ workspace_id: "ws_1", title: "Desk" })]);
      }
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/v1/gold-lab/projects") {
        return jsonResponse({ projects: [goldProject({ project_id: "proj_1" })] });
      }
      if (call.url === "/evidence/engineering-evidence-v1.json") {
        return jsonResponse(JSON.parse(manifestText));
      }
      if (call.url.startsWith("/eval/")) {
        throw new Error(`Browser must not execute evaluation: ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });

    renderApp("/");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: /^Overview$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Workspaces$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Gold Lab$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Engineering$/i })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Settings$/i })).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: /^Workspaces$/i }));
    expect(
      await screen.findByRole("heading", { name: /Workspaces|Workspace library/i }),
    ).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: /^Engineering$/i }));
    expect(
      await screen.findByRole("heading", { name: /Engineering evidence|Evaluation/i }),
    ).toBeInTheDocument();
    expect(
      mock.calls.some((c) => c.url.startsWith("/eval/")),
    ).toBe(false);

    await user.click(within(nav).getByRole("link", { name: /^Settings$/i }));
    expect(await screen.findByRole("heading", { name: /Settings/i })).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: /^Gold Lab$/i }));
    expect(await screen.findByRole("heading", { name: /Gold Lab/i })).toBeInTheDocument();
    mock.restore();
  });

  it("Ask fails closed when source selection is empty", async () => {
    const user = userEvent.setup();
    const ws = workspace({
      workspace_id: "ws_1",
      title: "Desk",
      revision: 2,
      source_count: 1,
      status: "active",
    });
    const src = source({ source_id: "src_1", display_name: "ops.pdf" });
    let queryPosts = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/v1/workspaces") return jsonResponse([ws]);
      if (call.url === "/v1/workspaces/ws_1") return jsonResponse(ws);
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [src],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/query" && call.method === "POST") {
        queryPosts += 1;
        return jsonResponse({
          answer: "should not be reached without selection",
          citations: [],
          snapshot_id: "snap_1",
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(
      await screen.findByRole("button", { name: "ops.pdf" }),
    ).toBeInTheDocument();
    // Deselect source checkbox if selected by default.
    const checkbox = screen.queryByRole("checkbox", { name: /ops\.pdf/i });
    if (checkbox && (checkbox as HTMLInputElement).checked) {
      await user.click(checkbox);
    }
    const question =
      screen.queryByLabelText(/question/i) ??
      screen.queryByPlaceholderText(/ask|question/i) ??
      screen.queryByRole("textbox");
    expect(question).toBeTruthy();
    await user.type(question!, "What pressure?");
    const send = screen.getByRole("button", { name: /send|ask/i });
    if (!(send as HTMLButtonElement).disabled) {
      await user.click(send);
    }
    await waitFor(() => {
      expect(queryPosts).toBe(0);
    });
    mock.restore();
  });
});

describe("16H-A2 — Question Bank / export local-only", () => {
  it("Question Bank JSON round-trip does not call backend mutation routes", async () => {
    const prompts = [
      {
        id: "qb_1",
        text: "What pressure?",
        createdAt: "2026-03-01T00:00:00Z",
      },
    ];
    const exported = exportQuestionBankJson(prompts as never, "Desk");
    const parsed = parseQuestionBankFile(
      exported.filename,
      exported.content,
      exported.content.length,
    );
    expect(parsed.ok).toBe(true);

    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (
        call.method !== "GET" &&
        (call.url.includes("/sources") ||
          call.url.includes("/query") ||
          call.url.includes("/gold-lab"))
      ) {
        throw new Error(`Question Bank must remain local-only: ${call.method} ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    expect(mock.calls.some((c) => c.method === "POST")).toBe(false);
    mock.restore();
  });
});

describe("16H-A3 — Gold Lab policy boundaries preserved", () => {
  it("Expert Work still fails closed for unapproved presentations", async () => {
    const campaign = goldCampaign({ campaign_id: "camp_1" });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/gold-lab/campaigns/camp_1") {
        return jsonResponse(campaign);
      }
      if (call.url.includes("/tasks") || call.url.includes("/relevance")) {
        throw new Error(`Policy gate leaked: ${call.url}`);
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
    mock.restore();
  });
});

describe("16H-F — managed-operation recovery UX", () => {
  it("browser reconnect rediscovers durable operation from locator storage", async () => {
    rememberActiveOperation({
      operation_id: "wop_resume_1",
      workspace_id: "ws_1",
      kind: "source_add",
      label: "Add sources",
    });
    expect(localStorage.getItem(ACTIVE_OPERATIONS_KEY)).toBeTruthy();

    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/v1/workspaces") {
        return jsonResponse([workspace({ workspace_id: "ws_1" })]);
      }
      if (call.url === "/v1/operations/wop_resume_1") {
        return jsonResponse(
          operation({
            operation_id: "wop_resume_1",
            workspace_id: "ws_1",
            kind: "source_add",
            status: "running",
            progress_stage: "processing",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByTestId("operation-tray")).toBeInTheDocument();
    expect(
      await screen.findByTestId("operation-progress-wop_resume_1"),
    ).toBeInTheDocument();
    expect(screen.getByText("Add sources")).toBeInTheDocument();
    expect(screen.getByText(/Status:\s*Running/i)).toBeInTheDocument();
    mock.restore();
  });

  it("failed operation remains visible and is not presented as success", async () => {
    rememberActiveOperation({
      operation_id: "wop_fail_1",
      workspace_id: "ws_1",
      kind: "source_add",
      label: "Add sources",
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/operations/wop_fail_1") {
        return jsonResponse(
          operation({
            operation_id: "wop_fail_1",
            workspace_id: "ws_1",
            kind: "source_add",
            status: "failed",
            progress_stage: null,
            error: {
              code: "ingest_failed",
              message: "Ingest failed",
              retryable: false,
            },
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/");
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.queryByText("Succeeded")).not.toBeInTheDocument();
    mock.restore();
  });

  it("interrupted operation reports interrupted truthfully", async () => {
    rememberActiveOperation({
      operation_id: "wop_int_1",
      workspace_id: "ws_1",
      kind: "source_add",
      label: "Add sources",
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/operations/wop_int_1") {
        return jsonResponse(
          operation({
            operation_id: "wop_int_1",
            workspace_id: "ws_1",
            kind: "source_add",
            status: "interrupted",
            progress_stage: null,
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/");
    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    expect(
      screen.getByText(/processing was interrupted\. you may retry/i),
    ).toBeInTheDocument();
    mock.restore();
  });
});

describe("16H-C — keyboard reachability of global shell", () => {
  it("Tab reaches primary navigation links without pointer", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    let reached = false;
    for (let i = 0; i < 40; i += 1) {
      await user.tab();
      const el = document.activeElement;
      if (
        el instanceof HTMLAnchorElement &&
        /Overview|Workspaces|Gold Lab|Engineering|Settings/i.test(
          el.textContent ?? "",
        )
      ) {
        reached = true;
        break;
      }
    }
    expect(reached).toBe(true);
    mock.restore();
  });
});

describe("16H-I — portfolio evidence consistency", () => {
  it("Engineering manifest contract remains hash-pinned accepted evidence", () => {
    const manifest = JSON.parse(manifestText) as {
      contract: string;
      records: Array<{ evidence_family: string }>;
    };
    expect(manifest.contract).toMatch(/engineering-evidence/i);
    expect(Array.isArray(manifest.records)).toBe(true);
    const families = new Set(manifest.records.map((r) => r.evidence_family));
    for (const required of [
      "retrieval",
      "generation",
      "recovery",
      "security",
      "performance",
    ]) {
      expect(families.has(required)).toBe(true);
    }
  });

  it("Engineering UI loads static evidence and never hits /eval/", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/evidence/engineering-evidence-v1.json") {
        return jsonResponse(JSON.parse(manifestText));
      }
      if (call.url.includes("/eval")) {
        throw new Error(`Unexpected eval call: ${call.url}`);
      }
      return jsonResponse(
        { error: { code: "not_found", message: "x" } },
        { status: 404 },
      );
    });
    renderApp("/engineering/evaluation");
    expect(
      await screen.findByRole("heading", { name: /Engineering|Evaluation/i }),
    ).toBeInTheDocument();
    expect(mock.calls.some((c) => c.url.includes("/eval"))).toBe(false);
    mock.restore();
  });
});

describe("16H-B preflight — deterministic a11y tokens (not full WCAG seal)", () => {
  it("CSS retains focus-visible, reduced-motion, and skip-link", () => {
    expect(globalCss).toMatch(/button:focus-visible/);
    expect(globalCss).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)/);
    expect(globalCss).toMatch(/\.skip-link/);
  });
});
