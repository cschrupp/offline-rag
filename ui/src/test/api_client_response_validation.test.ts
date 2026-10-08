import { afterEach, describe, expect, it, vi } from "vitest";
import { listSources } from "../api/client";
import { ApiError } from "../api/errors";
import { validateSourceListResponse } from "../api/sourceListValidation";
import { source } from "./mockApi";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("validateSourceListResponse", () => {
  it("accepts a valid SourceListResponse", () => {
    const validated = validateSourceListResponse(
      {
        workspace_id: "ws_1",
        revision: 7,
        sources: [source({ source_id: "src_1" })],
      },
      "ws_1",
    );
    expect(validated.sources).toHaveLength(1);
  });

  it("rejects null, {}, missing sources, wrong workspace, invalid entries", () => {
    expect(() => validateSourceListResponse(null, "ws_1")).toThrow(ApiError);
    expect(() => validateSourceListResponse({}, "ws_1")).toThrow(ApiError);
    expect(() =>
      validateSourceListResponse({ workspace_id: "ws_1", revision: 7 }, "ws_1"),
    ).toThrow(ApiError);
    expect(() =>
      validateSourceListResponse(
        { workspace_id: "ws_other", revision: 7, sources: [] },
        "ws_1",
      ),
    ).toThrow(ApiError);
    expect(() =>
      validateSourceListResponse(
        { workspace_id: "ws_1", revision: 7, sources: [{ source_id: "x" }] },
        "ws_1",
      ),
    ).toThrow(ApiError);
  });
});

describe("apiRequest JSON parse fail-closed via listSources", () => {
  it("throws ApiError on incomplete JSON instead of succeeding with null", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("{", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(listSources("ws_1")).rejects.toMatchObject({
      name: "ApiError",
      code: "unexpected_response",
      retryable: true,
    });
  });

  it("throws ApiError on HTTP 200 null JSON body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("null", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    await expect(listSources("ws_1")).rejects.toBeInstanceOf(ApiError);
  });
});
