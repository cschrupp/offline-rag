# Seneca Research — The 59-Second Retrieval

## Mission

Conduct a rigorous investigation of neural reranking cost versus retrieval quality in CPU-only RAG.

Produce a reproducible research study and a professional, technically detailed report with excellent scientific storytelling.

The report must be suitable for independent technical review and eventual publication in the Seneca engineering portfolio.

Working title:

**The 59-Second Retrieval: Finding the Quality–Latency Frontier in CPU-Only RAG**

Subtitle:

*An empirical investigation of candidate depth, length-aware batching, and the marginal value of neural reranking.*

## 1. Scientific baseline and authority

Repository: `cschrupp/offline-rag`

Production deployment baseline:
`9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`

Recipes snapshot:
`snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`

Review the existing `AGENTS.md`, scientific authority documents, Slice 9 retrieval evaluation, accepted Slice 14C evidence, and recent BGE CPU diagnostics.

Existing relevant surfaces:

- `src/offline_rag/evaluation/`
- `src/offline_rag/evaluation/performance_14/`
- `docs/slice9_retrieval_evaluation.md`
- `docs/milestone7_performance_ui.md`
- `eval/results/performance_14/`
- `src/offline_rag/rerank/cross_encoder.py`
- `src/offline_rag/rerank/retrieve.py`
- `src/offline_rag/context/assemble.py`

Do not overwrite frozen experiments, redefine accepted metrics, or reinterpret the previous numerical-parity failures.

Create a separate research branch from the appropriate approved base. Record the exact parent SHA.

## 2. Research hypotheses

Pre-register these hypotheses before conducting new measurements.

H1: Length-aware batching reduces BGE CPU forward-pass time relative to consecutive batching without materially changing retrieval ranking or selected evidence.

H2: For some queries, reranking fewer than 30 RRF candidates retains comparable relevance at lower computational cost.

H3: The incremental relevance benefit of BGE varies by query, and some queries may not require full cross-encoder reranking.

H4: A quality-aware selection of retrieval depth may offer a better performance–quality tradeoff than an unconditional fixed-depth pipeline.

H5: Retrieval ranking improvements do not necessarily translate into better grounded answers or fewer model abstentions.

Define null hypotheses, primary metrics, relevant quality constraints, exploratory comparisons, and evidence requirements.

Distinguish confirmatory findings from exploratory observations.

## 3. Phase A — Inventory existing research assets

Inspect the accepted Slice 14C quality-versus-cost benchmark and available GoldDataset v1 cases.

Determine:

- The number and type of human-adjudicated cases.
- Which corpora and chunk-set identities they belong to.
- Whether full fused candidate orders and BGE scores are retained.
- Whether prefix replay can be performed without new inference.
- Whether candidate evidence and gold relevance judgments can be linked.
- Which historical measurements are descriptive only.
- Which assets remain frozen and must not be rewritten.

Do not substitute the Slice 9 validation fixture for real relevance labels.

Do not assume the Recipes snapshot has human-adjudicated gold labels.

Record limitations and blockers explicitly.

## 4. Phase B — Candidate-depth evaluation

Compare:

- Hybrid RRF without BGE.
- BGE reranking of RRF top 5.
- BGE reranking of RRF top 10.
- BGE reranking of RRF top 15.
- BGE reranking of RRF top 20.
- BGE reranking of RRF top 30.

For each query, the smaller depth must mean the first k candidates in the original fused RRF ranking, reranked using their original BGE scores.

Do not incorrectly truncate the output of a completed 30-candidate rerank and call that a smaller input-depth experiment.

Where original full-pool scores exist, reuse them for deterministic replay.

Compare using established IR metrics where eligible:

- Recall@5 and Recall@10.
- nDCG@5 and nDCG@10.
- MRR.
- HitRate and Precision where supported.
- Retention of relevant passages.
- Selected-anchor agreement and evidence changes.

Report eligible populations and missing judgments.

Treat agreement with BGE-30 as a diagnostic, not as ground-truth quality.

Use identical query populations and corpus identities in paired comparisons.

Do not claim measured latency savings from score replay alone. Identify which cost reductions are theoretical and which have actually been timed.

## 5. Phase C — Length-aware batching investigation

Study the existing 30-pair measured workload.

Compare the theoretical workload for:

1. Current consecutive batches of 16 + 14.
2. Length-sorted batches of 16.
3. Length-sorted batches of 8.
4. Length-sorted batches of 4.
5. Length-sorted batches of 2.

Keep the original BGE checkpoint, precision, 30 candidates, full passages, 1,024-token maximum and passage-only truncation.

For each strategy, calculate actual post-tokenization sequence lengths, padded positions, padding fraction, and the attention-work proxy.

Develop an isolated research-only benchmark or experimental adapter if justified.

Any executable comparison must preserve candidate identity and restore scores to the original input ordering.

Predefine numeric logit tolerance and require exact ranked IDs and evidence selection wherever those can be evaluated.

If authorized local model artifacts and input pairs are available, run a bounded local paired benchmark with documented warm-up and measured repetitions.

Keep the CPU thread setting constant for the batch-shape comparison.

Do not run a new VM inference campaign under this authorization.

If local inputs or model artifacts are unavailable, complete the arithmetic and design work, classify the actual performance result as pending, and identify the minimum required execution.

## 6. Phase D — Retrieval and grounded-answer analysis

Investigate the difference between ranking quality and answer usefulness.

Use available accepted generation-evaluation contracts and recorded observations.

For the original Recipes incident, identify what existing evidence can establish about:

- Presence of the requested ingredients in retrieved passages.
- Whether BGE promoted answer-bearing passages.
- Whether the assembled context contained sufficient information.
- Why the generation attempt ended in `model_abstain`.

Do not infer answer correctness from ranking metrics.

Do not invent a generator evaluation or rerun OpenRouter queries without separate authorization.

If answer-quality evaluation is unavailable, record it as an open limitation.

## 7. Phase E — Quality–latency frontier

Combine eligible quality measurements and valid timing observations.

Identify nondominated configurations: alternatives for which no other measured option provides equal or better quality at lower cost.

Where measurements come from different machines, corpora or configurations, present separate frontiers. Never aggregate incompatible populations.

Use an explicitly defined quality decision policy; do not choose thresholds after seeing results solely to justify an optimization.

If a candidate improves speed but violates the relevant parity or quality gate, report the failure and retain its observations.

Include sensitivity analysis for query category, passage length, candidate count, and CPU resources wherever supported.

Do not recommend promotion based solely on the original Recipes example.

## 8. Research reporting — mandatory deliverables

Produce a polished Markdown report suitable for publication, with professionally generated figures and tables.

Suggested canonical report:

`docs/research/bge_quality_latency_frontier/REPORT.md`

Place machine-readable observations, figures, methodology, provenance, and research scripts under the same dedicated research directory or an appropriate existing evidence path.

Avoid unrelated repository changes.

The report must follow this narrative:

### Chapter 1 — The 59-second question

Introduce the real user-visible failure, the unexpectedly slow response, and why a 603-passage corpus initially seemed an unlikely source of trouble.

### Chapter 2 — Following the evidence

Present the latency breakdown and the successive elimination of candidate causes.

Explain the cold/warm diagnostics, dense retrieval behavior, BGE forward-pass dominance, CPU-thread comparison, and ONNX FP32 experiment.

Retain negative experimental findings.

### Chapter 3 — Reframing the problem

Explain the distinction between corpus search cost and cross-encoder inference cost.

Introduce candidate-depth reduction and length-aware batching as competing or complementary efficiency mechanisms.

### Chapter 4 — Experimental methodology

Explain hypotheses, datasets, population provenance, evaluation metrics, hardware, controls, pairing, statistical procedures, parity gates, and limitations.

Make independent reproduction feasible.

### Chapter 5 — Experimental results

Present factual observations, clearly separated from estimates.

Use tables and meaningful visualizations. At minimum, plan for:

- Retrieval latency breakdown.
- CPU backend experiment comparison.
- Batch-length distribution and padding visualization.
- Candidate depth versus retrieval quality.
- Batch strategy versus measured forward latency.
- Quality–latency Pareto frontier.

Only render charts with measured data where the title implies measured results. Label theoretical projections explicitly.

### Chapter 6 — What the model earns

Explain the incremental relevance contributed by BGE at different candidate depths.

Discuss cases in which reranking helps, hurts, or makes no measurable difference.

Include concrete query examples only when supported by recorded evidence and permitted by source-content handling rules.

### Chapter 7 — Engineering implications

Discuss CPU resource budgets, Docker constraints, concurrency, memory, candidate-selection policy, reproducibility and deployment portability.

Clearly distinguish measured behavior from future architectural proposals.

### Chapter 8 — Conclusion and next decisions

Answer the original research questions.

Provide a concrete engineering recommendation, remaining scientific risks, production-qualification requirements, and the next controlled experiment if necessary.

Include an executive summary written only after analyzing the actual results.

## 9. Reporting quality standards

The report should read like an engineering research paper and a compelling case study, not a chronological dump of Codex commands.

Require:

- Clear scientific terminology.
- Strong opening problem statement.
- Explicit transitions between hypotheses and discoveries.
- Clear explanations of why unsuccessful experiments matter.
- Figure and table captions with units and populations.
- Reproducible equations or plain-language metric definitions.
- Primary references for relevant external methods.
- Exact artifact and execution provenance.
- Honest uncertainty and methodological limitations.
- Consistent formatting and professional visual design.

Do not exaggerate speedups or claim production readiness.

Do not present a single diagnostic observation as a statistically representative benchmark.

Avoid presenting the study as proof that neural reranking is unnecessary unless relevance evidence actually establishes that conclusion.

## 10. Research integrity and evidence

Save:

- Full authorization prompt.
- Codex implementation and execution responses.
- Pre-registered experimental plan.
- Exact executing commit SHA.
- Parent and branch identity.
- Dataset and snapshot identities.
- Model/checkpoint identities.
- Hardware and thread settings.
- Raw observations and deterministic aggregation methods.
- Test results.
- Figures and report-generation source.
- Explicit exclusions, missing data, and failed experiments.

Use separate evidence directories for design, exploratory work and executed measurements.

Preserve previously accepted artifacts unchanged.

Do not expose private source texts, credentials or sensitive production paths in a public-facing report.

## 11. Execution boundaries

Authorized:

- Repository and evidence inventory.
- Read-only analysis of existing accepted results.
- Deterministic candidate-depth replay using available data.
- Local research-only scripts, tests and report generation.
- Bounded offline performance experiments if necessary local models and inputs are already available.
- Creating a research branch and committing research artifacts.
- Producing a draft report with clearly labeled pending results.

Not authorized:

- Modifying production retrieval defaults.
- Replacing BGE or Qwen3.
- Altering frozen Slice 9 or Slice 14 results.
- New model downloads.
- New VM maintenance or inference campaigns.
- New OpenRouter generation calls.
- Deployments or promotion to main.
- Changing scientific acceptance rules.

If missing data makes a valid comparison impossible, report the limitation rather than improvising an incompatible evaluation.

## 12. Final response

Return:

1. Research branch and commit SHA.
2. Inventory of usable historical evidence.
3. Experiments completed versus blocked.
4. Initial quantitative findings.
5. Links to the full research report, figures, and reproducibility artifacts.
6. Independent-review issues and limitations.
7. Exact proposed next execution, if further measurements require authorization.

The report is a mandatory deliverable, even if some experiments remain pending. Present it as an interim research report until the evidence supports final conclusions.

Retain the complete authorization and response as research evidence.

Stop before production integration or promotion.