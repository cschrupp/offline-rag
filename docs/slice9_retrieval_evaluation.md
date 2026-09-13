# Slice 9 — Retrieval evaluation harness v1

Slice 9 makes retrieval quality evaluation a first-class subsystem:
GoldDataset v1, deterministic IR metrics with eligibility rules, a shared
result envelope across retrieve methods, and artifact-only comparison.

**Status:** implemented (commit `9073c37`).

Operational detail: [`eval/README.md`](../eval/README.md). Portfolio target
schema (broader than what shipped): [`EVALUATION_HARNESS.md`](../EVALUATION_HARNESS.md).

## Architecture

```text
GoldDataset v1 (meta.json + cases.jsonl)
        ↓
load_gold_dataset
        ↓
offline-rag eval retrieve --method …
        ↓
method runner (dense | lexical | hybrid | hybrid-rerank | hybrid-rerank-context)
        ↓
metrics @ k ∈ {1,5,10} (+ conditional HitRate@30)
        ↓
offline-rag-retrieval-eval-result-v1
        ↓
offline-rag eval compare  (no retrieval rerun)
        ↓
offline-rag-retrieval-eval-comparison-v1
```

Package: `src/offline_rag/evaluation/`

| Module | Role |
|---|---|
| `gold.py` | Load / validate GoldDataset v1 (+ legacy read-compat) |
| `metrics.py` | Per-case IR metrics + eligibility |
| `runner.py` | Method dispatch + aggregation |
| `result.py` | Shared result envelope |
| `compare.py` | Exact-float win/loss/tie on two result artifacts |
| `format.py` | Human-readable summaries |

## GoldDataset v1

Schema: `offline-rag-gold-v1`

```text
<meta.json>     # schema_version, chunk_set_id, optional corpus / dataset identity
<cases.jsonl>   # native judgments[] cases
```

Native case fields: `id`, `query`, optional `category` / `tags[]`, and
`judgments[]` of `{chunk_id, relevance}` where relevance is `1` or `2`.

Primary quality identity is child `chunk_id` bound to `chunk_set_id`.
Context / hybrid-rerank-context eval scores **anchor child chunks**, not
`EvidenceUnit` IDs.

Legacy `schema_version: 1` + `relevant_chunk_ids[]` remains read-compatible
(each positive → relevance `1`). Document-only legacy cases are
quality-ineligible.

Authoring drafts (`offline-rag-gold-authoring-v1`) are rejected by the gold
loader — silver ≠ gold.

Fixture: `eval/datasets/slice9_validation/` (harness proof only; not an
`ics_modules` production gold set).

## Metrics

Canonical cutoffs: `k ∈ {1,5,10}` for Recall / Precision / HitRate / nDCG,
plus MRR and conditional HitRate@30 when requested depth ≥ 30.

Binary relevance threshold for quality metrics: `grade >= 1`.

Zero-positive / quality-ineligible cases report quality metrics as `null`.
Macro-averages use quality-eligible queries only. Category aggregates are
retained when `category` is present.

## Result & comparison contracts

| Artifact | Schema |
|---|---|
| Retrieval eval result | `offline-rag-retrieval-eval-result-v1` |
| Comparison | `offline-rag-retrieval-eval-comparison-v1` |

Results carry a shared envelope plus method diagnostics (index IDs, fusion /
rerank / context hashes as applicable).

`eval compare` requires compatible artifacts and never reruns retrieval.
Win/loss/tie uses exact float comparison.

## CLI

```bash
offline-rag eval retrieve --method dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context \
  --dataset eval/datasets/<name> --corpus <name> [--top-k N] [--json]

offline-rag eval compare --a <result-a.json> --b <result-b.json> [--json]
```

## Boundaries

- Slice 8 `offline-rag eval query` stays operational generation outcomes only
  (answered / abstention / generation_failed / citation_invalid) — not answer
  correctness or faithfulness
- No semantic answer/citation quality metrics (Milestone 5 / Slice 10)
- No production `ics_modules` gold yet (Milestone 4 / 9A–9H)
- No promotion of experimental retrieval/generation contracts via this harness alone

## Next

Milestone 4 uses this harness on human-adjudicated private gold.
Slice **9A** (authoring boundary) done — [`slice9a_gold_authoring.md`](slice9a_gold_authoring.md).
Slice **9B** (`gold propose`) done — [`slice9b_gold_propose.md`](slice9b_gold_propose.md).
Next decision track: **9C**.
