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
  | "proposing"
  | "pooling"
  | "prelabeling"
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
  | "empty_transition"
  | "gold_lab_baseline_bootstrap";

export type OperationError = {
  code: string;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown> | null;
};

export type OperationProgressStep =
  | "parsing_documents"
  | "chunking_documents"
  | "embedding_chunks"
  | "materializing_dense_index"
  | "analyzing_lexical_chunks"
  | "materializing_lexical_index"
  | "proposing_questions"
  | "pooling_cases"
  | "prelabeling_candidates"
  | "publishing"
  | "finalizing"
  | string;

export type OperationProgressUnit =
  | "documents"
  | "chunks"
  | "questions"
  | "cases"
  | "candidates"
  | "model_calls"
  | string;

export type OperationProgressTelemetry = {
  step: OperationProgressStep;
  current: number;
  total: number | null;
  unit: OperationProgressUnit;
  started_at: string;
};

export type OperationWorklistPhase =
  | "pending"
  | "parsing"
  | "parsed"
  | "chunking"
  | "chunked"
  | "indexing"
  | "indexed"
  | "removed"
  | "failed"
  | "requires_ocr";

export type OperationWorklistDocument = {
  document_id: string;
  display_name: string;
  phase: OperationWorklistPhase;
  child_chunk_count?: number | null;
  embeddings_generated?: number | null;
  embeddings_reused?: number | null;
};

export type OperationWorklist = {
  total_document_count: number;
  pending_count: number;
  completed_count?: number | null;
  remaining_count?: number | null;
  documents: OperationWorklistDocument[];
  active_documents: OperationWorklistDocument[];
};

export type OperationDenseExecution = {
  device?: string | null;
  dtype?: string | null;
  batch_size?: number | null;
  attention_backend?: string | null;
  embedding_dimension?: number | null;
  profile_id?: string | null;
  representation_id?: string | null;
  backend?: string | null;
  provider?: string | null;
  resolved_precision?: string | null;
};

export type OperationStageDurations = {
  parsing_ms?: number | null;
  chunking_ms?: number | null;
  dense_generation_ms?: number | null;
  dense_materialization_ms?: number | null;
  lexical_ms?: number | null;
  publication_ms?: number | null;
  finalization_ms?: number | null;
  total_ms?: number | null;
};

export type OperationLexicalFacts = {
  searchable_units_contract?: string | null;
  chunk_set_child_count?: number | null;
  zero_term_excluded_count?: number | null;
  eligible_child_count?: number | null;
  indexed_child_count?: number | null;
};

export type OperationMetrics = {
  requested_document_count?: number | null;
  pre_active_source_count?: number | null;
  post_active_source_count?: number | null;
  uploaded_raw_bytes?: number | null;
  parsed_searchable_document_count?: number | null;
  child_chunk_count?: number | null;
  oversized_unsplittable_count?: number | null;
  parsed_artifacts_generated?: number | null;
  parsed_artifacts_reused?: number | null;
  chunk_artifacts_generated?: number | null;
  chunk_artifacts_reused?: number | null;
  embeddings_generated?: number | null;
  embeddings_reused?: number | null;
  embeddings_failed?: number | null;
  dense_failure_classification?: string | null;
  dense_execution?: OperationDenseExecution | null;
  generated_chunks_per_sec?: number | null;
  model_input_tokens_per_sec?: number | null;
  stage_durations?: OperationStageDurations | null;
  lexical?: OperationLexicalFacts | null;
};

export type Operation = {
  operation_id: string;
  kind: OperationKind | string;
  workspace_id: string;
  expected_revision: number | null;
  status: OperationStatus | string;
  progress_stage: ProgressStage | string | null;
  progress?: OperationProgressTelemetry | null;
  metrics?: OperationMetrics | null;
  worklist?: OperationWorklist | null;
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
  transport_limits?: {
    max_files_per_upload_request: number;
    max_bytes_per_uploaded_file: number;
    max_bytes_per_upload_request: number;
  };
  workspace_capacity?: {
    max_active_sources: number | null;
    max_searchable_child_chunks: number | null;
    max_active_source_bytes?: number | null;
  };
  large_pdf?: {
    policy_supported: boolean;
    policy_max_bytes: number;
    qualified_profile: string;
    reference_host_memory_bytes: number;
    reference_host_available_memory_bytes: number;
    runtime_eligible: boolean;
    effective_max_bytes: number;
    unavailable_reason: string | null;
  };
  /** Legacy projection: bytes are transport; max_active_sources is workspace or null. */
  source_limits: {
    max_active_sources: number | null;
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
  authoring?: {
    enabled: boolean;
    provider: string;
    base_url: string;
    model: string | null;
    timeout_seconds: number;
    ready: boolean;
    reason_codes: string[];
    api_key_configured?: boolean;
  };
  embedding?: {
    model: string;
    configured_device: string;
    active_device: string | null;
    batch_size: number;
    cuda_available: boolean | null;
    torch_cuda_build: string | null;
    selection_reason: string | null;
  };
};

export type EmbeddingDevicePolicy = "auto" | "cpu" | "cuda";

export type ComputeSettingsSnapshot = {
  embedding_device: EmbeddingDevicePolicy;
};

export type ComputeSettingsLocks = {
  embedding_device: boolean;
};

export type ComputeRuntimeView = {
  active_device: string | null;
  cuda_available: boolean | null;
  torch_cuda_build: string | null;
  selection_reason: string | null;
  configured_device?: string | null;
  configured_precision?: string | null;
  resolved_device?: string | null;
  resolved_precision?: string | null;
  profile_id?: string | null;
  representation_id?: string | null;
  embedding_state?: string | null;
  backend?: string | null;
  provider?: string | null;
  model?: string | null;
  model_revision?: string | null;
  embedding_dimension?: number | null;
  failure_reason?: string | null;
};

export type ComputeAvailabilityEntry = {
  available: boolean;
  reason?: string | null;
};

export type ComputeAvailability = {
  auto: ComputeAvailabilityEntry;
  cpu: ComputeAvailabilityEntry;
  cuda: { available: boolean; reason: string | null };
};

export type ComputeSettingsState = {
  active: ComputeSettingsSnapshot;
  pending: ComputeSettingsSnapshot | null;
  restart_required: boolean;
  locks: ComputeSettingsLocks;
  runtime: ComputeRuntimeView;
  availability: ComputeAvailability;
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

export type AuthoringSettingsSnapshot = {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string | null;
  timeout_seconds: number;
  network_policy: string;
  api_key_configured: boolean;
};

export type AuthoringSettingsLocks = {
  enabled: boolean;
  base_url: boolean;
  model: boolean;
  timeout_seconds: boolean;
  api_key: boolean;
  network_policy: boolean;
};

export type AuthoringReadinessView = {
  ready: boolean;
  reason_codes: string[];
  enabled: boolean;
  endpoint_configured: boolean;
  endpoint_approved: boolean;
  model_configured: boolean;
  model_approved: boolean;
  network_policy_satisfied: boolean;
  api_key_configured: boolean;
};

export type AuthoringSettingsState = {
  active: AuthoringSettingsSnapshot;
  pending: AuthoringSettingsSnapshot | null;
  restart_required: boolean;
  locks: AuthoringSettingsLocks;
  strict_offline: boolean;
  readiness: AuthoringReadinessView;
};

export type AuthoringProbeResult = {
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
