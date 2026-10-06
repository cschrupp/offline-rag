/** One opaque key represents one user intent (S16-D14). */
export function createIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Holds an idempotency key bound to a canonical client-request fingerprint.
 *
 * - Same fingerprint after transport ambiguity → reuse key
 * - Changed fingerprint → new key
 * - Terminal backend success/failure → reset for the next user action
 * - Network ambiguity → keep current key + fingerprint
 */
export class IntentHandle {
  private key: string;
  private boundFingerprint: string | null;

  constructor(key: string = createIdempotencyKey()) {
    this.key = key;
    this.boundFingerprint = null;
  }

  static newIntent(): IntentHandle {
    return new IntentHandle();
  }

  /** Current key (may be unbound until prepare). Prefer prepare(). */
  get currentKey(): string {
    return this.key;
  }

  get fingerprint(): string | null {
    return this.boundFingerprint;
  }

  /**
   * Bind or reuse a key for the canonical request fingerprint about to be sent.
   */
  prepare(fingerprint: string): string {
    if (this.boundFingerprint === null) {
      this.boundFingerprint = fingerprint;
      return this.key;
    }
    if (this.boundFingerprint === fingerprint) {
      return this.key;
    }
    this.key = createIdempotencyKey();
    this.boundFingerprint = fingerprint;
    return this.key;
  }

  /** Terminal success or terminal backend failure → next action is a new intent. */
  reset(): void {
    this.key = createIdempotencyKey();
    this.boundFingerprint = null;
  }
}

export function fingerprintCreateWorkspace(
  title: string,
  description: string,
): string {
  return JSON.stringify({
    op: "create_workspace",
    title,
    description,
  });
}

export function fingerprintPatchWorkspace(params: {
  workspaceId: string;
  revision: number;
  title: string;
  description: string;
}): string {
  return JSON.stringify({
    op: "patch_workspace",
    workspace_id: params.workspaceId,
    expected_revision: params.revision,
    title: params.title,
    description: params.description,
  });
}

export function fingerprintDeleteWorkspace(params: {
  workspaceId: string;
  revision: number;
}): string {
  return JSON.stringify({
    op: "delete_workspace",
    workspace_id: params.workspaceId,
    expected_revision: params.revision,
  });
}

export type FileIdentity = {
  name: string;
  size: number;
  lastModified: number;
  type: string;
};

export function fileIdentity(file: File): FileIdentity {
  return {
    name: file.name,
    size: file.size,
    lastModified: file.lastModified,
    type: file.type,
  };
}

export function fingerprintAddSources(params: {
  workspaceId: string;
  revision: number;
  files: File[];
}): string {
  return JSON.stringify({
    op: "add_sources",
    workspace_id: params.workspaceId,
    expected_revision: params.revision,
    files: params.files.map(fileIdentity),
  });
}

export function fingerprintRenameSource(params: {
  workspaceId: string;
  sourceId: string;
  revision: number;
  displayName: string;
}): string {
  return JSON.stringify({
    op: "rename_source",
    workspace_id: params.workspaceId,
    source_id: params.sourceId,
    expected_revision: params.revision,
    display_name: params.displayName,
  });
}

export function fingerprintReplaceSource(params: {
  workspaceId: string;
  sourceId: string;
  revision: number;
  file: File;
}): string {
  return JSON.stringify({
    op: "replace_source",
    workspace_id: params.workspaceId,
    source_id: params.sourceId,
    expected_revision: params.revision,
    file: fileIdentity(params.file),
  });
}

export function fingerprintRemoveSource(params: {
  workspaceId: string;
  sourceId: string;
  revision: number;
}): string {
  return JSON.stringify({
    op: "remove_source",
    workspace_id: params.workspaceId,
    source_id: params.sourceId,
    expected_revision: params.revision,
  });
}
