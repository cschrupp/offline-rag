# S16K-R04 CUDA OOM Adaptive Recovery — Implementation Result

## Authority and candidate context

- Authority: `S16K-R04-CUDA-OOM-ADAPTIVE-RECOVERY-IMPLEMENTATION-AUTH-001`
- Authorized base: `02923af0630400e94cd1a3659837cd8f9f75ac40`
- Branch: `implementation/16k-r04-cuda-oom-adaptive-recovery`
- Scope: CUDA OOM adaptive recovery, bounded diagnostics, execution reporting, user feedback, and observation-only process/GPU preflight.

The source incident is identified by operation `wop_70fb3e3001854d56909a735667d9f837`, workspace `ws_464d92440ba343bf9372216e508e81b4`, dense run `index_b439a1324b174848b520df5c899f2c47`, source `Well Logging for Earth Scientists.pdf` (22,656,044 bytes; SHA-256 `f50a3df2e1d22c8c925a60981a79b4e70a675cb70504ce725e7d0d2e03195afd`). Its private incident payload remains outside this artifact.

## Implemented behavior

### CUDA recovery and lifecycle

- CUDA document encoding starts with the current effective batch size. A fresh embedder starts at its configured size, currently 32.
- Recognized CUDA memory exhaustion retries the same logical payload at the bounded ladder `32 → 16 → 8 → 4`. No attempt below 4 is made.
- A successful smaller batch becomes the monotonic process-local effective batch for subsequent calls on that embedder. A new process/runtime starts from the configured default.
- CPU encoding remains a single attempt. Generic CUDA errors, model errors, and other non-OOM exceptions are not retried.
- Between retry attempts, cleanup clears attempt traceback references, runs garbage collection, and calls `torch.cuda.empty_cache()` best-effort. Cleanup failure is recorded when diagnostics are enabled and does not mask the original OOM classification.
- No CPU fallback, runtime reconstruction, device/profile switching, allocator policy change, or embedding/index identity change was introduced.
- After all four CUDA sizes fail, `CudaMemoryExhaustedError` escapes; `QualifiedEmbeddingRuntime` preserves final batch facts, releases the backend, and remains terminal `FAILED` until process restart.

The detector recognizes PyTorch `OutOfMemoryError` and specific CUDA allocation-exhaustion messages, including cause/context chains. It does not treat an arbitrary `AcceleratorError`, illegal memory access, device-side assertion, or generic runtime failure as OOM.

### Dense diagnostics and public error

When `OFFLINE_RAG_DIAG_DENSE_PROFILE=1`, `dense-cuda-profile-v2` now retains per-attempt bounded facts: logical outer batch and item count, ordered chunk identity digests, token distribution, aggregate/padded token workload, allocator and device-wide memory before the attempt, external GPU observations, elapsed time, outcome, next batch, and cleanup results. No source text is recorded. Failed indexing reports retain this profile summary.

`cuda_memory_exhausted` is a trusted dense failure reason and maps to the safe public shape `{stage: "dense", reason: "cuda_memory_exhausted"}`. Raw CUDA/PyTorch exception text remains in operator diagnostics and is not projected into the public error DTO.

### Effective execution facts and UI

- `ManagedOperationDenseExecution.batch_size` reports the effective batch; optional `configured_batch_size` preserves the configured value. Historical records without the new field remain valid.
- Successful CUDA operations show a warning badge only when effective batch is below configured batch. Details include configured/effective batch and device when available.
- The trusted terminal OOM reason receives concise GPU-memory guidance and an `Open Compute settings` link to `/settings?section=compute`. Generic embedding failures do not receive OOM copy. No retry/fallback action was added.

### Observation-only host preflight

The stdlib-only `scripts/diag_16k_r04_cuda_oom/preflight.py` inspects `/proc`, listeners, and `nvidia-smi`; it does not import Torch or signal processes. Known secret flags, bearer values, and URL credentials are redacted from emitted command lines.

One authorized host snapshot was captured at `artifacts/diag_16k_r04_cuda_oom/preflight-run.json` (local evidence, not committed; SHA-256 `4b16b035d258886caeee07208b9960e9e034615d30c8085fca0307f906252df7`). It observed 7,161/8,192 MiB GPU memory in use, zero attributable compute processes, and no identifiable generation server. Process attribution was `NOT_OBSERVABLE`; the high GPU occupancy flag was raised.

The initial snapshot counted two command lines containing the API module. Review of the saved process facts showed these were `uv` PID 44311 and its Python child PID 44362; only PID 44362 owned the `127.0.0.1:8080` listener. The preflight classifier was narrowed to count actual server executables, and a synthetic launcher/child test passes. The one-run authorization was honored: the host was not queried again. Interpreted result: one observed Seneca API process, no duplicate server established, and GPU consumer attribution unavailable.

## Validation

- `uv run pytest -q tests/unit/dense tests/unit/test_dense_failure_observability.py tests/unit/test_slice16k_r04_preflight.py tests/unit/app/test_slice16k_b_ingestion_observability.py tests/unit/app/test_slice16k_d_p2_dual_backend_product_integration.py` — **313 passed**, one pre-existing Starlette/httpx deprecation warning.
- `npx vitest run src/test/slice16k_r04_cuda_oom.test.tsx` — **4 passed**.
- `npx eslint src/components/OperationProgress.tsx src/components/Badge.tsx src/features/operations/operationErrorMessages.ts src/test/slice16k_r04_cuda_oom.test.tsx` — **passed**.
- `npx vite build` — **passed**; Vite emitted a large-chunk advisory.
- `git diff --check` — **passed**.
- Ruff on the changed Python paths other than `src/offline_rag/dense/profiling.py` — **passed**. Ruff on `profiling.py` reports five existing findings (three RUF046, one SIM102, one PLR1730); the exact authorized-base version has the same five findings plus an existing UP035 import finding. No R04-introduced Ruff finding remains.

Validation used deterministic OOM mocks. The real incident workload and any CUDA OOM A/B/C/D reproduction were not run.

## Production posture and limitations

- Product limits, capacity policy, parser behavior, model/profile identity, precision, and durable embedding/index identity: unchanged.
- Real `Well Logging for Earth Scientists.pdf` retry: **NOT EXECUTED**.
- CPU fallback or profile switching: **NOT IMPLEMENTED**.
- Scientific or capacity qualification: **NONE**.
- 16K-F/G, Slice 17, and promotion: **NOT AUTHORIZED**.
- The saved incident did not establish which process consumed the unavailable GPU memory attribution. Adaptive recovery itself still requires independent review before any real-workload execution gate.

## Review readiness

Implementation and deterministic validation are complete for the bounded R04 scope. This artifact and the candidate commit are the durable review handoff. Stop for independent review; do not retry the incident workload or promote this branch.
