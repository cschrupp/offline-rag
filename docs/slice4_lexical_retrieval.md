# Slice 4 — Lexical (BM25) Retrieval Baseline

Slice 4 adds an independent lexical retrieval path over the same child chunks as
dense retrieval, with project-owned BM25 scoring and durable inverted indexes.

**Status:** implemented.

## Flow

```text
CorpusState → ChunkState → ChunkSetManifest → child Chunks
        ↓
LexicalTextBuilder (plain-v1) = Chunk.text exactly
        ↓
LexicalAnalyzer (technical-v1)
        ↓
LocalInvertedIndexBackend (local-inverted-index-v1)
        ↓
bm25-okapi-v1 scoring
        ↓
LexicalIndexManifest + LexicalIndexState
        ↓
LexicalRetriever / eval retrieve --method lexical
```

## Locked contracts

| Layer | Contract |
|---|---|
| Text | `plain-v1` |
| Analyzer | `technical-v1` (NFKC → casefold → technical tokenizer; no stopwords/stemming) |
| Scorer | `bm25-okapi-v1` (`k1=1.2`, `b=0.75`, positive-smoothed IDF) |
| Backend | `local-inverted-index-v1` |

IDF:

```text
ln(1 + (N - df + 0.5) / (df + 0.5))
```

Ranking: score DESC, then `chunk_id` ASC. Unique analyzed query terms only.

## Identity

`lexical_index_id` ← `chunk_set_id + lexical_config_hash + backend contract`

`top_k` is query-time only and is **not** part of `lexical_config_hash`.

## CLI

```bash
offline-rag index lexical --corpus <name>
offline-rag index lexical inspect --corpus <name> [--term|--chunk] [--json]
offline-rag retrieve lexical --corpus <name> --query "..."
offline-rag eval retrieve --method lexical --dataset <path> --corpus <name>
```

Bare `index` / `retrieve` / `eval retrieve` remain **dense**.

## Config

Top-level key is `lexical:` (not `sparse:`). Legacy `sparse:` fails with a migration message.

Default `lexical.top_k = 30`.

## Paths

```text
data/lexical-indexes/<lexical_index_id>/
data/lexical-index-manifests/<lexical_index_id>.json
data/corpora/<corpus>/lexical/state.json
```

## Out of scope

Reranking is Slice 6 (done — see `docs/slice6_cross_encoder_reranking.md`). Parent expansion (Slice 7), section-prefix lexical text,
third-party BM25 engines, learned sparse retrieval, lexical GC.
Hybrid/RRF is Slice 5 (see `docs/slice5_hybrid_retrieval.md`).
