import { ApiError, parseErrorEnvelope } from "./errors";
import type {
  Capabilities,
  GenerationProbeResult,
  GenerationSettingsState,
  HealthReady,
  Operation,
  Source,
  SourceListResponse,
  Workspace,
  WorkspaceQueryResponse,
} from "./types";
import { uploadMultipart } from "./upload";

export type RequestOptions = {
  method?: string;
  headers?: Record<string, string>;
  body?: BodyInit | null;
  signal?: AbortSignal;
  /** When set, transport-level retries reuse these exact headers/body. */
  idempotencyKey?: string;
  ifMatch?: string | number;
  json?: unknown;
};

function quotedRevision(revision: string | number): string {
  const text = String(revision).trim();
  if (text.startsWith('"') && text.endsWith('"')) {
    return text;
  }
  return `"${text}"`;
}

async function readPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
  // Never surface raw HTML/exception bodies to callers as primary UX.
  try {
    await response.text();
  } catch {
    /* ignore */
  }
  return null;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  if (!path.startsWith("/")) {
    throw new Error("API paths must be root-relative");
  }

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers ?? {}),
  };

  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.ifMatch !== undefined) {
    headers["If-Match"] = quotedRevision(options.ifMatch);
  }

  let body = options.body ?? null;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
    });
  } catch {
    throw new ApiError({
      kind: "network",
      code: "network_error",
      message:
        "Could not reach OfflineRAG. Check that this installation is running and reachable.",
      retryable: true,
      status: null,
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    const apiError = parseErrorEnvelope(payload, response.status);
    if (apiError) {
      throw apiError;
    }
    throw new ApiError({
      kind: "unexpected",
      code: "unexpected_response",
      message: `Request failed with status ${response.status}`,
      retryable: false,
      status: response.status,
    });
  }

  return payload as T;
}

export function getHealthReady(signal?: AbortSignal): Promise<HealthReady> {
  return apiRequest<HealthReady>("/health/ready", { signal });
}

export function listWorkspaces(signal?: AbortSignal): Promise<Workspace[]> {
  return apiRequest<Workspace[]>("/v1/workspaces", { signal });
}

export function getWorkspace(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<Workspace> {
  return apiRequest<Workspace>(`/v1/workspaces/${workspaceId}`, { signal });
}

export function createWorkspace(params: {
  title: string;
  description: string;
  idempotencyKey: string;
}): Promise<Workspace> {
  return apiRequest<Workspace>("/v1/workspaces", {
    method: "POST",
    idempotencyKey: params.idempotencyKey,
    json: { title: params.title, description: params.description },
  });
}

export function patchWorkspace(params: {
  workspaceId: string;
  title?: string;
  description?: string;
  revision: number;
  idempotencyKey: string;
}): Promise<Workspace> {
  const body: Record<string, string> = {};
  if (params.title !== undefined) body.title = params.title;
  if (params.description !== undefined) body.description = params.description;
  return apiRequest<Workspace>(`/v1/workspaces/${params.workspaceId}`, {
    method: "PATCH",
    idempotencyKey: params.idempotencyKey,
    ifMatch: params.revision,
    json: body,
  });
}

export function deleteWorkspace(params: {
  workspaceId: string;
  revision: number;
  idempotencyKey: string;
}): Promise<Workspace> {
  return apiRequest<Workspace>(`/v1/workspaces/${params.workspaceId}`, {
    method: "DELETE",
    idempotencyKey: params.idempotencyKey,
    ifMatch: params.revision,
  });
}

export function listSources(
  workspaceId: string,
  signal?: AbortSignal,
): Promise<SourceListResponse> {
  return apiRequest<SourceListResponse>(
    `/v1/workspaces/${workspaceId}/sources`,
    { signal },
  );
}

export function addSources(params: {
  workspaceId: string;
  files: File[];
  revision: number;
  idempotencyKey: string;
  signal?: AbortSignal;
}): Promise<Operation> {
  const form = new FormData();
  for (const file of params.files) {
    form.append("files", file, file.name);
  }
  // Dedicated multipart transport (XHR): abortable, honest interruption
  // classification, browser-owned Content-Type boundary.
  return uploadMultipart<Operation>({
    path: `/v1/workspaces/${params.workspaceId}/sources`,
    formData: form,
    idempotencyKey: params.idempotencyKey,
    ifMatch: params.revision,
    signal: params.signal,
  });
}

export function renameSource(params: {
  workspaceId: string;
  sourceId: string;
  displayName: string;
  revision: number;
  idempotencyKey: string;
}): Promise<Source> {
  return apiRequest<Source>(
    `/v1/workspaces/${params.workspaceId}/sources/${params.sourceId}`,
    {
      method: "PATCH",
      idempotencyKey: params.idempotencyKey,
      ifMatch: params.revision,
      json: { display_name: params.displayName },
    },
  );
}

export function replaceSource(params: {
  workspaceId: string;
  sourceId: string;
  file: File;
  revision: number;
  idempotencyKey: string;
}): Promise<Operation> {
  const form = new FormData();
  form.append("files", params.file, params.file.name);
  return apiRequest<Operation>(
    `/v1/workspaces/${params.workspaceId}/sources/${params.sourceId}`,
    {
      method: "PUT",
      idempotencyKey: params.idempotencyKey,
      ifMatch: params.revision,
      body: form,
    },
  );
}

export function removeSource(params: {
  workspaceId: string;
  sourceId: string;
  revision: number;
  idempotencyKey: string;
}): Promise<Operation> {
  return apiRequest<Operation>(
    `/v1/workspaces/${params.workspaceId}/sources/${params.sourceId}`,
    {
      method: "DELETE",
      idempotencyKey: params.idempotencyKey,
      ifMatch: params.revision,
    },
  );
}

export function getOperation(
  operationId: string,
  signal?: AbortSignal,
): Promise<Operation> {
  return apiRequest<Operation>(`/v1/operations/${operationId}`, { signal });
}

export function getCapabilities(signal?: AbortSignal): Promise<Capabilities> {
  return apiRequest<Capabilities>("/v1/capabilities", { signal });
}

export function getGenerationSettings(
  signal?: AbortSignal,
): Promise<GenerationSettingsState> {
  return apiRequest<GenerationSettingsState>("/v1/settings/generation", {
    signal,
  });
}

export function probeGenerationSettings(body: {
  enabled: boolean;
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key?: string | null;
  api_key_action: "keep" | "set" | "clear";
}): Promise<GenerationProbeResult> {
  return apiRequest<GenerationProbeResult>("/v1/settings/generation/probe", {
    method: "POST",
    json: body,
  });
}

export function saveGenerationSettings(body: {
  enabled: boolean;
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key?: string | null;
  api_key_action: "keep" | "set" | "clear";
}): Promise<{
  saved: boolean;
  restart_required: boolean;
  pending: GenerationSettingsState["pending"];
  active: GenerationSettingsState["active"];
}> {
  return apiRequest("/v1/settings/generation", {
    method: "PUT",
    json: body,
  });
}

export function queryWorkspace(params: {
  workspaceId: string;
  question: string;
  sourceIds?: string[];
  signal?: AbortSignal;
}): Promise<WorkspaceQueryResponse> {
  const body: { question: string; source_ids?: string[] } = {
    question: params.question,
  };
  if (params.sourceIds !== undefined) {
    body.source_ids = params.sourceIds;
  }
  return apiRequest<WorkspaceQueryResponse>(
    `/v1/workspaces/${params.workspaceId}/query`,
    {
      method: "POST",
      json: body,
      signal: params.signal,
    },
  );
}

export type SourceContentFetch = {
  blob: Blob;
  contentType: string;
  etag: string | null;
};

async function fetchSourceBytes(
  path: string,
  signal?: AbortSignal,
): Promise<SourceContentFetch> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "GET",
      headers: { Accept: "*/*" },
      signal,
    });
  } catch {
    throw new ApiError({
      kind: "network",
      code: "network_error",
      message:
        "Could not reach OfflineRAG. Check that this installation is running and reachable.",
      retryable: true,
      status: null,
    });
  }
  if (!response.ok) {
    const payload = await readPayload(response);
    const apiError = parseErrorEnvelope(payload, response.status);
    if (apiError) throw apiError;
    throw new ApiError({
      kind: "unexpected",
      code: "unexpected_response",
      message: `Request failed with status ${response.status}`,
      retryable: false,
      status: response.status,
    });
  }
  return {
    blob: await response.blob(),
    contentType: response.headers.get("content-type") ?? "application/octet-stream",
    etag: response.headers.get("etag"),
  };
}

export function getSourceContent(params: {
  workspaceId: string;
  sourceId: string;
  signal?: AbortSignal;
}): Promise<SourceContentFetch> {
  return fetchSourceBytes(
    `/v1/workspaces/${params.workspaceId}/sources/${params.sourceId}/content`,
    params.signal,
  );
}

export function getSourceVersionContent(params: {
  workspaceId: string;
  sourceId: string;
  version: number;
  workspaceRevision: number;
  signal?: AbortSignal;
}): Promise<SourceContentFetch> {
  const path =
    `/v1/workspaces/${params.workspaceId}/sources/${params.sourceId}` +
    `/versions/${params.version}/content` +
    `?workspace_revision=${params.workspaceRevision}`;
  return fetchSourceBytes(path, params.signal);
}
