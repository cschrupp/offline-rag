# S16K-R04 — Integrated Workload Freeze and Conditional M0–M5 Execution Plan

## Status and decision gate

```yaml
status: READY_FOR_INITIAL_HUMAN_GO
scientific_execution: NOT_AUTHORIZED_UNTIL_INITIAL_HUMAN_GO
workload_freeze: NOT_RUN
model_or_cuda_execution: NOT_RUN
cpu_onnx_reference: NOT_RUN
```

This plan joins the accepted R04 design, Amendment 001, and reviewed diagnostic
harness into one executable envelope. It is submitted for the program's single
**Initial Human GO**. That GO will authorize the bounded CPU-only workload
freeze and every conditional campaign branch below. No further Human gate is
required between branches when work remains inside this plan. Independent
reviews remain controls; accepted review results continue, and bounded findings
are corrected and re-reviewed. Return to the Human only for a material change
to scope, scientific rules, cost/risk limits, or production behavior.

## Bound subjects

- Accepted design: `beecfd56fb5c085fabcca0131f0af7e67923836f`
- Accepted design Human-acceptance record: `e078c56c94eef63e00d4b347f057f89b71da7f0b`
- Accepted Amendment 001: `7a2a4427e76a6c675df1e833deb4b6dce0fadb83`
- Amendment Human-acceptance record: `2ad161e2b3bb266a531fbd3adb9a4ea061eb142c`
- Accepted harness implementation subject: `f69a56cd1a251b83d2b0cda0a02bb4714e2fda0a`
- Harness handoff/review lineage tip: `d97908656099238aac2ab4d618a99716b58778c5`
- Scientific implementation subject for all execution evidence: the accepted
  harness subject above; no code changes are permitted during this campaign.

The reviewed harness, frozen design, and amendment are controlling. This plan
does not modify production behavior, choose a production candidate, or authorize
a Well Logging ingestion retry.

## Objective and outputs

Measure the frozen 32-item Qwen embedding workload to distinguish cache,
materialization, attention, token-padding, allocator, and external-device-memory
effects. For each applicable treatment, report separate mechanism and
production-candidate dispositions under the existing rules.

The campaign produces a privacy-safe frozen workload manifest; exact cell
specifications and their authority hashes; raw cell evidence and claim ledger;
bounded allocator snapshots on OOM; deterministic reductions and comparisons;
and one consolidated scientific assessment with limitations and deviations.
Private source text, token IDs, vectors, allocator snapshots, and logs remain in
local ignored data paths unless the evidence custody policy explicitly calls
for a hash-only derived artifact. Never put private corpus content in Git.

## Execution phases

### 1. CPU-only workload freeze

After Initial Human GO, reconstruct the first pending 32-item outer batch from
the Run 001 source/workspace state and immutable parsed/chunk/cache artifacts.
Use the accepted pipeline traversal and selection order. Do not load Qwen,
SentenceTransformers, or an embedding model; do not initialize CUDA.

First attempt `EXACT_INCIDENT_BATCH`. Verify the source SHA, workspace/source
state, model and embedding configuration identities, chunk-set identity, and
the reported 893 reused / first 32 failed boundary. Record only ordered chunk
IDs, per-item text digests, aggregate workload digest, Qwen token counts, and
the required configuration identities. Do not persist text or raw token IDs.

If the exact identity cannot be reconstructed, use only the design's specified
deterministic first-32-missing-artifact selection from preserved parsed/chunk
artifacts and label it `INCIDENT_ADJACENT_SUBSTITUTE`. Do not call it exact
incident reproduction. If artifacts are missing or would require re-parsing
the PDF, stop and report; do not invent a substitute source or parsing path.

Freeze the manifest and its SHA-256 before any model or CUDA process. Verify it
contains exactly 32 unique ordered items, positive token counts, exact model
revision, and no private text/token fields. Workload identity is immutable for
all cells.

### 2. Deterministic authority and cell-spec materialization

After the frozen workload digest exists, but before M0 or any model import,
materialize an immutable campaign authority and a finite catalog of exact cell
specifications. The catalog is generated from the frozen manifest and the
finite control values already allowed by the accepted design/harness. It must
include all legal conditional active-control combinations for M1/M2/M3/M4/M5,
all three replicate hashes where applicable, the single M3 profile hash, and
the optional single CPU ONNX reference hash. For M3, include only supported
backend names admitted by the harness. M5 spec variants cover only combinations
of frozen controls that could be selected; the campaign controller still
requires the selected settings to equal evidence-derived `ACTIVE_CONTROLS`.

Every spec is canonical JSON, names the exact workload digest and expected
model revision, and is hashed before the first model process. The authority
binds the accepted design, accepted implementation subject, frozen workload
digest, allowed cell IDs, exact per-cell/per-replicate spec hashes, and the
Human GO. No spec or authority hash may be added, edited, or replaced after M0
starts. If a required legal spec is absent, stop before the affected model
process; do not widen authority during execution.

The full exact-spec catalog is pre-authorized, while evidence-derived
`authorize_cell_start()` controls which specific spec can actually start next.
Only one model process runs at a time. Each cell uses its own exact hash and
single-use claim. Failed, invalid, or already-claimed cells are never retried.

### 3. Preflight and pairing

Before the first model cell, record the host, GPU/device, driver, CUDA/PyTorch,
Transformers, SentenceTransformers, model revision, available memory, process
visibility, and the absence of a competing embedding workload. Confirm the
frozen local model bundle and offline operation. Do not change allocator
configuration, environment memory fractions, batch recovery, or device policy.

Before each later cell, verify the same model/runtime/device identity and no
unexpected process or concurrent workload. Pair baseline/treatment initial
device-free memory within 256 MiB; comparisons also become inconclusive if
paired external device usage changes by more than 256 MiB. Record
`NOT_OBSERVABLE` when process ownership is unavailable. Do not infer owners from
the allocator/device gap.

### 4. Conditional experiment sequence

All cells use one fresh process, the exact frozen 32 texts, batch size 32 unless
M4's accepted deterministic partitions apply, and no internal retry. The
controller is the admission authority; operators do not bypass it or manually
promote rejected controls.

1. **M0 — current path, three fresh processes.** Characterize the existing
   load-then-`.half()` runtime without treatment. Capture loaded/effective cache
   state and witnesses, dtype and load peaks, configured and observed attention,
   Qwen token shapes, vectors, allocator/device metrics, and correctness. If a
   qualified CUDA OOM occurs before vector output, the one CPU ONNX parity
   reference may run under the pre-authorized exact reference spec. It is an
   offline diagnostic reference only, never fallback.
2. **M1 — cache disabled, conditional.** Run three replicates only if M0 shows
   cache configured enabled and an authoritative activation/use witness. Change
   only `use_cache=true` to false, verify the false forward state and absence of
   cache construction/update. If M0 proves cache disabled/no use, record
   `NOT_APPLICABLE` without a cell. If M0 cannot reach the cache boundary,
   record `INCONCLUSIVE` and stop progression that depends on cache resolution.
   M1 enters `ACTIVE_CONTROLS` only if its mechanism is `SUPPORTED` and its
   candidate is `QUALIFIED`; otherwise later baselines retain the prior active
   controls.
3. **M2 — direct FP16 materialization, three replicates.** Compare current
   load-then-half with direct FP16 model construction, changing materialization
   only. Use the accepted active cache state. Measure loading/materialization,
   steady, and forward stages separately. M2 enters `ACTIVE_CONTROLS` only if
   both frozen acceptance axes qualify.
4. **M3 — attention, conditional.** Apply Amendment 001 to the current
   `ACTIVE_CONTROLS` after M0/M1/M2. Open M3 if all three active-state forwards
   complete and the median incremental working set meets
   `max(256 MiB, 5% × median(P))`, with at least two of three individual
   increments meeting that threshold; or if at least two valid active-state
   replicates OOM after model load and encode entry. Run one separate profiler
   cell. Normalize the actual baseline from profiler operator keys. Derive
   eligible treatment alternatives as the intersection of backend eligibility
   over every observed SDPA call minus the observed baseline. An unresolved or
   ambiguous baseline is `INCONCLUSIVE / BASELINE_ATTENTION_BACKEND_UNRESOLVED`
   and no treatment cell starts. A known baseline with no alternatives closes
   M3 as `NOT_APPLICABLE / NO_ELIGIBLE_ALTERNATE`. If one or two alternatives
   remain, map all of them to M3_A/M3_B in sorted backend-name order (ordering
   labels cells only; it does not rank candidates). If more than two remain,
   do not choose a subset: report `INCONCLUSIVE / ALTERNATIVE_SET_EXCEEDS_TWO`
   and stop downstream stages that require M3 resolution. Each selected
   treatment uses three replicates and is independently compared to the
   pre-M3 active condition. Only a supported and qualified treatment updates
   active controls. If multiple alternatives qualify, fail closed because the
   accepted design defines no winner.
5. **M4 — token-budget batches, conditional.** Evaluate the exact 32 frozen
   token counts for the active condition. Open only if the deterministic greedy
   partitioner creates more than one partition, lowers padded tokens, and
   saves at least 5%, with identical token counts across the three active-state
   runs. The accepted padded-token budget and item cap apply; any oversized
   individual sequence makes M4 `NOT_APPLICABLE`. The proxy opens an experiment
   only; H-TOKEN is supported only by actual memory/correctness/parity/
   performance results. Run three replicates if admitted.
6. **M5 — selected-candidate confirmation, conditional.** Start only after all
   applicable prior stages are resolved. Select settings exactly equal to the
   cumulative `ACTIVE_CONTROLS` produced by treatments that are both
   `SUPPORTED` and `QUALIFIED`. `NOT_APPLICABLE` stages do not block. An
   applicable incomplete, invalid, or inconclusive stage blocks M5. If no
   treatment changed controls from M0, report
   `NOT_APPLICABLE / NO_QUALIFIED_TREATMENT`; do not repeat baseline. Otherwise
   run three fresh-process confirmations using fixed32, or M4 partitions when
   that is the selected qualified control.

### 5. Measurements and analysis

Use the accepted per-stage allocator counters and 10 Hz device sampling. Reset
allocator peak counters at each registered phase boundary and synchronize CUDA
around encode measurement. On OOM capture the bounded allocator history/snapshot
in the exception path, sample device-free memory within 250 ms where possible,
and preserve diagnostic validity separately from mechanism comparability.
Profiler-run measurements are characterization only and never replace
unprofiled M3 treatment peaks.

Use the frozen D2 parity gates without weakening: 1024-dimensional finite
normalized vectors (norm tolerance `1e-4`); per-vector cosine median `>=0.999`
and minimum `>=0.995`; retrieval mean top-10 overlap `>=0.95`, minimum
`>=0.80`, and top-1 agreement at least 15/16. Preserve exact vector count,
identity/order, and artifact identity. Candidate qualification also requires
the accepted memory effect: `max(256 MiB, 5% of paired baseline peak)`, direction
in at least two of three pairs, no other primary peak regression over 256 MiB,
and median encode latency regression no greater than 10%. Keep mechanism and
candidate dispositions separate. Right-censored OOM is resource evidence, not
a completed mechanism measurement.

The final analysis reports each hypothesis as `SUPPORTED`, `FALSIFIED`,
`INCONCLUSIVE`, or `NOT_APPLICABLE`, and each production candidate using the
accepted candidate outcomes. State whether the batch is exact incident or
adjacent substitute and do not generalize a 32-item diagnostic to a full PDF or
workspace lifecycle.

## Fixed budgets and stop conditions

- At most three fresh-process replicates per applicable condition.
- One M3 profiler characterization; at most two M3 treatments (three
  replicates each).
- At most 22 CUDA measured cells and one CPU ONNX reference process: 23 model
  process executions maximum.
- One process at a time; 15-minute maximum per CUDA cell; four-hour total
  campaign ceiling; no within-cell retry.
- Stop on workload identity failure, model/runtime/device mismatch, competing
  workload, unapproved process, failed preflight, invalid evidence, non-OOM
  execution error, process crash, privacy leak, parity failure, inability to
  obtain three valid replicates within budget, cell timeout, or campaign cap.
- Keep the accepted production `32 → 16 → 8 → 4` safety ladder unchanged.
- No production code/config/dependency changes; no production candidate,
  capacity-policy change, full Well Logging operation, or promotion.
- If an outcome is outside a frozen rule, stop and report rather than inventing
  a new gate or selecting an unregistered treatment.

## Final review and Human gate

After the campaign and deterministic analysis, prepare one consolidated report
covering the frozen workload identity, host/runtime, all cells and evidence
hashes, every conditional branch and reason, resource traces, parity,
mechanism/candidate dispositions, deviations, limitations, and recommended
next actions. Independent reviewers assess the complete campaign. Only after
that general review is complete does the program return for **Final Human
Acceptance**.

That final acceptance does not itself authorize production implementation,
promotion, or a full Well Logging retry; each remains a separate later decision.

## Initial Human GO request

```yaml
requested_gate: INITIAL_HUMAN_GO
subject: this exact integrated execution plan and its committed SHA
scope: CPU-only workload freeze plus conditional R04 M0-M5 campaign
conditional_cpu_onnx_reference: at most one process, only after qualifying M0 OOM
cuda_measured_cell_cap: 22
total_model_process_cap: 23
per_cuda_cell_cap: 15 minutes
campaign_cap: 4 hours
production_changes: NOT_AUTHORIZED
well_logging_retry: NOT_AUTHORIZED
promotion: NOT_AUTHORIZED
```

The GO authorizes no work beyond this envelope. Without that explicit GO,
workload freeze and all campaign execution remain unauthorized.
