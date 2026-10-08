/** Browser-local training prompt library (presentation data only). */

export type SavedTrainingPrompt = {
  id: string;
  text: string;
  createdAt: string;
};

const KEY_PREFIX = "seneca.training-prompts.v1:";
/** Local Question Bank capacity (A4-D08). */
export const PROMPT_MAX = 100;

function storageKey(workspaceId: string): string {
  return `${KEY_PREFIX}${workspaceId}`;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isSavedPrompt(value: unknown): value is SavedTrainingPrompt {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return (
    isNonEmptyString(row.id) &&
    typeof row.text === "string" &&
    row.text.trim().length > 0 &&
    isNonEmptyString(row.createdAt)
  );
}

export function loadTrainingPrompts(workspaceId: string): SavedTrainingPrompt[] {
  if (!workspaceId) return [];
  try {
    const raw = localStorage.getItem(storageKey(workspaceId));
    if (raw == null || raw === "") return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const prompts = parsed.filter(isSavedPrompt).slice(0, PROMPT_MAX);
    return prompts.map((prompt) => ({
      id: prompt.id,
      text: prompt.text.trim(),
      createdAt: prompt.createdAt,
    }));
  } catch {
    return [];
  }
}

function persist(workspaceId: string, prompts: SavedTrainingPrompt[]): void {
  try {
    localStorage.setItem(
      storageKey(workspaceId),
      JSON.stringify(prompts.slice(0, PROMPT_MAX)),
    );
  } catch {
    // Quota / private mode — leave in-memory list authoritative for this session.
  }
}

export function saveTrainingPrompt(
  workspaceId: string,
  text: string,
): SavedTrainingPrompt[] {
  const trimmed = text.trim();
  if (!workspaceId || trimmed.length === 0) {
    return loadTrainingPrompts(workspaceId);
  }
  const existing = loadTrainingPrompts(workspaceId);
  const duplicate = existing.find((prompt) => prompt.text === trimmed);
  if (duplicate) return existing;
  const next: SavedTrainingPrompt[] = [
    {
      id:
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `tp_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
      text: trimmed,
      createdAt: new Date().toISOString(),
    },
    ...existing,
  ].slice(0, PROMPT_MAX);
  persist(workspaceId, next);
  return next;
}

export function deleteTrainingPrompt(
  workspaceId: string,
  promptId: string,
): SavedTrainingPrompt[] {
  if (!workspaceId || !promptId) return loadTrainingPrompts(workspaceId);
  const next = loadTrainingPrompts(workspaceId).filter(
    (prompt) => prompt.id !== promptId,
  );
  persist(workspaceId, next);
  return next;
}

export function trainingPromptsStorageKey(workspaceId: string): string {
  return storageKey(workspaceId);
}
