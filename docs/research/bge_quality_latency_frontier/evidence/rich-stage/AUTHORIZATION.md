# Seneca — Rich Workspace Retrieval Stage Attribution

**Disposition:** HTTP delivery confirmed on one isolated browser request. Authorize a bounded, isolated retrieval-only diagnostic. No production changes authorized.

## Baseline

Repository: `cschrupp/offline-rag`

Deployed revision:\
`9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`

Workspace: Rich's test workspace, revision 2.

Snapshot:\
`snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`

Single-document, all-active source scope.

Question:\
`Describe the naturalistic decision method`

Observed successful request:

- Browser: HTTP 200 in 46.095 seconds
- Context: 39.775 seconds
- Generation: 4.396 seconds
- Two prior conversation turns
- Resolver invoked
- Answered with two citations

## Objective

Attribute the approximately 40-second context latency to existing retrieval stages without changing the production application, scientific settings, or generation path.

## Phase A — Identity and resolver reconciliation

Inspect the historical successful conversation and query traces.

Determine whether the resolver's retrieval-question SHA-256 matches the normalized original question.

Do not expose or reconstruct private prior-turn content.

If the hashes differ, explicitly state that a no-history assembler call is a related but nonidentical retrieval workload. Do not claim exact request reproduction.

## Phase B — Existing instrumentation inventory

Use the nested `HybridRerankContextResult.metadata["latency_ms"]` diagnostics.

Capture non-overlapping stage timings:

- Dense retrieval, including Qwen3 query embedding.
- Lexical retrieval.
- RRF fusion.
- Reranker pair construction.
- BGE `score_pairs()`.
- Reranker sorting.
- Context expansion and packing.
- Assembler total.

Record actual fused candidate count, reranker input count, padded batch widths, post-tokenization pair lengths, context token count and evidence-unit count.

Ensure nested parent/child timers are not added together twice.

Reuse existing BGE diagnostic code if necessary, without modifying model semantics.

## Phase C — Controlled execution

Use the previously validated maintenance and isolated-snapshot procedure.

Preflight:

- Correct image, model artifacts, snapshot, scope and settings.
- Available CPU, RAM, disk and VM STOP deadline.
- Safe isolation and restoration requirements.
- Absence of active user requests or competing experiments.

Stop the original container gracefully, create an isolated consistent data copy, and use isolated Qdrant storage.

Keep model artifacts read-only and disable external network access.

Execute exactly:

1. One cold assembler call.
2. One warm assembler call in the same process.

No generator or HTTP query is authorized.

Preserve the deployed PyTorch 2/2 policy, 30-candidate ceiling, existing batching, and approved models.

## Phase D — Scientific and performance checks

For both calls, record:

- Every retrieval stage's wall time.
- BGE forward time if already available from approved diagnostics.
- Input pool size and batch shapes.
- Process CPU time and sampled CPU utilization.
- Process RSS and host memory.
- Ranked candidate identity hashes.
- Anchor and evidence-unit identity hashes.
- Packed context identity hash.

Confirm both calls preserve the same scientific input and output identities.

Compare results against the historical 39.775-second context observation, identifying differences in execution environment and resolved query.

Do not infer that stage timings from the Recipes snapshot apply to Rich's workspace.

## Phase E — Restoration and reporting

Restore the original container and verify both health endpoints, image, mounts, restart policy, workspace revision, snapshot and source inventory.

Retain:

- Full authorization.
- Implementation and execution response.
- Exact runtime identity.
- Numeric stage measurements.
- Scientific parity evidence.
- Restoration record.

Produce a concise diagnostic report with a stage waterfall and a ranked recommendation for the next performance treatment.

Do not change timeouts, reranking depth, batching strategy, backend, worker ownership, or production settings.

Stop after reporting.
