# Evaluation Directory

- `datasets/` — gold / fixture datasets
  - `dense_smoke/` — legacy-compatible smoke placeholder (`schema_version: 1` + `relevant_chunk_ids`)
  - `slice9_validation/` — small native GoldDataset v1 harness fixture (not an `ics_modules` gold set)
- `baselines/` — frozen baseline metric artifacts (future)
- `results/` — machine-readable retrieval-eval results by method subdirectory
- `reports/` — generated human-readable comparisons (optional / future)

## Retrieval eval (Slice 9)

```bash
offline-rag eval retrieve --method dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context \
  --dataset eval/datasets/<name> --corpus <name> [--top-k N] [--json]

offline-rag eval compare --a <result-a.json> --b <result-b.json> [--json]
```

`eval compare` consumes two `offline-rag-retrieval-eval-result-v1` artifacts and never reruns retrieval.

## GoldDataset v1 layout

```text
<meta.json>     # schema_version: offline-rag-gold-v1, chunk_set_id, optional corpus identity / dataset_id
<cases.jsonl>   # native judgments[] cases (new datasets must not write relevant_chunk_ids)
```

Native case fields: `id`, `query`, optional `category` / `tags[]`, and `judgments[]` of `{chunk_id, relevance}` where relevance is `1` or `2`.

Legacy `schema_version: 1` + `relevant_chunk_ids[]` remains read-compatible and normalizes each positive to relevance `1`.

Primary quality identity is child `chunk_id` bound to `chunk_set_id`. Context eval scores anchor child chunks, not EvidenceUnit IDs.

## Metrics and artifacts

Canonical cutoffs `k ∈ {1,5,10}` for Recall / Precision / HitRate / nDCG, plus MRR and conditional HitRate@30 when requested depth ≥ 30.

Results use `offline-rag-retrieval-eval-result-v1` (shared envelope + method diagnostics). Comparisons use `offline-rag-retrieval-eval-comparison-v1`.

`offline-rag eval query` remains Slice 8 operational generation evaluation and is separate from Slice 9 retrieval-quality metrics.

Do not commit private/proprietary evaluation data to a public repository.
