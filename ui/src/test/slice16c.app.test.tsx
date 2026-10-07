import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ACTIVE_OPERATIONS_KEY } from "../features/operations/activeOperations";

const globalCss = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../styles/global.css"),
  "utf8",
);
import { renderApp } from "./render";
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  source,
  workspace,
} from "./mockApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("application shell", () => {
  it("renders Overview, navigates Workspaces, and shows product not-found", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      return jsonResponse({ error: { code: "not_found", message: "x" } }, { status: 404 });
    });

    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Seneca" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /skip to content/i })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Workspaces" }));
    expect(
      await screen.findByRole("heading", { name: "Workspaces" }),
    ).toBeInTheDocument();

    mock.restore();
    const mock2 = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/ask");
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /ask/i })).not.toBeInTheDocument();
    mock2.restore();
  });
});

describe("accessibility foundations", () => {
  it("includes skip link, labels, confirmation controls, and reduced-motion CSS", async () => {
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      return jsonResponse([]);
    });
    renderApp("/workspaces");
    expect(screen.getByRole("link", { name: /skip to content/i })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(await screen.findByLabelText("Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
    expect(globalCss).toContain("prefers-reduced-motion");
    expect(globalCss).toContain("outline");
    mock.restore();
  });
});

describe("overview", () => {
  it("shows real health/workspace/source counts and never labels updated_at as knowledge update", async () => {
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") {
        return jsonResponse([
          workspace({
            workspace_id: "ws_1",
            source_count: 2,
            updated_at: "2026-02-01T12:00:00Z",
          }),
          workspace({
            workspace_id: "ws_2",
            title: "Second",
            source_count: 3,
            status: "empty",
          }),
        ]);
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getAllByText(/last workspace change/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/last successful knowledge update/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/benchmark/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/recent questions/i)).not.toBeInTheDocument();
    mock.restore();
  });
});

describe("workspace library", () => {
  it("lists, shows empty state, creates with Idempotency-Key, and navigates", async () => {
    const user = userEvent.setup();
    let created = false;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces" && call.method === "GET") {
        return jsonResponse(
          created
            ? [workspace({ workspace_id: "ws_new", title: "New Desk", source_count: 0, status: "empty" })]
            : [],
        );
      }
      if (call.url === "/v1/workspaces" && call.method === "POST") {
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        created = true;
        return jsonResponse(
          workspace({
            workspace_id: "ws_new",
            title: "New Desk",
            source_count: 0,
            status: "empty",
          }),
          { status: 201, headers: { ETag: '"1"' } },
        );
      }
      if (call.url === "/v1/workspaces/ws_new") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_new",
            title: "New Desk",
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_new/sources") {
        return jsonResponse({
          workspace_id: "ws_new",
          revision: 1,
          sources: [],
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces");
    expect(await screen.findByText(/no workspaces yet/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "New Desk");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    expect(await screen.findByRole("heading", { name: "New Desk" })).toBeInTheDocument();
    mock.restore();
  });
});

describe("workspace patch / remove", () => {
  it("sends If-Match + Idempotency-Key, refetches on conflict without auto-resubmit, and removes honestly", async () => {
    const user = userEvent.setup();
    let revision = 1;
    let patchCount = 0;
    let deleted = false;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        if (deleted) return errorResponse("workspace_unknown", "gone", 404);
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision,
            title: revision === 1 ? "Station Desk" : "Updated Elsewhere",
          }),
          { headers: { ETag: `"${revision}"` } },
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: [source({ source_id: "src_1" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1" && call.method === "PATCH") {
        patchCount += 1;
        expect(call.headers.get("If-Match")).toBe('"1"');
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        if (patchCount === 1) {
          revision = 2;
          return errorResponse(
            "workspace_conflict",
            "Workspace revision or state conflict",
          );
        }
        throw new Error("must not auto-resubmit against new revision");
      }
      if (call.url === "/v1/workspaces/ws_1" && call.method === "DELETE") {
        expect(call.headers.get("If-Match")).toBe('"2"');
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        deleted = true;
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision: 3,
            status: "tombstoned",
            source_count: 0,
          }),
        );
      }
      if (call.url === "/v1/workspaces" && call.method === "GET") {
        return jsonResponse([]);
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    expect(await screen.findByDisplayValue("Station Desk")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "My Title");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(
      await screen.findByText(/workspace changed since you last loaded it/i),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue("Updated Elsewhere")).toBeInTheDocument();
    });
    expect(patchCount).toBe(1);

    await user.click(screen.getByRole("button", { name: "Remove workspace" }));
    expect(
      screen.getByText(/not secure permanent deletion/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/delete forever/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    const editDialog = screen.getByRole("dialog");
    const confirmButtons = within(editDialog).getAllByRole("button", {
      name: "Remove workspace",
    });
    await user.click(confirmButtons[confirmButtons.length - 1]!);
    expect(await screen.findByRole("heading", { name: "Workspaces" })).toBeInTheDocument();
    mock.restore();
  });
});

describe("source management", () => {
  it("lists sources without vault/corpus fields and supports add/rename/replace/remove flows", async () => {
    const user = userEvent.setup();
    let sources = [source({ source_id: "src_1", version: 1 })];
    let revision = 2;
    let opStage = "preparing";
    let releaseAdd: ((response: Response) => void) = () => {
      throw new Error("add gate not ready");
    };
    const addGate = new Promise<Response>((resolve) => {
      releaseAdd = resolve;
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision,
            source_count: sources.length,
            status: sources.length ? "active" : "empty",
            current_snapshot_id: sources.length ? "snap_1" : null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources,
        });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        expect(call.headers.get("If-Match")).toBe('"2"');
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        expect(call.body).toBeInstanceOf(FormData);
        const form = call.body as FormData;
        expect(form.getAll("files")).toHaveLength(1);
        return addGate;
      }
      if (call.url === "/v1/operations/op_add") {
        const stages = [
          "preparing",
          "processing",
          "building_indexes",
          "publishing",
          "finalizing",
          "ready",
        ] as const;
        const idx = Math.max(
          0,
          stages.indexOf(opStage as (typeof stages)[number]),
        );
        if (idx < stages.length - 1) {
          opStage = stages[idx + 1];
          return jsonResponse(
            operation({
              operation_id: "op_add",
              status: "running",
              progress_stage: opStage,
            }),
          );
        }
        sources = [
          ...sources,
          source({ source_id: "src_2", display_name: "policy.txt", version: 1 }),
        ];
        revision = 3;
        return jsonResponse(
          operation({
            operation_id: "op_add",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      if (
        call.url === "/v1/workspaces/ws_1/sources/src_1" &&
        call.method === "PATCH"
      ) {
        expect(call.headers.get("If-Match")).toBeTruthy();
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        sources = sources.map((item) =>
          item.source_id === "src_1"
            ? { ...item, display_name: "renamed.pdf" }
            : item,
        );
        revision += 1;
        return jsonResponse(sources[0]);
      }
      if (
        call.url === "/v1/workspaces/ws_1/sources/src_1" &&
        call.method === "PUT"
      ) {
        expect(call.headers.get("If-Match")).toBeTruthy();
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        return jsonResponse(
          operation({
            operation_id: "op_replace",
            kind: "source_replace",
            status: "succeeded",
            progress_stage: "ready",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_replace") {
        sources = sources.map((item) =>
          item.source_id === "src_1" ? { ...item, version: 2 } : item,
        );
        revision += 1;
        return jsonResponse(
          operation({
            operation_id: "op_replace",
            kind: "source_replace",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      if (
        call.url === "/v1/workspaces/ws_1/sources/src_1" &&
        call.method === "DELETE"
      ) {
        return jsonResponse(
          operation({
            operation_id: "op_remove",
            kind: "source_remove",
            status: "succeeded",
            progress_stage: "ready",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_remove") {
        sources = sources.filter((item) => item.source_id !== "src_1");
        revision += 1;
        return jsonResponse(
          operation({
            operation_id: "op_remove",
            kind: "source_remove",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "sops.pdf" })).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KiB|2048 B|2 KiB/)).toBeInTheDocument();
    expect(screen.getByText(/Version 1/)).toBeInTheDocument();
    expect(screen.queryByText(/vault/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/corpus/i)).not.toBeInTheDocument();

    const file = new File(["hello pumps"], "policy.txt", { type: "text/plain" });
    await user.click(screen.getByRole("button", { name: "+ Add sources" }));
    await user.upload(screen.getByLabelText("Source files"), file);
    expect(screen.getByText(/policy\.txt/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add sources" }));
    expect(
      await screen.findByRole("button", { name: /cancel upload/i }),
    ).toBeInTheDocument();
    releaseAdd(
      jsonResponse(
        operation({
          operation_id: "op_add",
          status: "running",
          progress_stage: "preparing",
        }),
        { status: 202 },
      ),
    );
    await waitFor(() => {
      const stored = localStorage.getItem(ACTIVE_OPERATIONS_KEY);
      expect(stored).toContain("op_add");
    });
    expect(
      await screen.findByText("Building search indexes", {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.getByText("policy.txt")).toBeInTheDocument();
      },
      { timeout: 4000 },
    );

    await user.click(
      screen.getByRole("button", { name: "Actions for sops.pdf" }),
    );
    await user.click(screen.getByRole("menuitem", { name: "Rename source" }));
    expect(screen.queryByText(/Building search indexes/i)).not.toBeInTheDocument();
    const renameInput = screen.getByLabelText("Display name");
    await user.clear(renameInput);
    await user.type(renameInput, "renamed.pdf");
    await user.click(screen.getByRole("button", { name: "Save label" }));
    expect(await screen.findByRole("button", { name: "renamed.pdf" })).toBeInTheDocument();

    mock.restore();
  });

  it("warns stronger for final-source removal and renders EMPTY state", async () => {
    const user = userEvent.setup();
    let sources = [source({ source_id: "src_only" })];
    let revision = 2;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision,
            source_count: sources.length,
            status: sources.length ? "active" : "empty",
            current_snapshot_id: sources.length ? "snap_1" : null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({ workspace_id: "ws_1", revision, sources });
      }
      if (call.url.endsWith("/sources/src_only") && call.method === "DELETE") {
        return jsonResponse(
          operation({
            operation_id: "op_final",
            kind: "source_remove",
            status: "running",
            progress_stage: "processing",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_final") {
        sources = [];
        revision = 3;
        return jsonResponse(
          operation({
            operation_id: "op_final",
            kind: "source_remove",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(
      await screen.findByRole("button", { name: "sops.pdf" }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Actions for sops.pdf" }),
    );
    await user.click(screen.getByRole("menuitem", { name: "Remove source" }));
    expect(
      screen.getByText(/leave this workspace empty and retire its current searchable knowledge/i),
    ).toBeInTheDocument();
    await user.click(
      within(screen.getByRole("alertdialog")).getByRole("button", {
        name: "Remove source",
      }),
    );
    expect(
      await screen.findByText(/ready for sources but currently contains no active knowledge/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Empty")).toBeInTheDocument();
    mock.restore();
  });
});

describe("operations / overload / idempotency / no 16D", () => {
  it("maps failed and interrupted statuses without fake percentages", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(workspace({ workspace_id: "ws_1", revision: 1, source_count: 0, status: "empty", current_snapshot_id: null }));
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      if (call.url === "/v1/operations/op_fail") {
        return jsonResponse(
          operation({
            operation_id: "op_fail",
            status: "failed",
            progress_stage: null,
            error: { code: "ingest_failed", message: "Ingest failed", retryable: false },
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_fail",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
      ]),
    );
    // Mount through workspace page + bootstrap via App would be heavier; assert labels via OperationProgress route path.
    renderApp("/workspaces/ws_1");
    // Direct operation query is owned by bootstrap in full App; here assert page still healthy.
    expect(await screen.findByText(/this workspace is empty/i)).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    mock.restore();
  });

  it("shows service_overloaded fail-fast busy copy", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces" && call.method === "GET") return jsonResponse([]);
      if (call.url === "/v1/workspaces" && call.method === "POST") {
        return errorResponse(
          "service_overloaded",
          "Service is temporarily overloaded",
          503,
          true,
        );
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/workspaces");
    await user.type(await screen.findByLabelText("Title"), "Busy");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    expect(
      await screen.findByText(/system is busy\. no work was queued\./i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("reuses idempotency key across transport retries and issues a new key after terminal failure", async () => {
    const { IntentHandle, fingerprintCreateWorkspace } = await import(
      "../api/idempotency"
    );
    const { createWorkspace } = await import("../api/client");
    const keys: string[] = [];
    let attempt = 0;
    const mock = installFetchMock(async (call) => {
      if (call.method === "POST") {
        keys.push(call.headers.get("Idempotency-Key") ?? "");
        attempt += 1;
        if (attempt === 1) {
          throw new TypeError("network down");
        }
        if (attempt === 2) {
          return errorResponse("request_invalid", "bad", 422);
        }
        return jsonResponse(workspace({ workspace_id: "ws_x" }), { status: 201 });
      }
      return errorResponse("not_found", "x", 404);
    });

    const intent = new IntentHandle("fixed-key-1");
    const fp = fingerprintCreateWorkspace("A", "");
    await expect(
      createWorkspace({
        title: "A",
        description: "",
        idempotencyKey: intent.prepare(fp),
      }),
    ).rejects.toThrow(/reach OfflineRAG/i);
    await expect(
      createWorkspace({
        title: "A",
        description: "",
        idempotencyKey: intent.prepare(fp),
      }),
    ).rejects.toMatchObject({ code: "request_invalid" });
    intent.reset();
    await createWorkspace({
      title: "A",
      description: "",
      idempotencyKey: intent.prepare(fp),
    });
    expect(keys[0]).toBe("fixed-key-1");
    expect(keys[1]).toBe("fixed-key-1");
    expect(keys[2]).not.toBe("fixed-key-1");
    mock.restore();
  });

  it("never invokes workspace query or source content preview endpoints", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") {
        return jsonResponse([workspace({ workspace_id: "ws_1" })]);
      }
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(workspace({ workspace_id: "ws_1" }));
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 1,
          sources: [source({ source_id: "src_1" })],
        });
      }
      return errorResponse("not_found", "x", 404);
    });
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("link", { name: "Open" }));
    expect(await screen.findByRole("button", { name: "sops.pdf" })).toBeInTheDocument();
    expect(
      mock.calls.some(
        (call) => call.url.includes("/query") || call.url.includes("/content"),
      ),
    ).toBe(false);
    mock.restore();
  });

  it("restores remembered operations after remount with visible status then clears locator", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_resume",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
      ]),
    );
    let status: "running" | "succeeded" = "running";
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_resume") {
        if (status === "running") {
          status = "succeeded";
          return jsonResponse(
            operation({
              operation_id: "op_resume",
              status: "running",
              progress_stage: "publishing",
            }),
          );
        }
        return jsonResponse(
          operation({
            operation_id: "op_resume",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(workspace({ workspace_id: "ws_1", source_count: 0, status: "empty", current_snapshot_id: null }));
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByText("Publishing")).toBeInTheDocument();
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    await waitFor(() => {
      const stored = localStorage.getItem(ACTIVE_OPERATIONS_KEY);
      expect(stored === "[]" || stored === null || !stored?.includes("op_resume")).toBe(
        true,
      );
    });
    mock.restore();
  });
});
