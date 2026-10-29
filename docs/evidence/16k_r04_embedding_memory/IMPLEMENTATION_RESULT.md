# S16K-R04 Embedding-Memory Diagnostic Harness — Final Corrective

## Authority and subjects

- Governing authority: `S16-K-R04-EMBEDDING-MEMORY-DIAGNOSTIC-HARNESS-IMPLEMENTATION-AUTH-001`
- Human authorization record: `04492cc42d236c5c36227d081f94ffb165abb370`
- Accepted parent design: `beecfd56fb5c085fabcca0131f0af7e67923836f`
- Parent design Human-acceptance tip: `e078c56c94eef63e00d4b347f057f89b71da7f0b`
- Accepted Amendment 001: `7a2a4427e76a6c675df1e833deb4b6dce0fadb83`
- Amendment Human-acceptance record: `2ad161e2b3bb266a531fbd3adb9a4ea061eb142c`
- Prior harness handoff: `b7dffeb404d0d374b03233a028c599ae64d3738b`
- Technical implementation starting subject, including Amendment 001: `3eb5f052a4a1368de8fd017111cc4c8db7de4393`
- Technical candidate: `bcdef88e6dc05ce864696e195c9d0cf842caf106`
- Branch: `implementation/16k-r04-embedding-memory-diagnostic-harness-final`

The technical candidate is the implementation subject for independent review. This file is a separate documentation-only handoff commit and intentionally does not contain its own commit SHA.

## Changed paths in the technical candidate

- `ROADMAP.md` — restored the human-facing R04 checklist and marked the final harness corrective complete, with independent implementation review as the current item.
- `scripts/diag_16k_r04_embedding_memory/campaign.py` — derives cumulative accepted controls and enforces Amendment 001 applicability/admission rules.
- `scripts/diag_16k_r04_embedding_memory/cell_executor.py` — safely classifies cell failures, including CUDA OOM, before serialization and finalization.
- `scripts/diag_16k_r04_embedding_memory/cpu_reference.py` — records the bounded `NONE` failure classification for successful CPU reference evidence.
- `scripts/diag_16k_r04_embedding_memory/evidence.py` — validates failure-class/status consistency and derives the forward-OOM applicability fact from phase evidence.
- `scripts/diag_16k_r04_embedding_memory/runtime.py` — provides safe failure classification and includes it in the evidence allowlist.
- `tests/unit/test_slice16k_r04_embedding_memory_harness.py` — covers F008, active controls, M3/M4/M5 gates, and critical regressions.

## Implemented decisions

- **F008 — CLOSED.** CUDA OOM classification is explicit and bounded across exception handling, evidence serialization, reduction, and claim finalization. Safe summaries remain redacted. A qualified CUDA OOM remains an OOM outcome even if allocator diagnostics are incomplete; allocator diagnosis may separately remain inconclusive. Non-OOM failures stop campaign progression.
- **`ACTIVE_CONTROLS` — IMPLEMENTED.** Controls accumulate only from treatments whose evidence establishes both `mechanism=SUPPORTED` and `candidate=QUALIFIED`. Rejected or inconclusive treatments do not become later baselines. Replicate condition identity is checked before use. If multiple M3 alternatives qualify and the accepted contract gives no ranking, the controller fails closed.
- **M3 applicability — IMPLEMENTED.** The successful-forward gate uses incremental working set `I=max(0,P-B)`, threshold `M=max(256 MiB, 5% of median peak P)`, median incremental memory at least `M`, and at least two of three replicates at or above `M`. The alternate gate requires at least two valid forward CUDA OOMs after load and before fixed-32 completion. OOM before encode does not count. Right-censored OOM is applicability/resource evidence only, never a completed mechanism comparison.
- **M4 applicability — IMPLEMENTED.** The deterministic greedy partitioner is evaluated against the exact frozen 32 token counts. Applicability requires identical counts across the three active-state runs, more than one partition, lower partitioned padding than fixed padding, and at least 5% padded-token savings. This proxy does not mark H-TOKEN supported.
- **M5 admission — IMPLEMENTED.** M5 is blocked while an applicable M3/M4 stage is unresolved; `NOT_APPLICABLE` stages do not block it. It requires a qualified treatment and exact equality between requested confirmation settings and final evidence-derived `ACTIVE_CONTROLS`. With no qualified treatment, M5 is not applicable.
- The existing authority hashes, evidence tamper checks, privacy filtering, workload identity binding, no-retry/no-fallback behavior, process/cell limits, deadlines, and parity rules remain covered by the focused harness suite.

## Validation

Commands run against the repository `.venv`:

- `.venv/bin/ruff format scripts/diag_16k_r04_embedding_memory tests/unit/test_slice16k_r04_embedding_memory_harness.py` — pass; 10 files unchanged.
- `.venv/bin/ruff check scripts/diag_16k_r04_embedding_memory tests/unit/test_slice16k_r04_embedding_memory_harness.py` — pass.
- `.venv/bin/pytest -q tests/unit/test_slice16k_r04_embedding_memory_harness.py` — **33 passed**.
- `.venv/bin/python -m compileall -q scripts/diag_16k_r04_embedding_memory` — pass.
- Fresh-process import check across `campaign`, `cell_executor`, `contract`, `cpu_reference`, `evidence`, `freeze_workload`, `runtime`, and `analyze` — pass; `torch`, `transformers`, and `sentence_transformers` were not imported.
- `git diff --check` — pass.

The focused suite includes the permitted installed Torch CPU SDPA delegation regression. No CUDA tests were run.

## Execution and production state

```yaml
implementation:
  F008: CLOSED
  ACTIVE_CONTROLS: IMPLEMENTED
  M3_applicability: IMPLEMENTED
  M4_applicability: IMPLEMENTED
  M5_admission: IMPLEMENTED

workload_freeze: NOT_RUN
M0_M5_scientific_execution: NOT_RUN
Qwen_or_sentence_transformer_model_load: NONE
cuda_model_execution: NOT_RUN
cpu_onnx_reference: NOT_RUN
well_logging_retry: NOT_RUN
real_ingestion_or_server_interaction: NONE
production_behavior_or_limits_changed: NO

working_tree:
  tracked_candidate_changes: COMMITTED
  unrelated_preexisting_untracked_user_files: LEFT_UNTOUCHED

terminal: READY_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW
```

Independent review is the next step. Workload freeze and all scientific execution remain unauthorized until the integrated execution plan receives the program's Initial Human GO. No production implementation, production promotion, or Well Logging retry is authorized by this harness corrective.
