# Slice 9C — Multi-retriever candidate pooling

Slice 9C turns pending `SilverCase.proposed_query` values into deterministic,
high-recall retrieval candidate pools under `candidate-pooling-v1`, via
`offline-rag gold pool`. Retrieval-only: no LLM, no relevance grades, no 9D
prelabel/shuffle.

**Status:** implemented.

## Architecture

```text
offline-rag-gold-authoring-v1
        ↓
pending SilverCase.proposed_query
        ↓
candidate-pooling-v1 six-arm ensemble
        ↓
historically compatible retrieval artifacts only
        ↓
union / dedupe by chunk_id
        ↓
deterministic pool inspection order
        ↓
candidate provenance (no body text)
        ↓
enriched offline-rag-gold-authoring-v1
```

Package additions under `src/offline_rag/gold_authoring/`:

- `pool.py` — orchestrator
- `pool_preflight.py` — historical ChunkSet artifact graph
- `pool_arms.py` — six-arm historical executor
- `pool_union.py` — union + 9C-4 ordering
- `pooling_models.py` — hits / candidates / outcomes

## Ensemble (`candidate-pooling-v1`)

| Arm | Identity | Depth |
|---|---|---|
| Lexical | `lexical-plain-v1` | 50 |
| Dense baseline | `dense-plain-v1` (raw-query-v1) | 50 |
| Dense query-prompt | `dense-model-query-prompt-v1` | 50 |
| Arm H dense | `dense-arm-h-v1` (exclude-heading-only-v1 + query-prompt) | 50 |
| Hybrid RRF | `hybrid-rrf-v1` | 50 |
| Hybrid-rerank | `hybrid-rerank-v1` (reranked output) | 20 |

Experimental arms (`model-query-prompt-v1`, Arm H) remain **candidate generators only** — not production defaults.

## CLI

```bash
offline-rag gold pool \
  --run <authoring-run.json> \
  [--output <path>] \
  [--force]
```

- Default: atomic in-place enrichment of `--run` (same `authoring_run_id`)
- `--output`: write enriched copy; leave input unchanged
- `--force`: re-pool non-empty `candidates[]` and/or overwrite existing `--output`
- No `--top-k` / `--corpus` / retriever selection knobs

## Exit codes

| Code | Meaning |
|---|---|
| 2 | Could not validly start (preflight / no targets / force required / …); zero retrieval |
| 1 | Valid run completed; zero successful pools (diagnostics persisted) |
| 0 | ≥1 successful pool (partial success included) |

## Invariants

- Candidate identity = child `chunk_id`
- Exact historical `run.chunk_set_id` for all corpus-derived artifacts
- Complete six-arm success or no pool for that case
- No seed injection, neighborhood expansion, index builds, or CURRENT fallback
- No candidate body text in the authoring artifact
- Pool order = inspection order only (not 9D judging order)

## Next

Slice **9D** — relevance prelabel / blind judge presentation — done:
[`slice9d_relevance_prelabel.md`](slice9d_relevance_prelabel.md).

Slice **9E** — human review / GoldDataset finalization — done:
[`slice9e_human_review.md`](slice9e_human_review.md).

Next: Slice **9F** — 20-case authoring pilot.
