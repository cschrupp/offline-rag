# Slice 9H-P — Pilot Retrieval A/B Results

```text
PILOT / NON-PROMOTIONAL
```

**Status:** executed measure-once pilot; **does not** authorize retrieval promotion,
`base.yaml` changes, or completion of 9G / formal 9H.

Contract: [`slice9h_p_pilot_contract.md`](slice9h_p_pilot_contract.md)  
Execution plan: [`slice9h_p_execution_plan.md`](slice9h_p_execution_plan.md)  
Plan commit: `9509c81d78707609942f5d6ffbaa11e5c9ab234c`

Local artifacts (gitignored): `eval/results/9h_p/`

---

## 1. Experiment identity / provenance

```text
corpus: ics_modules
authoring_run_id: authorrun_b28d88f64054491a837cb4a144cbe056
chunk_set_id: chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2
gold_dataset_id: gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172
GoldCases: 22
requested depth: --top-k 30 (HitRate@30 diagnostic)
retrieval executions: 6 (full-22 only; human-16 post-hoc)
```

### Historical artifacts (9C preflight)

```text
baseline dense index_id:
  denseindex_80f7da5c50c6de0a00502e169c75198af3f7f2f48d56dcae8ca961d3e42710e9
Arm H dense index_id:
  denseindex_61c8c1bcde14d4e9e366e15e578b886f5889d183d2ee2e98c8a7863403bd5bfd
lexical index_id:
  lexical_9c43385ecf20cacbbe31e1243d37afca3ce88520e30be39f1aa2017a2bb1c337
corpus_id:
  corpus_040e49a1d261dba4e853939b36348dc40109551d6fdb49b38c7a9d896409eadb
```

### CURRENT dense state

```text
pre-execution CURRENT:
  denseindex_80f7da5c50c6de0a00502e169c75198af3f7f2f48d56dcae8ca961d3e42710e9
  (= historical baseline; index no_op verification)

baseline activation for A/B/C/E/F: verified (already CURRENT / no_op)

Arm H activation for D:
  offline-rag index --config base + dense_no_heading_peers
  reused_published_collection=true
  CURRENT == historical Arm H index_id
  source_chunk_set_id unchanged

post-D restoration:
  offline-rag index --config base
  restored CURRENT == original baseline index_id
  manifest + source_chunk_set_id match pre-execution capture
```

### Six raw runs (exit 0)

| Arm | method | run_id | index / notes |
|---|---|---|---|
| A dense-baseline | dense | `evalretrieve_bdfbae63759441099f4cf0b885a187c8` | baseline + `raw-query-v1` |
| B lexical-baseline | lexical | `evallexretrieve_15a6a43a56614678b1e793a790752714` | plain lexical |
| C dense-query-prompt | dense | `evalretrieve_8fab061d210d4a3588029c5e062a0cf4` | **same** baseline index + `model-query-prompt-v1` |
| D dense-arm-h | dense | `evalretrieve_457462a9a4c746cab66bd73b8af4444c` | Arm H index + `model-query-prompt-v1` |
| E hybrid-rrf | hybrid | `evalhybretrieve_d15a9564963247cf8c514faf7aaaf0d4` | baseline dense + plain lexical |
| F hybrid-rerank | hybrid-rerank | `evalhybrerank_770241211814412fbf8e28c28d5e3635` | same hybrid inputs as E + reranker; `input_k=30` |

Provenance checks: A/C share baseline dense index; E/F use baseline dense (not Arm H); D uses Arm H; all `population.total_cases=executed_cases=22`; depth 30; zero case errors.

Dense compares (same method only):

```text
compare_A_C_dense_full22.json
compare_A_D_dense_full22.json
compare_C_D_dense_full22.json
```

Analysis: `eval/results/9h_p/9hp_analysis.json` (local).

---

## 2. Six-arm aggregates — full-22

| Arm | nDCG@10 | Hit@1 | Hit@10 | Hit@30 | MRR | R@10 | P@10 | lat mean ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A dense-baseline | 0.7643 | 0.8636 | 1.0000 | 1.0000 | 0.9242 | 0.7232 | 0.3045 | 6847 |
| B lexical-baseline | 0.7062 | 0.7273 | 1.0000 | 1.0000 | 0.8220 | 0.7013 | 0.2682 | 149 |
| C dense-query-prompt | 0.8573 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.8243 | 0.3455 | 7138 |
| D dense-arm-h | **0.8596** | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.8224 | 0.3409 | 5060 |
| E hybrid-rrf | 0.7905 | 0.7727 | 1.0000 | 1.0000 | 0.8864 | 0.8070 | 0.3227 | 7023 |
| F hybrid-rerank | 0.8422 | 0.8636 | 1.0000 | 1.0000 | 0.9318 | 0.8136 | 0.3409 | 68771 |

nDCG@10 order (full-22): **D > C > F > E > A > B**

---

## 3. Six-arm aggregates — human-16

| Arm | nDCG@10 | Hit@1 | Hit@10 | Hit@30 | MRR | R@10 | P@10 | lat mean ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A dense-baseline | 0.7477 | 0.8125 | 1.0000 | 1.0000 | 0.8958 | 0.6808 | 0.3312 | 6932 |
| B lexical-baseline | 0.6641 | 0.6875 | 1.0000 | 1.0000 | 0.7865 | 0.6695 | 0.2812 | 146 |
| C dense-query-prompt | **0.8457** | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.7741 | 0.3688 | 7246 |
| D dense-arm-h | 0.8411 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.7715 | 0.3625 | 5104 |
| E hybrid-rrf | 0.7684 | 0.7500 | 1.0000 | 1.0000 | 0.8750 | 0.7628 | 0.3438 | 7057 |
| F hybrid-rerank | 0.8283 | 0.8125 | 1.0000 | 1.0000 | 0.9062 | 0.7905 | 0.3688 | 73255 |

nDCG@10 order (human-16): **C > D > F > E > A > B**

---

## 4. Full-22 vs human-16 sensitivity

Primary question:

```text
Does removal of the six assistant-only cases materially change
the comparative retrieval findings?
```

**Answer (descriptive, n small):** **Partially yes — mainly a C↔D top-rank swap.**

| Check | full-22 | human-16 | consistent? |
|---|---|---|---|
| nDCG@10 arm order | D > C > F > E > A > B | C > D > F > E > A > B | **No** (top two swap) |
| A→C nDCG@10 | C higher | C higher | Yes |
| A→D nDCG@10 | D higher | D higher | Yes |
| dense vs lexical (A vs B nDCG@10) | A > B | A > B | Yes |
| hybrid vs rerank (E vs F nDCG@10) | F > E | F > E | Yes |
| C vs D mean nDCG@10 delta | D slightly ahead (+0.002) | C slightly ahead (−0.005 for D) | **Sign flip (tiny)** |

Interpretation:

- Query-prompt (C) and Arm H (D) both **clearly beat** raw dense (A) on both cohorts (Hit@1 1.0; large nDCG gains on most cases).
- Whether **D outranks C** is **sensitive** to the six assistant-only labels: D leads on full-22; C leads on human-16. Absolute gaps are small (~0.002–0.005 nDCG@10).
- Lower-rank story (F > E > A > B) is stable.

This is evidence that assistant-only cases can tip a **close** C↔D comparison, not that the broad pilot story collapses.

---

## 5. Dense contract comparisons A / C / D

Paired nDCG@10 vs A (case counts: b better / a better / ties):

| Pair | full-22 | human-16 |
|---|---|---|
| A→C | 15 / 1 / 6 ; mean Δ +0.093 | 12 / 1 / 3 ; mean Δ +0.098 |
| A→D | 14 / 2 / 6 ; mean Δ +0.095 | 11 / 2 / 3 ; mean Δ +0.093 |
| C→D | 3 / 1 / 18 ; mean Δ +0.002 | 1 / 1 / 14 ; mean Δ −0.005 |

Notable per-case facts:

- Largest shared A→C / A→D gains include Module 4 resource-allocation case `…d2bcb5dd` (Δ ≈ +0.33) and Module 3 `…3897fcb3` (Δ ≈ +0.27).
- Persistent A→D regression: Module 3 roof-decking case `…323f3367` (Δ ≈ −0.077 vs A; also the main C→D regression ≈ −0.092).
- C and D are **nearly tied** on most cases (18/22 ties on full-22).

**Pilot fact (not promotion):** on this frozen set, `model-query-prompt-v1` alone already recovers most of the dense gain; `exclude-heading-only-v1` (Arm H) adds little aggregate beyond C and can lose on individual Module 3 cases.

---

## 6. Cross-stage observations B / E / F

```text
Lexical (B): weakest nDCG/Hit@1; fastest (~0.15 s).
Hybrid RRF (E): above A on nDCG@10 / R@10; Hit@1 below A on both cohorts.
Hybrid-rerank (F): above E and A on nDCG@10; Hit@1 ≈ A; ~10× slower than dense (~69–73 s mean).
```

On this pilot, reranking improves ranking quality over RRF but does **not** dominate C/D dense query-prompt arms on nDCG@10, and latency is an order of magnitude higher.

---

## 7. Per-case / module / category findings

Module nDCG@10 (full-22) for leading dense arms:

| Module | n | A | C | D |
|---|---:|---:|---:|---:|
| Module 1 Incident Scene Decision Making SM | 1 | 0.423 | 0.634 | 0.634 |
| Module 2 Safety Management SM | 4 | 0.795 | 0.902 | 0.902 |
| Module 3 Preincident Preparation SM | 10 | 0.775 | 0.831 | 0.825 |
| Module 4 Resource Allocation SM | 6 | 0.835 | 0.941 | 0.944 |
| Module 7 Post Incident Analysis SM | 1 | 0.451 | 0.662 | 0.758 |

Category aggregates exist in the raw results / analysis JSON (many singleton categories). No single category overturns the cohort-level C/D story; Module 3 holds the clearest C↔D disagreement case (`…323f3367`).

---

## 8. Latency / diagnostics

```text
B lexical ~0.15 s mean
D Arm H dense ~5.1 s mean
A/C/E dense/hybrid ~6.8–7.2 s mean
F hybrid-rerank ~69–73 s mean
```

HitRate@10 and HitRate@30 are **1.0 for all six arms** on both cohorts at depth 30 — useful pool coverage, little discrimination at those cutoffs. Discrimination lives in nDCG / Hit@1 / MRR / Precision.

---

## 9. Limitations

```text
n=22 / n=16 are small pilot populations — descriptive only; no significance claims.
Hybrid-adjudicated gold: 6 assistant-only cases remain in full-22.
No held-out / 9G freeze; no tuning loop was run (measure-once).
Module 1 is a single finalized case by 9F accounting.
n=2 smoke metrics are superseded and not mixed into these tables.
Cross-method comparisons use the pilot postprocessor, not eval compare.
```

---

## 10. Observed facts

1. Six planned arms completed once; CURRENT restored to pre-pilot baseline.
2. On both cohorts, C and D beat A on nDCG@10, Hit@1, and MRR.
3. C and D are nearly tied; **which leads depends on including assistant-only cases**.
4. F beats E on nDCG@10 on both cohorts, with large latency cost.
5. Lexical is the weakest quality arm and the fastest.
6. Hit@10/@30 saturate at 1.0 for all arms here.

---

## 11. Hypotheses for future 9G / formal 9H

```text
H1: model-query-prompt-v1 is the primary dense gain vs raw-query on ICS-like gold;
    exclude-heading-only-v1 is a secondary, case-sensitive add-on — validate on larger 9G.
H2: Close C↔D margins will remain label-sensitive; prefer human-reviewed or held-out
    cohorts before any Arm H promotion discussion.
H3: Hybrid-rerank may help mid-rank quality but is unlikely to justify default latency
    without a larger cost/quality study.
H4: Saturated Hit@10/@30 on this pool suggests future comparisons should emphasize
    nDCG / early precision and hard negatives, not hit@k alone.
```

**Explicit non-conclusions:**

```text
Do not change base.yaml.
Do not promote model-query-prompt-v1, exclude-heading-only-v1, or Arm H.
Do not remove the reranker.
Do not treat this pilot as formal 9H.
```

---

## Hard stop

9H-P execution and reporting complete. Next steps require **separate authorization**
(9G expansion, formal 9H, or another experiment ID). No second 9H-P run under this
claim without a new authorization.
