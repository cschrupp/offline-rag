# Slice 10E — Controlled Generation Prompt A/B

```text
DEVELOPMENT / NON-PROMOTIONAL
```

**Status:** measure-once development experiment complete. Does **not** authorize
promotion of `prompt-grounded-provenance-v2`, any `config/base.yaml` change, or
start of Milestone 6 / 9G / formal 9H.

Authoritative design: [`docs/slice10_generation_semantic_evaluation.md`](../slice10_generation_semantic_evaluation.md)

Local artifacts (gitignored): `eval/results/generation_semantic/10e/`

---

## 1. Experiment identity

```text
corpus_name:     ics_modules
corpus_id:       corpus_040e49a1d261dba4e853939b36348dc40109551d6fdb49b38c7a9d896409eadb
chunk_set_id:    chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2
authoring_run_id: authorrun_b28d88f64054491a837cb4a144cbe056
gold_dataset_id: gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172
```

Cohort map (local, gitignored): `offline-rag-generation-cohort-map-v1`

```text
source: eval/results/9h_p/9hp_analysis.json cohorts
        (cross-checked vs docs/pilots/slice9f_gold_provenance_audit.json,
         docs/pilots/slice9f_ics_modules.md, frozen GoldDataset)
accounting: 22 total / 16 human_reviewed / 6 assistant_only
```

Arms (exactly four live generation executions; exit 0 each):

| Arm | Evidence | Prompt | `run_id` |
|---|---|---|---|
| P-A | positive gold | `prompt-grounded-v1` | `genesem_bda9e6fbad284ca186518d69b6e4db9d` |
| P-B | same positive | `prompt-grounded-provenance-v2` | `genesem_2ced233dcbbc46d890e3d0e630ac2659` |
| N-A | human hard-negative | `prompt-grounded-v1` | `genesem_ae183add0e0b49d088bb98f82db6ba0b` |
| N-B | same negative | `prompt-grounded-provenance-v2` | `genesem_8dc42fa09ab84452ac3310ce640fec2b` |

Comparisons (artifact-only; no generation/judge/retrieval):

| Pair | `comparison_id` |
|---|---|
| Positive P-A vs P-B | `gencompare_f346c5e33981e7822b56d2f5fc92cbb2ab51233e9a2e49517c4b177c6ff0b0ec` |
| Negative N-A vs N-B | `gencompare_11b871e138e16be6692a7bc28e29b87b144e1bd6238d560cf9650ee6109245c8` |

Schema: `offline-rag-generation-semantic-eval-result-v1` /
`offline-rag-generation-semantic-eval-comparison-v1`

---

## 2. Generator configuration

```text
provider:           openai_compatible
adapter_contract:   openai-compatible-generator-v1
model:              qwen3.6-35b-a3b
endpoint:           http://192.168.2.142:8888/v1
temperature:        0.0
max_output_tokens:  1200
output_contract:    grounded-answer-v1
recovery_contract:  no-retry-v1
reasoning_contract: direct-output-v1
```

Config hashes:

```text
gencfg A (v1):  gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3
gencfg B (v2):  gencfg_38be5045b9f30257258289c34caafde270d0c84eedda7ef465848b29f2a4554a
```

Isolation proof: generation semantic payloads equal **except** `prompt_contract`
(`prompt-grounded-v1` vs `prompt-grounded-provenance-v2`). Overlay used for B:
`config/experiments/generation_provenance_prompt.yaml` (unchanged; changes only
`generation.prompt`). Runtime values came from a private local overlay — not
from editing `config/base.yaml`.

---

## 3. Judge configuration / self-judge limitation

```text
judge_enabled:              true (all four runs)
judgecfg:                   judgecfg_1a171d77f8e6a05e89de8ee8549ec26d1f00f7eb6cb01d52181224bb64258cca
provider:                   openai_compatible
endpoint:                   http://192.168.2.142:8888/v1
model:                      qwen3.6-35b-a3b
prompt_contract:            generation-semantic-judge-v1
output_contract:            generation-semantic-judge-output-v1
network_policy:             private_network
preflight:                  READY
same_model_self_judge:      true
same_endpoint_as_generator: true
```

**Limitation (prominent):** generator and judge used the **same model and
endpoint**. Independent judge preferred scientifically; not required for this
development experiment. Judge was arm-blind (no v1/v2/baseline/candidate
metadata in judge inputs). Judge contract identical across all four runs.

---

## 4. Positive evidence identity

```text
evidence_contract:  gold-evidence-v1
expected_behavior:  answer
evidence_set_id:    genevidence_f2d3857d68a77b45915ebf6930c89e62f650304e2234c923e352b3f5e2f59385
total_cases:        22
P-A evidence_set_id == P-B evidence_set_id  (verified)
```

---

## 5. Negative evidence identity

```text
evidence_contract:  human-grade0-hard-negative-v1
expected_behavior:  abstain
evidence_set_id:    genevidence_f3f013c42f08cc35034a8b8fa08ace89bdc1198bcf34e75ca0f02f077fbda91e
total_cases:        16 (human_reviewed only; assistant_only = 0)
N-A evidence_set_id == N-B evidence_set_id  (verified)
positive_id != negative_id                  (verified)
```

---

## 6. Four run IDs

See §1 table. Exit codes: **0 / 0 / 0 / 0**. No successful arm rerun.

---

## 7. Positive full-22 results

Population: answered 20/22 both arms; generation_failed 2/22 both arms
(same two cases); model_abstain 0; citation_invalid 0.

| Metric | v1 (A) | v2 (B) | Δ (B−A) | notes |
|---|---:|---:|---:|---|
| answer_rate | 0.909 (20/22) | 0.909 (20/22) | 0.000 | |
| false_abstention_rate | 0.000 (0) | 0.000 (0) | 0.000 | |
| generation_failed_rate | 0.091 (2/22) | 0.091 (2/22) | 0.000 | same cases |
| citation_invalid_rate | 0.000 | 0.000 | 0.000 | |
| mean_gold_citation_recall | 0.636 (n=20) | 0.596 (n=20) | −0.040 | mild v2 regression |
| grade2_citation_hit_rate | 0.944 (17/18) | 0.889 (16/18) | −0.056 | one additional miss on v2 |
| fully_correct_rate | 1.000 (20/20) | 1.000 (20/20) | 0.000 | judge denom |
| fully_supported_rate | 1.000 (20/20) | 1.000 (20/20) | 0.000 | |
| complete_answer_rate | 1.000 (20/20) | 1.000 (20/20) | 0.000 | |
| complete_citation_coverage_rate | 1.000 (20/20) | 1.000 (20/20) | 0.000 | |
| all_citations_useful_rate | 1.000 (20/20) | 1.000 (20/20) | 0.000 | |
| latency_mean_ms | 42471 | 37339 | −5132 | descriptive |
| judge success coverage | 20/20 eligible | 20/20 | 0 | no judge_failed |

Shared positive generation_failed cases (both arms):

- `draft_08f83eaef198495d92ff557eda974bf4`
- `draft_127ac342012d47fc9720a0c13a577550`

---

## 8. Positive human-reviewed sensitivity (n=16)

Derived from the **same** P-A / P-B artifacts (no separate 16-case run).

| Metric | v1 | v2 | Δ | notes |
|---|---:|---:|---:|---|
| answer_rate | 0.875 (14/16) | 0.875 (14/16) | 0.000 | |
| false_abstention_rate | 0.000 | 0.000 | 0.000 | |
| generation_failed_rate | 0.125 (2/16) | 0.125 (2/16) | 0.000 | |
| citation_invalid_rate | 0.000 | 0.000 | 0.000 | |
| mean_gold_citation_recall | 0.627 (n=14) | 0.588 (n=14) | −0.039 | same direction as full-22 |
| grade2_citation_hit_rate | 0.917 (11/12) | 0.833 (10/12) | −0.083 | same direction; larger magnitude |
| fully_correct / supported / complete / coverage / useful | 1.000 (14/14) | 1.000 (14/14) | 0.000 | ceiling both |
| latency_mean_ms | 43372 | 41212 | −2160 | |
| judge success | 14/14 | 14/14 | 0 | |

**22-vs-human sensitivity conclusion:** direction **stable**. Layer-2 semantic
rates remain ceiling-neutral on both populations. Layer-1 citation recall and
grade-2 hit show a mild v2 regression on both full-22 and human-16 (no direction
flip). Magnitude of the grade-2 delta is slightly larger on human-16. No
statistical-significance language applies (descriptive n=22 / n=16).

---

## 9. Assistant-only descriptive view (n=6)

Descriptive only — not a primary decision population.

| Metric | v1 | v2 | Δ |
|---|---:|---:|---:|
| answer_rate | 1.000 (6/6) | 1.000 (6/6) | 0.000 |
| mean_gold_citation_recall | 0.656 | 0.614 | −0.042 |
| grade2_citation_hit_rate | 1.000 (6/6) | 1.000 (6/6) | 0.000 |
| Layer-2 rates (all five) | 1.000 | 1.000 | 0.000 |
| latency_mean_ms | 40069 | 27012 | −13057 |

---

## 10. Positive paired semantic transitions

For cases with both arms `judge_status == succeeded` (20/22; 2 not_comparable
due to shared generation_failed):

| Dimension | improved | unchanged | regressed | not_comparable |
|---|---:|---:|---:|---:|
| answer_correctness | 0 | 20 | 0 | 2 |
| faithfulness | 0 | 20 | 0 | 2 |
| completeness | 0 | 20 | 0 | 2 |
| citation_coverage | 0 | 20 | 0 | 2 |
| citation_usefulness | 0 | 20 | 0 | 2 |

No composite score. Status transitions: all paired statuses identical
(including the two shared failures).

---

## 11. Citation behavior

Mean citation counts (answered cases): full-22 A 2.00 / B 1.85; human-16 A 2.07 /
B 1.93.

Paired gold-citation-recall changes (5 cases; 4 human_reviewed, 1 assistant_only):

| case_id | cohort | recall A→B | cites A→B | grade2 A→B |
|---|---|---|---|---|
| `draft_29389bdab2f84345b596e45fcf2e2bcc` | human_reviewed | 1.000→0.667 | 3→2 | T→T |
| `draft_54115e36a58442e0a1574bc8017248c9` | human_reviewed | 0.100→0.200 | 1→2 | n/a |
| `draft_94722ca912bd46ada6b9689f388d1b17` | human_reviewed | 0.333→0.222 | 3→2 | F→F |
| `draft_aad45b4a4bd940459793788e716aa580` | human_reviewed | 0.400→0.200 | 2→1 | T→F |
| `draft_959387c7d1fc48f0a7ac4b38166d1fb1` | assistant_only | 0.500→0.250 | 2→1 | T→T |

Net: provenance-v2 tended toward slightly fewer citations and slightly lower
gold citation recall under identical evidence. Judge Layer-2 citation dimensions
remained at ceiling for all judged answered cases.

---

## 12. Negative abstention results (human_reviewed n=16)

| Metric | v1 | v2 | Δ | counts |
|---|---:|---:|---:|---|
| correct_abstention_rate | 0.688 | 0.688 | 0.000 | 11/16 both |
| false_answer_rate | 0.312 | 0.312 | 0.000 | 5/16 both |
| generation_failed_rate | 0.000 | 0.000 | 0.000 | |
| citation_invalid_rate | 0.000 | 0.000 | 0.000 | |
| empty_context_rate | 0.000 | 0.000 | 0.000 | |
| latency_mean_ms | 27110 | 21388 | −5722 | descriptive |
| false_answers_judged | 5 | 5 | 0 | |
| false_answers_fully_supported | 5 | 5 | 0 | fixture-review |
| false_answers_fully_correct | 5 | 5 | 0 | fixture-review |

---

## 13. Negative per-case transitions

| Transition | count |
|---|---:|
| `correct_abstention → correct_abstention` | 11 |
| `false_answer → false_answer` | 5 |
| `correct_abstention → false_answer` | 0 |
| `false_answer → correct_abstention` | 0 |

No abstain↔answer flips between v1 and provenance-v2 under identical hard-negative
evidence.

---

## 14. Fixture-review signals

Judge remains blind to the negative contract. For all five stable false-answer
cases on **both** arms, the judge returned `fully_correct` and `fully_supported`.

False-answer case IDs (fixture-review signal = true; **not** an automatic label
correction):

- `draft_127ac342012d47fc9720a0c13a577550`
- `draft_4c185aa9607b42688627ef26323f3367`
- `draft_7df2ca731edf4daaa794ee20507205ca`
- `draft_a597e472c3e141c3bf4a5539d2bcb5dd`
- `draft_cc9a054620e040a5adee66a1f4dc3540`

Interpretation: hard-negative cases where the model answered and the self-judge
found the answer fully correct/supported relative to the (misleading) evidence.
These are **fixture-review diagnostics**, not grounds to modify Gold/Silver.

---

## 15. Latency

Across positive and negative pairs, mean latency was lower on provenance-v2 in
this single measure-once pass. Treat as descriptive only (same model, temp 0,
small n; no promotion implication).

---

## 16. Judge coverage

| Arm | eligible answered | judge_succeeded | judge_failed | judge_unavailable |
|---|---:|---:|---:|---:|
| P-A | 20 | 20 | 0 | 0 |
| P-B | 20 | 20 | 0 | 0 |
| N-A | 5 | 5 | 0 | 0 |
| N-B | 5 | 5 | 0 | 0 |

Semantic coverage complete for all eligible answered cases. Denominators above
are actual judged counts (missing judge cases would not be treated as failures
or successes).

---

## 17. Limitations

- Frozen 22-case / human-16 pilot is **not** publication-grade gold.
- `same_model_self_judge = true` and `same_endpoint_as_generator = true`.
- Ceiling effects on Layer-2 positive metrics (all 1.0) limit discrimination.
- Two shared positive `generation_failed` cases reduce judged n to 20/22.
- Descriptive n only; no significance claims; no corpus generalization.
- Hard-negative fixture is label-defined development machinery (Slice 10D).

---

## 18. Observed facts

1. Under identical positive gold evidence, provenance-v2 did **not** change
   Layer-2 semantic rates (already at ceiling for judged answers on v1).
2. Provenance-v2 did **not** change answer / false-abstention / failure rates
   on the positive fixture.
3. Provenance-v2 showed a **mild regression** in mean gold citation recall and
   grade-2 citation hit (full-22 and human-16; direction stable).
4. Under identical hard-negative evidence, abstention behavior was **identical**
   (11 correct abstentions, 5 stable false answers; no flips).
5. All five negative false answers were judged fully_correct + fully_supported
   on both arms (fixture-review signal).
6. Evidence isolation held: shared positive `genevidence_…f59385`; shared
   negative `genevidence_…bda91e`; IDs differ across contracts.
7. Generator isolation held: only `prompt_contract` differed; temperature 0.0;
   same model/endpoint/judgecfg across four runs.

---

## 19. Hypotheses

- On this small fixed-evidence pilot with a strong local model, provenance
  metadata may be largely redundant for answer correctness once gold evidence
  is already supplied (ceiling on Layer-2).
- Provenance-v2 may encourage slightly sparser citation sets, which can lower
  gold citation recall without moving judge citation-usefulness/coverage off
  ceiling.
- Hard-negative false answers that the self-judge marks fully supported may
  indicate evidence-text plausibility rather than prompt-contract differences
  (behavior identical across arms).

---

## 20. Explicit non-conclusions

- Does **not** conclude that provenance-v2 should (or should not) become the
  production default.
- Does **not** claim statistical significance or corpus-wide generalization.
- Does **not** authorize promotion, `base.yaml` edits, or Milestone 6 work.
- Does **not** resolve publication validation (9G / formal 9H remain deferred).
- Does **not** treat fixture-review signals as Gold/Silver corrections.

---

## Reproduction (local only)

Comparator (artifact-only):

```text
offline-rag eval generation-compare \
  --a eval/results/generation_semantic/10e/P_A_positive_v1.json \
  --b eval/results/generation_semantic/10e/P_B_positive_provenance_v2.json \
  --output eval/results/generation_semantic/10e/compare_positive_v1_vs_v2.json

offline-rag eval generation-compare \
  --a eval/results/generation_semantic/10e/N_A_negative_v1.json \
  --b eval/results/generation_semantic/10e/N_B_negative_provenance_v2.json \
  --output eval/results/generation_semantic/10e/compare_negative_v1_vs_v2.json
```

Raw generation artifacts remain private/gitignored.
