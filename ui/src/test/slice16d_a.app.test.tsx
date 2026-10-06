import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "./render";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
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
    expect(screen.getByText(/Week02\.pdf/)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

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
