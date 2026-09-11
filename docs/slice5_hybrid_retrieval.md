# Slice 5 — Hybrid Retrieval (RRF)

Slice 5 adds **query-time** hybrid retrieval: CURRENT dense and lexical branches
fused with **rrf-v1**. There is no hybrid index, HybridState, or HybridManifest.

**Status:** implemented.

## Architecture

```text
active ChunkSet
      │
      ├── DenseRetriever(top_k=dense_top_k)
      │      ↓
      │   ranked child chunk_ids
      │
      └── LexicalRetriever(top_k=lexical_top_k)
             ↓
          ranked child chunk_ids
                │
                ▼
             rrf-v1
                │
                ▼
       truncate to output_top_k
```

Hybrid consumes already-published dense and lexical indexes. Branches run
**sequentially** (dense → lexical → RRF). Parallel execution is deferred.

## Readiness

Hybrid is READY only when:

1. ChunkState is CURRENT
2. Dense index is CURRENT
3. Lexical index is CURRENT
4. Dense and lexical `source_chunk_set_id` match
5. Both equal active `ChunkState.current_chunk_set_id`
6. Effective `fusion:` config validates (`method=rrf`, `contract_version=rrf-v1`, positive depths)

If either branch is missing, stale, corrupt, or config-incompatible, hybrid
**fails**. There is no silent dense-only / lexical-only fallback labeled hybrid.

### Valid empty vs unavailable

| Situation | Behavior |
|---|---|
| CURRENT retriever, zero matches | Valid fusion input (contributes nothing) |
| Missing / stale / failed retriever | Hybrid failure |

## Candidate identity

Universal identity remains `chunk_id` (shared with dense, lexical, gold, future
rerank/expansion). Parents stay out of the candidate pool.

## rrf-v1

Exact score for document `d`:

```text
RRF(d) = Σ 1 / (rrf_k + rank_r(d))
```

Defaults: `rrf_k = 60`. Sum only over branches that returned `d`. Ranks are
**1-based**. No branch weights. No synthetic deep rank for absent candidates.

Final ordering:

1. RRF score descending
2. `chunk_id` ascending

Within a branch, duplicate `chunk_id` values never double-contribute (best/lowest
rank is kept).

Canonical hybrid `score` is the RRF score. Raw dense cosine / BM25 scores are
diagnostic provenance only and are not normalized or combined.

## Branch depths vs final top_k

Canonical baseline:

```yaml
fusion:
  method: rrf
  contract_version: rrf-v1
  rrf_k: 60
  dense_top_k: 30
  lexical_top_k: 30
  output_top_k: 10
```

Branches always fetch `dense_top_k` / `lexical_top_k` independently of final
`output_top_k`. CLI `--top-k` overrides only the final truncation.

```text
dense 30 ─────┐
              ├── RRF ──► truncate final 10
lexical 30 ───┘
```

## fusion_config_hash

Hashed (`fuscfg_…`):

- method, contract (`rrf-v1`), `rrf_k`
- dense/lexical fetch depths
- equal branch weighting, present-only missing policy
- 1-based ranks, `chunk_id` ascending tie-break

**Not** hashed: `output_top_k`, corpus name, query, index IDs, timestamps,
latency, output format. Index IDs are recorded as provenance separately.

## Package

```text
src/offline_rag/hybrid/
├── config_hash.py
├── fusion.py          # ReciprocalRankFusion
├── retrieve.py        # HybridRetriever
├── status.py          # derived READY / NOT_READY
└── evaluate.py        # HybridRetrievalEvaluator (shared metrics)
```

`HybridRetriever` does not touch Qdrant, SentenceTransformers, postings, or BM25
internals — it only composes project-owned dense/lexical retrievers + RRF.

## Result provenance

`HybridCandidate` / `HybridRetrievalResult` retain:

- final hybrid rank, RRF score, `chunk_id`
- dense rank/score or null; lexical rank/score or null
- corpus / chunk_set / dense index / lexical index IDs
- `fusion_config_hash`, requested final top_k
- latency: dense, lexical, fusion, total (sequential wall clock)

## CLI

```bash
offline-rag retrieve hybrid --corpus <name> --query "..." [--top-k N] [--json]
offline-rag eval retrieve --method hybrid --dataset <path> --corpus <name>
```

Unchanged:

```text
offline-rag retrieve              = dense
offline-rag retrieve lexical      = lexical
offline-rag retrieve hybrid       = hybrid
```

## Evaluation

Same gold dataset, `chunk_set_id` binding, Recall@1/5/10, and MRR helpers as
dense/lexical. Persisted hybrid reports include fusion hash, both index IDs,
branch depths, and per-case outcomes.

## Doctor

Hybrid status is **derived only** (no HybridState file):

```text
Chunking status                 CURRENT
Indexing status                 CURRENT
Lexical indexing status         CURRENT
Hybrid status                   READY
```

or `NOT_READY` when any dependency fails.

## Latency

Recorded fields: dense branch, lexical branch, RRF, total. No hypothetical
parallel latency.

## Out of scope (Slice 5)

- Hybrid index / state / manifest
- Parallel branch execution
- Weighted RRF, score normalization, learned fusion
- Reranking / cross-encoders (Slice 6; see `docs/slice6_cross_encoder_reranking.md`)
- Parent/neighbor expansion (Slice 7; see `docs/slice7_context_expansion.md`)
- Grounded generation (Slice 8; see `docs/slice8_grounded_generation.md`)
- Query rewriting, LangGraph
- Automatic branch fallback
- Retrieval mega-package refactor
- Artifact/index GC

## Ablation ladder

Dense → +BM25 → **+RRF (this slice)** → +reranker (Slice 6) → +expansion (Slice 7) → generation (Slice 8).
