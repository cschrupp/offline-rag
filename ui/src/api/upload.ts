import { ApiError, parseErrorEnvelope } from "./errors";

export type MultipartUploadRequest = {
  path: string;
  formData: FormData;
  idempotencyKey: string;
  ifMatch: string | number;
  signal?: AbortSignal;
};

export type MultipartUploadCall = {
  path: string;
  method: string;
  headers: Headers;
  formData: FormData;
  signal?: AbortSignal;
};

type MultipartUploadHandler = (
  call: MultipartUploadCall,
) => Promise<{ status: number; body: unknown }>;

function quotedRevision(revision: string | number): string {
  const text = String(revision).trim();
  if (text.startsWith('"') && text.endsWith('"')) {
    return text;
  }
  return `"${text}"`;
}

/** Test seam — production uses XHR. */
let testUploadHandler: MultipartUploadHandler | null = null;

export function installUploadHandlerForTests(
  handler: MultipartUploadHandler | null,
): void {
  testUploadHandler = handler;
}

function abortedError(): ApiError {
  return new ApiError({
    kind: "network",
    code: "request_aborted",
    message: "Upload canceled before Seneca confirmed acceptance.",
    retryable: false,
    status: null,
  });
}

function interruptedError(): ApiError {
  return new ApiError({
    kind: "network",
    code: "upload_transport_interrupted",
    message:
      "Seneca couldn't confirm whether this upload was accepted. Retry the same upload safely.",
    retryable: true,
    status: null,
  });
}

function parseJsonBody(text: string): unknown {
  if (!text.trim()) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function resolveResponsePayload<T>(status: number, body: unknown): T {
  if (status === 204) {
    return undefined as T;
  }
  if (status >= 200 && status < 300) {
    return body as T;
  }
  const apiError = parseErrorEnvelope(body, status);
  if (apiError) {
    throw apiError;
  }
  throw new ApiError({
    kind: "unexpected",
    code: "unexpected_response",
    message: `Request failed with status ${status}`,
    retryable: false,
    status,
  });
}

/**
 * Browser multipart upload via XMLHttpRequest.
 * Does NOT set Content-Type — the browser owns the multipart boundary.
 */
function xhrMultipartUpload<T>(request: MultipartUploadRequest): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (!request.path.startsWith("/")) {
      reject(new Error("API paths must be root-relative"));
      return;
    }

    const xhr = new XMLHttpRequest();
    let settled = false;

    const settleReject = (error: unknown) => {
      if (settled) return;
      settled = true;
      reject(error);
    };

    const settleResolve = (value: T) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };

    const onAbort = () => {
      xhr.abort();
    };

    if (request.signal?.aborted) {
      settleReject(abortedError());
      return;
    }
    request.signal?.addEventListener("abort", onAbort);

    xhr.open("POST", request.path);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("Idempotency-Key", request.idempotencyKey);
    xhr.setRequestHeader("If-Match", quotedRevision(request.ifMatch));
    // Do not set Content-Type — browser supplies multipart boundary.

    xhr.onload = () => {
      request.signal?.removeEventListener("abort", onAbort);
      if (settled) return;
      if (request.signal?.aborted) {
        settleReject(abortedError());
        return;
      }
      try {
        const body = parseJsonBody(xhr.responseText);
        settleResolve(resolveResponsePayload<T>(xhr.status, body));
      } catch (error) {
        settleReject(error);
      }
    };

    xhr.onerror = () => {
      request.signal?.removeEventListener("abort", onAbort);
      if (request.signal?.aborted) {
        settleReject(abortedError());
        return;
      }
      settleReject(interruptedError());
    };

    xhr.onabort = () => {
      request.signal?.removeEventListener("abort", onAbort);
      settleReject(abortedError());
    };

    try {
      xhr.send(request.formData);
    } catch {
      request.signal?.removeEventListener("abort", onAbort);
      if (request.signal?.aborted) {
        settleReject(abortedError());
        return;
      }
      settleReject(interruptedError());
    }
  });
}

async function testHandlerUpload<T>(
  request: MultipartUploadRequest,
): Promise<T> {
  if (!testUploadHandler) {
    throw new Error("upload test handler missing");
  }
  if (request.signal?.aborted) {
    throw abortedError();
  }

  const headers = new Headers({
    Accept: "application/json",
    "Idempotency-Key": request.idempotencyKey,
    "If-Match": quotedRevision(request.ifMatch),
  });

  let aborted = false;
  const onAbort = () => {
    aborted = true;
  };
  request.signal?.addEventListener("abort", onAbort);

  try {
    const result = await testUploadHandler({
      path: request.path,
      method: "POST",
      headers,
      formData: request.formData,
      signal: request.signal,
    });
    if (aborted || request.signal?.aborted) {
      throw abortedError();
    }
    return resolveResponsePayload<T>(result.status, result.body);
  } catch (error) {
    if (aborted || request.signal?.aborted) {
      throw abortedError();
    }
    if (error instanceof ApiError) {
      throw error;
    }
    throw interruptedError();
  } finally {
    request.signal?.removeEventListener("abort", onAbort);
  }
}

export function uploadMultipart<T>(
  request: MultipartUploadRequest,
): Promise<T> {
  if (testUploadHandler) {
    return testHandlerUpload<T>(request);
  }
  return xhrMultipartUpload<T>(request);
}
