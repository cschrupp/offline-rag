# Research protocol

Parent `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`. This protocol precedes
new replay or inference. Previously observed diagnostic results are historical.

| Hypothesis | Null | Primary endpoint and guardrail |
|---|---|---|
| H1 Sorted batching reduces cost | Warm paired forward time does not decrease | Sorted 8 vs consecutive 16+14 on one synthetic incident-length surrogate. Median paired wall reduction ≥20%, FP32 atol 1e-4/rtol 1e-5, exact ranked IDs, and exact evidence when available |
| H2 Shallower prefixes preserve relevance | A reduced depth loses more than the proposed quality margin | Paired nDCG@10 and Recall@10 versus BGE-30. Exploratory screen: mean nDCG loss ≤0.02, Recall loss ≤0.05, no loss of HitRate@5. A development screen does not qualify deployment |
| H3 BGE benefit varies by query | Full rerank has the same nDCG@10 effect on all queries | Paired changes versus RRF, report improvements, harms, and ties on human-reviewed cases |
| H4 Adaptive depth improves tradeoff | No adaptive policy dominates eligible fixed depths | Held-out quality and measured same-host CPU/wall cost; fit and freeze policy separately before test |
| H5 Ranking improvement need not improve answers | Ranking changes have no discordance with paired grounded-answer changes | Paired independently judged answer support/correctness, citation validity, and abstention disposition under frozen generation |

Primary depth population is the existing human-reviewed cohort. All 22 cases
and assistant-only cases are descriptive sensitivity strata. Candidate replay
restricts the complete BGE permutation to each original RRF prefix, after
requiring equal candidate sets and exact fused input order. Reuse canonical
metric functions. Bootstrap queries, not repeated timings, with 10,000 paired
resamples and fixed seed 59. Intervals are descriptive given selection, small
population, and multiple comparisons. No threshold or policy fit on test cases.

Projection uses exact observed tokenized lengths, stable sort by length then
original ordinal, and batch maxima. Compute padded slots and sum of batch
size times squared width. This proxy has no time units.

Local pilot uses pinned local BGE, FP32, Torch 2/2, same 30 deterministic
synthetic pairs across arms, tokenizer passage-only truncation max 1024.
One warm-up per arm and two measured blocks AB then BA, A consecutive
16+14, B sorted 8. Reorder logits to original candidate order before parity.
Report all trials, process CPU and forward wall, and host/runtime details.
Synthetic inputs support forward and ranking feasibility only. Exact incident
pairs are absent locally. Other batch sizes are projections. No new VM or
generator calls.

A descriptive Pareto front may use accepted Slice 14C two-arm quality and
latency from the same suite. Keep it separate from 9H-P replay (quality only)
and Recipes/synthetic timing (no adjudicated quality). A point is dominated
when another is at least as good on quality and cost and strictly better on
one. Use nDCG@10 and median total latency for the descriptive two-arm plot.
