import type { ProgressStage } from "../../api/types";

const STAGE_LABELS: Record<ProgressStage, string> = {
  preparing: "Preparing",
  processing: "Processing",
  building_indexes: "Building search indexes",
  proposing: "Proposing candidate questions",
  pooling: "Pooling evidence",
  prelabeling: "Adding advisory prelabels",
  publishing: "Publishing",
  finalizing: "Finalizing",
  ready: "Ready",
};

const GOLD_BOOTSTRAP_STAGE_LABELS: Record<string, string> = {
  preparing: "Preparing",
  proposing: "Proposing candidate questions",
  pooling: "Pooling evidence",
  prelabeling: "Adding advisory prelabels",
  publishing: "Publishing baseline",
  finalizing: "Finalizing",
  ready: "Ready",
};

export function progressStageLabel(
  stage: string | null | undefined,
  kind?: string,
): string {
  if (!stage) return "Working";
  if (
    kind === "gold_lab_baseline_bootstrap" &&
    stage in GOLD_BOOTSTRAP_STAGE_LABELS
  ) {
    return GOLD_BOOTSTRAP_STAGE_LABELS[stage]!;
  }
  if (stage in STAGE_LABELS) {
    return STAGE_LABELS[stage as ProgressStage];
  }
  return "Working";
}

export function operationStatusLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Pending";
    case "preparing":
      return "Preparing";
    case "running":
      return "Running";
    case "succeeded":
      return "Succeeded";
    case "failed":
      return "Failed";
    case "interrupted":
      return "Interrupted";
    default:
      return status;
  }
}
