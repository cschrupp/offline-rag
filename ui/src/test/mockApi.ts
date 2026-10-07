import type {
  Capabilities,
  Operation,
  Source,
  Workspace,
} from "../api/types";
import { installUploadHandlerForTests } from "../api/upload";

export function workspace(partial: Partial<Workspace> & Pick<Workspace, "workspace_id">): Workspace {
  return {
    title: "Station Desk",
    description: "Primary sources",
    revision: 1,
    status: "active",
    current_snapshot_id: "snap_1",
    source_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    ...partial,
  };
}

export function source(partial: Partial<Source> & Pick<Source, "source_id">): Source {
  return {
    version: 1,
    display_name: "sops.pdf",
    content_type: "application/pdf",
    byte_size: 2048,
    content_hash: "abc123",
    document_id: "doc_abcdef1234567890",
    created_at: "2026-01-01T00:00:00Z",
    active_from_revision: 2,
    active_from_snapshot_id: "snap_1",
    ...partial,
  };
}

export function operation(
  partial: Partial<Operation> & Pick<Operation, "operation_id">,
): Operation {
  return {
    kind: "source_add",
    workspace_id: "ws_1",
    expected_revision: 1,
    status: "running",
    progress_stage: "processing",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:01Z",
    result: null,
    error: null,
    ...partial,
  };
}

export function capabilities(
  partial: Partial<Capabilities> = {},
): Capabilities {
  return {
    product: {
      name: "Seneca",
      descriptor: "Grounded knowledge workspace",
      ...(partial.product ?? {}),
    },
    source_limits: {
      max_active_sources: 32,
      max_bytes_per_source: 26_214_400,
      max_active_source_bytes: 104_857_600,
      ...(partial.source_limits ?? {}),
    },
    generation: {
      enabled: true,
      provider: "openai_compatible",
      base_url: "http://127.0.0.1:11434/v1",
      model: "local-test-model",
      timeout_seconds: 120,
      ...(partial.generation ?? {}),
    },
  };
}

export function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
}

export function errorResponse(
  code: string,
  message: string,
  status = 409,
  retryable = false,
): Response {
  return jsonResponse(
    {
      error: { code, message },
      retryable,
      details: null,
    },
    { status },
  );
}

export type FetchCall = {
  url: string;
  method: string;
  headers: Headers;
  body: BodyInit | null | undefined;
};

export function installFetchMock(
  handler: (call: FetchCall) => Response | Promise<Response>,
): { calls: FetchCall[]; restore: () => void } {
  const calls: FetchCall[] = [];
  const original = globalThis.fetch;

  // Route dedicated multipart upload transport through the same handler so
  // existing Add Sources tests keep working after the XHR boundary.
  installUploadHandlerForTests(async (uploadCall) => {
    const call: FetchCall = {
      url: uploadCall.path,
      method: uploadCall.method,
      headers: uploadCall.headers,
      body: uploadCall.formData,
    };
    calls.push(call);

    if (uploadCall.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }

    const waitAbort = new Promise<never>((_resolve, reject) => {
      if (!uploadCall.signal) return;
      uploadCall.signal.addEventListener(
        "abort",
        () => reject(new DOMException("Aborted", "AbortError")),
        { once: true },
      );
    });

    const response = await Promise.race([
      Promise.resolve(handler(call)),
      waitAbort,
    ]);

    if (
      response.status === 404 &&
      (uploadCall.path === "/v1/capabilities" ||
        uploadCall.path.endsWith("/v1/capabilities"))
    ) {
      return { status: 200, body: capabilities() };
    }

    let body: unknown = null;
    const contentType = response.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      try {
        body = await response.json();
      } catch {
        body = null;
      }
    }
    return { status: response.status, body };
  });

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    const call: FetchCall = { url, method, headers, body: init?.body };
    calls.push(call);
    const response = await handler(call);
    // Workspace capacity needs capabilities; default when tests leave them unhandled.
    if (
      response.status === 404 &&
      (url === "/v1/capabilities" || url.endsWith("/v1/capabilities"))
    ) {
      return jsonResponse(capabilities());
    }
    return response;
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
      installUploadHandlerForTests(null);
    },
  };
}
