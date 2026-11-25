# Stage 2 Campaign B — Lifecycle Qualification

**Result:** `NATIVE_STAGE2_LIFECYCLE_COMPLETE`
**Disposition:** Campaign B execution complete; submitted for the final combined assessment. Production batching activation remains unauthorized.

## Execution identity

- Session: `7b95b124c4cd0906`
- Driver candidate: `e47cd36c0c9ded3b89a86e4f1ffd2c6b02f7995c`
- Integrated application source: `1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`
- Diagnostic image: `seneca-rich2-local:1f79eca0`, digest `sha256:59252d0655267001c4c9ac42e5a2045131b4086bb1ab84e10dbfd98f2e831dee`
- Original service image: `seneca-review:9c92e706c4b9`, image ID `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`
- Runtime settings remained the frozen Stage 2 settings: 4 effective CPUs; PyTorch FP32, intra/inter-op 2/2; Qwen ONNX 8/1; one query slot; 180-second application query deadline; 30-second application drain grace; 6-GiB diagnostic memory ceiling; zero diagnostic swap; no external network.
- Recipes and Rich 2 published data were not modified. Lifecycle cases used the approved Recipes binding.

## Submission outcomes

Exactly eight submissions were attempted and settled, with zero retries:

| Ordinal | Strategy | Scenario | Terminal | Reason | Client delivery/status | Server HTTP | Worker returned | Slot released |
| ---: | --- | --- | --- | --- | --- | ---: | --- | --- |
| 1 | consecutive | disconnect before scorer | cancelled | client_disconnect | disconnected | 204 | yes | yes |
| 2 | consecutive | disconnect during scorer | cancelled | client_disconnect | disconnected | not observed | yes | yes |
| 3 | consecutive | cooperative deadline | timed_out | query_deadline_exceeded | HTTP 504 | 504 | yes | yes |
| 4 | consecutive | shutdown drain | cancelled | shutdown | HTTP 500 | 500 | yes | yes |
| 5 | length_sorted_8 | disconnect before scorer | cancelled | client_disconnect | disconnected | 204 | yes | yes |
| 6 | length_sorted_8 | disconnect during scorer | cancelled | client_disconnect | disconnected | 204 | yes | yes |
| 7 | length_sorted_8 | cooperative deadline | timed_out | query_deadline_exceeded | HTTP 504 | 504 | yes | yes |
| 8 | length_sorted_8 | shutdown drain | cancelled | shutdown | HTTP 500 | 500 | yes | yes |

The drain responses were HTTP 500 during the deliberately initiated shutdown path; this is recorded as the harness's observed lifecycle outcome, not represented as a normal successful user query. Disconnect scenarios were canceled and settled, deadline scenarios reached the unchanged application deadline and returned 504, and every worker returned before query capacity was released.

## Lifecycle observations

- **Disconnect before inference:** both strategies observed cancellation at the pre-grounded checkpoint. No scorer or forward pass was entered. The worker returned, query capacity was released, and no query trace was present.
- **Disconnect during inference:** the client disconnect was observed while the actual BGE scorer was held at the native forward seam. The scorer was released and completed its real scoring path; the worker then settled as canceled. Capacity remained held until worker return. The completed scoring path emitted a query trace, while the request terminal remained canceled; a trace does not imply HTTP delivery or an answered conversation.
- **Deadline:** both requests retained the 180-second application deadline. After the bounded forward hold was released, the route returned HTTP 504 with `query_deadline_exceeded`; the worker subsequently returned and released capacity.
- **Shutdown drain:** the server began drain with the real query slot occupied. Cancellation was signaled for `shutdown`; scoring unwound, the worker returned, and capacity was released before restoration completed.

The deadline and drain scenarios deliberately include their 180-second and 30-second barrier holds. Their scorer and assembler wall times therefore describe lifecycle timing under the test hooks, not natural query latency. They must not be used as a sorted-versus-consecutive performance comparison. Disconnect-during cases also test cancellation behavior and do not replace Campaign A's parity qualification.

The native observer captured real score associations, candidate ranking/tie-break identity, context anchor/evidence identities and packed-context hashes on scored cases. The sanitized per-submission observations preserve those hashes, logits, batch shapes, latency measurements and process CPU/RSS observations without source text, passages, request paths, workspace IDs, operation IDs or trace IDs. The raw VM journal SHA-256 is recorded in that file; the unredacted journal remains on the VM.

Across the six scored lifecycle executions, candidate/input associations matched, all 30 candidates were scored, and the maximum absolute raw-logit difference relative to the first scored execution was `3.82e-6` (2.64% of the largest applicable per-pair tolerance). Full ranking, anchor, evidence-unit and packed-context hashes matched across these executions. This is an internal consistency check on the captured lifecycle observations; Campaign A remains the formal fixed-depth parity qualification.

## Resource observations

The diagnostic process remained within its 6-GiB RSS ceiling. Peak process RSS across scored lifecycle requests was approximately 4.26 GiB for consecutive and 4.02 GiB for length-sorted-eight. The no-inference cases peaked at approximately 418 and 416 MiB. Sampled Docker memory peaked at approximately 2.923 GiB of the 6-GiB limit; sampled CPU peaked at approximately 198.6% (about two of four CPUs). No OOM was observed. The run began with at least 2 GiB of available host memory and retained the accepted four-CPU allocation.

For context only, measured native forward batches included:

| Strategy / scenario | Batch shapes (pairs × padded width) | Forward wall times |
| --- | --- | --- |
| consecutive / disconnect during | 16×368, 14×406 | 29.950 s, 28.385 s |
| consecutive / deadline | 16×368, 14×406 | 38.328 s, 33.701 s |
| consecutive / drain | 16×368, 14×406 | 29.485 s, 28.705 s |
| length-sorted-eight / disconnect during | 8×86, 8×166, 8×241, 6×406 | 3.898 s, 7.096 s, 10.443 s, 13.133 s |
| length-sorted-eight / deadline | 8×86, 8×166, 8×241, 6×406 | 13.046 s, 7.080 s, 9.560 s, 12.577 s |
| length-sorted-eight / drain | 8×86, 8×166, 8×241, 6×406 | 3.354 s, 6.557 s, 10.071 s, 12.526 s |

These timings include lifecycle barriers in the surrounding scorer wall time, reflect a small number of scenario-specific executions, and are not a paired performance estimate. Campaign A remains the source of the accepted performance comparison: Recipes improved materially; Rich 2 showed no material benefit. Campaign B establishes lifecycle behavior only.

## Restoration

The driver exited 0, the independent watchdog exited 0, and `native_host_control.py verify` exited 0. The original `seneca-review` container was running again with its original image, `/srv/seneca/data:/data` read-write mount, `/srv/seneca/models:/models` read-only mount and `unless-stopped` restart policy. `/health/live` and `/health/ready` each returned HTTP 200. Publication metadata was unchanged; no process owned the scratch Qdrant storage; no session diagnostic container remained. Session scratch was retained on the VM for evidence custody.

See `RESTORATION_VERIFICATION.json` for the machine-readable restoration result. The local evidence set intentionally omits the raw event journal because it contains private operational identifiers; its SHA-256 is `cd888446beaba7f656db97036d556b2c43bdeb2efde03e5b9f316a777446ed6b`.

## Combined assessment and limits

Campaign B completed all eight lifecycle scenarios under both strategies. No lifecycle worker retained query capacity after returning, and restoration passed. Together with accepted Campaign A, the program now has workload-specific performance/parity evidence and lifecycle evidence. It does not establish production p95, concurrency performance beyond the tested admission contract, or a universal latency improvement. The performance benefit is specific to the Recipes workload; Rich 2 showed no material gain. A final policy decision should preserve that workload-specific distinction.

No production default, published workspace, image, or deployment was changed. Production activation remains pending the combined assessment and is not authorized by this evidence commit.
