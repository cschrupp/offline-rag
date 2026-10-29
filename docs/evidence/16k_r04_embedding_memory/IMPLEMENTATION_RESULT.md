# S16K-R04 Embedding-Memory Diagnostic Harness — Implementation Result

## Authority and subject

```yaml
authority: S16-K-R04-EMBEDDING-MEMORY-DIAGNOSTIC-HARNESS-IMPLEMENTATION-AUTH-001
accepted_design_subject: beecfd56fb5c085fabcca0131f0af7e67923836f
design_human_acceptance_record_tip: e078c56c94eef63e00d4b347f057f89b71da7f0b
authorized_base: e078c56c94eef63e00d4b347f057f89b71da7f0b
technical_candidate: ca93d89fdb8ae33e4fc062b79305eff0e4b5206d
branch: implementation/16k-r04-embedding-memory-diagnostic-harness

implementation: COMPLETE
independent_review: PENDING
scientific_execution: NOT AUTHORIZED
production_changes: NONE
promotion: NOT AUTHORIZED
```

The candidate is one implementation commit on the accepted design/acceptance
record base. A documentation-only result/projection successor records this
handoff; it does not change the technical candidate above.

## Implemented scope

- **CPU-only workload reconstruction:** rebuilds the first pending 32-item
  passage batch from corpus/chunk/cache artifacts, verifies artifact identities
  and source hashes, counts local Qwen tokenizer tokens, and classifies the
  workload as exact incident identity only when the required identity receipt
  matches. The manifest stores identities, hashes, token counts, and the query
  text contract; raw text and token IDs are excluded.
- **Measurement runtime:** lazy imports keep PyTorch, Transformers, and
  SentenceTransformers out of module import. Authorized cells collect staged
  allocator/device/process RSS and CPU/rusage facts, 10 Hz best-effort
  owner-classified GPU samples, runtime/device/driver facts, and profiler
  operators. Cache and SDPA observers delegate calls unchanged and record only
  state/shape/eligibility metadata.
- **Cell controls:** exact cell/spec/workload/implementation authority binding,
  fresh-process single-use claims, three-M0-before-treatment gating, a single
  CPU-reference process gated on an observed M0 OOM, 15-minute cell alarms,
  four-hour wall-time and cumulative execution caps, and no retry claims.
- **OOM evidence:** captures allocator history only for a cell, snapshots on
  OOM, OOM-time free memory, allocation request size, allocator summaries,
  paired device/process observations, and conservative independent
  classifications. A missing or non-matching allocator OOM request leaves the
  diagnosis inconclusive.
- **Parity and offline analysis:** deterministic M4 partitions, D2 vector and
  retrieval parity thresholds, paired-mechanism and production-candidate
  evaluators, budget checks, OOM classification, and a separately gated CPU
  ONNX reference executor.
- **Privacy and local artifacts:** evidence uses an allowlist, rejects unknown
  and private-text fields, redacts exception messages and process PIDs, and
  requires runtime files to be ignored/untracked. Generated evidence is
  excluded by the narrow
  `artifacts/diag_16k_r04_embedding_memory/` ignore entry.

## Changed paths

The technical candidate changes exactly:

```text
.gitignore
ROADMAP.md
docs/BACKLOG.md
docs/evidence/16k_r04_embedding_memory/IMPLEMENTATION_AUTHORITY.md
scripts/diag_16k_r04_embedding_memory/__init__.py
scripts/diag_16k_r04_embedding_memory/analyze.py
scripts/diag_16k_r04_embedding_memory/cell_executor.py
scripts/diag_16k_r04_embedding_memory/contract.py
scripts/diag_16k_r04_embedding_memory/cpu_reference.py
scripts/diag_16k_r04_embedding_memory/freeze_workload.py
scripts/diag_16k_r04_embedding_memory/runtime.py
tests/unit/test_slice16k_r04_embedding_memory_harness.py
```

No `src/offline_rag/` production implementation, configuration, dependency,
lockfile, UI, or scientific evidence file changed. No migration, API, UI, or
product admission-order change was made. Production limits and adaptive CUDA
recovery behavior are unchanged.

## Admission, errors, and execution boundary

No workspace/product admission path is changed. Harness admission is ordered:
validate separate Human scientific execution authority and exact commit/design
binding; validate cell spec, workload digest, and spec hash; validate ignored
output paths; reconstruct and verify the frozen workload; claim the single-use
process under the campaign lock and enforce sequence/budgets; only then import
the model runtime and execute an authorized cell.

Missing/malformed authority, wrong hashes, duplicate claims, invalid treatment
controls, a missing M0 prerequisite, budget exhaustion, identity mismatch,
tokenizer mismatch, or unsafe output path fails closed. CUDA OOM, non-OOM cell
failure, missing telemetry, and incomplete snapshot are recorded as bounded,
sanitized evidence when execution is authorized; they do not trigger internal
retry or a production fallback. The CPU ONNX parity executor is a distinct
entry point and requires the separate future scientific execution authority.

## Validation

Commands run against the repository `.venv` executables:

```text
.venv/bin/ruff format scripts/diag_16k_r04_embedding_memory tests/unit/test_slice16k_r04_embedding_memory_harness.py
  PASS — 8 files unchanged on final run

.venv/bin/ruff check scripts/diag_16k_r04_embedding_memory tests/unit/test_slice16k_r04_embedding_memory_harness.py
  PASS — All checks passed

.venv/bin/pytest -q tests/unit/test_slice16k_r04_embedding_memory_harness.py
  PASS — 14 passed

.venv/bin/python -m compileall -q scripts/diag_16k_r04_embedding_memory
  PASS

git diff --check
  PASS

Fresh-process import boundary check
  PASS — torch, transformers, and sentence_transformers absent from sys.modules
```

An initial `uv run` validation attempt could not create its cache temporary file
because the sandbox cache location was read-only. Validation was completed
successfully with the already-present canonical `.venv` executables; no package
was downloaded or installed.

The tests are synthetic harness tests. No parser, embedding model, tokenizer
workload reconstruction, CUDA context, Qwen encode, CPU ONNX parity run, or
live ingestion was executed. The full repository test suite was not run.

## Limits and remaining gates

- Workload identity and token-count reconstruction are implemented but have not
  been run against the incident workspace/artifacts.
- Runtime integration with the pinned CUDA stack, profiler, allocator snapshot
  schema, and host telemetry remains unexecuted and therefore unqualified.
- If a PyTorch allocator snapshot does not expose a uniquely matching OOM
  allocation size, the related diagnosis remains `INCONCLUSIVE` by design.
- A separate scientific execution authority and its host preflight are still
  required before any M0–M5 model or CUDA execution, including the CPU ONNX
  reference.
- No Well Logging retry, production change, capacity change, L5 evidence
  change, or promotion is authorized by this implementation.

## Readiness

```yaml
tracked_worktree:
  candidate_changes_committed: true
  unrelated_preexisting_untracked_user_data: PRESERVED / NOT STAGED

independent_review_readiness:
  implementation: COMPLETE
  tests_and_static_checks: PASS
  durable_result: COMMITTED IN SUCCESSOR HANDOFF COMMIT
  remote_branch: PUSHED / EXACT HEAD VERIFIED
  verified_handoff_commit: 1e5624ae01675bf711e6bd8e113c196b91b9ca62
```

The exact remote verification command was:

```text
git ls-remote origin refs/heads/implementation/16k-r04-embedding-memory-diagnostic-harness
1e5624ae01675bf711e6bd8e113c196b91b9ca62  refs/heads/implementation/16k-r04-embedding-memory-diagnostic-harness
```
