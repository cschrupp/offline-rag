import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
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
    reason_codes: ["disabled"],
    enabled: false,
    endpoint_configured: true,
    endpoint_approved: false,
    model_configured: false,
    model_approved: false,
    network_policy_satisfied: false,
    api_key_configured: false,
  },
};

function computeState(overrides: Record<string, unknown> = {}) {
  return {
    active: { embedding_device: "auto" as const },
    pending: null as null | { embedding_device: "auto" | "cpu" | "cuda" },
    restart_required: false,
    locks: { embedding_device: false },
    runtime: {
      active_device: "cuda",
      cuda_available: true,
      torch_cuda_build: "12.8",
      selection_reason: "cuda_available",
    },
    availability: {
      auto: { available: true },
      cpu: { available: true },
      cuda: { available: true, reason: null as string | null },
    },
    ...overrides,
  };
}

function installSettingsMocks(compute: ReturnType<typeof computeState>) {
  let current = { ...compute };
  return installFetchMock(async ({ url, method, body }) => {
    if (url === "/health/ready") return jsonResponse({ status: "ready" });
    if (url === "/v1/workspaces") return jsonResponse([]);
    if (url === "/v1/settings/generation" && method === "GET") {
      return jsonResponse(generationState);
    }
    if (url === "/v1/settings/authoring" && method === "GET") {
      return jsonResponse(authoringState);
    }
    if (url === "/v1/settings/compute" && method === "GET") {
      return jsonResponse(current);
    }
    if (url === "/v1/settings/compute" && method === "PUT") {
      const parsed = JSON.parse(String(body ?? "{}")) as {
        embedding_device: "auto" | "cpu" | "cuda";
      };
      const pending =
        parsed.embedding_device === current.active.embedding_device
          ? null
          : { embedding_device: parsed.embedding_device };
      current = {
        ...current,
        pending,
        restart_required: pending !== null,
      };
      return jsonResponse({
        saved: true,
        restart_required: pending !== null,
        active: current.active,
        pending,
        locks: current.locks,
        runtime: current.runtime,
        availability: current.availability,
      });
    }
    if (url === "/v1/capabilities") {
      return jsonResponse({
        product: { name: "Seneca", descriptor: "Grounded knowledge workspace" },
        source_limits: {
          max_active_sources: 32,
          max_bytes_per_source: 1,
          max_active_source_bytes: 1,
        },
        generation: generationState.active,
        embedding: {
          model: "Qwen/Qwen3-Embedding-0.6B",
          configured_device: "auto",
          active_device: compute.runtime.active_device,
          batch_size: 32,
          cuda_available: compute.runtime.cuda_available,
          torch_cuda_build: compute.runtime.torch_cuda_build,
          selection_reason: compute.runtime.selection_reason,
        },
      });
    }
    return errorResponse("not_found", "x", 404);
  });
}

describe("Slice 16L Compute settings UX", () => {
  it("navigates to Compute section", async () => {
    const compute = computeState();
    const mock = installSettingsMocks(compute);
    const user = userEvent.setup();
    renderApp("/settings");
    await screen.findByRole("heading", { name: "Settings" });
    await user.click(screen.getByRole("button", { name: "Compute" }));
    expect(
      await screen.findByRole("heading", { name: "Embedding acceleration" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Compute" }),
    ).toHaveAttribute("aria-pressed", "true");
    mock.restore();
  });

  it("shows active CUDA witness and Auto policy", async () => {
    const mock = installSettingsMocks(computeState());
    renderApp("/settings?section=compute");
    expect(
      await screen.findByRole("heading", { name: "Embedding acceleration" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("compute-active-device")).toHaveTextContent(
      "GPU (CUDA)",
    );
    expect(screen.getByText(/Configured policy:\s*Auto/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Auto/i })).toBeEnabled();
    expect(screen.getByRole("radio", { name: /^CPU/i })).toBeEnabled();
    expect(screen.getByRole("radio", { name: /GPU \(CUDA\)/i })).toBeEnabled();
    mock.restore();
  });

  it("shows active CPU witness", async () => {
    const mock = installSettingsMocks(
      computeState({
        runtime: {
          active_device: "cpu",
          cuda_available: false,
          torch_cuda_build: null,
          selection_reason: "cuda_unavailable",
        },
        availability: {
          auto: { available: true },
          cpu: { available: true },
          cuda: { available: false, reason: "pytorch_cpu_only" },
        },
      }),
    );
    renderApp("/settings?section=compute");
    expect(await screen.findByText("Active device")).toBeInTheDocument();
    const card = screen.getByRole("heading", {
      name: "Embedding acceleration",
    }).parentElement!;
    expect(within(card).getByText("CPU", { selector: "p" })).toBeInTheDocument();
    mock.restore();
  });

  it("disables GPU for CPU-only distribution with explanation", async () => {
    const mock = installSettingsMocks(
      computeState({
        runtime: {
          active_device: "cpu",
          cuda_available: false,
          torch_cuda_build: null,
          selection_reason: "cuda_unavailable",
        },
        availability: {
          auto: { available: true },
          cpu: { available: true },
          cuda: { available: false, reason: "pytorch_cpu_only" },
        },
      }),
    );
    renderApp("/settings?section=compute");
    await screen.findByRole("heading", { name: "Embedding acceleration" });
    expect(screen.getByRole("radio", { name: /GPU \(CUDA\)/i })).toBeDisabled();
    expect(
      screen.getByText(
        /GPU acceleration is unavailable in this Seneca installation/i,
      ),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("disables GPU when CUDA build has no device", async () => {
    const mock = installSettingsMocks(
      computeState({
        runtime: {
          active_device: "cpu",
          cuda_available: false,
          torch_cuda_build: "12.8",
          selection_reason: "cuda_unavailable",
        },
        availability: {
          auto: { available: true },
          cpu: { available: true },
          cuda: { available: false, reason: "cuda_device_unavailable" },
        },
      }),
    );
    renderApp("/settings?section=compute");
    await screen.findByRole("heading", { name: "Embedding acceleration" });
    expect(screen.getByRole("radio", { name: /GPU \(CUDA\)/i })).toBeDisabled();
    expect(
      screen.getByText(/no usable GPU is visible to Seneca/i),
    ).toBeInTheDocument();
    mock.restore();
  });

  it("locks all choices when operator controlled", async () => {
    const mock = installSettingsMocks(
      computeState({
        locks: { embedding_device: true },
      }),
    );
    renderApp("/settings?section=compute");
    await screen.findByText(/Operator controlled/i);
    expect(screen.getByRole("radio", { name: /Auto/i })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /^CPU/i })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /GPU \(CUDA\)/i })).toBeDisabled();
    mock.restore();
  });

  it("shows pending CPU without changing active device witness", async () => {
    const mock = installSettingsMocks(
      computeState({
        active: { embedding_device: "auto" },
        pending: { embedding_device: "cpu" },
        restart_required: true,
        runtime: {
          active_device: "cuda",
          cuda_available: true,
          torch_cuda_build: "12.8",
          selection_reason: "cuda_available",
        },
      }),
    );
    renderApp("/settings?section=compute");
    await screen.findByText(/Restart required/i);
    expect(screen.getByTestId("compute-active-device")).toHaveTextContent(
      "GPU (CUDA)",
    );
    expect(screen.getByText(/Pending policy:\s*CPU/i)).toBeInTheDocument();
    mock.restore();
  });

  it("saves compute settings", async () => {
    const compute = computeState();
    const mock = installSettingsMocks(compute);
    const user = userEvent.setup();
    renderApp("/settings?section=compute");
    await screen.findByRole("heading", { name: "Embedding acceleration" });
    await user.click(screen.getByRole("radio", { name: /^CPU/i }));
    await user.click(screen.getByRole("button", { name: /Save settings/i }));
    await waitFor(() => {
      expect(
        mock.calls.some(
          (call) =>
            call.url === "/v1/settings/compute" && call.method === "PUT",
        ),
      ).toBe(true);
    });
    expect(await screen.findByText(/Restart required/i)).toBeInTheDocument();
    expect(screen.getByText(/Pending policy:\s*CPU/i)).toBeInTheDocument();
    mock.restore();
  });

  it("keeps accessible radiogroup label", async () => {
    const mock = installSettingsMocks(computeState());
    renderApp("/settings?section=compute");
    const group = await screen.findByRole("radiogroup", {
      name: /Embedding device policy/i,
    });
    expect(within(group).getAllByRole("radio").length).toBe(3);
    mock.restore();
  });
});
