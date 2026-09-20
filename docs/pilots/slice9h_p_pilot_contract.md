# Slice 9H-P — Pilot Retrieval A/B Contract

**Status:** `COMPLETE / NON-PROMOTIONAL`

Executed measure-once pilot. Results: [`slice9h_p_results.md`](slice9h_p_results.md).
Does **not** authorize retrieval promotion or completion of 9G / formal 9H.

---

## Positioning

9H-P is a pilot evaluation detour after 9F GO.

9G remains deferred to publication readiness (not completed).

Formal 9H remains downstream of 9G and retains responsibility for any
production retrieval-contract promotion decision.

9H-P may generate evidence and hypotheses only.

It does **not** replace, complete, or silently skip:

```text
9G — Production Retrieval Gold Set
9H — Formal Retrieval Candidate Evaluation & Promotion Decision
```

Canonical production order remains:

```text
9F → 9G → 9H
```

---

## Frozen benchmark identity

```text
corpus_name:
    ics_modules

authoring_run_id:
    authorrun_b28d88f64054491a837cb4a144cbe056

chunk_set_id:
    chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2

GoldDataset:
    gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172

total GoldCases:
    22
```

GoldDataset and chunkset must remain byte/identity stable throughout 9H-P.
Do not mutate, refinalize, or retarget gold for this pilot.

Provenance reference: [`slice9f_ics_modules.md`](slice9f_ics_modules.md),
[`slice9f_gold_provenance_audit.json`](slice9f_gold_provenance_audit.json).

---

## Cohorts

Evaluate two deterministic cohorts from the **same** frozen GoldDataset.

### Full cohort — `full-22`

All 22 GoldCases.

### Human-reviewed sensitivity cohort — `human-16`

Exact finalized case ordinals:

```text
1
3
8
9
11
13
15
17
19
20
21
23
29
31
33
34
```

Exclude the assistant-only finalized cases:

```text
2
22
26
27
30
32
```

`human-16` is a **sensitivity analysis**, not a second GoldDataset and not a new
semantic gold identity. Do not mutate or refinalize gold merely to form the
cohort. Implement at evaluation/reporting time by deterministic case-ID
selection from the same frozen GoldDataset.

---

## Retrieval arms

Lock exactly six conceptual arms:

```text
A. dense-baseline
B. lexical-baseline
C. dense-model-query-prompt
D. dense-arm-h
E. hybrid-rrf
F. hybrid-rerank
```

Definitions:

```text
dense-baseline:
    existing dense baseline contracts / current historical baseline

lexical-baseline:
    existing lexical plain-v1 baseline

dense-model-query-prompt:
    existing dense retrieval with model-query-prompt-v1
    no heading exclusion

dense-arm-h:
    existing model-query-prompt-v1
    +
    exclude-heading-only-v1

hybrid-rrf:
    existing hybrid RRF retrieval contract

hybrid-rerank:
    existing hybrid + reranker contract
```

`dense-model-query-prompt` and `dense-arm-h` are configuration/contract
compositions using already-existing overlays/contracts.

Do **not** implement new public `--method` values merely to name these arms.
Public evaluation methods remain the existing methods
(`dense` | `lexical` | `hybrid` | `hybrid-rerank` | …). Exact overlay
composition/commands must be resolved from current repo contracts **before
execution** (separate authorization).

No retrieval algorithm changes are authorized.

---

## Metrics

Use only existing Slice 9 retrieval metrics:

```text
Recall@1
Recall@5
Recall@10

Precision@1
Precision@5
Precision@10

HitRate@1
HitRate@5
HitRate@10

nDCG@1
nDCG@5
nDCG@10

MRR

conditional HitRate@30
```

Also retain already-supported:

```text
latency/timing
method diagnostics
category aggregates
retriever/reranker diagnostics where applicable
```

Do not invent a composite score.
Do not introduce new promotion thresholds in 9H-P.

---

## Required analysis

For every arm, evaluate both:

```text
full-22
human-16
```

Primary sensitivity question:

```text
Does the comparative retrieval conclusion remain materially consistent
when the six assistant-only cases are removed?
```

Produce:

```text
aggregate metrics by arm/cohort
paired per-case comparison
module/document breakdown
category breakdown where supported
latency/diagnostic comparison
22-vs-16 sensitivity analysis
```

The per-case analysis must preserve case identity so we can identify:

```text
wins
losses
ties
large regressions
large gains
```

Do not reduce the experiment to aggregate means alone.

---

## Experimental discipline

9H-P is a **measure-once comparison pass**, not an optimization loop.

Forbidden during execution:

```text
parameter tuning based on results
query-contract modification
embedding-contract modification
heading policy modification
RRF tuning
reranker tuning
top-k search/tuning beyond locked existing contracts
base.yaml edits
retrieval algorithm changes
gold changes
relabeling cases because retrieval disagrees
```

If an arm performs poorly, record it.
Do not fix it and rerun under the same 9H-P experiment claim.

Any later corrected experiment requires an explicit new authorization and must
remain distinguishable from the original run.

---

## Promotion boundary

**9H-P CANNOT promote a retrieval contract to production/default.**

It may produce findings such as:

```text
candidate X improved nDCG/Recall on this pilot
candidate X regressed specific categories
full-22 and human-16 tell the same/different story
reranking added/did not add value on this pilot
```

It may **not** conclude:

```text
change base.yaml
replace the dense default
promote model-query-prompt-v1
promote exclude-heading-only-v1
promote Arm H
remove the reranker
```

Those remain formal 9H architectural decisions after a larger 9G benchmark or
another explicitly authorized decision process.

---

## Relationship to the n=2 smoke

The old 2-case evaluation remains:

```text
pipeline smoke only
superseded as a benchmark
not a promotion signal
```

Do not combine its metrics statistically with 9H-P.

---

## Output contract for later execution

When execution is separately authorized, require:

```text
serialized Slice 9 eval-result artifacts for every arm
comparison artifacts using existing eval compare where applicable
pilot report:
    docs/pilots/slice9h_p_results.md
```

The report must clearly label:

```text
PILOT / NON-PROMOTIONAL
```

Hard-stop after artifacts + report.

Do not start 9G, formal 9H promotion, or Slice 10 automatically.
