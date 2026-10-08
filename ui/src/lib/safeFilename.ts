/** Sanitize workspace titles into safe, deterministic download filenames. */

const UNSAFE = /[^a-z0-9]+/gi;

export function slugForFilename(title: string, fallback = "workspace"): string {
  const slug = title
    .trim()
    .toLowerCase()
    .replace(UNSAFE, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
  return slug.length > 0 ? slug : fallback;
}

export function buildExportFilename(
  kind: "question-bank" | "conversation",
  title: string,
  extension: "json" | "md",
): string {
  return `seneca-${kind}-${slugForFilename(title)}.${extension}`;
}
