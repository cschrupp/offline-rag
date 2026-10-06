export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(kib < 10 ? 1 : 0)} KiB`;
  const mib = kib / 1024;
  return `${mib.toFixed(mib < 10 ? 1 : 0)} MiB`;
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

/** Frozen backend safety envelope (client hints only). */
export const SOURCE_LIMITS = {
  maxActiveSources: 32,
  maxBytesPerFile: 25 * 1024 * 1024,
  maxDesiredActiveBytes: 100 * 1024 * 1024,
} as const;
