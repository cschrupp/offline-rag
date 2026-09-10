# Evaluation Directory

- `datasets/` — gold / fixture datasets. Slice 3 includes `dense_smoke/` (placeholder meta + cases; bind real `chunk_set_id` after indexing a corpus).
- `baselines/` — frozen baseline metric artifacts (future).
- `results/` — machine-readable experiment results (`dense-retrieval/` for Slice 3).
- `reports/` — generated human-readable comparisons (future).

## Dense retrieval eval (Slice 3)

```bash
offline-rag eval retrieve --dataset eval/datasets/<name> --corpus <name> [--json]
```

Dataset directory shape:

```text
<meta.json>          # must include chunk_set_id (and optionally corpus_id)
<cases.jsonl>        # id, query, relevant_chunk_ids, ...
```

Primary metrics: chunk Recall@1/5/10, MRR, latency.

Do not commit private/proprietary evaluation data to a public repository.
