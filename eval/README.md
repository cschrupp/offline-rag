# Evaluation Directory

- `datasets/` — gold / fixture datasets
  - `dense_smoke/` — legacy-compatible smoke placeholder (`schema_version: 1` + `relevant_chunk_ids`)
  - `slice9_validation/` — small native GoldDataset v1 harness fixture (not an `ics_modules` gold set)
  - future production gold (e.g. `ics_modules_v1/`) — created via Milestone 4 `offline-rag gold …` finalization; do not commit private proprietary labels to a public remote
- `baselines/` — frozen baseline metric artifacts (future)
- `results/` — machine-readable retrieval-eval results by method subdirectory
- `reports/` — generated human-readable comparisons (optional / future)
- authoring drafts / silver runs — local data under `<corpus>/gold_authoring/runs/` from `offline-rag gold propose` (Slice 9B+); schema `offline-rag-gold-authoring-v1` is **not** gold and is rejected by `eval retrieve`

## Retrieval eval (Slice 9)

Authoritative notes: [`docs/slice9_retrieval_evaluation.md`](../docs/slice9_retrieval_evaluation.md).

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

## Offline gold authoring (Milestone 4)

Canonical plan: [`docs/milestone4_offline_gold_authoring.md`](../docs/milestone4_offline_gold_authoring.md). Slice **9A** notes: [`docs/slice9a_gold_authoring.md`](../docs/slice9a_gold_authoring.md).

Next decision track: **Slice 9D** (relevance prelabel / blind judging prep).

Target CLI (surface continues through 9D+):

```bash
offline-rag gold propose|pool|prelabel|review|finalize|status
```

`gold propose` is implemented (Slice 9B). See [`docs/slice9b_gold_propose.md`](../docs/slice9b_gold_propose.md).
`gold pool` is implemented (Slice 9C). See [`docs/slice9c_candidate_pooling.md`](../docs/slice9c_candidate_pooling.md).
Silver/authoring artifacts (`offline-rag-gold-authoring-v1`) are distinct from GoldDataset v1. Only human-finalized cases are exported to gold. Local LLM labels never become gold automatically. Authoring must not reuse Slice 8 production generation prompt contracts.

Do not commit private/proprietary evaluation data to a public repository.
