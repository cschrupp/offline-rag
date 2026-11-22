# Seneca — PR #3 Integration Correction and CPU Pilot Stage 1

## Independent review decision

Accept the follow-up at `6900aeb33f063492ab6709a73707ed1e65e6ab8d` as sufficient preparation for a bounded CPU experiment.

Keep PR #3 in draft.

No merge, deployment, global strategy change, production query, publication migration or CUDA activation is authorized.

## Part A — Resolve the pre-existing CI defect separately

The frontend failure was reproduced at both the exact 18D-R base and PR #3 head.

The accepted Engineering page renders a level-one heading named `Engineering`, whereas the existing test expects `Engineering summary`.

On a dedicated corrective branch based on the current 18D-R integration line:

1. Apply the smallest assertion-only correction consistent with the accepted UI.
2. Do not change the Engineering page or any production frontend behavior.
3. Run the affected 13-case test and the full deterministic frontend checks.
4. Commit the fix separately and create a reviewable PR against the appropriate 18D-R integration branch.
5. Record the exact original failure, corrected assertion, test results and full Codex response.

Do not merge the corrective PR without independent review.

Recheck PR #3's newest hosted results and record any remaining failures distinctly.

## Part B — Execute the isolated CPU Stage 1 pilot

Canonical protocol:

`docs/evidence/bge30-length-sorted/pr3-follow-up/CPU_PILOT.md`

Feature candidate:

`6900aeb33f063492ab6709a73707ed1e65e6ab8d`

Use the actual application scorer and assembler from PR #3. Do not substitute the earlier research-only scorer.

Authorize only the two mandatory workloads:

- Recipes revision 4, original single-source question and 30-candidate snapshot.
- Rich revision 2, ten-candidate no-history question and existing snapshot.

Compare `consecutive` against `length_sorted_8` at unchanged BGE-30 depth.

### Call budget

One warm-up per arm and three counterbalanced measured pairs per workload.

Exactly 16 assembler calls maximum.

No retries, generation, external provider traffic or live product queries.

Optional workload slots 3–5 are not authorized in this execution.

### Safety envelope

Use a fresh maintenance window.

Before stopping the original container, require:

- At least 3,600 seconds remaining before automatic VM STOP.
- A hard 2,400-second diagnostic execution ceiling.
- A reserved restoration window of at least 900 seconds.
- A 180-second per-call deadline.
- A 6-GiB diagnostic process RSS ceiling.
- At least 2 GiB host available memory throughout the campaign.
- Sufficient disk space for a consistent isolated data copy.
- No competing experiment or live request in progress.

These are experimental safety limits, not production resource specifications.

If any limit is incompatible with the actual VM configuration or accepted maintenance procedure, stop before maintenance and report the conflict. Do not silently change the limits.

Stop the original container gracefully and use one network-disabled diagnostic environment with copied writable data, exclusive Qdrant ownership and read-only model artifacts.

Preserve original image, mount, settings, snapshot and workspace identities.

### Required measurements

For both workloads, report:

- Paired complete assembler wall and CPU time.
- BGE forward and scorer wall time.
- Tokenizer prepass overhead.
- Actual batch shapes and padding.
- Candidate count and original candidate order.
- Raw FP32 logit differences.
- Full rank and tie-break parity.
- Anchor identities and order.
- Evidence-unit identities and order.
- Exact packed-context byte identity.
- Memory and sampled CPU usage.
- All failures, incomplete observations and near ties.

Apply the existing numerical tolerance:

`abs(delta) <= 1e-4 + 1e-5 * abs(baseline)`

Any ranking or evidence parity failure blocks qualification for that workload, regardless of performance.

Assess Recipes and Rich independently using the existing 20% performance screen. Do not average a Rich regression away with a Recipes speedup.

### Restoration

Always restore the original deployment.

Verify:

- Original container is running.
- Both health endpoints return HTTP 200.
- Image and mount identities match.
- Restart policy is unchanged.
- Recipes and Rich revisions and snapshots match.
- Source inventories and publication pointers match.
- No diagnostic container retains the Qdrant lock.

Preserve measurements, authorization, full Codex response and restoration evidence in a separately reviewable commit.

## Restrictions

Do not execute Stage 2 lifecycle/concurrency testing under this authorization.

Do not enable sorted-eight for users, modify CUDA settings, change the production image or merge PR #3.

Stop after the test-only correction candidate and the isolated Stage 1 pilot have been reported for independent review.
