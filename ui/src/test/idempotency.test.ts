import { afterEach, describe, expect, it, vi } from "vitest";
import { createIdempotencyKey, IntentHandle } from "../api/idempotency";

const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createIdempotencyKey", () => {
  it("uses the native randomUUID implementation when available", () => {
    const nativeUuid = "7a7b7c7d-1111-4111-8111-123456789abc";
    const randomUUID = vi.fn(() => nativeUuid);
    const getRandomValues = vi.fn((bytes: Uint8Array) => bytes);
    vi.stubGlobal("crypto", { randomUUID, getRandomValues });

    expect(createIdempotencyKey()).toBe(nativeUuid);
    expect(randomUUID).toHaveBeenCalledOnce();
    expect(getRandomValues).not.toHaveBeenCalled();
  });

  it("generates a valid UUID v4 using getRandomValues when randomUUID is absent", () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.fill(0xff);
      return bytes;
    });
    vi.stubGlobal("crypto", { getRandomValues });

    const key = createIdempotencyKey();

    expect(key).toMatch(UUID_V4_PATTERN);
    expect(key).toMatch(/-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-/i);
    expect(getRandomValues).toHaveBeenCalledOnce();
    expect(getRandomValues.mock.calls[0][0]).toHaveLength(16);
  });

  it("returns different keys for separate fallback calls", () => {
    let fillByte = 0;
    vi.stubGlobal("crypto", {
      getRandomValues: vi.fn((bytes: Uint8Array) => {
        fillByte += 1;
        bytes.fill(fillByte);
        return bytes;
      }),
    });

    const first = createIdempotencyKey();
    const second = createIdempotencyKey();

    expect(first).toMatch(UUID_V4_PATTERN);
    expect(second).toMatch(UUID_V4_PATTERN);
    expect(second).not.toBe(first);
  });
});

describe("IntentHandle", () => {
  it("reuses keys for the same fingerprint and rotates them on change and reset", () => {
    let fillByte = 0;
    vi.stubGlobal("crypto", {
      getRandomValues: vi.fn((bytes: Uint8Array) => {
        fillByte += 1;
        bytes.fill(fillByte);
        return bytes;
      }),
    });

    const intent = new IntentHandle("initial-key");
    const first = intent.prepare("fingerprint-a");
    expect(intent.prepare("fingerprint-a")).toBe(first);
    expect(intent.fingerprint).toBe("fingerprint-a");

    const changed = intent.prepare("fingerprint-b");
    expect(changed).not.toBe(first);
    expect(intent.fingerprint).toBe("fingerprint-b");

    intent.reset();
    expect(intent.fingerprint).toBeNull();
    const reset = intent.prepare("fingerprint-b");
    expect(reset).not.toBe(changed);
    expect(intent.fingerprint).toBe("fingerprint-b");
  });
});
