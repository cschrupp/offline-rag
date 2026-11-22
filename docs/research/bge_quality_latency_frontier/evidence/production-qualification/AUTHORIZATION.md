# Seneca — Post-Experiment Qualification and Production Decision Design

## Disposition

The BGE-15 four-arm performance experiment at commit `05a38aaf4820f598defe8d4c9c13d87f3bddb641` is accepted as exploratory scientific and performance evidence.

All measured performance gates passed. Fixed-depth batching parity passed. Cross-depth evidence equivalence did not hold and was not required by the protocol.

Production promotion remains unauthorized.

## Task A — Consolidate the evidence

Use *The 59-Second Retrieval* as the canonical research report.

Preserve the actual findings for:

- Recipes BGE-30 consecutive: 60.361 seconds.
- Recipes BGE-15 consecutive: 29.346 seconds.
- Recipes BGE-30 sorted-eight: 33.950 seconds.
- Recipes BGE-15 sorted-eight: 20.491 seconds.
- Rich's ten-pair experiment: no smaller-batch treatment achieved the 20% gate.

Retain all observed timing outliers, query-level regressions, parity evidence and experimental limitations.

Do not reinterpret a quality change as scientific equivalence.

## Task B — Prepare sorted-eight production qualification

Define a representative multi-query evaluation of BGE-30 consecutive versus BGE-30 sorted-eight.

Include short, long, homogeneous and heterogeneous sequence-length workloads.

Require:

- Same ordered candidates and encoded inputs.
- Predefined raw-logit tolerance.
- Exact ranked candidate identity and tie-breaking.
- Exact anchors, evidence units and packed context.
- Paired warm latency and CPU measurements.
- Memory and concurrent-load assessment.
- No regression in failure or cancellation behavior.

Investigate whether length-aware batching should be conditional on measured workload characteristics rather than universally enabled.

Do not implement or deploy the policy during this task.

## Task C — Prepare BGE-15 held-out quality qualification

Apply the acceptance framework already preregistered in:

`docs/research/bge_quality_latency_frontier/evidence/bge15-cpu/PROTOCOL.md`

Prepare a representative, independently adjudicated evaluation population.

Include multiple document types, passage lengths, naturally small candidate pools, pools with 30 or more candidates, multilingual queries, and technical questions.

Preserve the preregistered non-inferiority margins and require query-level harm analysis.

Blindly judge the union of candidate passages and selected evidence, accounting explicitly for unjudged candidates.

Include evidence-sufficiency and grounded-answer evaluation where supported.

Retain the two known development regressions.

Do not select margins after seeing held-out outcomes or substitute agreement with BGE-30 for human relevance judgments.

## Task D — Deployment and rollback design

Prepare separate designs for:

1. BGE-30 sorted-eight execution without reducing candidate depth.
2. BGE-15 sorted-eight using a new qualified immutable snapshot identity.

For each, define:

- Required implementation and review.
- Scientific fingerprint and provenance.
- Snapshot/publication compatibility.
- Workspace migration requirements, if any.
- Docker CPU and memory behavior.
- Concurrency and admission safeguards.
- Rollback to the existing PyTorch BGE-30 deployment.
- Post-deployment latency, error and quality monitoring.

Do not change production defaults, publish production snapshots, merge, or deploy.

## Deliverable

Produce a consolidated qualification plan and decision memorandum explaining:

- Which evidence is accepted.
- Which claims remain workload-specific.
- What must be measured before production approval.
- Which candidate has the lowest scientific risk.
- Which candidate has the greatest demonstrated performance benefit.
- Exact proposed execution authorizations for the next qualification campaigns.

Retain this prompt and the complete response in the research evidence.

Commit and push the report revision on a reviewable research branch.

Stop before execution or promotion.
