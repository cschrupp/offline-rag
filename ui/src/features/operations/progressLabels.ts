import type { ProgressStage } from "../../api/types";

const STAGE_LABELS: Record<ProgressStage, string> = {
  preparing: "Preparing",
  processing: "Processing",
  building_indexes: "Building search indexes",
  publishing: "Publishing",
  finalizing: "Finalizing",
  ready: "Ready",
};

export function progressStageLabel(stage: string | null | undefined): string {
  if (!stage) return "Working";
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
