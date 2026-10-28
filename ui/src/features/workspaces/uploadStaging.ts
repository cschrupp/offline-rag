import type { SourceCapacityLimits } from "./format";

const SUPPORTED_EXTENSIONS = new Set([".pdf", ".txt", ".md", ".markdown"]);

export type UploadSelectionValidation = {
  fileErrors: Array<string | null>;
  aggregateErrors: string[];
};

function stagingIdentity(file: File): string {
  return JSON.stringify([
    file.name,
    file.size,
    file.lastModified,
    file.type,
  ]);
}

/** Append newly selected files while preserving order and dropping repeats. */
export function appendUniqueFiles(current: File[], incoming: File[]): File[] {
  const staged = [...current];
  const identities = new Set(staged.map(stagingIdentity));

  for (const file of incoming) {
    const identity = stagingIdentity(file);
    if (identities.has(identity)) continue;
    identities.add(identity);
    staged.push(file);
  }

  return staged;
}

function extensionOf(name: string): string {
  const separator = name.lastIndexOf(".");
  return separator < 0 ? "" : name.slice(separator).toLowerCase();
}

function formatMiB(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0);
}

/** Validate upload envelopes without attempting to duplicate parser checks. */
export function validateUploadSelection(params: {
  files: File[];
  limits: SourceCapacityLimits | null;
  existingSourceCount: number;
  existingSourceBytes: number;
}): UploadSelectionValidation {
  const { files, limits, existingSourceCount, existingSourceBytes } = params;
  const fileErrors = files.map((file) => {
    const extension = extensionOf(file.name);
    if (!SUPPORTED_EXTENSIONS.has(extension)) {
      return `${file.name} is not a supported file type. Choose PDF, TXT, or Markdown.`;
    }
    if (!limits) return null;

    // The server's validated extension mapping, not multipart MIME, decides PDF policy.
    const isPdf = extension === ".pdf";
    const limit = isPdf
      ? limits.maxBytesPerPdfSource
      : limits.maxBytesPerUploadedFile;
    if (file.size > limit) {
      return `${file.name} exceeds the ${formatMiB(limit)} MiB per-file upload limit.`;
    }
    return null;
  });

  const aggregateErrors: string[] = [];
  if (files.length === 0) {
    aggregateErrors.push("Select at least one file.");
  }
  if (limits) {
    if (files.length > limits.maxFilesPerUploadRequest) {
      aggregateErrors.push(
        `At most ${limits.maxFilesPerUploadRequest} ${limits.maxFilesPerUploadRequest === 1 ? "file" : "files"} may be uploaded in one request.`,
      );
    }

    const incomingBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (incomingBytes > limits.maxBytesPerUploadRequest) {
      aggregateErrors.push(
        `Selected files exceed the ${formatMiB(limits.maxBytesPerUploadRequest)} MiB per-request upload limit.`,
      );
    }
    if (
      limits.maxActiveSourceBytes != null &&
      existingSourceBytes + incomingBytes > limits.maxActiveSourceBytes
    ) {
      aggregateErrors.push(
        `Selected files exceed the ${formatMiB(limits.maxActiveSourceBytes)} MiB workspace source limit.`,
      );
    }
    if (
      limits.maxActiveSources != null &&
      existingSourceCount + files.length > limits.maxActiveSources
    ) {
      aggregateErrors.push(
        `At most ${limits.maxActiveSources} active sources are allowed in this workspace.`,
      );
    }
  }

  return { fileErrors, aggregateErrors };
}
