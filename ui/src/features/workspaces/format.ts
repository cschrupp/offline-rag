export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(kib < 10 ? 1 : 0)} KiB`;
  const mib = kib / 1024;
  return `${mib.toFixed(mib < 10 ? 1 : 0)} MiB`;
}

export function formatMiB(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  const mib = bytes / (1024 * 1024);
  return mib.toFixed(mib < 10 ? 1 : 0);
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function shortenId(value: string | null | undefined, size = 12): string {
  if (!value) return "—";
  if (value.length <= size) return value;
  return `${value.slice(0, size)}…`;
}

export type SourceCapacityLimits = {
  maxActiveSources: number;
  maxBytesPerFile: number;
  maxDesiredActiveBytes: number;
};

export function activeSourceBytes(
  sources: Array<{ byte_size: number }>,
): number {
  return sources.reduce((sum, source) => sum + source.byte_size, 0);
}
