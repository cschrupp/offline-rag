import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import { authoringReadinessStatusText } from "../features/goldLab/authoringReadinessCopy";
import { goldLabErrorMessage } from "../features/goldLab/errors/goldLabErrors";
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  vi.restoreAllMocks();
});

const generationState = {
  active: {
    enabled: true,
    provider: "openai_compatible",
    base_url: "http://127.0.0.1:11434/v1",
    model: "gen-model",
    timeout_seconds: 120,
    api_key_configured: false,
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
};

const authoringState = {
  active: {
    enabled: false,
    provider: "openai_compatible",
    base_url: "http://127.0.0.1:11434/v1",
    model: null,
    timeout_seconds: 120,
    network_policy: "localhost_only",
    api_key_configured: false,
  },
  pending: null,
  restart_required: false,
  locks: {
    enabled: true,
    base_url: true,
    model: true,
    timeout_seconds: true,
    api_key: true,
    network_policy: true,
  },
  strict_offline: true,
  readiness: {
    ready: false,
    reason_codes: ["disabled", "model_unset"],
    enabled: false,
    endpoint_configured: true,
    endpoint_approved: false,
    model_configured: false,
    model_approved: false,
    network_policy_satisfied: false,
    api_key_configured: false,
  },
};

function projectFixture(projectId: string) {
  return {
    project_id: projectId,
    title: "Demo",
    description: "",
    project_type: "benchmark",
    status: "active",
    workspace_id: "ws_1",
    created_at: "2026-01-01T00:00:00Z",
  };
}

function capabilitiesBody(authoring: unknown) {
  return {
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
    ...(authoring === undefined ? {} : { authoring }),
  };
}

describe("Slice 16 authoring Settings UX", () => {
  it("exposes dual selectors with aria-pressed and deep-links authoring", async () => {
    const user = userEvent.setup();
    const mock = installFetchMock(async ({ url, method }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/settings/generation" && method === "GET") {
        return jsonResponse(generationState);
      }
      if (url === "/v1/settings/authoring" && method === "GET") {
        return jsonResponse(authoringState);
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/settings?section=authoring");

    await screen.findByRole("heading", { name: "Gold Lab authoring server" });
    const group = screen.getByRole("group", { name: "Settings section" });
    const generation = within(group).getByRole("button", {
      name: "Answer generation",
    });
    const authoring = within(group).getByRole("button", {
      name: "Gold Lab authoring",
    });
    expect(authoring).toHaveAttribute("aria-pressed", "true");
    expect(generation).toHaveAttribute("aria-pressed", "false");
    expect(
      screen.getAllByText(/Operator controlled/i).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/Gold Lab authoring is disabled/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/model_unset/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/disabled,/i)).not.toBeInTheDocument();

    await user.click(generation);
    await screen.findByRole("heading", { name: "Generation server" });
    expect(
      within(group).getByRole("button", { name: "Answer generation" }),
    ).toHaveAttribute("aria-pressed", "true");
    mock.restore();
  });

  it("preserves generation form on default /settings", async () => {
    const mock = installFetchMock(async ({ url, method }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/settings/generation" && method === "GET") {
        return jsonResponse(generationState);
      }
      return errorResponse("not_found", "x", 404);
    });
    renderApp("/settings");
    await screen.findByRole("heading", { name: "Generation server" });
    expect(
      screen.getByRole("button", { name: "Test connection" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save settings" }),
    ).toBeInTheDocument();
    mock.restore();
  });
});

describe("authoring readiness product language", () => {
  it("maps known codes and never echoes unknown identifiers", () => {
    expect(
      authoringReadinessStatusText({
        ready: true,
        reasonCodes: ["disabled"],
      }),
    ).toBe("Gold Lab authoring is ready.");

    expect(
      authoringReadinessStatusText({
        ready: false,
        reasonCodes: ["disabled", "model_unset"],
      }),
    ).toMatch(/disabled/i);
    expect(
      authoringReadinessStatusText({
        ready: false,
        reasonCodes: ["disabled", "model_unset"],
      }),
    ).toMatch(/No authoring model is configured/i);
    expect(
      authoringReadinessStatusText({
        ready: false,
        reasonCodes: ["disabled", "model_unset"],
      }),
    ).not.toMatch(/model_unset/);

    expect(
      authoringReadinessStatusText({
        ready: false,
        reasonCodes: ["totally_unknown_code"],
      }),
    ).toBe("Gold Lab authoring is not ready.");
  });
});

describe("Gold Lab authoring readiness + reason mapping", () => {
  it("maps authoring_not_ready and authoring_endpoint_unauthorized distinctly", () => {
    expect(
      goldLabErrorMessage(
        new ApiError({
          kind: "api",
          code: "gold_conflict",
          message: "ignored",
          details: { reason: "authoring_not_ready" },
        }),
      ),
    ).toMatch(/authoring is not ready/i);

    expect(
      goldLabErrorMessage(
        new ApiError({
          kind: "api",
          code: "gold_conflict",
          message: "ignored",
          details: { reason: "authoring_endpoint_unauthorized" },
        }),
      ),
    ).toMatch(/not authorized by the active network policy/i);

    expect(
      goldLabErrorMessage(
        new ApiError({
          kind: "api",
          code: "gold_conflict",
          message: "ignored",
          details: { reason: "project_drift_before_commit" },
        }),
      ),
    ).toMatch(/changed before the action could complete/i);

    expect(
      goldLabErrorMessage(
        new ApiError({
          kind: "api",
          code: "gold_conflict",
          message: "ignored",
          details: { reason: "some_unknown_reason" },
        }),
      ),
    ).toMatch(/changed since you last loaded it/i);
  });
});

describe("Gold baseline bootstrap fail-closed readiness", () => {
  it("loading: shows checking status and no create action", async () => {
    const projectId = `goldproj_${"b".repeat(32)}`;
    let resolveCaps: ((value: Response) => void) | null = null;
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/capabilities") {
        return await new Promise<Response>((resolve) => {
          resolveCaps = resolve;
        });
      }
      if (url === `/v1/gold-lab/projects/${projectId}`) {
        return jsonResponse(projectFixture(projectId));
      }
      if (url.endsWith("/baselines")) return jsonResponse({ baselines: [] });
      if (url.endsWith("/campaigns")) return jsonResponse({ campaigns: [] });
      return errorResponse("not_found", "x", 404);
    });
    renderApp(`/gold-lab/projects/${projectId}`);
    await screen.findByText(/Checking Gold Lab authoring readiness/i);
    expect(
      screen.queryByRole("button", {
        name: /Create baseline from workspace/i,
      }),
    ).not.toBeInTheDocument();
    resolveCaps?.(
      jsonResponse(
        capabilitiesBody({
          enabled: true,
          provider: "openai_compatible",
          base_url: "http://127.0.0.1:11434/v1",
          model: "m",
          timeout_seconds: 120,
          ready: true,
          reason_codes: [],
        }),
      ),
    );
    await screen.findByRole("button", {
      name: /Create baseline from workspace/i,
    });
    mock.restore();
  });

  it("capabilities error: blocks create and offers retry", async () => {
    const projectId = `goldproj_${"c".repeat(32)}`;
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/capabilities") {
        return errorResponse("internal_error", "boom", 500);
      }
      if (url === `/v1/gold-lab/projects/${projectId}`) {
        return jsonResponse(projectFixture(projectId));
      }
      if (url.endsWith("/baselines")) return jsonResponse({ baselines: [] });
      if (url.endsWith("/campaigns")) return jsonResponse({ campaigns: [] });
      return errorResponse("not_found", "x", 404);
    });
    renderApp(`/gold-lab/projects/${projectId}`);
    await screen.findByText(/readiness could not be checked/i);
    expect(
      screen.getByRole("button", { name: /Retry readiness check/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: /Create baseline from workspace/i,
      }),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("missing authoring capability: blocks create", async () => {
    const projectId = `goldproj_${"d".repeat(32)}`;
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/capabilities") {
        return jsonResponse(capabilitiesBody(undefined));
      }
      if (url === `/v1/gold-lab/projects/${projectId}`) {
        return jsonResponse(projectFixture(projectId));
      }
      if (url.endsWith("/baselines")) return jsonResponse({ baselines: [] });
      if (url.endsWith("/campaigns")) return jsonResponse({ campaigns: [] });
      return errorResponse("not_found", "x", 404);
    });
    renderApp(`/gold-lab/projects/${projectId}`);
    await screen.findByText(/readiness is unavailable/i);
    expect(
      screen.queryByRole("button", {
        name: /Create baseline from workspace/i,
      }),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("ready=false: Settings CTA and no create action", async () => {
    const projectId = `goldproj_${"e".repeat(32)}`;
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/capabilities") {
        return jsonResponse(
          capabilitiesBody({
            enabled: false,
            provider: "openai_compatible",
            base_url: "http://127.0.0.1:11434/v1",
            model: null,
            timeout_seconds: 120,
            ready: false,
            reason_codes: ["disabled"],
          }),
        );
      }
      if (url === `/v1/gold-lab/projects/${projectId}`) {
        return jsonResponse(projectFixture(projectId));
      }
      if (url.endsWith("/baselines")) return jsonResponse({ baselines: [] });
      if (url.endsWith("/campaigns")) return jsonResponse({ campaigns: [] });
      return errorResponse("not_found", "x", 404);
    });
    renderApp(`/gold-lab/projects/${projectId}`);

    await waitFor(() => {
      expect(
        screen.getByText(/Gold Lab authoring is not ready/i),
      ).toBeInTheDocument();
    });
    const link = screen.getByRole("link", {
      name: "Configure Gold Lab authoring",
    });
    expect(link).toHaveAttribute("href", "/settings?section=authoring");
    expect(
      screen.queryByRole("button", {
        name: /Create baseline from workspace/i,
      }),
    ).not.toBeInTheDocument();
    mock.restore();
  });

  it("ready=true: renders bootstrap form", async () => {
    const projectId = `goldproj_${"f".repeat(32)}`;
    const mock = installFetchMock(async ({ url }) => {
      if (url === "/health/ready") return jsonResponse({ status: "ready" });
      if (url === "/v1/workspaces") return jsonResponse([]);
      if (url === "/v1/capabilities") {
        return jsonResponse(
          capabilitiesBody({
            enabled: true,
            provider: "openai_compatible",
            base_url: "http://127.0.0.1:11434/v1",
            model: "m",
            timeout_seconds: 120,
            ready: true,
            reason_codes: [],
          }),
        );
      }
      if (url === `/v1/gold-lab/projects/${projectId}`) {
        return jsonResponse(projectFixture(projectId));
      }
      if (url.endsWith("/baselines")) return jsonResponse({ baselines: [] });
      if (url.endsWith("/campaigns")) return jsonResponse({ campaigns: [] });
      return errorResponse("not_found", "x", 404);
    });
    renderApp(`/gold-lab/projects/${projectId}`);
    await screen.findByRole("button", {
      name: /Create baseline from workspace/i,
    });
    mock.restore();
  });
});
