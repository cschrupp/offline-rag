import { QueryClient } from "@tanstack/react-query";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { AppRouter } from "../app/router";
import { queryKeys } from "../api/queryKeys";
import {
  SOURCE_STATE_STALE_MESSAGE,
  canAddSources,
  canMutateExistingSource,
  deriveSourceListPhase,
  headerSourceCountLabel,
  sourceMutationStateKnown,
  sourcesRecordsAvailable,
  workspaceStatusBadge,
} from "../features/workspaces/sourceLoadingState";
import { renderApp, renderWithProviders } from "./render";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  source,
  workspace,
} from "./mockApi";

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

const here = dirname(fileURLToPath(import.meta.url));
const viteConfig = readFileSync(join(here, "../../vite.config.ts"), "utf8");

const tenSources = Array.from({ length: 10 }, (_, index) =>
  source({
    source_id: `src_${index + 1}`,
    display_name: `doc-${index + 1}.txt`,
    byte_size: 100 + index,
  }),
);

function installWorkspaceMocks(options: {
  status?: "active" | "empty";
  sourceCount?: number;
  sourcesMode:
    | "pending"
    | "ok"
    | "empty-ok"
    | "http-500"
    | "network"
    | "wrong-workspace"
    | "missing-sources"
    | "null-json"
    | "empty-object"
    | "invalid-entry"
    | "parse-fail"
    | "parse-then-ok";
  sourcesPayload?: typeof tenSources;
}) {
  let resolveSources: ((value: Response) => void) | null = null;
  let parseAttempts = 0;

  const mock = installFetchMock(async (call) => {
    if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
      const status = options.status ?? "active";
      const sourceCount =
        options.sourceCount ??
        (status === "empty" ? 0 : (options.sourcesPayload?.length ?? 10));
      return jsonResponse(
        workspace({
          workspace_id: "ws_1",
          title: "B1 Upload Smoke",
          revision: 7,
          status,
          source_count: sourceCount,
          current_snapshot_id: status === "empty" ? null : "snap_1",
        }),
      );
    }
    if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
      if (options.sourcesMode === "pending") {
        return new Promise<Response>((resolve) => {
          resolveSources = resolve;
        });
      }
      if (options.sourcesMode === "http-500") {
        return errorResponse("internal_error", "sources failed", 500);
      }
      if (options.sourcesMode === "network") {
        throw new TypeError("Failed to fetch");
      }
      if (options.sourcesMode === "parse-fail") {
        return new Response("{", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (options.sourcesMode === "parse-then-ok") {
        parseAttempts += 1;
        if (parseAttempts === 1) {
          return new Response("{", {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: options.sourcesPayload ?? tenSources,
        });
      }
      if (options.sourcesMode === "null-json") {
        return new Response("null", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (options.sourcesMode === "empty-object") {
        return jsonResponse({});
      }
      if (options.sourcesMode === "missing-sources") {
        return jsonResponse({ workspace_id: "ws_1", revision: 7 });
      }
      if (options.sourcesMode === "wrong-workspace") {
        return jsonResponse({
          workspace_id: "ws_other",
          revision: 7,
          sources: [],
        });
      }
      if (options.sourcesMode === "invalid-entry") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: [{ source_id: "src_bad" }],
        });
      }
      if (options.sourcesMode === "empty-ok") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: [],
        });
      }
      return jsonResponse({
        workspace_id: "ws_1",
        revision: 7,
        sources: options.sourcesPayload ?? tenSources,
      });
    }
    return errorResponse("not_found", "x", 404);
  });

  return {
    mock,
    resolveSourcesOk: (payload = tenSources) => {
      resolveSources?.(
        jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: payload,
        }),
      );
    },
  };
}

describe("sourceLoadingState helpers", () => {
  it("keeps loading/error/empty/ready/inconsistent distinct and symmetric", () => {
    expect(
      deriveSourceListPhase({
        workspace: { status: "active", source_count: 10 },
        sourcePayloadAvailable: false,
        sourcesFailed: false,
        sources: [],
      }),
    ).toBe("loading");
    expect(
      deriveSourceListPhase({
        workspace: { status: "active", source_count: 10 },
        sourcePayloadAvailable: false,
        sourcesFailed: true,
        sources: [],
      }),
    ).toBe("error");
    expect(
      deriveSourceListPhase({
        workspace: { status: "empty", source_count: 0 },
        sourcePayloadAvailable: true,
        sourcesFailed: false,
        sources: [],
      }),
    ).toBe("empty");
    expect(
      deriveSourceListPhase({
        workspace: { status: "active", source_count: 10 },
        sourcePayloadAvailable: true,
        sourcesFailed: false,
        sources: [],
      }),
    ).toBe("inconsistent");
    expect(
      deriveSourceListPhase({
        workspace: { status: "empty", source_count: 0 },
        sourcePayloadAvailable: true,
        sourcesFailed: false,
        sources: tenSources.slice(0, 1),
      }),
    ).toBe("inconsistent");
    expect(
      deriveSourceListPhase({
        workspace: { status: "active", source_count: 10 },
        sourcePayloadAvailable: true,
        sourcesFailed: false,
        sources: tenSources,
      }),
    ).toBe("ready");

    expect(workspaceStatusBadge({ workspaceStatus: "active", sourcePhase: "loading" }).label).toBe(
      "Active",
    );
    expect(workspaceStatusBadge({ workspaceStatus: "empty", sourcePhase: "loading" }).label).toBe(
      "Empty",
    );
    expect(
      workspaceStatusBadge({ workspaceStatus: "active", sourcePhase: "inconsistent" }).label,
    ).toBe("Source issue");
    expect(sourceMutationStateKnown("ready")).toBe(true);
    expect(sourceMutationStateKnown("empty")).toBe(true);
    expect(sourceMutationStateKnown("loading")).toBe(false);
    expect(canAddSources("ready")).toBe(true);
    expect(canAddSources("empty")).toBe(true);
    expect(canAddSources("error")).toBe(false);
    expect(canAddSources("inconsistent")).toBe(false);
    expect(canMutateExistingSource("ready")).toBe(true);
    expect(canMutateExistingSource("empty")).toBe(false);
    expect(canMutateExistingSource("error")).toBe(false);
    expect(canMutateExistingSource("inconsistent")).toBe(false);
    expect(sourcesRecordsAvailable("ready")).toBe(true);
    expect(
      headerSourceCountLabel({
        phase: "loading",
        workspace: { source_count: 10 },
        loadedCount: 0,
        maxActiveSources: 32,
      }),
    ).toBe("10 sources recorded");
  });

  it("Vite config fails closed on occupied 5173", () => {
    expect(viteConfig).toMatch(/port:\s*5173/);
    expect(viteConfig).toMatch(/strictPort:\s*true/);
  });
});

describe("Workspace source-loading presentation", () => {
  it("1 ACTIVE + pending /sources → Active, loading, Add/Ask disabled", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "pending", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.getAllByText(/10 sources recorded/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Loading source details/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("2 ACTIVE + /sources HTTP error → Active, error, Retry, Add/Ask disabled", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "http-500", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.queryByText("Source issue")).toBeNull();
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("3 EMPTY + pending /sources → Empty, loading, Add disabled", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "pending",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Empty")).toBeInTheDocument();
    expect(screen.queryByText("Active")).toBeNull();
    expect(screen.getAllByText(/Loading source details/i).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    ctl.mock.restore();
  });

  it("4 EMPTY + /sources error → Empty, error, Add disabled", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "http-500",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Empty")).toBeInTheDocument();
    expect(screen.queryByText("Active")).toBeNull();
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    ctl.mock.restore();
  });

  it("5 EMPTY + valid [] → genuine Empty, Add enabled, Ask disabled", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "empty-ok",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Empty")).toBeInTheDocument();
    expect(await screen.findByText("This workspace is empty")).toBeInTheDocument();
    expect(screen.queryByText("Source issue")).toBeNull();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeEnabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("6 ACTIVE + valid nonempty → ready rows, Add allowed, Ask can enable", async () => {
    const user = userEvent.setup();
    const ctl = installWorkspaceMocks({ sourcesMode: "ok", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(await screen.findByText(/10 \/ 32 sources/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeEnabled();
    await user.type(screen.getByLabelText(/Ask a follow-up/i), "What is grounding?");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    });
    ctl.mock.restore();
  });

  it("7 ACTIVE + valid [] → Source issue, Retry, Add/Ask disabled", async () => {
    const ctl = installWorkspaceMocks({
      status: "active",
      sourceCount: 10,
      sourcesMode: "empty-ok",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Source issue")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent ?? "").toMatch(
      /Source list does not match the saved workspace state/i,
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("8 EMPTY + valid nonempty → Source issue, not ordinary Empty", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "ok",
      sourcesPayload: tenSources.slice(0, 1),
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Source issue")).toBeInTheDocument();
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("9 inconsistent Retry recovers to ready without page reload", async () => {
    const user = userEvent.setup();
    let sourcesMode: "empty-ok" | "ok" = "empty-ok";
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "B1 Upload Smoke",
            revision: 7,
            status: "active",
            source_count: 10,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        if (sourcesMode === "empty-ok") {
          return jsonResponse({ workspace_id: "ws_1", revision: 7, sources: [] });
        }
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: tenSources,
        });
      }
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Source issue")).toBeInTheDocument();
    sourcesMode = "ok";
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Source issue")).toBeNull();
    expect(screen.getByRole("heading", { name: "B1 Upload Smoke" })).toBeInTheDocument();
    mock.restore();
  });

  it("10 HTTP 200 + JSON parse rejection → error, not inconsistent", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "parse-fail", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Source issue")).toBeNull();
    expect(screen.queryByText("Empty")).toBeNull();
    ctl.mock.restore();
  });

  it("11–15 invalid successful payloads → error, not empty/inconsistent", async () => {
    for (const mode of [
      "null-json",
      "empty-object",
      "missing-sources",
      "wrong-workspace",
      "invalid-entry",
    ] as const) {
      const ctl = installWorkspaceMocks({ sourcesMode: mode, sourceCount: 10 });
      const view = renderApp("/workspaces/ws_1");
      expect(await screen.findByText("Active")).toBeInTheDocument();
      expect(
        (await screen.findAllByText(/Source details could not be loaded/i)).length,
      ).toBeGreaterThan(0);
      expect(screen.queryByText("Source issue")).toBeNull();
      expect(screen.queryByText("This workspace is empty")).toBeNull();
      ctl.mock.restore();
      view.unmount();
      sessionStorage.clear();
    }
  });

  it("16 HTTP 200 + valid SourceListResponse → accepted ready", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "ok", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText(/10 \/ 32 sources/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "doc-10.txt" })).toBeInTheDocument();
    ctl.mock.restore();
  });

  it("17 transient parse failure then production RQ retry success → ready", async () => {
    const ctl = installWorkspaceMocks({
      sourcesMode: "parse-then-ok",
      sourceCount: 10,
    });
    // Match production queryClient retry: 1 without changing global test defaults.
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 1, retryDelay: 10 },
        mutations: { retry: false },
      },
    });
    renderWithProviders(<AppRouter />, {
      initialPath: "/workspaces/ws_1",
      queryClient,
    });
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Source issue")).toBeNull();
    ctl.mock.restore();
  });
});

type MutableSourcesMode = "ok" | "empty-ok" | "http-500";

function installMutableWorkspaceMocks(options?: {
  status?: "active" | "empty";
  sourceCount?: number;
  initialMode?: MutableSourcesMode;
}) {
  let sourcesMode: MutableSourcesMode = options?.initialMode ?? "ok";
  const mutationCalls: { method: string; url: string }[] = [];

  const mock = installFetchMock(async (call) => {
    if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
    if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
    if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
      const status = options?.status ?? "active";
      const sourceCount =
        options?.sourceCount ?? (status === "empty" ? 0 : 10);
      return jsonResponse(
        workspace({
          workspace_id: "ws_1",
          title: "B1 Upload Smoke",
          revision: 7,
          status,
          source_count: sourceCount,
          current_snapshot_id: status === "empty" ? null : "snap_1",
        }),
      );
    }
    if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
      if (sourcesMode === "http-500") {
        return errorResponse("internal_error", "sources failed", 500);
      }
      if (sourcesMode === "empty-ok") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: [],
        });
      }
      return jsonResponse({
        workspace_id: "ws_1",
        revision: 7,
        sources: tenSources,
      });
    }
    if (
      call.url.startsWith("/v1/workspaces/ws_1/sources") &&
      (call.method === "POST" ||
        call.method === "PATCH" ||
        call.method === "PUT" ||
        call.method === "DELETE")
    ) {
      mutationCalls.push({ method: call.method, url: call.url });
      return errorResponse("internal_error", "mutation should not dispatch", 500);
    }
    if (call.url === "/v1/workspaces") return jsonResponse([]);
    return errorResponse("not_found", "x", 404);
  });

  return {
    mock,
    mutationCalls,
    setSourcesMode: (mode: MutableSourcesMode) => {
      sourcesMode = mode;
    },
  };
}

describe("Workspace source mutation stale-open-dialog guards (Rework 2)", () => {
  it("A ADD: open modal then source becomes unsafe → submit disabled and POST blocked", async () => {
    const user = userEvent.setup();
    const ctl = installMutableWorkspaceMocks();
    const { queryClient } = renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "+ Add sources" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    await user.upload(
      within(dialog).getByLabelText(/source files/i),
      new File(["hello"], "new.txt", { type: "text/plain" }),
    );
    expect(
      within(dialog).getByRole("button", { name: /^add sources$/i }),
    ).toBeEnabled();

    // ACTIVE + [] → inconsistent (fail-closed for Add)
    ctl.setSourcesMode("empty-ok");
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources("ws_1"),
    });
    await waitFor(() => {
      expect(
        within(dialog).getByRole("button", { name: /^add sources$/i }),
      ).toBeDisabled();
    });
    expect(within(dialog).getByText(SOURCE_STATE_STALE_MESSAGE)).toBeInTheDocument();

    fireEvent.submit(
      within(dialog).getByRole("button", { name: /^add sources$/i }).closest("form")!,
    );
    expect(ctl.mutationCalls.filter((c) => c.method === "POST")).toHaveLength(0);
    ctl.mock.restore();
  });

  it("B ADD Retry safely: frozen intent preserved; unsafe state blocks retry POST", async () => {
    const user = userEvent.setup();
    let sourcesMode: MutableSourcesMode = "ok";
    const posts: string[] = [];
    let postAttempt = 0;
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "B1 Upload Smoke",
            revision: 7,
            status: "active",
            source_count: 10,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        if (sourcesMode === "http-500") {
          return errorResponse("internal_error", "sources failed", 500);
        }
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: tenSources,
        });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        posts.push(call.method);
        postAttempt += 1;
        if (postAttempt === 1) {
          throw new TypeError("Failed to fetch");
        }
        return errorResponse("internal_error", "should not retry", 500);
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    const { queryClient } = renderApp("/workspaces/ws_1");
    await user.click(
      (await screen.findAllByRole("button", { name: "+ Add sources" }))[0]!,
    );
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    await user.upload(
      within(dialog).getByLabelText(/source files/i),
      new File(["x"], "x.txt", { type: "text/plain" }),
    );
    await user.click(within(dialog).getByRole("button", { name: /^add sources$/i }));
    const retry = await within(dialog).findByRole("button", { name: /retry safely/i });
    expect(retry).toBeEnabled();
    expect(posts).toHaveLength(1);

    sourcesMode = "http-500";
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources("ws_1"),
    });
    await waitFor(() => {
      expect(retry).toBeDisabled();
    });
    expect(within(dialog).getByText(SOURCE_STATE_STALE_MESSAGE)).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /retry safely/i }),
    ).toBeInTheDocument();

    fireEvent.click(retry);
    expect(posts).toHaveLength(1);
    mock.restore();
  });

  it("C RENAME: open then unsafe → Save disabled and no PATCH", async () => {
    const user = userEvent.setup();
    const ctl = installMutableWorkspaceMocks();
    const { queryClient } = renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Actions for doc-1.txt" }));
    await user.click(screen.getByRole("menuitem", { name: "Rename source" }));
    const dialog = await screen.findByRole("dialog", { name: /rename display label/i });
    expect(within(dialog).getByRole("button", { name: "Save label" })).toBeEnabled();

    ctl.setSourcesMode("http-500");
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources("ws_1"),
    });
    await waitFor(() => {
      expect(within(dialog).getByRole("button", { name: "Save label" })).toBeDisabled();
    });
    expect(within(dialog).getByText(SOURCE_STATE_STALE_MESSAGE)).toBeInTheDocument();

    fireEvent.submit(within(dialog).getByRole("button", { name: "Save label" }).closest("form")!);
    expect(ctl.mutationCalls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeEnabled();
    ctl.mock.restore();
  });

  it("D REPLACE: open then unsafe → Replace disabled, no PUT, not uploading", async () => {
    const user = userEvent.setup();
    const ctl = installMutableWorkspaceMocks();
    const { queryClient } = renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Actions for doc-1.txt" }));
    await user.click(screen.getByRole("menuitem", { name: "Replace current version" }));
    const dialog = await screen.findByRole("dialog", { name: /replace current version/i });
    await user.upload(
      within(dialog).getByLabelText(/replacement file/i),
      new File(["new"], "replacement.txt", { type: "text/plain" }),
    );
    expect(
      within(dialog).getByRole("button", { name: "Replace current version" }),
    ).toBeEnabled();

    ctl.setSourcesMode("http-500");
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources("ws_1"),
    });
    await waitFor(() => {
      expect(
        within(dialog).getByRole("button", { name: "Replace current version" }),
      ).toBeDisabled();
    });

    fireEvent.submit(
      within(dialog)
        .getByRole("button", { name: "Replace current version" })
        .closest("form")!,
    );
    expect(ctl.mutationCalls.filter((c) => c.method === "PUT")).toHaveLength(0);
    expect(screen.queryByText(/^Uploading/i)).toBeNull();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeEnabled();
    ctl.mock.restore();
  });

  it("E REMOVE: open then unsafe → confirm disabled, Cancel available, no DELETE", async () => {
    const user = userEvent.setup();
    const ctl = installMutableWorkspaceMocks();
    const { queryClient } = renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Actions for doc-1.txt" }));
    await user.click(screen.getByRole("menuitem", { name: "Remove source" }));
    const dialog = await screen.findByRole("alertdialog", { name: /remove source/i });
    const confirm = within(dialog).getByRole("button", { name: "Remove source" });
    expect(confirm).toBeEnabled();

    ctl.setSourcesMode("http-500");
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workspaceSources("ws_1"),
    });
    await waitFor(() => {
      expect(confirm).toBeDisabled();
    });
    expect(within(dialog).getByText(SOURCE_STATE_STALE_MESSAGE)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeEnabled();

    fireEvent.click(confirm);
    expect(ctl.mutationCalls.filter((c) => c.method === "DELETE")).toHaveLength(0);
    ctl.mock.restore();
  });

  it("F EMPTY: Add remains allowed; rename/replace/remove remain impossible", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "empty-ok",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("This workspace is empty")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Actions for/i })).toBeNull();
    ctl.mock.restore();
  });

  it("G READY: normal Add/Rename/Replace/Remove controls remain enabled", async () => {
    const user = userEvent.setup();
    const ctl = installMutableWorkspaceMocks();
    renderApp("/workspaces/ws_1");
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "+ Add sources" })[0]).toBeEnabled();

    await user.click(screen.getAllByRole("button", { name: "+ Add sources" })[0]!);
    const addDialog = await screen.findByRole("dialog", { name: /add sources/i });
    await user.upload(
      within(addDialog).getByLabelText(/source files/i),
      new File(["a"], "a.txt", { type: "text/plain" }),
    );
    expect(
      within(addDialog).getByRole("button", { name: /^add sources$/i }),
    ).toBeEnabled();
    await user.click(within(addDialog).getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Actions for doc-1.txt" }));
    expect(screen.getByRole("menuitem", { name: "Rename source" })).toBeEnabled();
    expect(
      screen.getByRole("menuitem", { name: "Replace current version" }),
    ).toBeEnabled();
    expect(screen.getByRole("menuitem", { name: "Remove source" })).toBeEnabled();
    ctl.mock.restore();
  });
});
