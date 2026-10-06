export type WorkspaceStatus = "active" | "empty" | "tombstoned";

export type Workspace = {
  workspace_id: string;
  title: string;
  description: string;
  revision: number;
  status: WorkspaceStatus;
  current_snapshot_id: string | null;
  source_count: number;
  created_at: string;
  updated_at: string;
};

export type Source = {
  source_id: string;
  version: number;
  display_name: string;
  content_type: string;
  byte_size: number;
  content_hash: string;
  document_id: string | null;
  created_at: string;
  active_from_revision: number;
  active_from_snapshot_id: string | null;
};

export type SourceListResponse = {
  workspace_id: string;
  revision: number;
  sources: Source[];
};

export type OperationStatus =
  | "pending"
  | "preparing"
  | "running"
  | "succeeded"
  | "failed"
  | "interrupted";

export type ProgressStage =
  | "preparing"
  | "processing"
  | "building_indexes"
  | "publishing"
  | "finalizing"
  | "ready";

export type OperationKind =
  | "workspace_create"
  | "workspace_metadata_patch"
  | "workspace_delete"
  | "source_add"
  | "source_remove"
  | "source_replace"
  | "source_metadata_patch"
  | "empty_transition";

export type OperationError = {
  code: string;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown> | null;
};

export type Operation = {
  operation_id: string;
  kind: OperationKind | string;
  workspace_id: string;
  expected_revision: number | null;
  status: OperationStatus | string;
  progress_stage: ProgressStage | string | null;
  created_at: string;
  updated_at: string;
  result: Record<string, unknown> | null;
  error: OperationError | null;
};

export type HealthReady = {
  status: string;
};

export type ErrorEnvelope = {
  error: {
    code: string;
    message: string;
  };
  retryable: boolean;
  trace_id?: string | null;
  details?: Record<string, unknown> | null;
};
