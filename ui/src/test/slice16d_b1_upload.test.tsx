import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { addSources } from "../api/client";
import { ApiError, userFacingErrorMessage } from "../api/errors";
import { installUploadHandlerForTests } from "../api/upload";
import { ACTIVE_OPERATIONS_KEY } from "../features/operations/activeOperations";
import {
  capabilities,
  errorResponse,
  installFetchMock,
  jsonResponse,
  operation,
  workspace,
} from "./mockApi";
import { renderApp } from "./render";

afterEach(() => {
  installUploadHandlerForTests(null);
  localStorage.removeItem(ACTIVE_OPERATIONS_KEY);
});

describe("B1 upload transport — multipart contract", () => {
  it("posts N files as one request with N repeated files parts and no manual Content-Type", async () => {
    const calls: Array<{
      headers: Headers;
      formData: FormData;
    }> = [];

    installUploadHandlerForTests(async (call) => {
      calls.push({ headers: call.headers, formData: call.formData });
      expect(call.headers.has("Content-Type")).toBe(false);
      expect(call.headers.get("Idempotency-Key")).toBeTruthy();
      expect(call.headers.get("If-Match")).toBe('"5"');
      return {
        status: 202,
        body: operation({
          operation_id: `op_${calls.length}`,
          status: "pending",
        }),
      };
    });

    const two = [
      new File(["a"], "a.txt", { type: "text/plain" }),
      new File(["b"], "b.txt", { type: "text/plain" }),
    ];
    await addSources({
      workspaceId: "ws_1",
      files: two,
      revision: 5,
      idempotencyKey: "key-n",
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]!.formData.getAll("files")).toHaveLength(2);
    expect(calls[0]!.headers.get("Idempotency-Key")).toBe("key-n");

    const four = [
      new File(["1"], "1.txt", { type: "text/plain" }),
      new File(["2"], "2.txt", { type: "text/plain" }),
      new File(["3"], "3.txt", { type: "text/plain" }),
      new File(["4"], "4.txt", { type: "text/plain" }),
    ];
    await addSources({
      workspaceId: "ws_1",
      files: four,
      revision: 5,
      idempotencyKey: "key-n2",
    });
    expect(calls).toHaveLength(2);
    expect(calls[1]!.formData.getAll("files")).toHaveLength(4);
    expect(calls[1]!.headers.get("Idempotency-Key")).toBe("key-n2");
  });
});

describe("B1 upload — error copy", () => {
  it("distinguishes abort, transport interruption, and canonical conflicts", () => {
    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "network",
          code: "request_aborted",
          message: "Upload canceled before Seneca confirmed acceptance.",
        }),
      ),
    ).toMatch(/canceled before Seneca confirmed acceptance/i);
    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "network",
          code: "request_aborted",
          message: "Upload canceled before Seneca confirmed acceptance.",
        }),
      ),
    ).not.toMatch(/Could not reach OfflineRAG/);

    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "network",
          code: "upload_transport_interrupted",
          message:
            "Seneca couldn't confirm whether this upload was accepted. Retry the same upload safely.",
          retryable: true,
        }),
      ),
    ).toMatch(/couldn't confirm whether this upload was accepted/i);
    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "network",
          code: "upload_transport_interrupted",
          message:
            "Seneca couldn't confirm whether this upload was accepted. Retry the same upload safely.",
          retryable: true,
        }),
      ),
    ).not.toMatch(/Could not reach OfflineRAG/);

    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "api",
          code: "workspace_conflict",
          message: "conflict",
        }),
      ),
    ).toMatch(/workspace changed since you last loaded it/i);

    expect(
      userFacingErrorMessage(
        new ApiError({
          kind: "api",
          code: "idempotency_conflict",
          message: "conflict",
        }),
      ),
    ).toMatch(/conflicts with a different earlier action/i);
  });
});

describe("B1 upload — immutable intent / safe retry", () => {
  it("retries with frozen revision + key after transport ambiguity even if live revision advances", async () => {
    const user = userEvent.setup();
    const posts: Array<{ ifMatch: string | null; key: string | null }> = [];
    let attempt = 0;
    let liveRevision = 5;

    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Upload Desk",
            revision: liveRevision,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: liveRevision,
          sources: [],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        posts.push({
          ifMatch: call.headers.get("If-Match"),
          key: call.headers.get("Idempotency-Key"),
        });
        const form = call.body as FormData;
        expect(form.getAll("files")).toHaveLength(2);
        attempt += 1;
        if (attempt === 1) {
          throw new TypeError("Failed to fetch");
        }
        return jsonResponse(
          operation({
            operation_id: "op_replay",
            status: "pending",
            progress_stage: "preparing",
            expected_revision: 5,
          }),
          { status: 202 },
        );
      }
      if (call.url === "/v1/operations/op_replay") {
        return jsonResponse(
          operation({
            operation_id: "op_replay",
            status: "running",
            progress_stage: "processing",
          }),
        );
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    const addButtons = await screen.findAllByRole("button", {
      name: "+ Add sources",
    });
    await user.click(addButtons[0]!);
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    const fileA = new File(["aaa"], "a.txt", { type: "text/plain" });
    const fileB = new File(["bbb"], "b.txt", { type: "text/plain" });
    await user.upload(within(dialog).getByLabelText(/source files/i), [
      fileA,
      fileB,
    ]);
    await user.click(
      within(dialog).getByRole("button", { name: /^add sources$/i }),
    );

    expect(
      await within(dialog).findByText(
        /couldn't confirm whether this upload was accepted/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: /retry safely/i }),
    ).toBeInTheDocument();

    // Live workspace advances — must not alter frozen retry identity.
    liveRevision = 6;
    await user.click(
      within(dialog).getByRole("button", { name: /retry safely/i }),
    );

    await waitFor(() => {
      expect(posts.length).toBeGreaterThanOrEqual(2);
    });
    expect(posts[0]!.ifMatch).toBe('"5"');
    expect(posts[1]!.ifMatch).toBe('"5"');
    expect(posts[1]!.key).toBe(posts[0]!.key);
    expect(posts[1]!.key).toBeTruthy();

    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: /add sources/i })).toBeNull();
    });
    await waitFor(() => {
      const stored = JSON.parse(
        localStorage.getItem(ACTIVE_OPERATIONS_KEY) ?? "[]",
      ) as Array<{ operation_id: string }>;
      expect(
        stored.filter((item) => item.operation_id === "op_replay"),
      ).toHaveLength(1);
    });

    mock.restore();
  });

  it("surfaces workspace_conflict on safe retry without auto-adapting revision", async () => {
    const user = userEvent.setup();
    let attempt = 0;
    const posts: Array<{ ifMatch: string | null; key: string | null }> = [];
    const mock = installFetchMock(async (call) => {
      if (call.url === "/v1/capabilities") return jsonResponse(capabilities());
      if (call.url === "/health/ready") return jsonResponse({ status: "ready" });
      if (call.url === "/v1/workspaces/ws_1" && call.method === "GET") {
        return jsonResponse(
          workspace({
            workspace_id: "ws_1",
            title: "Conflict Desk",
            revision: 5,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 5,
          sources: [],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        posts.push({
          ifMatch: call.headers.get("If-Match"),
          key: call.headers.get("Idempotency-Key"),
        });
        attempt += 1;
        if (attempt === 1) {
          throw new TypeError("Failed to fetch");
        }
        return errorResponse(
          "workspace_conflict",
          "Workspace revision conflict",
          409,
        );
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(
      (await screen.findAllByRole("button", { name: "+ Add sources" }))[0]!,
    );
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    await user.upload(
      within(dialog).getByLabelText(/source files/i),
      new File(["x"], "x.txt", { type: "text/plain" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: /^add sources$/i }),
    );
    expect(
      await within(dialog).findByRole("button", { name: /retry safely/i }),
    ).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: /retry safely/i }),
    );

    expect(
      await within(dialog).findByText(
        /workspace changed since you last loaded it/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: /retry safely/i }),
    ).toBeNull();
    expect(posts).toHaveLength(2);
    expect(posts[0]!.ifMatch).toBe('"5"');
    expect(posts[1]!.ifMatch).toBe('"5"');
    expect(posts[1]!.key).toBe(posts[0]!.key);
    // No third automatic post with revision 6.
    expect(posts).toHaveLength(2);
    mock.restore();
  });

  it("cancels pre-202 upload without fabricating an operation", async () => {
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
            title: "Cancel Desk",
            revision: 1,
            source_count: 0,
            status: "empty",
            current_snapshot_id: null,
          }),
        );
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "GET") {
        return jsonResponse({
          workspace_id: "ws_1",
          revision: 1,
          sources: [],
        });
      }
      if (call.url === "/v1/workspaces/ws_1/sources" && call.method === "POST") {
        return addGate;
      }
      if (call.url === "/v1/workspaces") return jsonResponse([]);
      return errorResponse("not_found", "x", 404);
    });

    renderApp("/workspaces/ws_1");
    await user.click(
      (await screen.findAllByRole("button", { name: "+ Add sources" }))[0]!,
    );
    const dialog = await screen.findByRole("dialog", { name: /add sources/i });
    await user.upload(
      within(dialog).getByLabelText(/source files/i),
      new File(["z"], "z.txt", { type: "text/plain" }),
    );
    await user.click(
      within(dialog).getByRole("button", { name: /^add sources$/i }),
    );
    const cancelUpload = await within(dialog).findByRole("button", {
      name: /cancel upload/i,
    });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeEnabled();
    await user.click(cancelUpload);

    expect(
      await within(dialog).findByText(
        /canceled before Seneca confirmed acceptance/i,
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: /retry safely/i }),
    ).toBeNull();
    expect(localStorage.getItem(ACTIVE_OPERATIONS_KEY)).toBeNull();
    // Late response must not fabricate a remembered operation after abort.
    releaseAdd?.(
      jsonResponse(
        operation({ operation_id: "op_late", status: "pending" }),
        { status: 202 },
      ),
    );
    await waitFor(() => {
      expect(localStorage.getItem(ACTIVE_OPERATIONS_KEY)).toBeNull();
    });
    mock.restore();
  });
});

describe("B1 upload — XHR Content-Type boundary", () => {
  it("does not manually set multipart Content-Type on real XHR path", async () => {
    installUploadHandlerForTests(null);
    const setRequestHeader = vi.fn();
    const send = vi.fn();
    const listeners: Record<string, () => void> = {};

    class FakeXHR {
      status = 202;
      responseText = JSON.stringify(
        operation({ operation_id: "op_xhr", status: "pending" }),
      );
      upload = {};
      open = vi.fn();
      abort = vi.fn();
      setRequestHeader = setRequestHeader;
      send = (body: Document | XMLHttpRequestBodyInit | null | undefined) => {
        send(body);
        listeners.onload?.();
      };
      addEventListener() {
        /* unused */
      }
      removeEventListener() {
        /* unused */
      }
      set onload(fn: () => void) {
        listeners.onload = fn;
      }
      set onerror(fn: () => void) {
        listeners.onerror = fn;
      }
      set onabort(fn: () => void) {
        listeners.onabort = fn;
      }
    }

    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);
    try {
      await addSources({
        workspaceId: "ws_1",
        files: [
          new File(["a"], "a.txt", { type: "text/plain" }),
          new File(["b"], "b.txt", { type: "text/plain" }),
        ],
        revision: 2,
        idempotencyKey: "xhr-key",
      });
      const headerNames = setRequestHeader.mock.calls.map(
        (call: unknown[]) => String(call[0]).toLowerCase(),
      );
      expect(headerNames).toContain("accept");
      expect(headerNames).toContain("idempotency-key");
      expect(headerNames).toContain("if-match");
      expect(headerNames).not.toContain("content-type");
      expect(send).toHaveBeenCalledTimes(1);
      expect(send.mock.calls[0]![0]).toBeInstanceOf(FormData);
      expect((send.mock.calls[0]![0] as FormData).getAll("files")).toHaveLength(
        2,
      );
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
