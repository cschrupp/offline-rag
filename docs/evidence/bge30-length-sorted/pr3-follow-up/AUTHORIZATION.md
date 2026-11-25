# Seneca — PR #3 Independent Review Follow-up

Repository: `cschrupp/offline-rag`

PR: [https://github.com/cschrupp/offline-rag/pull/3](https://github.com/cschrupp/offline-rag/pull/3)

Reviewed head: `3a6317c51010de6242adf187554842de52ddf174`

Disposition: `REVISE / HOLD MERGE`

The core length-sorted batching implementation is acceptable as a review candidate. Consecutive remains the default. Production deployment is not authorized.

## Task 1 — Reconcile failing GitHub Actions

Inspect failed workflow run `44971589913`.

The frontend failure is in:

`ui/src/test/slice16h_integration_acceptance.test.tsx`

The test expects an `Engineering summary` heading, while the page renders `Engineering`.

Both files have unchanged Git blobs between PR base and head.

Reproduce the failing test at the exact base and PR-head commits under equivalent conditions.

Classify it as:

- Pre-existing baseline failure.
- Flaky test.
- Genuine PR regression.
- Inconclusive.

If correction is necessary, determine the smallest contract-consistent fix.

Do not alter the UI merely to satisfy an obsolete assertion. Do not mix unrelated frontend corrective work into the batching implementation without a clear integration reason.

Record test evidence and ensure the PR's CI disposition is explicit.

## Task 2 — Validate final scorer implementation

Recheck the final, post-tokenizer-lock implementation for:

- Concurrent calls sharing a tokenizer/model.
- Tokenizer prepass and batch-tokenization consistency.
- Original candidate-score association.
- Near-tie behavior.
- Exact ranking and packed-evidence parity.
- Empty and malformed inputs.
- Default `consecutive` behavior.
- Snapshot identity compatibility.

Retain the approved BGE model, FP32 precision, `input_k=30`, and source scope.

Do not change scientific tolerances.

## Task 3 — Prepare a bounded CPU opt-in pilot

Propose a small, independently reviewable CPU pilot using the actual feature-branch implementation, not the earlier instrumented research scorer.

Include at least:

- One 30-pair heterogeneous Recipes case.
- One ten-pair, mostly homogeneous Rich case.
- Additional representative length and candidate-count shapes where available.

Measure warm scorer and assembler latency, CPU-seconds, memory, and complete parity.

Include bounded concurrency and cancellation checks before any user-facing activation.

Use the accepted isolated-snapshot procedure and explicit service-restoration checks.

No VM execution is authorized by this task.

## Task 4 — CUDA qualification plan

Preserve CUDA implementation support.

Document the minimum GPU-backed test needed for numerical parity, ranking, packed evidence, GPU memory, and completed-inference timing.

Do not claim CUDA optimization effectiveness until measured.

## Task 5 — Release dependency check

Record the relationship between:

- The deployed `9c92e706` baseline.
- `corrective/18d-r-reranker-initialization`.
- PR #3.
- `main`.

Propose a merge order that preserves the initialization correction and avoids unintentionally incorporating unrelated changes.

Do not merge, deploy, or change production defaults.

## Deliverable

Return:

1. CI root-cause classification and reproduction evidence.
2. Any corrective commit and updated PR status.
3. Final scorer review findings.
4. Exact bounded CPU pilot protocol.
5. CUDA qualification requirements.
6. Release dependency and rollback plan.

Retain the authorization and full execution response.

Stop before production activation.
