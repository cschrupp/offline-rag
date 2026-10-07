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

export type Capabilities = {
  product: {
    name: string;
    descriptor: string;
  };
  source_limits: {
    max_active_sources: number;
    max_bytes_per_source: number;
    max_active_source_bytes: number;
  };
  generation: {
    enabled: boolean;
    provider: string;
    base_url: string;
    model: string;
    timeout_seconds: number;
  };
};

export type GenerationSettingsSnapshot = {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key_configured: boolean;
};

export type GenerationSettingsLocks = {
  enabled: boolean;
  base_url: boolean;
  model: boolean;
  timeout_seconds: boolean;
  api_key: boolean;
};

export type GenerationSettingsState = {
  active: GenerationSettingsSnapshot;
  pending: GenerationSettingsSnapshot | null;
  restart_required: boolean;
  locks: GenerationSettingsLocks;
  strict_offline: boolean;
};

export type GenerationSettingsCandidate = {
  enabled: boolean;
  base_url: string;
  model: string;
  timeout_seconds: number;
  api_key_action: "keep" | "set" | "clear";
  api_key?: string | null;
};

export type GenerationProbeResult = {
  ok: boolean;
  reason?: string | null;
  available_models?: string[] | null;
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

export type WorkspaceCitationKind = "parent" | "child";

export type WorkspaceCitation = {
  evidence_unit_id: string;
  document_id: string;
  source_chunk_id: string;
  kind: WorkspaceCitationKind | string;
  section_path: string[];
  page_start: number | null;
  page_end: number | null;
  line_start: number | null;
  line_end: number | null;
  clipped: boolean;
  source_id: string;
  source_version: number;
  source_display_name: string;
  citation_ref: string;
  excerpt: string;
  excerpt_clipped: boolean;
};

export type AnswerBlock = {
  text: string;
  citation_refs: string[];
};

export type AbstentionReason =
  | "no_evidence"
  | "insufficient_support"
  | "conflicting_evidence"
  | "model_declined"
  | string;

export type WorkspaceQueryStatus =
  | "answered"
  | "insufficient_evidence"
  | "model_abstain";

export type WorkspaceQueryResponse = {
  workspace_id: string;
  workspace_revision: number;
  snapshot_id: string;
  product_mode_id: string;
  trace_id: string;
  status: WorkspaceQueryStatus | string;
  answer: string | null;
  citations: WorkspaceCitation[];
  answer_blocks: AnswerBlock[];
  abstention_reason: AbstentionReason | null;
};

export type ConversationTurnStatus =
  | WorkspaceQueryStatus
  | "clarification_required";

export type ConversationPriorTurn = {
  role: "user" | "assistant";
  text: string;
};

/** POST /v1/workspaces/{id}/conversation/turn response (A2-D05). */
export type ConversationTurnResponse = {
  workspace_id: string;
  workspace_revision: number;
  snapshot_id: string;
  product_mode_id: string;
  conversation_trace_id: string;
  query_trace_id: string | null;
  status: ConversationTurnStatus | string;
  abstention_reason: AbstentionReason | null;
  question: string;
  retrieval_question: string | null;
  context_used: boolean;
  answer: string | null;
  citations: WorkspaceCitation[];
  answer_blocks: AnswerBlock[];
};
