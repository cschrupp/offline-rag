export type TextLineWindow = {
  startLine: number; // 1-based
  lines: Array<{ lineNumber: number; text: string; cited: boolean }>;
  hasExactLocation: boolean;
};

const CONTEXT = 20;
const MAX_PREVIEW_LINES = 200;

export function buildTextLineWindow(
  text: string,
  lineStart: number | null,
  lineEnd: number | null,
): TextLineWindow {
  const allLines = text.split(/\r?\n/);
  const hasExact =
    typeof lineStart === "number" &&
    lineStart >= 1 &&
    typeof lineEnd === "number" &&
    lineEnd >= lineStart;

  if (!hasExact) {
    const slice = allLines.slice(0, MAX_PREVIEW_LINES);
    return {
      startLine: 1,
      hasExactLocation: false,
      lines: slice.map((textLine, index) => ({
        lineNumber: index + 1,
        text: textLine,
        cited: false,
      })),
    };
  }

  const start = Math.max(1, lineStart! - CONTEXT);
  const end = Math.min(allLines.length, lineEnd! + CONTEXT);
  const boundedEnd = Math.min(end, start + MAX_PREVIEW_LINES - 1);
  const lines = [];
  for (let lineNumber = start; lineNumber <= boundedEnd; lineNumber += 1) {
    lines.push({
      lineNumber,
      text: allLines[lineNumber - 1] ?? "",
      cited: lineNumber >= lineStart! && lineNumber <= lineEnd!,
    });
  }
  return { startLine: start, lines, hasExactLocation: true };
}

export function isTextPreviewContentType(contentType: string): boolean {
  const base = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return (
    base === "text/plain" ||
    base === "text/markdown" ||
    base === "text/x-markdown" ||
    base.startsWith("text/")
  );
}

export function isPdfContentType(contentType: string): boolean {
  const base = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return base === "application/pdf";
}

export function isUnsafePreviewContentType(contentType: string): boolean {
  const base = contentType.split(";")[0]?.trim().toLowerCase() ?? "";
  return (
    base === "text/html" ||
    base === "application/xhtml+xml" ||
    base === "image/svg+xml" ||
    base.includes("javascript")
  );
}
