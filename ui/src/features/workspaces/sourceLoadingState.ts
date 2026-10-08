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
 * loading ≠ empty; error ≠ empty; active + [] ≠ empty.
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
  if (sources.length > 0) {
    return "ready";
  }
  if (workspace.status === "empty") {
    return "empty";
  }
  // ACTIVE (or any non-empty status) with a successful empty list is inconsistent
  // with the backend invariant that active workspaces have ≥1 active source.
  return "inconsistent";
}

export function isGenuineEmptyPhase(phase: SourceListPhase): boolean {
  return phase === "empty";
}

export function sourcesRecordsAvailable(phase: SourceListPhase): boolean {
  return phase === "ready";
}

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
