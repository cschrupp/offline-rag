import type { Source } from "../../api/types";

export type SourceSelectionState = {
  knownSourceIds: string[];
  selectedSourceIds: string[];
};

const KEY_PREFIX = "seneca.source-selection.v1:";

function storageKey(workspaceId: string): string {
  return `${KEY_PREFIX}${workspaceId}`;
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
    return { knownSourceIds, selectedSourceIds };
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
    const next = {
      knownSourceIds: activeIds,
      selectedSourceIds: activeIds,
    };
    persistSourceSelection(workspaceId, next);
    return next;
  }

  const knownSet = new Set(prior.knownSourceIds);
  const selectedSet = new Set(
    prior.selectedSourceIds.filter((id) => activeIds.includes(id)),
  );
  const previouslyAllSelected =
    prior.knownSourceIds.length > 0 &&
    prior.knownSourceIds.every((id) => prior.selectedSourceIds.includes(id));

  for (const id of activeIds) {
    if (!knownSet.has(id) && previouslyAllSelected) {
      selectedSet.add(id);
    }
  }

  const next: SourceSelectionState = {
    knownSourceIds: activeIds,
    selectedSourceIds: activeIds.filter((id) => selectedSet.has(id)),
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
  const next: SourceSelectionState = {
    knownSourceIds: sources.map((source) => source.source_id),
    selectedSourceIds: sources
      .map((source) => source.source_id)
      .filter((id) => selectedSet.has(id)),
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
  };
  persistSourceSelection(workspaceId, next);
  return next;
}

/** When every active source is selected, omit source_ids (all-active semantics). */
export function sourceIdsForQuery(
  sources: Source[],
  selectedSourceIds: string[],
): string[] | undefined {
  if (sources.length === 0) return [];
  if (selectedSourceIds.length === 0) return [];
  const allSelected = sources.every((source) =>
    selectedSourceIds.includes(source.source_id),
  );
  if (allSelected) return undefined;
  return selectedSourceIds.slice();
}
