# S16K-R04 — Execution Binding Reconciliation

```yaml
initial_human_go_plan:
  d972379d6851c1416cd9ff52b62d89f286b11f94

finite_spec_corrective:
  technical_subject: feff974696682d287d277d7264ac1e4d46100e00
  independent_review: S16K_R04_FINITE_SPEC_AUTHORITY_CORRECTIVE_IR_001_ACCEPT
  documentation_handoff: f3a0a0119eb98dd21cf14e411c7238f2973b0434

previously_accepted_harness:
  f69a56cd1a251b83d2b0cda0a02bb4714e2fda0a

execution_implementation_subject:
  feff974696682d287d277d7264ac1e4d46100e00

initial_human_go:
  REMAINS_IN_FORCE

additional_human_go:
  NOT_REQUIRED

scientific_scope:
  UNCHANGED
```

The accepted finite-spec corrective is the implementation subject for all
future R04 execution evidence. This reconciliation does not change the
Human-approved scientific plan, any experimental rule, workload identity,
campaign budget, or production behavior.

The preserved local workload was rehashed before reuse:

```yaml
workload_kind: INCIDENT_ADJACENT_SUBSTITUTE
item_count: 32
workload_sha256: e4ea6d13f5c0d5dcd0c1783afc86dde8c88d7957d586fd9f2f4ddf0c96001453
manifest_sha256: 276f8ea3e920933f8c06a55cc800efe66b1dba14b2c796346b00a1ebf11abb90
reconstructed_reused_count: 893
reconstructed_desired_count: 1498
```

The manifest remains the same 32-item adjacent substitute and was not
regenerated. No authority was reused from the prior implementation subject.
The finite execution authority must be materialized against
`feff974696682d287d277d7264ac1e4d46100e00` before M0.

## Pre-M0 materialization

The finite catalog and authority were generated and verified without importing
PyTorch, Transformers, SentenceTransformers, loading Qwen, or initializing
CUDA:

```yaml
authority_path:
  artifacts/diag_16k_r04_embedding_memory/execution_001/authority_001.json
authority_sha256:
  02c6723af2d764570c40d19b8637b7fd4ab913e8f0c1822e2ad47a953f18c9b5
catalog_index_sha256:
  cc794cc1414ecf84cf9e66553d1cc4e99d17321574f80ce40aba67ba3188c66c
spec_count: 293
specs_by_cell:
  M0: 3
  M1: 3
  M2: 6
  M3_PROFILE: 4
  M3_A: 48
  M3_B: 48
  M4: 60
  M5: 120
  CPU_ONNX_REFERENCE: 1
authority_implementation_subject:
  feff974696682d287d277d7264ac1e4d46100e00
authority_workload_sha256:
  e4ea6d13f5c0d5dcd0c1783afc86dde8c88d7957d586fd9f2f4ddf0c96001453
```

Every canonical spec file was rehashed and checked against the finite exact
allowlist. Single-variant slots use the legacy singleton form; conditional
slots use lists. All variants use the frozen model revision and workload
digest. No authority file is committed or modified after M0 starts.

The local environment check also passed before the transient GPU preflight:

```yaml
python: 3.14.5
torch_distribution: 2.14.0
torch_cuda_build: "13.0"
transformers: 4.57.6
sentence_transformers: 5.7.0
host_mem_total_bytes: 33507905536
host_mem_available_bytes: 24974704640
model_bundle_readiness: READY
model_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
strict_offline: true
environment_record_sha256:
  7b630dcc8794cd3a34e0b3e2455b847c10073cd218ce875b0ca09553ac136037
```

The fresh host/process/GPU preflight completed immediately before the M0
replicate-1 launch:

```yaml
preflight_path:
  artifacts/diag_16k_r04_embedding_memory/execution_001/preflight_002.json
preflight_sha256:
  1c9eb9938505a8334c3def4f239486aa7a1e82935519104f5918d0a87c54deaf
gpu_memory_mib: {total: 8192, used: 6313, free: 1675}
gpu_process_ownership: NOT_OBSERVABLE
known_seneca_repo_api_generation_processes: 0
preflight_flags: [GPU_PROCESS_ATTRIBUTION_UNAVAILABLE]
```

## M0 replicate-1 launch stop

One executor launch was attempted using the pre-authorized M0 replicate-1 spec.
The process returned `CELL_FAILED: ImportError` before writing a single-use
claim or any cell output. The launch was invoked by file path, leaving
`__package__` unset; the runtime fallback imports top-level `campaign`, whose
imports are package-relative. This invocation-path diagnosis is supported by
the command form, import layout, and absence of claim/evidence files.

The failed launch is governed by the accepted campaign's non-OOM execution
error stop rule:

```yaml
launch_attempt_record:
  artifacts/diag_16k_r04_embedding_memory/execution_001/launch_attempt_001.json
launch_attempt_record_sha256:
  163ca17bf3e4777dc671c620374c3f197720c34aaaea9dc7a2d4027c626db1aa

M0_replicate_1:
  launch_attempted: true
  claim_created: false
  raw_cell_evidence: NONE
  vectors: NONE
  allocator_snapshot: NONE
  model_weights_loaded: false
  cuda_scientific_execution: false
  scientific_cell_consumed: false

campaign_terminal:
  STOPPED_NON_OOM_EXECUTION_ERROR
  retry: FORBIDDEN_BY_CURRENT_PLAN
```

No M0 retry or later cell was started. The detached executor remained pinned at
`feff974696682d287d277d7264ac1e4d46100e00`. Any further campaign action must
resolve this stop under a separate explicit disposition; the existing plan's
no-retry rule was not bypassed.

At reconciliation time:

```yaml
M0: LAUNCH_ATTEMPT_FAILED_BEFORE_CLAIM
M1_M5: NOT_STARTED
scientific_cells_consumed: 0
model_execution: NONE
cuda_execution: NONE
cpu_onnx_reference: NONE
```
