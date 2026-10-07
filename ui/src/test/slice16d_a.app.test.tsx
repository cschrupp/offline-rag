import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "./render";
import { ACTIVE_OPERATIONS_KEY } from "../features/operations/activeOperations";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  source,
  workspace,
} from "./mockApi";

const indexHtml = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../index.html"),
  "utf8",
);
const formatSource = readFileSync(
  join(
    dirname(fileURLToPath(import.meta.url)),
    "../features/workspaces/format.ts",
  ),
  "utf8",
);

afterEach(() => {
  vi.restoreAllMocks();
});

function generationSettings(partial: Record<string, unknown> = {}) {
  return {
    active: {
      enabled: true,
      provider: "openai_compatible",
      base_url: "http://127.0.0.1:11434/v1",
      model: "active-model",
      timeout_seconds: 120,
      api_key_configured: true,
    },
    pending: null,
    restart_required: false,
    locks: {
      enabled: false,
      base_url: false,
      model: false,
      timeout_seconds: false,
      api_key: false,
    },
    strict_offline: true,
    ...partial,
  };
}

describe("Slice 16D-A Seneca brand", () => {
  it("uses Seneca product title and shell brand", async () => {
    expect(indexHtml).toContain("Seneca — Grounded knowledge workspace");
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Seneca" })).toBeInTheDocument();
    expect(screen.getByText("Grounded knowledge workspace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
    mock.restore();
  });
});

describe("Slice 16D-A Settings", () => {
  it("navigates to Settings and never populates API key from GET", async () => {
    const user = userEvent.setup();
    let saved = false;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      if (call.url === "/v1/settings/generation" && call.method === "GET") {
        if (saved) {
          return jsonResponse(
            generationSettings({
              restart_required: true,
              pending: {
                enabled: true,
                provider: "openai_compatible",
                base_url: "http://127.0.0.1:11434/v1",
                model: "pending-model",
                timeout_seconds: 120,
                api_key_configured: true,
              },
              locks: {
                enabled: false,
                base_url: true,
                model: false,
                timeout_seconds: false,
                api_key: false,
              },
            }),
          );
        }
        return jsonResponse(
          generationSettings({
            locks: {
              enabled: false,
              base_url: true,
              model: false,
              timeout_seconds: false,
              api_key: false,
            },
          }),
        );
      }
      if (call.url === "/v1/settings/generation/probe") {
        return jsonResponse({
          ok: true,
          reason: "ok",
          available_models: ["active-model"],
        });
      }
      if (call.url === "/v1/settings/generation" && call.method === "PUT") {
        saved = true;
        return jsonResponse({
          saved: true,
          restart_required: true,
          active: generationSettings().active,
          pending: {
            enabled: true,
            provider: "openai_compatible",
            base_url: "http://127.0.0.1:11434/v1",
            model: "pending-model",
            timeout_seconds: 120,
            api_key_configured: true,
          },
        });
      }
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/");
    await user.click(screen.getByRole("link", { name: /settings/i }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByLabelText(/endpoint \(operator controlled\)/i)).toBeDisabled();
    const apiKey = screen.getByLabelText(/^API key/i) as HTMLInputElement;
    expect(apiKey.value).toBe("");
    expect(apiKey).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByText(/Connected/i)).toBeInTheDocument();
    expect(saved).toBe(false);

    await user.clear(screen.getByLabelText(/^Model/i));
    await user.type(screen.getByLabelText(/^Model/i), "pending-model");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText(/Restart required/i)).toBeInTheDocument();
    mock.restore();
  });

  it("shows ACTIVE vs PENDING and restart banner", async () => {
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/settings/generation") {
        return jsonResponse(
          generationSettings({
            restart_required: true,
            pending: {
              enabled: true,
              provider: "openai_compatible",
              base_url: "http://10.0.0.5:11434/v1",
              model: "pending-model",
              timeout_seconds: 90,
              api_key_configured: false,
            },
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/settings");
    expect(await screen.findByText(/Restart required/i)).toBeInTheDocument();
    expect(screen.getByText(/pending-model/i)).toBeInTheDocument();
    expect(screen.getByText(/active-model/)).toBeInTheDocument();
    mock.restore();
  });
});

describe("Slice 16D-A compact workspace", () => {
  it("shows capabilities-driven capacity and overflow source actions", async () => {
    expect(formatSource).not.toMatch(/SOURCE_LIMITS\s*=/);
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") {
        return jsonResponse(
          capabilities({
            source_limits: {
              max_active_sources: 32,
              max_bytes_per_source: 26_214_400,
              max_active_source_bytes: 104_857_600,
            },
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "testRAG",
            revision: 2,
            source_count: 2,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [
            source({
              source_id: "src_1",
              display_name: "Week02.pdf",
              byte_size: 2_411_520,
            }),
            source({
              source_id: "src_2",
              display_name: "Week07.pdf",
              byte_size: 1_048_576,
            }),
          ],
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("heading", { name: "testRAG" })).toBeInTheDocument();
    expect(await screen.findByText(/2 \/ 32 sources/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Week02.pdf" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);

    const menuButton = screen.getByRole("button", {
      name: "Actions for Week07.pdf",
    });
    await user.click(menuButton);
    expect(screen.getByRole("menuitem", { name: "Rename source" })).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Replace current version" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove source" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(menuButton);
    });

    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(
      await screen.findByRole("dialog", { name: /edit workspace/i }),
    ).toBeInTheDocument();
    expect(within(screen.getByRole("dialog")).getByLabelText("Title")).toBeInTheDocument();
    mock.restore();
  });
});

describe("Slice 16D-A FAILED/INTERRUPTED operation UX (F5)", () => {
  it("keeps FAILED details when local op terminates before bootstrap import", async () => {
    const user = userEvent.setup();
    // Intentionally empty — global bootstrap must not be the source of truth.
    localStorage.removeItem(ACTIVE_OPERATIONS_KEY);
    let opCalls = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Fail Desk",
            revision: 1,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        return jsonResponse(
          operation({
            operation_id: "op_fast_fail",
            kind: "source_add",
            status: "queued",
            progress_stage: "preparing",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_fast_fail") {
        opCalls += 1;
        return jsonResponse(
          operation({
            operation_id: "op_fast_fail",
            kind: "source_add",
            status: "failed",
            progress_stage: null,
            error: {
              code: "ingest_failed",
              message: "Ingest failed before bootstrap",
              retryable: false,
            },
          }),
        );
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("heading", { name: "Fail Desk" })).toBeInTheDocument();
    const addButtons = screen.getAllByRole("button", { name: "+ Add sources" });
    await user.click(addButtons[0]);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    const fileInput = within(dialog).getByLabelText(/source files/i);
    const file = new File(["pump"], "pump.txt", { type: "text/plain" });
    await user.upload(fileInput, file);
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Ingest failed before bootstrap")).toBeInTheDocument();
    expect(screen.getByText("ingest_failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    // Must not collapse to a bare compact "failed · Add sources" status line.
    expect(screen.queryByText(/^failed · Add sources$/i)).not.toBeInTheDocument();
    expect(opCalls).toBeGreaterThan(0);
    mock.restore();
  });

  it("keeps INTERRUPTED retry guidance on local terminal surface", async () => {
    const user = userEvent.setup();
    localStorage.removeItem(ACTIVE_OPERATIONS_KEY);
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Interrupt Desk",
            revision: 2,
            source_count: 1,
            status: "active",
            current_snapshot_id: "snap_1",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [source({ source_id: "src_1", display_name: "manual.pdf" })],
        });
      }
      if (
        call.url === "/v1/workspaces/ws_1/sources/src_1" &&
        call.method === "PUT"
      ) {
        return jsonResponse(
          operation({
            operation_id: "op_fast_int",
            kind: "source_replace",
            status: "queued",
            progress_stage: "preparing",
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_fast_int") {
        return jsonResponse(
          operation({
            operation_id: "op_fast_int",
            kind: "source_replace",
            status: "interrupted",
            progress_stage: null,
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "manual.pdf" })).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Actions for manual.pdf" }),
    );
    await user.click(
      screen.getByRole("menuitem", { name: "Replace current version" }),
    );
    const dialog = await screen.findByRole("dialog", { name: /replace/i });
    const fileInput = within(dialog).getByLabelText(/file/i);
    await user.upload(
      fileInput,
      new File(["v2"], "manual_v2.pdf", { type: "application/pdf" }),
    );
    await user.click(within(dialog).getByRole("button", { name: /replace/i }));
    expect(await screen.findByText("Interrupted")).toBeInTheDocument();
    expect(
      screen.getByText(/processing was interrupted\. you may retry/i),
    ).toBeInTheDocument();
    mock.restore();
  });
});

describe("Slice 16D-A SourceActionsMenu keyboard (F7)", () => {
  it("supports arrow navigation within the menu", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Menu Desk",
            revision: 2,
            source_count: 1,
            status: "active",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [source({ source_id: "src_1", display_name: "menu.pdf" })],
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const trigger = await screen.findByRole("button", {
      name: "Actions for menu.pdf",
    });
    trigger.focus();
    await user.keyboard("{ArrowDown}");
    const rename = await screen.findByRole("menuitem", { name: "Rename source" });
    expect(rename).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(
      screen.getByRole("menuitem", { name: "Replace current version" }),
    ).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitem", { name: "Remove source" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(rename).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    });
    expect(trigger).toHaveFocus();
    mock.restore();
  });
});

describe("Slice 16D-A Edit workspace modal UX (F11)", () => {
  it("shows Close, restores focus, Escape dismisses, and successful save closes", async () => {
    const user = userEvent.setup();
    let revision = 2;
    let title = "Edit Desk";
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title,
            revision,
            source_count: 1,
            status: "active",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: [source({ source_id: "src_1", display_name: "manual.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1" && call.method === "PATCH") {
        title = "Renamed Desk";
        revision = 3;
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title,
            revision,
            source_count: 1,
            status: "active",
          }),
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const editButton = await screen.findByRole("button", { name: "Edit" });
    await user.click(editButton);
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    const closeButton = within(dialog).getByRole("button", { name: "Close" });
    expect(closeButton).toBeEnabled();

    await user.click(closeButton);
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /edit workspace/i })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(editButton);
    });

    await user.click(editButton);
    expect(
      await screen.findByRole("dialog", { name: /edit workspace/i }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /edit workspace/i })).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(editButton);
    });

    await user.click(editButton);
    const openDialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.clear(within(openDialog).getByLabelText("Title"));
    await user.type(within(openDialog).getByLabelText("Title"), "Renamed Desk");
    await user.click(
      within(openDialog).getByRole("button", { name: "Save changes" }),
    );
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /edit workspace/i })).not.toBeInTheDocument();
    });
    expect(await screen.findByRole("heading", { name: "Renamed Desk" })).toBeInTheDocument();
    mock.restore();
  });

  it("keeps Edit dialog open when metadata save fails", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Fail Edit",
            revision: 2,
            source_count: 1,
            status: "active",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 2,
          sources: [source({ source_id: "src_1", display_name: "manual.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1" && call.method === "PATCH") {
        return errorResponse(
          "workspace_conflict",
          "Workspace revision or state conflict",
          409,
        );
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    expect(
      await within(dialog).findByText(/workspace changed since you last loaded it/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /edit workspace/i })).toBeInTheDocument();
    mock.restore();
  });

  it("keeps Close available on Add sources during pre-202 upload (abortable)", async () => {
    const user = userEvent.setup();
    let releaseAdd: ((response: Response) => void) | null = null;
    const addGate = new Promise<Response>((resolve) => {
      releaseAdd = resolve;
    });
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Add Desk",
            revision: 1,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({ workspace_id: "ws_1", revision: 1, sources: [] });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        return addGate;
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const addButtons = await screen.findAllByRole("button", { name: "+ Add sources" });
    await user.click(addButtons[0]);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeEnabled();

    const fileInput = within(dialog).getByLabelText(/source files/i);
    await user.upload(fileInput, new File(["pump"], "pump.txt", { type: "text/plain" }));
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));
    await waitFor(() => {
      expect(
        within(dialog).getByRole("button", { name: /cancel upload/i }),
      ).toBeEnabled();
    });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeEnabled();
    releaseAdd?.(
      jsonResponse(
        operation({
          operation_id: "op_add",
          status: "succeeded",
          progress_stage: "ready",
        }),
        { status: 202 },
      ),
    );
    mock.restore();
  });
});

describe("Slice 16D-A Edit workspace inline remove (F12)", () => {
  function editWorkspaceMock(handlers: {
    onDelete?: (call: {
      url: string;
      method: string;
      headers: Headers;
    }) => Response | Promise<Response>;
  } = {}) {
    const revision = 2;
    let deleted = false;
    return installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        if (deleted) return errorResponse("workspace_unknown", "gone", 404);
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Remove Desk",
            revision,
            source_count: 1,
            status: "active",
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision,
          sources: [source({ source_id: "src_1", display_name: "manual.pdf" })],
        });
      }
      if (call.url === "/v1/workspaces/ws_1" && call.method === "DELETE") {
        if (handlers.onDelete) {
          const response = await handlers.onDelete(call);
          if (response.ok) deleted = true;
          return response;
        }
        deleted = true;
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision: revision + 1,
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
  }

  it("shows inline remove confirmation without a second dialog", async () => {
    const user = userEvent.setup();
    const mock = editWorkspaceMock();

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );

    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("heading", { name: /remove this workspace/i }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(/not secure permanent deletion/i),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Cancel" }),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("Cancel returns to normal edit form controls", async () => {
    const user = userEvent.setup();
    const mock = editWorkspaceMock();

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(
      within(dialog).queryByRole("heading", { name: /remove this workspace/i }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Save changes" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /edit workspace/i })).toBeInTheDocument();
    mock.restore();
  });

  it("Escape while inline confirmation is shown closes the Edit dialog", async () => {
    const user = userEvent.setup();
    const mock = editWorkspaceMock();

    renderApp("/workspaces/ws_1");
    const editButton = await screen.findByRole("button", { name: "Edit" });
    await user.click(editButton);
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );
    expect(
      within(dialog).getByRole("heading", { name: /remove this workspace/i }),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: /edit workspace/i }),
      ).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(document.activeElement).toBe(editButton);
    });
    mock.restore();
  });

  it("confirm Remove calls DELETE and navigates to /workspaces", async () => {
    const user = userEvent.setup();
    let deleteCount = 0;
    const mock = editWorkspaceMock({
      onDelete: (call) => {
        deleteCount += 1;
        expect(call.headers.get("If-Match")).toBe('"2"');
        expect(call.headers.get("Idempotency-Key")).toBeTruthy();
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            revision: 3,
            status: "tombstoned",
            source_count: 0,
          }),
        );
      },
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );

    expect(await screen.findByRole("heading", { name: "Workspaces" })).toBeInTheDocument();
    expect(deleteCount).toBe(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    mock.restore();
  });

  it("failed removal stays in Edit dialog with a safe error", async () => {
    const user = userEvent.setup();
    const mock = editWorkspaceMock({
      onDelete: () =>
        errorResponse(
          "workspace_conflict",
          "Workspace revision or state conflict",
          409,
        ),
    });

    renderApp("/workspaces/ws_1");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog", { name: /edit workspace/i });
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Remove workspace" }),
    );

    expect(
      await within(dialog).findByText(/workspace changed since you last loaded it/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /edit workspace/i })).toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    mock.restore();
  });
});
