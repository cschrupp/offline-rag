# S16K-R04 Live Execution Authority — Run 001

## Authority

- Authority: `S16K-R04-CUDA-OOM-LIVE-EXECUTION-AUTH-001`
- Human authorization: granted in the conversation after acceptance of R04 implementation.
- Accepted implementation subject: `469bb8a3b137c279b1dcfa8bcef8cb8c7fbeaf40`.
- Execution branch: `implementation/16k-r04-cuda-oom-adaptive-recovery`.
- Current execution checkout includes governance-only Human-acceptance record `1c047caadf13a7347f579c1bf268bd7888a23794`; production code remains the accepted subject above.
- Scope: one bounded, live `SOURCE_ADD` attempt using the exact source bytes from the preserved incident.

## Frozen workload

- Workspace: `ws_464d92440ba343bf9372216e508e81b4`.
- Required pre-submit workspace state: revision `2`, one active source.
- Source object: `vobj_7cdf0819b4df4336a2e7a950762552af`.
- Display name: `Well Logging for Earth Scientists.pdf`.
- Size: `22,656,044` bytes.
- SHA-256: `f50a3df2e1d22c8c925a60981a79b4e70a675cb70504ce725e7d0d2e03195afd`.
- Request: exactly one multipart `SOURCE_ADD`, guarded by `If-Match: "2"` and a fresh idempotency key.

## Execution bounds and stop conditions

1. Start one Seneca API process from the authorized branch using the repository `.venv`; do not start a second server or change settings/dependencies.
2. Capture one fresh observation-only host preflight and verify API readiness, the active `cuda_fp16_v1` profile, and the exact workspace precondition before submitting.
3. Submit the frozen source once. The embedder may perform only its implemented CUDA batch ladder `32 → 16 → 8 → 4` within that one logical operation.
4. Poll that operation for at most 45 minutes. Do not repeat the submission, restart the API after submission, or issue another workspace mutation. If the operation has not reached a terminal state at the limit, capture its current state and stop without cancelling or resubmitting it.
5. At terminal state, perform read-only checks of the operation, workspace, and `/health/ready`, then stop.

The run ends on the first terminal operation result, API health loss, a failed pre-submit invariant, or the 45-minute observation limit. On a failed operation, do not retry after runtime failure. No CPU fallback, profile change, process kill, allocator change, source removal, retrieval query, or additional science is authorized by this record.

## Interpretation boundary

- A successful operation with effective batch below 32 is live evidence of adaptive recovery for this source and observed host state.
- Success at batch 32 demonstrates only that this one live workload completed without adaptation.
- Terminal `cuda_memory_exhausted` demonstrates bounded recovery exhaustion in this one run; it does not authorize another attempt.
- Any other failure is recorded as observed without inferring an OOM cause.
- This single run is not a multi-arm A/B/C/D campaign and does not establish broader capacity qualification.

## Evidence handling

Capture preflight, operation, workspace, capability, and health responses under a new local `artifacts/diag_16k_r04_cuda_oom/live_run_001/` directory. Keep the PDF, vault payload, credentials, and unsanitized machine command lines out of Git. Record hashes for JSON evidence and report the final operation/workspace state. Do not modify `main`, promote the implementation, or authorize 16K-F/G or Slice 17.
