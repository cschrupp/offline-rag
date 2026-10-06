import type { Operation, Source, Workspace } from "../api/types";

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
    return handler(call);
  }) as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}
