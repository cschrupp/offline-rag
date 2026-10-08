/** Seneca Question Bank JSON/Markdown interchange (Amendment A4). */

import type { DownloadArtifact } from "../../lib/downloadFile";
import { buildExportFilename } from "../../lib/safeFilename";
import {
  PROMPT_MAX,
  type SavedTrainingPrompt,
} from "./trainingPrompts";

export const QUESTION_BANK_FORMAT = "seneca-question-bank";
export const QUESTION_BANK_VERSION = 1;
/** Deterministic local file-size guard (bytes). */
export const QUESTION_BANK_MAX_BYTES = 256 * 1024;

export type QuestionBankDocument = {
  format: typeof QUESTION_BANK_FORMAT;
  version: typeof QUESTION_BANK_VERSION;
  title?: string;
  exported_at?: string;
  questions: Array<{ text: string }>;
};

export type ImportClassification =
  | "new"
  | "duplicate"
  | "invalid"
  | "capacity-skipped";

export type ImportPlanEntry = {
  text: string;
  classification: ImportClassification;
};

export type QuestionBankImportPlan = {
  title: string | null;
  entries: ImportPlanEntry[];
  newCount: number;
  duplicateCount: number;
  invalidCount: number;
  capacitySkippedCount: number;
  importableTexts: string[];
};

export type ParseQuestionBankResult =
  | { ok: true; questions: string[]; title: string | null }
  | { ok: false; error: string };

function stripBom(raw: string): string {
  return raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
}

function normalizeQuestionLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function exportQuestionBankJson(
  prompts: SavedTrainingPrompt[],
  workspaceTitle: string,
  exportedAt: string = new Date().toISOString(),
): DownloadArtifact {
  const doc: QuestionBankDocument = {
    format: QUESTION_BANK_FORMAT,
    version: QUESTION_BANK_VERSION,
    title: workspaceTitle,
    exported_at: exportedAt,
    questions: prompts.map((prompt) => ({ text: prompt.text })),
  };
  return {
    filename: buildExportFilename("question-bank", workspaceTitle, "json"),
    mimeType: "application/json;charset=utf-8",
    content: `${JSON.stringify(doc, null, 2)}\n`,
  };
}

export function exportQuestionBankMarkdown(
  prompts: SavedTrainingPrompt[],
  workspaceTitle: string,
): DownloadArtifact {
  const lines = [
    `# Seneca Question Bank — ${workspaceTitle}`,
    "",
    ...prompts.map((prompt) => `- ${normalizeQuestionLine(prompt.text)}`),
    "",
  ];
  return {
    filename: buildExportFilename("question-bank", workspaceTitle, "md"),
    mimeType: "text/markdown;charset=utf-8",
    content: lines.join("\n"),
  };
}

function parseJsonQuestionBank(raw: string): ParseQuestionBankResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(stripBom(raw));
  } catch {
    return { ok: false, error: "Question bank file is not valid JSON." };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "Question bank JSON must be an object." };
  }
  const doc = parsed as Record<string, unknown>;
  if (doc.format !== QUESTION_BANK_FORMAT) {
    return {
      ok: false,
      error: `Unsupported question bank format (expected "${QUESTION_BANK_FORMAT}").`,
    };
  }
  if (doc.version !== QUESTION_BANK_VERSION) {
    return {
      ok: false,
      error: `Unsupported question bank version (expected ${QUESTION_BANK_VERSION}).`,
    };
  }
  if (!Array.isArray(doc.questions)) {
    return { ok: false, error: "Question bank JSON must include a questions array." };
  }
  const questions: string[] = [];
  for (const row of doc.questions) {
    if (!row || typeof row !== "object" || Array.isArray(row)) {
      questions.push("");
      continue;
    }
    const text = (row as Record<string, unknown>).text;
    questions.push(typeof text === "string" ? text : "");
  }
  const title =
    typeof doc.title === "string" && doc.title.trim().length > 0
      ? doc.title.trim()
      : null;
  return { ok: true, questions, title };
}

/**
 * CommonMark-ish fence line (A4-D07 / A4-R1 / A4-R3):
 * 0–3 leading spaces, 3+ backticks or tildes, then a suffix.
 * Opening may carry an info string; closing requires whitespace-only suffix.
 */
const FENCE_LINE = /^( {0,3})(`{3,}|~{3,})(.*)$/;

function parseMarkdownQuestionBank(raw: string): ParseQuestionBankResult {
  const text = stripBom(raw).replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const questions: string[] = [];
  let title: string | null = null;
  /** Active fence: same character, close length >= open length, whitespace suffix. */
  let activeFence: { char: "`" | "~"; length: number } | null = null;

  for (const line of lines) {
    const fence = line.match(FENCE_LINE);
    if (fence) {
      const marker = fence[2]!;
      const suffix = fence[3] ?? "";
      const char = marker[0] as "`" | "~";
      const length = marker.length;
      if (activeFence == null) {
        // Opening fence: info-string/content after the marker is allowed.
        activeFence = { char, length };
        continue;
      }
      // Closing fence: matching char, sufficient length, whitespace-only suffix.
      if (
        char === activeFence.char &&
        length >= activeFence.length &&
        /^\s*$/.test(suffix)
      ) {
        activeFence = null;
      }
      // Info-string / mismatched fence lines remain code-block content.
      continue;
    }

    if (activeFence != null) {
      // Inside fenced code (including unclosed): never import bullets.
      continue;
    }

    const heading = line.match(/^#\s+(.+)\s*$/);
    if (heading && title == null) {
      const headingText = heading[1]!.trim();
      const stripped = headingText.replace(/^Seneca Question Bank\s*[—-]\s*/i, "");
      title = stripped.length > 0 ? stripped : headingText;
      continue;
    }
    const bullet = line.match(/^- (.+)$/);
    if (bullet) {
      questions.push(bullet[1]!);
    }
  }
  return { ok: true, questions, title };
}

export function detectQuestionBankKind(
  filename: string,
): "json" | "markdown" | null {
  const lower = filename.trim().toLowerCase();
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
  return null;
}

export function parseQuestionBankFile(
  filename: string,
  raw: string,
  byteLength: number,
): ParseQuestionBankResult {
  if (byteLength > QUESTION_BANK_MAX_BYTES) {
    return {
      ok: false,
      error: `Question bank file exceeds the ${QUESTION_BANK_MAX_BYTES} byte limit.`,
    };
  }
  const kind = detectQuestionBankKind(filename);
  if (kind == null) {
    return {
      ok: false,
      error: "Unsupported file type. Use .json, .md, or .markdown.",
    };
  }
  return kind === "json"
    ? parseJsonQuestionBank(raw)
    : parseMarkdownQuestionBank(raw);
}

export function planQuestionBankMerge(
  existing: SavedTrainingPrompt[],
  candidateTexts: string[],
): QuestionBankImportPlan {
  const seen = new Set(existing.map((prompt) => prompt.text));
  let capacityLeft = Math.max(0, PROMPT_MAX - existing.length);
  const entries: ImportPlanEntry[] = [];
  const importableTexts: string[] = [];

  for (const raw of candidateTexts) {
    const trimmed = typeof raw === "string" ? raw.trim() : "";
    if (trimmed.length === 0) {
      entries.push({ text: "", classification: "invalid" });
      continue;
    }
    if (seen.has(trimmed)) {
      entries.push({ text: trimmed, classification: "duplicate" });
      continue;
    }
    if (capacityLeft <= 0) {
      entries.push({ text: trimmed, classification: "capacity-skipped" });
      continue;
    }
    seen.add(trimmed);
    capacityLeft -= 1;
    entries.push({ text: trimmed, classification: "new" });
    importableTexts.push(trimmed);
  }

  return {
    title: null,
    entries,
    newCount: entries.filter((e) => e.classification === "new").length,
    duplicateCount: entries.filter((e) => e.classification === "duplicate")
      .length,
    invalidCount: entries.filter((e) => e.classification === "invalid").length,
    capacitySkippedCount: entries.filter(
      (e) => e.classification === "capacity-skipped",
    ).length,
    importableTexts,
  };
}

export function filterQuestionBankSearch(
  prompts: SavedTrainingPrompt[],
  query: string,
): SavedTrainingPrompt[] {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) return prompts;
  return prompts.filter((prompt) =>
    prompt.text.toLowerCase().includes(needle),
  );
}
