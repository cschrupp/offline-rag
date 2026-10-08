import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deriveSourceListPhase,
  headerSourceCountLabel,
  sourcesRecordsAvailable,
} from "../features/workspaces/sourceLoadingState";
import { renderApp } from "./render";
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
    | "network";
  sourcesPayload?: typeof tenSources;
}) {
  let resolveSources: ((value: Response) => void) | null = null;
  let rejectSources: ((reason?: unknown) => void) | null = null;
  let sourcesCalls = 0;

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
      sourcesCalls += 1;
      if (options.sourcesMode === "pending") {
        return new Promise<Response>((resolve, reject) => {
          resolveSources = resolve;
          rejectSources = reject;
        });
      }
      if (options.sourcesMode === "http-500") {
        return errorResponse("internal_error", "sources failed", 500);
      }
      if (options.sourcesMode === "network") {
        throw new TypeError("Failed to fetch");
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
    sourcesCalls: () => sourcesCalls,
    resolveSourcesOk: (payload = tenSources) => {
      resolveSources?.(
        jsonResponse({
          workspace_id: "ws_1",
          revision: 7,
          sources: payload,
        }),
      );
    },
    rejectSourcesNetwork: () => {
      rejectSources?.(new TypeError("Failed to fetch"));
    },
  };
}

describe("sourceLoadingState helpers", () => {
  it("keeps loading/error/active-empty distinct from genuine empty", () => {
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
        workspace: { status: "active", source_count: 10 },
        sourcePayloadAvailable: true,
        sourcesFailed: false,
        sources: tenSources,
      }),
    ).toBe("ready");

    expect(sourcesRecordsAvailable("ready")).toBe(true);
    expect(sourcesRecordsAvailable("loading")).toBe(false);
    expect(
      headerSourceCountLabel({
        phase: "loading",
        workspace: { source_count: 10 },
        loadedCount: 0,
        maxActiveSources: 32,
      }),
    ).toBe("10 sources recorded");
  });
});

describe("Workspace source-loading presentation", () => {
  it("ACTIVE + source_count=10 + /sources loading → not Empty; shows loading + recorded count", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "pending", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(
      await screen.findByRole("heading", { name: "B1 Upload Smoke" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.getAllByText(/10 sources recorded/i).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/Loading source details/i).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("ACTIVE + source_count=10 + /sources 500 → not Empty; shows source-loading error", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "http-500", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("ACTIVE + source_count=10 + /sources network failure → same error path", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "network", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    ctl.mock.restore();
  });

  it("ACTIVE + source_count=10 + successful payload → Active, 10/32, source rows", async () => {
    const ctl = installWorkspaceMocks({ sourcesMode: "ok", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(await screen.findByText(/10 \/ 32 sources/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "doc-10.txt" })).toBeInTheDocument();
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    ctl.mock.restore();
  });

  it("EMPTY + source_count=0 + successful [] → genuine Empty unchanged", async () => {
    const ctl = installWorkspaceMocks({
      status: "empty",
      sourceCount: 0,
      sourcesMode: "empty-ok",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Empty")).toBeInTheDocument();
    expect(
      await screen.findByText("This workspace is empty"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Inconsistent")).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("ACTIVE + source_count>0 + successful [] → inconsistent, not Empty", async () => {
    const ctl = installWorkspaceMocks({
      status: "active",
      sourceCount: 10,
      sourcesMode: "empty-ok",
    });
    renderApp("/workspaces/ws_1");
    expect(await screen.findByText("Inconsistent")).toBeInTheDocument();
    expect(screen.queryByText("Empty")).toBeNull();
    expect(screen.queryByText("This workspace is empty")).toBeNull();
    expect(
      await screen.findByText(/Inconsistent workspace\/source state/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.mock.restore();
  });

  it("Ask remains disabled until real source records are available", async () => {
    const user = userEvent.setup();
    const ctl = installWorkspaceMocks({ sourcesMode: "pending", sourceCount: 10 });
    renderApp("/workspaces/ws_1");
    await screen.findAllByText(/Loading source details/i);
    const ask = screen.getByLabelText(/Ask a follow-up/i);
    await user.type(ask, "What is grounding?");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    ctl.resolveSourcesOk();
    await screen.findByRole("button", { name: "doc-1.txt" });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
    });
    ctl.mock.restore();
  });

  it("Retry/refetch recovers from failed source load without page reload", async () => {
    const user = userEvent.setup();
    let sourcesMode: "http-500" | "ok" = "http-500";
    let sourcesCalls = 0;
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
        sourcesCalls += 1;
        if (sourcesMode === "http-500") {
          return errorResponse("internal_error", "sources failed", 500);
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
    expect(
      (await screen.findAllByText(/Source details could not be loaded/i)).length,
    ).toBeGreaterThan(0);
    expect(sourcesCalls).toBeGreaterThanOrEqual(1);
    const failedCalls = sourcesCalls;
    sourcesMode = "ok";
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: "doc-1.txt" })).toBeInTheDocument();
    expect(screen.getByText(/10 \/ 32 sources/i)).toBeInTheDocument();
    expect(screen.queryByText(/Source details could not be loaded/i)).toBeNull();
    expect(sourcesCalls).toBeGreaterThan(failedCalls);
    expect(screen.getByRole("heading", { name: "B1 Upload Smoke" })).toBeInTheDocument();
    expect(within(document.body).getByText("Active")).toBeInTheDocument();
    mock.restore();
  });
});
