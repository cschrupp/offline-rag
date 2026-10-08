import type { Source, Workspace } from "../../api/types";

/** Mutually exclusive Workspace source-list presentation phases. */
export type SourceListPhase =
  | "loading"
  | "error"
  | "empty"
  | "ready"
  | "inconsistent";

type DeriveArgs = {
  workspace: Pick<Workspace, "status" | "source_count">;
  /** True once a sources response body has been received (success). */
  sourcePayloadAvailable: boolean;
  sourcesFailed: boolean;
  sources: Source[];
};

/**
 * Derive source-list UI phase.
 * loading ≠ empty; error ≠ empty;
 * ACTIVE+[] and EMPTY+nonempty are inconsistent (valid payload contradiction).
 */
export function deriveSourceListPhase({
  workspace,
  sourcePayloadAvailable,
  sourcesFailed,
  sources,
}: DeriveArgs): SourceListPhase {
  if (sourcesFailed) {
    return "error";
  }
  if (!sourcePayloadAvailable) {
    return "loading";
  }
  if (workspace.status === "empty") {
    return sources.length === 0 ? "empty" : "inconsistent";
  }
  if (sources.length > 0) {
    return "ready";
  }
  // ACTIVE (non-empty status) with a successful empty list contradicts
  // the backend invariant that active workspaces have ≥1 active source.
  return "inconsistent";
}

/** Workspace badge uses saved status unless a valid payload proves mismatch. */
export function workspaceStatusBadge(args: {
  workspaceStatus: Workspace["status"];
  sourcePhase: SourceListPhase;
}): { tone: "ready" | "empty" | "error"; label: string } {
  if (args.sourcePhase === "inconsistent") {
    return { tone: "error", label: "Source issue" };
  }
  if (args.workspaceStatus === "empty") {
    return { tone: "empty", label: "Empty" };
  }
  return { tone: "ready", label: "Active" };
}

/** Add Sources may run in a genuine empty workspace or a ready populated one. */
export function canAddSources(phase: SourceListPhase): boolean {
  return phase === "ready" || phase === "empty";
}

/** Rename / replace / remove require an authoritative nonempty source list. */
export function canMutateExistingSource(phase: SourceListPhase): boolean {
  return phase === "ready";
}

/** @deprecated Prefer canAddSources — kept as the Add-compatible known-state check. */
export function sourceMutationStateKnown(phase: SourceListPhase): boolean {
  return canAddSources(phase);
}

export function sourcesRecordsAvailable(phase: SourceListPhase): boolean {
  return phase === "ready";
}

export const SOURCE_STATE_STALE_MESSAGE =
  "Source details changed. Reload the source list before continuing.";

export function headerSourceCountLabel(args: {
  phase: SourceListPhase;
  workspace: Pick<Workspace, "source_count">;
  loadedCount: number;
  maxActiveSources: number | null;
}): string {
  const { phase, workspace, loadedCount, maxActiveSources } = args;
  if (phase === "ready") {
    return maxActiveSources !== null
      ? `${loadedCount} / ${maxActiveSources} sources`
      : `${loadedCount} sources`;
  }
  if (phase === "empty") {
    return maxActiveSources !== null
      ? `0 / ${maxActiveSources} sources`
      : "0 sources";
  }
  // loading / error / inconsistent — recorded count is not fake source rows
  const recorded = workspace.source_count;
  return `${recorded} source${recorded === 1 ? "" : "s"} recorded`;
}
