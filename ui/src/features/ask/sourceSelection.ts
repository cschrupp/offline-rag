import type { Source } from "../../api/types";

export type SourceSelectionMode = "all" | "subset";

export type SourceSelectionState = {
  knownSourceIds: string[];
  selectedSourceIds: string[];
  mode: SourceSelectionMode;
};

const KEY_PREFIX = "seneca.source-selection.v1:";

function storageKey(workspaceId: string): string {
  return `${KEY_PREFIX}${workspaceId}`;
}

function migrateLegacy(
  knownSourceIds: string[],
  selectedSourceIds: string[],
  modeRaw: unknown,
): SourceSelectionState {
  if (modeRaw === "all" || modeRaw === "subset") {
    return { knownSourceIds, selectedSourceIds, mode: modeRaw };
  }
  // Legacy shape without mode: empty known set was the EMPTY-workspace trap —
  // treat as follow-all. Otherwise infer all vs subset from arrays.
  if (knownSourceIds.length === 0) {
    return { knownSourceIds, selectedSourceIds: [], mode: "all" };
  }
  const allSelected = knownSourceIds.every((id) =>
    selectedSourceIds.includes(id),
  );
  return {
    knownSourceIds,
    selectedSourceIds,
    mode: allSelected ? "all" : "subset",
  };
}

function readRaw(workspaceId: string): SourceSelectionState | null {
  try {
    const raw = sessionStorage.getItem(storageKey(workspaceId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SourceSelectionState>;
    if (
      !Array.isArray(parsed.knownSourceIds) ||
      !Array.isArray(parsed.selectedSourceIds)
    ) {
      return null;
    }
    const knownSourceIds = parsed.knownSourceIds.filter(
      (id): id is string => typeof id === "string" && id.length > 0,
    );
    const selectedSourceIds = parsed.selectedSourceIds.filter(
      (id): id is string => typeof id === "string" && id.length > 0,
    );
    return migrateLegacy(knownSourceIds, selectedSourceIds, parsed.mode);
  } catch {
    return null;
  }
}

export function persistSourceSelection(
  workspaceId: string,
  state: SourceSelectionState,
): void {
  try {
    sessionStorage.setItem(storageKey(workspaceId), JSON.stringify(state));
  } catch {
    /* ignore quota / private mode */
  }
}

export function reconcileSourceSelection(
  workspaceId: string,
  sources: Source[],
): SourceSelectionState {
  const activeIds = sources.map((source) => source.source_id);
  const prior = readRaw(workspaceId);

  if (!prior) {
    const next: SourceSelectionState = {
      knownSourceIds: activeIds,
      selectedSourceIds: activeIds,
      mode: "all",
    };
    persistSourceSelection(workspaceId, next);
    return next;
  }

  if (prior.mode === "all") {
    const next: SourceSelectionState = {
      knownSourceIds: activeIds,
      selectedSourceIds: activeIds,
      mode: "all",
    };
    persistSourceSelection(workspaceId, next);
    return next;
  }

  const selectedSet = new Set(
    prior.selectedSourceIds.filter((id) => activeIds.includes(id)),
  );
  const next: SourceSelectionState = {
    knownSourceIds: activeIds,
    selectedSourceIds: activeIds.filter((id) => selectedSet.has(id)),
    mode: "subset",
  };
  persistSourceSelection(workspaceId, next);
  return next;
}

export function setSourceSelected(
  workspaceId: string,
  sources: Source[],
  sourceId: string,
  selected: boolean,
): SourceSelectionState {
  const current = reconcileSourceSelection(workspaceId, sources);
  const selectedSet = new Set(current.selectedSourceIds);
  if (selected) selectedSet.add(sourceId);
  else selectedSet.delete(sourceId);
  const selectedSourceIds = sources
    .map((source) => source.source_id)
    .filter((id) => selectedSet.has(id));
  // Uncheck → subset. Select-all is the only intentional path back to follow-all.
  // Checking boxes while in subset (even to full) stays subset.
  let mode: SourceSelectionMode = "subset";
  if (selected && current.mode === "all") {
    const stillAll =
      sources.length > 0 &&
      sources.every((source) => selectedSourceIds.includes(source.source_id));
    mode = stillAll ? "all" : "subset";
  }
  const next: SourceSelectionState = {
    knownSourceIds: sources.map((source) => source.source_id),
    selectedSourceIds,
    mode,
  };
  persistSourceSelection(workspaceId, next);
  return next;
}

export function selectAllSources(
  workspaceId: string,
  sources: Source[],
): SourceSelectionState {
  const next: SourceSelectionState = {
    knownSourceIds: sources.map((source) => source.source_id),
    selectedSourceIds: sources.map((source) => source.source_id),
    mode: "all",
  };
  persistSourceSelection(workspaceId, next);
  return next;
}

/**
 * Build request scope from selection intent.
 * Only mode=all with every known active source selected may omit source_ids.
 * mode=subset always sends the explicit selected IDs (never silent broaden).
 */
export function sourceIdsForQuery(
  sources: Source[],
  selectedSourceIds: string[],
  mode: SourceSelectionMode,
): string[] | undefined {
  if (sources.length === 0) return [];
  if (selectedSourceIds.length === 0) return [];
  if (mode === "subset") {
    return selectedSourceIds.slice();
  }
  const allSelected = sources.every((source) =>
    selectedSourceIds.includes(source.source_id),
  );
  if (allSelected) return undefined;
  // Defensive: mode=all but selection drifted — send explicit IDs.
  return selectedSourceIds.slice();
}
