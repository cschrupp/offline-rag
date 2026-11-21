# Proposed quality-gated reranker policy

An RRF-only candidate must earn a separate quality decision. Pool size and
source count alone are insufficient routing features. RRF retrieves and
orders a pool. BGE can alter which passages reach the context packer,
including passages from the same source. Agreement with BGE is a behavioral
comparison. Use independent relevance and evidence judgments for quality.

## Evidence needed

- Select development and held-out query families before scoring. Include
  naturally small pools (1–5 and 6–10), larger controls, short and long
  passages, cross-lingual queries and each consequential query category.
  Preserve corpus/chunk-set identity and report eligible denominators.
- For each query, collect the complete scoped fused pool and raw logits,
  ranked IDs and trace-linked context from each arm. Judge the union of
  candidate passages and selected evidence blinded to arm and rank, with
  independent double review and adjudication. Where feasible, exhaustively
  judge the small source scope, including passages absent from both arms,
  so recall has a defensible denominator. Treat missing judgments as
  missing in the decision evidence and include sensitivity to incomplete
  labels. Grade partial relevance separately from direct support.
- Judge independently whether each packed context contains the needed
  facts, essential direct evidence and any conflicting context. A claim
  about grounded answers would require a separately authorized paired
  generator evaluation with frozen provider settings and independent
  support/correctness judgments. When absent, report retrieval qualification
  only.
- Publish paired per-query and per-stratum harms, not only averages.
  No category policers can be fit from the current 1–3 human labels per
  category.

## Decision rule for review before qualification

Use canonical BGE as the control. Compare unconditional RRF-only and, only
if development results warrant it, a frozen deterministic allowlist policy.
The allowlist may consider pre-rerank features such as eligible pool size,
passage-length profile, and dense/lexical rank agreement. Freeze feature
extraction and thresholds before opening the held-out evaluation. Unknown
or poorly supported strata retain BGE. Shadow evaluation would be a
separate authorized, isolated workflow.

Proposed research gates, subject to scientific review before holdout:
paired lower 95% confidence bounds for RRF minus BGE above −0.02 on
nDCG@5 and −0.05 on Recall@5. Require no newly lost sole directly supporting
passage in the final top five, no adjudicated critical evidence-sufficiency
regressions, and no required stratum with insufficient review support.
Select a sample size justified by the agreed margins, expected variance and
query-family grouping. Report point estimates and paired query-family
intervals, with exact case counts and interval procedure. The small 9H-P
fixture is exploratory and cannot satisfy these gates. BGE-10's replayed
mean nDCG@5 gain of about 0.05 illustrates why a pool-count-only bypass is
a poor default.

Any policy advancing beyond quality review must separately show a
meaningful same-host reduction in process CPU and wall time, under both
isolated and realistic concurrent load, with reversible opt-in activation
and existing BGE retained for rollback. This design authorizes neither
deployment nor evaluation execution.
