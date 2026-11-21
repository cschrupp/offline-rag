# Seneca — BGE-15 CPU Profile Qualification

## Decision

Prioritize a controlled evaluation of reducing `reranker.input_k` from 30 to 15.

The objective is to improve CPU retrieval latency while preserving acceptable retrieval quality.

No immediate production configuration change is authorized.

## Existing evidence

- Recipes, 30 candidates: approximately 56–57 seconds warm BGE.
- Rich's workspace, 10 candidates: 30.615 seconds warm BGE.
- Exact-incident sorted-eight batching: 48.6% median forward-time reduction with ranking and evidence parity.
- Human-reviewed candidate-depth replay: BGE-15 retained comparable cohort-average quality to BGE-30, with two query-level regressions.
- No measured four-vCPU latency result currently exists for BGE-15.

## Task A — Scientific configuration and publication impact

Inspect the actual configuration and publication contracts.

Confirm that `reranker.input_k` participates in `reranker_config_hash` and immutable snapshot identity.

Design a safe BGE-15 candidate profile that:

- Retains the approved BGE checkpoint and FP32 precision.
- Retains `output_k=10`, current context-anchor policy and source scope.
- Preserves the original BGE-30 snapshots and their scientific identities.
- Does not silently change existing published snapshots.
- Identifies whether a new compatible publication can reuse validated dense and lexical artifacts without re-ingestion.
- Provides an explicit rollback procedure.

Do not edit production YAML and restart the container as a shortcut.

## Task B — Controlled performance evaluation

On the four-vCPU VM, in an isolated, safely restored experiment, compare:

1. BGE-30, original batching.
2. BGE-15, original batching.
3. BGE-30, sorted-eight batching.
4. BGE-15, sorted-eight batching.

Use the same original Recipes question, indexed content, source scope and underlying retrieval assets.

For depth-15 candidates, use the top 15 from the original fused RRF ordering, not the first 15 results of an already-reranked BGE-30 list.

Measure:

- Warm forward wall time.
- Complete assembler wall time.
- CPU-seconds.
- Memory.
- Candidate and evidence identities.
- Resulting latency improvement over the current production policy.

Use counterbalanced measurements and predefined acceptance criteria.

If immutable snapshot contracts prevent a scientifically valid isolated comparison, stop and report the necessary publication preparation rather than bypassing validation.

## Task C — Quality evaluation

Reuse the accepted human-reviewed Slice 9H-P evaluation.

Preserve and prominently report both BGE-15 regressions.

Compare nDCG, Recall, relevant-passage retention and changes to selected evidence.

Do not treat cohort-average equivalence as query-level equivalence.

Define a proposed production-quality acceptance gate before examining any new results.

## Task D — Deployment proposal

Only if the performance and quality evidence justify further qualification, prepare:

- A distinct, identifiable BGE-15 execution/retrieval profile.
- Compatible publication and workspace migration design.
- Regression tests for existing snapshot resolution.
- Rollback to BGE-30.
- Post-deployment latency and error monitoring.

Do not deploy, migrate existing workspaces, merge into main or change production defaults without independent review and explicit authorization.

## Deliverables

Update *The 59-Second Retrieval* research report with:

1. Direct BGE-15 performance evidence.
2. Quality–latency comparison with BGE-30.
3. Interaction with sorted-eight batching.
4. Scientific identity and publication implications.
5. Proposed deployment and rollback procedure.
6. Independent-review readiness.

Retain the complete authorization prompt and Codex responses.

Stop for review.
