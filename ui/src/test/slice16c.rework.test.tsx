import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  IntentHandle,
  fingerprintAddSources,
  fingerprintCreateWorkspace,
  fingerprintPatchWorkspace,
  fingerprintRenameSource,
  fingerprintReplaceSource,
} from "../api/idempotency";
import { ACTIVE_OPERATIONS_KEY } from "../features/operations/activeOperations";
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
  document.getElementById("root")?.removeAttribute("inert");
});

describe("F1 resumed operation visibility", () => {
  it("renders remembered RUNNING operation stage after fresh mount", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_run",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
      ]),
    );
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_run") {
        return jsonResponse(
          operation({
            operation_id: "op_run",
            status: "running",
            progress_stage: "building_indexes",
          }),
        );
      }
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByTestId("operation-tray")).toBeInTheDocument();
    expect(await screen.findByText("Add sources")).toBeInTheDocument();
    expect(screen.getByText("Building search indexes")).toBeInTheDocument();
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    mock.restore();
  });

  it("surfaces Ready on SUCCEEDED, invalidates caches, and clears locator", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_ok",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
      ]),
    );
    let polls = 0;
    let workspaceHits = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_ok") {
        polls += 1;
        if (polls === 1) {
          return jsonResponse(
            operation({
              operation_id: "op_ok",
              status: "running",
              progress_stage: "publishing",
            }),
          );
        }
        return jsonResponse(
          operation({
            operation_id: "op_ok",
            status: "succeeded",
            progress_stage: "ready",
          }),
        );
      }
      if (call.url === "/v1/workspaces") {
        workspaceHits += 1;
        return jsonResponse([]);
      }
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    await waitFor(() => {
      const stored = localStorage.getItem(ACTIVE_OPERATIONS_KEY);
      expect(stored === "[]" || stored === null || !stored?.includes("op_ok")).toBe(
        true,
      );
    });
    expect(screen.getByText(/workspace knowledge has been updated/i)).toBeInTheDocument();
    expect(workspaceHits).toBeGreaterThan(0);
    mock.restore();
  });

  it("surfaces FAILED message/code and does not silently disappear", async () => {
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
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_fail") {
        return jsonResponse(
          operation({
            operation_id: "op_fail",
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
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Ingest failed")).toBeInTheDocument();
    expect(screen.getByText("ingest_failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    mock.restore();
  });

  it("surfaces INTERRUPTED guidance", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_int",
          workspace_id: "ws_1",
          kind: "source_replace",
          label: "Replace source",
        },
      ]),
    );
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_int") {
        return jsonResponse(
          operation({
            operation_id: "op_int",
            kind: "source_replace",
            status: "interrupted",
            progress_stage: null,
          }),
        );
      }
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    expect(
      screen.getByText(/processing was interrupted\. you may retry/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("surfaces bounded lookup error and stops invisible polling", async () => {
    localStorage.setItem(
      ACTIVE_OPERATIONS_KEY,
      JSON.stringify([
        {
          operation_id: "op_missing",
          workspace_id: "ws_1",
          kind: "source_add",
          label: "Add sources",
        },
      ]),
    );
    let polls = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/operations/op_missing") {
        polls += 1;
        return errorResponse("operation_unknown", "Managed operation not found", 404);
      }
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    expect(await screen.findByTestId("operation-lookup-error")).toBeInTheDocument();
    expect(screen.getByText(/managed operation not found/i)).toBeInTheDocument();
    const pollsAfterVisible = polls;
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(polls).toBe(pollsAfterVisible);
    mock.restore();
  });
});

describe("F2 canonical intent fingerprints", () => {
  it("reuses key for same request and rotates when payload changes", () => {
    const intent = IntentHandle.newIntent();
    const k1 = intent.prepare(fingerprintCreateWorkspace("Manuals", ""));
    const k2 = intent.prepare(fingerprintCreateWorkspace("Manuals", ""));
    expect(k2).toBe(k1);
    const k3 = intent.prepare(fingerprintCreateWorkspace("Fire Manuals", ""));
    expect(k3).not.toBe(k1);
  });

  it("rotates key when metadata, files, rename, or replace identity changes", () => {
    const patch = IntentHandle.newIntent();
    const p1 = patch.prepare(
      fingerprintPatchWorkspace({
        workspaceId: "ws_1",
        revision: 1,
        title: "A",
        description: "",
      }),
    );
    expect(
      patch.prepare(
        fingerprintPatchWorkspace({
          workspaceId: "ws_1",
          revision: 1,
          title: "A",
          description: "",
        }),
      ),
    ).toBe(p1);
    expect(
      patch.prepare(
        fingerprintPatchWorkspace({
          workspaceId: "ws_1",
          revision: 2,
          title: "A",
          description: "",
        }),
      ),
    ).not.toBe(p1);

    const add = IntentHandle.newIntent();
    const fileA = new File(["a"], "a.txt", { type: "text/plain" });
    const fileB = new File(["b"], "b.txt", { type: "text/plain" });
    const a1 = add.prepare(
      fingerprintAddSources({ workspaceId: "ws_1", revision: 1, files: [fileA] }),
    );
    expect(
      add.prepare(
        fingerprintAddSources({ workspaceId: "ws_1", revision: 1, files: [fileA] }),
      ),
    ).toBe(a1);
    expect(
      add.prepare(
        fingerprintAddSources({ workspaceId: "ws_1", revision: 1, files: [fileB] }),
      ),
    ).not.toBe(a1);

    const rename = IntentHandle.newIntent();
    const r1 = rename.prepare(
      fingerprintRenameSource({
        workspaceId: "ws_1",
        sourceId: "src_1",
        revision: 1,
        displayName: "old.pdf",
      }),
    );
    expect(
      rename.prepare(
        fingerprintRenameSource({
          workspaceId: "ws_1",
          sourceId: "src_1",
          revision: 1,
          displayName: "new.pdf",
        }),
      ),
    ).not.toBe(r1);

    const replace = IntentHandle.newIntent();
    const rep1 = replace.prepare(
      fingerprintReplaceSource({
        workspaceId: "ws_1",
        sourceId: "src_1",
        revision: 1,
        file: fileA,
      }),
    );
    expect(
      replace.prepare(
        fingerprintReplaceSource({
          workspaceId: "ws_1",
          sourceId: "src_1",
          revision: 1,
          file: fileB,
        }),
      ),
    ).not.toBe(rep1);
  });

  it("create workspace reuses key after network ambiguity and rotates after edit", async () => {
    const user = userEvent.setup();
    const keys: string[] = [];
    let attempt = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces" && call.method === "GET") {
        return jsonResponse([]);
      }
      if (call.url === "/v1/workspaces" && call.method === "POST") {
        keys.push(call.headers.get("Idempotency-Key") ?? "");
        attempt += 1;
        if (attempt <= 2) {
          throw new TypeError("network down");
        }
        return jsonResponse(
          workspace({ workspace_id: "ws_new", title: "Fire Manuals", status: "empty", source_count: 0 }),
          { status: 201 },
        );
      }
      if (call.url === "/v1/workspaces/ws_new") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_new",
            title: "Fire Manuals",
            status: "empty",
            source_count: 0,
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_new/sources") {
        return jsonResponse({ workspace_id: "ws_new", revision: 1, sources: [] });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces");
    await user.type(await screen.findByLabelText("Title"), "Manuals");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    expect(await screen.findByText(/could not reach offlinerag/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    expect(keys[0]).toBe(keys[1]);
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Fire Manuals");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));
    await waitFor(() => expect(keys.length).toBe(3));
    expect(keys[2]).not.toBe(keys[0]);
    mock.restore();
  });
});

describe("F3 accessible dialogs and nested interactives", () => {
  it("confirmation traps focus, Escape closes, and restores trigger focus", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(workspace({ workspace_id: "ws_1", revision: 2 }));
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [source({ source_id: "src_1" })],
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const actionsBtn = await screen.findByRole("button", {
      name: "Actions for sops.pdf",
    });
    await user.click(actionsBtn);
    const removeBtn = await screen.findByRole("menuitem", {
      name: "Remove source",
    });
    await user.click(removeBtn);
    const dialog = await screen.findByRole("alertdialog");
    await waitFor(() => {
      expect(dialog.contains(document.activeElement)).toBe(true);
    });

    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(actionsBtn);
    });
    mock.restore();
  });

  it("rename and replace dialogs share focus containment behavior", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(workspace({ workspace_id: "ws_1", revision: 2 }));
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [source({ source_id: "src_1" })],
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const actionsBtn = await screen.findByRole("button", {
      name: "Actions for sops.pdf",
    });
    await user.click(actionsBtn);
    await user.click(screen.getByRole("menuitem", { name: "Rename source" }));
    const renameDialog = await screen.findByRole("dialog", {
      name: /rename display label/i,
    });
    await waitFor(() => {
      expect(renameDialog.contains(document.activeElement)).toBe(true);
    });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => {
      expect(document.activeElement).toBe(actionsBtn);
    });

    await user.click(actionsBtn);
    await user.click(
      screen.getByRole("menuitem", { name: "Replace current version" }),
    );
    const replaceDialog = await screen.findByRole("dialog", {
      name: /replace current version/i,
    });
    await waitFor(() => {
      expect(replaceDialog.contains(document.activeElement)).toBe(true);
    });
    await user.tab();
    expect(replaceDialog.contains(document.activeElement)).toBe(true);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => {
      expect(document.activeElement).toBe(actionsBtn);
    });
    mock.restore();
  });

  it("does not nest buttons inside anchors on Overview/Library", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") {
        return jsonResponse([workspace({ workspace_id: "ws_1" })]);
      }
      return errorResponse("not_found", "x", 404);
    });

    const first = renderApp("/");
    await screen.findByRole("heading", { name: "Seneca" });
    expect(first.container.querySelector("a button")).toBeNull();
    first.unmount();
    mock.restore();

    const mock2 = installFetchMock(async (call) => {
      if (call.url === "/v1/workspaces") {
        return jsonResponse([workspace({ workspace_id: "ws_1" })]);
      }
      return errorResponse("not_found", "x", 404);
    });
    const second = renderApp("/workspaces");
    expect(
      await within(second.container).findByRole("link", { name: "Open / Manage" }),
    ).toBeInTheDocument();
    expect(second.container.querySelector("a button")).toBeNull();
    mock2.restore();
  });
});
