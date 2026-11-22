# Seneca — BGE-30 Sorted-Eight CPU Stage 2 Qualification

## Review disposition

Accept CPU Stage 1 at commit:

`158f839bcdbea74764daf2c0fcc76d7431774355`

The actual PR #3 scorer has passed the required parity and performance screen for Recipes.

Rich passed parity but failed the performance screen. It is not qualified for a sorted-eight performance claim.

PR #3 remains draft. No production activation or merge is authorized.

## Task A — Stage 1 operational closeout

Review `docs/evidence/bge30-length-sorted/cpu-stage1/run.sh`.

Address the temporary `runtime.env` cleanup path so that credentials are never retained following failed setup, interrupts or teardown.

Inspect prior diagnostic directories for residual sensitive temporary files without printing or committing their contents.

Record the outcome and any cleanup performed. Preserve scientific measurement evidence unchanged.

Inspect the two setup failures and confirm they were confined to diagnostic staging.

## Task B — Execute Stage 2 in isolation

Use the accepted protocol:

`docs/evidence/bge30-length-sorted/pr3-follow-up/CPU_PILOT.md`

Compare the exact application implementations:

- A: BGE-30 consecutive.
- B: BGE-30 length_sorted_8.

Use the Recipes and Rich published-snapshot identities from Stage 1, unchanged checkpoint, original query bindings and source scopes.

Use an isolated Docker deployment, copied writable backing, exclusive Qdrant ownership, fixed CPU allocation, Torch FP32 2/2 and the approved Qwen3 profile.

No production HTTP requests or external provider calls.

Use the actual application HTTP route with a controlled local non-generative provider fixture.

### Exact execution budget

For each strategy and each workload:

- One serial client submission.
- One two-client wave.
- One four-client wave.

Maximum: 28 workload submissions across both strategies and workloads.

Separately execute, for each strategy:

- Disconnect before reranking.
- Disconnect during reranking.
- Deadline at the next supported cancellation checkpoint.
- Shutdown drain.

Maximum: eight additional lifecycle submissions.

Combined maximum: **36 submissions, zero retries**.

Do not expand the campaign or change established admission limits to obtain better results.

## Task C — Required verification

Capture separately for each route and workload:

- Client admission, rejection and queue behavior.
- Accepted and rejected request counts.
- Time to response and backend completion time.
- BGE forward and total assembler latency.
- CPU utilization and CPU-seconds.
- Process and container memory.
- HTTP response status.
- Grounded-result and citation-contract validation using the approved local fixture.
- Snapshot and source binding.
- Cancellation recognition and terminal state.
- Shutdown completion.
- Whether abandoned work continues consuming reserved capacity.

The synchronous workspace conversation route and managed query route have different lifecycle contracts.

Do not infer one route's correctness from the other. If either route is outside the authorized workload, explicitly classify its lifecycle behavior as unqualified.

Treat any unbounded request, premature capacity reuse, duplicate terminal record, unrecognized completion, or uncontrolled memory growth as a blocking failure.

Do not conceal a pre-existing lifecycle defect by attributing it to batching or by changing the route.

Preserve the Rich latency outlier and investigate any new comparable events without excluding observations.

## Task D — Production readiness assessment

Evaluate Recipes and Rich independently.

Provide:

1. Scientific parity results under the actual execution path.
2. Service latency and resource behavior under contention.
3. Request admission and lifecycle correctness.
4. The qualified workload scope, if any.
5. Whether sorted-eight can be enabled as an explicit CPU opt-in without a runtime selector.
6. Exact remaining release blockers.
7. Rollback and monitoring requirements.

Do not design an automatic workload classifier from these two queries.

Do not change `input_k`, production defaults, immutable publications, workspace data, CUDA settings or the approved model.

## Safety and restoration

Freeze a bounded maintenance window, per-submission deadlines and resource ceilings before stopping anything.

Require sufficient time for both the complete campaign and independent restoration.

Stop before maintenance if the window or isolation requirements cannot be met.

Always restore the original Seneca container, then verify it remains running.

Require both health endpoints to return HTTP 200 and confirm unchanged image, mounts, restart policy, workspace revisions, snapshots, source inventories and publication pointers.

Preserve the authorization prompt, full Codex responses, raw measurements, all failures, numeric evidence and restoration record.

Commit and push the findings to a separate reviewable evidence branch.

**Stop after Stage 2. No production rollout, merge or CUDA promotion is authorized.**