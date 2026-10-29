# S16K-R04 Live Execution Result — Run 001

## Authority and subject

- Authority: `S16K-R04-CUDA-OOM-LIVE-EXECUTION-AUTH-001`.
- Human authorization: granted after acceptance of R04 implementation subject `469bb8a3b137c279b1dcfa8bcef8cb8c7fbeaf40`.
- Execution branch: `implementation/16k-r04-cuda-oom-adaptive-recovery`.
- Checkout at execution: `e7156319fc0c2d6d8f21a59334ba37bc400efc1f`.
- Execution count: one `SOURCE_ADD` request; no resubmission.

## Frozen source and preconditions

- Workspace: `ws_464d92440ba343bf9372216e508e81b4`.
- Pre-submit revision/source count: `2` / `1`.
- Source: `Well Logging for Earth Scientists.pdf`.
- Source size: `22,656,044` bytes.
- Source SHA-256: `f50a3df2e1d22c8c925a60981a79b4e70a675cb70504ce725e7d0d2e03195afd`.
- Active profile: `cuda_fp16_v1`, device `cuda`, precision `fp16`.
- Pre-submit capability: large-PDF runtime eligible, effective limit `94,371,840` bytes.
- Request used `If-Match: "2"` and idempotency key `r04-live-001-20261028`.

## Terminal result

- Operation: `wop_7850c5198c2c49fdb601231be81e8db8`.
- HTTP submission result: `202 Accepted`.
- Operation terminal: `failed`, non-retryable `ingest_failed`.
- Dense failure classification: `cuda_memory_exhausted`.
- Dense execution report: CUDA FP16, configured batch `32`, final effective batch `4`, profile `cuda_fp16_v1`.
- Reported work: `893` embeddings reused, `0` generated, `32` failed; total reported chunks `1,498` across the two desired documents.
- Elapsed total stage time: `35,103 ms`.
- No CPU fallback, profile switch, second request, or post-submit server restart occurred.

This is a bounded recovery exhaustion result for this one source and observed host state. It shows that the implemented ladder did not produce a successful embedding batch at its minimum size. It does not establish the host-level root cause of CUDA allocation pressure, a general workload threshold, or a capacity qualification. No A/B/C/D campaign was run.

## Post-terminal state

- Workspace revision/source count: `2` / `1`, unchanged from pre-submit. The attempted second source was not published.
- `/health/ready`: `200`, `{"status":"ready"}`.
- Embedding runtime: `FAILED` with `runtime_execution_failed`.
- Post-run large-PDF capability: ineligible, effective limit `26,214,400` bytes, reason `memory_telemetry_unavailable`.
- No further source mutation, retrieval query, restart, or retry was performed after terminal state.

The API remained ready while its embedding runtime was failed. The operation's classified error is the evidence for CUDA memory exhaustion; the kernel log is not treated as proof of a system-wide OOM. The captured `dmesg` interval contains no OOM-killer or process-killed entry during the operation. It includes older unrelated segfault entries and a later `dxgkio_make_resident` `-12` entry at 20:19:33; that later host-driver observation is outside the operation interval and is not attributed to this run.

## Local evidence custody

Raw run evidence is local and untracked under:
`artifacts/diag_16k_r04_cuda_oom/live_run_001/`.

SHA-256 values:

| File | SHA-256 |
| --- | --- |
| `preflight-poststart.json` | `6baa7e47ab0a67dbd5a913bae9c4a1cb61baed9b6787420144bd2c11ee489455` |
| `workspace_before.json` | `90f77cdd08b1b329e51f02f012b70df8d40c0825b7302ef4c4372419988b73a3` |
| `capabilities_before.json` | `03b2b31ddf0bf73da7afa90405ba2ca570d044efc6b5833b84c1fa7b6897d066` |
| `health_ready.json` | `31bf75f4c0a97cc1f7b60df824fa390b3be9ba014f29b63c87c698ba63d9a9fd` |
| `source_add.response.json` | `e618880cab45a14af28ed80e3137f46aa83ef042d9666d8b589eb5f7b892f18e` |
| `source_add.headers` | `f1b0d0bb30042252aa93d355ac5d6d8940344a5ab03c2248605054f60b6c7f6d` |
| `operation.latest.json` | `7ada4f63edc055ac9b0b64be8629e79508acf06c085151d5fcbb90d928f2ec09` |
| `operation.terminal.json` | `f7470b3f46c8c01f02a371346c78468cc6d001d8b7e4f49782e3696bff8e74de` |
| `workspace_after.json` | `90f77cdd08b1b329e51f02f012b70df8d40c0825b7302ef4c4372419988b73a3` |
| `health_after.json` | `31bf75f4c0a97cc1f7b60df824fa390b3be9ba014f29b63c87c698ba63d9a9fd` |
| `capabilities_after.json` | `b2dd3485b1453a3f04723ada4a02f9368e549e4e1990e73e2982737573f98e3a` |
| `dmesg-after.txt` | `7c2f7eecf79d68a37d7e27293a5d3d6a69a44d1305261944ea1f906cd7a3bfa7` |

The preserved source PDF and vault payload are not included in this record or Git.

## Terminal and authority boundary

```yaml
live_execution:
  run_001: TERMINAL_FAILURE
  classification: CUDA_MEMORY_EXHAUSTED
  recovery_ladder: EXHAUSTED_AT_BATCH_4
  workspace_publication: ROLLED_BACK
  api_health_after: READY
  embedding_runtime_after: FAILED

additional_attempts:
  NOT_AUTHORIZED

16K-F/G:
  NOT_AUTHORIZED

promotion:
  NOT_AUTHORIZED

capacity_qualification:
  NOT_ESTABLISHED
```
