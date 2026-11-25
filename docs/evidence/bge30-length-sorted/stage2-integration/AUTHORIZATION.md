# Seneca — Stage 2 Integration Candidate and Execution Readiness

## Independent review decision

**PR #5 lifecycle implementation accepted for integration qualification.**

Exact accepted head:
`239ecd1ef30a200e023d87284d807bb3c444abba`

The dated amendment supersedes only the conflicting preflight-precedence requirement in the earlier design. Do not change the accepted lifecycle implementation without new evidence and review.

Other relevant candidates:

- PR #3 — BGE-30 length-sorted batching: `6900aeb33f063492ab6709a73707ed1e65e6ab8d`
- PR #4 — independent frontend assertion correction: `fee6515102ac2f8d9944e83d8b3d705dba9e1625`
- Shared integration base: `corrective/18d-r-reranker-initialization`

**Authorization covers integration preparation and local validation only. No VM campaign or production deployment.**

## Task 1 — Establish one controlled integration lineage

Inspect the current remote branches and exact commit ancestry.

Construct one separately reviewable integration candidate containing:

1. The approved 18D-R reranker initializer.
2. The exact accepted PR #5 lifecycle implementation.
3. The exact PR #3 BGE-30 batching implementation.
4. The independent PR #4 assertion correction where required to obtain a meaningful integrated CI result.

Keep the original PRs separate and draft.

Use a merge, cherry-pick or other traceable method that preserves attribution and exposes conflicts. Record the integration diff.

Do not silently incorporate unrelated commits or rewrite accepted evidence.

## Task 2 — Verify integrated application behavior

Run focused and representative regression tests against the actual combined source.

Require:

- Workspace conversations use the approved shared query gate.
- Preflight precedence matches the dated amendment.
- Disconnected workers retain capacity until termination.
- Cooperative deadlines and shutdown drain behave as accepted.
- BGE-30 consecutive remains the default.
- `length_sorted_8` is selectable without changing the candidate pool.
- Exact ranking, raw-logit tolerance and packed-evidence parity.
- Immutable snapshot fingerprints remain compatible.
- No duplicate query or conversation terminal records.

Check specifically for interactions between batching, the tokenizer lock, cancellation checkpoints and shared inference under contention.

Do not change concurrency capacity to manufacture throughput improvements.

## Task 3 — Resolve CI disposition

Validate the integrated frontend using PR #4's assertion-only correction.

Run hosted backend and frontend CI where available.

Retain the eight existing 15F fixture failures as explicitly classified baseline debt. Do not mark them passing or silently exclude them from a release gate.

If an independent correction is needed, propose it separately.

Report exact green, red and waived gates. Do not claim complete release readiness while mandatory CI is red.

## Task 4 — Prepare one diagnostic image

Produce or specify one immutable diagnostic image from the accepted integrated candidate.

Record:

- Git commit and complete parent provenance.
- Image digest.
- Python, PyTorch, Transformers and tokenizer versions.
- BGE checkpoint identity.
- CPU device and FP32 execution policy.
- Reranker input depth of 30.
- Available consecutive and sorted-eight strategies.
- Runtime operation limits.
- Scientific configuration hashes.

The two experimental arms must use the identical image, scientific configuration, query route and provider fixture.

**Only the execution batching strategy may vary.**

Do not deploy or start a campaign on the Seneca VM.

## Task 5 — Freeze Stage 2 inputs and execution envelope

Prepare a read-only execution manifest for Recipes revision 4 and Rich revision 2.

Freeze exact questions, source selections, workspace revisions, immutable snapshot IDs, model artifacts and local non-generative provider fixture.

Require the same corrected workspace conversation route for both arms.

Proposed workload budget:

- Recipes and Rich.
- Consecutive and sorted-eight.
- One serial, one two-client and one four-client wave per workload and strategy.
- Maximum 28 load submissions.
- Four lifecycle submissions per strategy.
- Maximum eight lifecycle submissions.
- Total maximum **36 submissions, zero retries**.

Specify how accepted, rejected, canceled and completed requests will be counted under the existing capacity-one policy.

Preserve resource ceilings, bounded per-submission deadlines, isolation requirements and restoration reserve.

Require copied writable snapshot backing, exclusive Qdrant ownership, read-only model files, disabled external networking and deterministic provider responses.

## Task 6 — Submission for independent execution authorization

Deliver:

1. Exact integrated source commit.
2. Integration diff and provenance.
3. CI and local regression results.
4. Diagnostic image digest and reproducible build procedure.
5. Frozen workload and provider-fixture manifest.
6. Exact 36-submission protocol.
7. Resource and maintenance-window preflight.
8. Failure, abort and rollback procedures.
9. Remaining blockers to experimental execution.

Retain this authorization and the complete Codex response.

Commit and push the integration preparation evidence on a dedicated branch.

Do not merge PRs #3, #4 or #5, modify the production image, alter defaults, run VM maintenance, or perform Stage 2 submissions.

**Stop at the integrated diagnostic candidate review checkpoint.**