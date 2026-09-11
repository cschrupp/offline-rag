# Slice 6 — Cross-encoder reranking

Slice 6 adds **query-time** second-stage reranking over a **hybrid-only**
candidate pool. There is no HybridRerankState, no dense/lexical-direct rerank
path, and no silent fallback to hybrid-only labeled as hybrid-rerank.

**Status:** implemented.

## Architecture

```text
HybridRetriever(top_k=input_k)
        │
        ▼
   hybrid pool (≤ input_k)
        │
        ▼
   plain-pair-v1 pairs
        │
        ▼
   CrossEncoder / FakeReranker
        │
        ▼
   raw-logit-v1 sort
   (score DESC, chunk_id ASC)
        │
        ▼
   truncate to output_k
```

Candidate source is always `HybridRetriever`. Dense-only or lexical-only pools
are out of scope for this method name.

## Depths

Canonical baseline:

```yaml
reranker:
  input_k: 30
  output_k: 10
```

Hybrid always fetches `input_k`. CLI `--top-k` overrides only final truncation
(`output_k`). `top_k > input_k` fails hard.

```text
hybrid 30 ──► score ──► truncate final 10
```

## Model identity

Production default:

| Field | Value |
|---|---|
| Model | `BAAI/bge-reranker-v2-m3` |
| Pinned revision | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |
| Adapter | `sentence-transformers-cross-encoder-v1` |
| Load | `local_files_only=true`, `trust_remote_code=false` |

Provision once: `offline-rag provision reranker`. Runtime never downloads.

## Contracts

| Contract | Role |
|---|---|
| `plain-pair-v1` | Query strip; passage text as stored (no further strip/normalize). Empty query or blank passage fails. |
| `seq-trunc-1024-passage-right-v1` | Tokenizer `max_length=1024`, truncation=`only_second` (passage side). |
| `raw-logit-v1` | Canonical score = raw relevance logit (no sigmoid / temperature). |
| `chunk-id-asc-v1` | Exact score ties → `chunk_id` ascending. |

Universal identity remains `chunk_id`.

## FakeReranker (`fake-rerank-digest-v1`)

CI/architecture only — never an automatic production fallback.

```text
score = (uint64(SHA256(query + 0x00 + passage)[:8]) / 2^64) * 20 − 10
```

Range `[-10, 10)`. Optional `score_map[(query, chunk_id)]` overrides for tests.
Identical digests tie-break with `chunk-id-asc-v1`.

## Readiness

Hybrid-rerank is READY only when:

1. Hybrid status is READY (dense+lexical CURRENT, same chunk set, fusion config OK)
2. `reranker.enabled` is true
3. Ranking contracts validate (`plain-pair-v1`, seq-trunc + max_length, raw-logit, tie-break, local-only)
4. Implementation is `fake` **or** local reranker artifacts are READY

Otherwise status is `NOT_READY` and retrieve fails. Disabled reranker is
`NOT_READY` / retrieve error — not a silent hybrid-only path.

## reranker_config_hash

Hashed (`rrkcfg_…`):

- model_id, revision, adapter_contract
- `input_k`
- input_construction, sequence_contract, max_length
- score_transform, tie_break

**Not** hashed: `output_k`, device, batch_size, paths, corpus/query, latency,
timestamps, output format. Index IDs and fusion hash remain separate provenance.

## Package

```text
src/offline_rag/rerank/
├── protocol.py        # RerankerPair / Reranker
├── input_builder.py   # plain-pair-v1
├── fake.py            # FakeReranker
├── cross_encoder.py   # CrossEncoderReranker
├── provision.py       # local BGE provision / validate
├── config_hash.py
├── status.py          # derived READY / NOT_READY
├── retrieve.py        # HybridRerankRetriever
└── evaluate.py        # HybridRerankRetrievalEvaluator
```

## Result provenance

`HybridRerankCandidate` retains:

- final rerank rank + raw logit score
- hybrid rank, RRF score, dense/lexical ranks & scores (or null)
- corpus / chunk_set / dense / lexical IDs
- `fusion_config_hash`, `reranker_config_hash`
- `input_k`, `input_pool_size`, `input_pool_chunk_ids`, `output_k`

## Latency hierarchy

Recorded wall-clock fields:

```text
latency_ms:
  hybrid              # HybridRetriever call
  pair_build
  rerank_infer
  sort
  total
  hybrid_breakdown:   # nested dense / lexical / fusion from hybrid
```

No hypothetical parallel hybrid+rerank latency.

## CLI taxonomy

```bash
offline-rag provision reranker
offline-rag retrieve hybrid-rerank --corpus <name> --query "..." [--top-k N] [--json]
offline-rag eval retrieve --method hybrid-rerank --dataset <path> --corpus <name>
```

Unchanged methods:

```text
offline-rag retrieve              = dense
offline-rag retrieve lexical      = lexical
offline-rag retrieve hybrid       = hybrid (no rerank)
offline-rag retrieve hybrid-rerank = hybrid pool + cross-encoder
```

## Evaluation

Same gold dataset and Recall@1/5/10 / MRR helpers as dense/lexical/hybrid.
Persisted under `eval_results/hybrid-rerank-retrieval/`.

### `gold_in_rerank_pool`

Per-case diagnostic: whether any gold `chunk_id` appeared in the **hybrid
input pool** (before final truncation). Separates generation miss (gold never
in top-`input_k` hybrid) from ranking miss (gold in pool but not promoted into
final top-k). Also records `input_pool_size`.

## Doctor

Three readiness lines (plus artifact/model detail):

```text
Hybrid status                   READY
Reranker artifacts              READY
Hybrid-rerank status            READY
```

`Hybrid-rerank status` is derived only (no HybridRerankState file).

## Out of scope (Slice 6)

- Dense-only / lexical-only / multi-source rerank pools
- Sigmoid / calibrated scores; learned fusion before rerank
- Parent/neighbor expansion (Slice 7 — see `docs/slice7_context_expansion.md`)
- Grounded generation (Slice 8 — see `docs/slice8_grounded_generation.md`)
- Query rewriting, LangGraph
- Automatic hybrid-only fallback when reranker disabled/absent
- HybridRerankState / persisted rerank index
- Artifact/index GC

## Ablation ladder

Dense → +BM25 → +RRF → +reranker → +expansion (Slice 7) → **generation (Slice 8)**.
