# Seneca Research — Small-Pool Reranking and CPU Execution

## Disposition

Accept Rich workspace stage-attribution diagnostic as valid exploratory performance evidence.

Production optimization remains unauthorized.

## Research context

Repository: `cschrupp/offline-rag`

Research workstream:\
`docs/research/bge_quality_latency_frontier/`

Deployed baseline:\
`9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`

Rich workspace snapshot:\
`snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`

Confirmed warm measurements:

- 10 BGE candidates.
- One 10 × 509 batch.
- BGE scorer: 30.615 s.
- BGE forward: 30.592 s.
- Dense retrieval: 0.465 s.
- Total assembler: 31.108 s.
- Padding: 12.3%.
- Three evidence units, 3,729 context tokens.

The historical browser request used a different resolver-derived retrieval question. Preserve that distinction.

## Task A — Incorporate the new case into the research report

Add a separately identified Rich workspace case study.

Explain:

1. Why a ten-passage workspace still requires expensive CPU inference.
2. Why cold Qwen3 startup and warm BGE inference are different problems.
3. Why the Recipes sorted-eight result does not automatically generalize.
4. Why candidate count, sequence length and batch shape must be studied together.
5. Why the successful browser response rules out a universal application outage but not intermittent transport failure.

Include the supplied stage waterfall and its numeric provenance.

Preserve the original report's conclusions and distinguish different workloads.

## Task B — Small-batch CPU experiment design

Using the original ten ordered query–passage pairs, design controlled comparisons of:

- Current batch size 10.
- Batch size 5.
- Batch size 4.
- Batch size 2.

Preserve:

- Original checkpoint, tokenizer and FP32 precision.
- All ten candidates.
- The 1,024-token ceiling.
- Passage-only truncation.
- Raw-logit scoring.
- Original candidate-score association.
- Ranking tie-breaking and context selection.

Determine whether valid existing research evidence can be reused.

Predefine numerical tolerance, exact ranking/evidence requirements, warm-up, paired measurement order, and meaningful performance thresholds.

Do not predict the winner from padding calculations alone.

## Task C — Assess the marginal value of BGE

Using available labeled evaluation data, compare hybrid RRF against BGE for queries with small candidate pools.

Determine:

- When BGE improves top-five relevance.
- When it changes evidence selection without improving judged relevance.
- Whether some query categories benefit more than others.
- Whether a low-cost ranking policy can satisfy defensible quality requirements.
- What additional human judgments are necessary.

For Rich's workspace, compare existing RRF and BGE candidate ordering only where the necessary evidence is available.

Do not treat agreement with BGE as ground-truth relevance.

Do not label a RRF-only result scientifically equivalent merely because the document scope is unchanged.

Do not rerun OpenRouter generation or inspect private source text without appropriate separate authorization.

## Task D — Develop an architectural recommendation

Compare:

1. Optimized batching of the existing BGE model.
2. Quality-qualified RRF-only retrieval.
3. A smaller multilingual reranker.
4. CPU quantization or an alternative inference representation.
5. Faster inference hardware.

For each option report expected mechanism, scientific risk, implementation cost, memory footprint, Docker implications and required validation.

Do not assert latency gains before measurement.

## Deliverables

Update the interim research report with:

- Rich workspace case study.
- Small-pool performance analysis.
- CPU batching experiment protocol.
- Quality-gated reranker policy design.
- Prioritized next experimental campaign.
- Reproducibility and provenance records.

Retain the authorization prompt and full Codex response.

Commit the research documentation on a dedicated branch without modifying frozen evidence or production code.

No VM inference, model download, generation call, deployment or production configuration change is authorized in this phase.

Stop for independent review.
