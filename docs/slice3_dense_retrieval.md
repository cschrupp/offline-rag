# Slice 3 — Dense Retrieval Baseline

Slice 3 indexes child chunks into a local dense vector store and exposes dense
retrieval plus a minimal Recall@k / MRR evaluator.

**Status:** implemented.

## Flow

```text
provision embedding          (explicit; network allowed here only)
        ↓
CorpusState → ChunkState → ChunkSetManifest → child Chunks
        ↓
EmbeddingTextBuilder (plain-v1)
        ↓
EmbeddingArtifact cache      (data/embeddings)
        ↓
QdrantLocalBackend           (data/qdrant)
        ↓
DenseIndexManifest + IndexState
        ↓
DenseRetriever / eval retrieve
```

## Searchable unit

Only `ChunkKind.CHILD` receives dense vectors. Parents are not indexed.

Canonical embedding input: `Chunk.text` via `plain-v1` (no section/title/parent prefix).

## Real vs test embedders

| Role | Implementation |
|---|---|
| Portfolio / quality baseline | `Qwen/Qwen3-Embedding-0.6B` @ pinned revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, 1024-d, normalized, cosine |
| CI / unit tests | `FakeEmbedder` (`indexing.embedding.implementation: fake`) |

Runtime loads Sentence Transformers **only from the local provisioned directory**
(`local_files_only=True`, `trust_remote_code=False`). No Hub download at index/retrieve time.

## Provisioning

```bash
offline-rag provision embedding
# or
uv run python scripts/provision_embedding.py
```

Installs under `models/embeddings/qwen3-embedding-0.6b/` with
`offline-rag-embedding.json`. States: ABSENT / INVALID / READY.

## Identities

| Identity | Meaning |
|---|---|
| `embedding_config_hash` | Vector-affecting semantics only |
| `embedding_id` | Per-child content-addressed vector |
| `index_config_hash` | Embedding + search/index semantics |
| `index_id` (`denseindex_<sha256>`) | Immutable dense derivation |
| Qdrant point ID | `UUID5(fixed namespace, chunk_id)` |

Published indexes and embedding artifacts are retained by default (no auto-GC).

## Paths

```yaml
paths:
  embeddings: data/embeddings
  index_manifests: data/index-manifests
  qdrant_storage: data/qdrant
  embedding_artifacts: models/embeddings
```

Mutable pointer: `data/corpora/<corpus>/indexing/state.json`

## CLI

```bash
offline-rag index --corpus <name> [--json]
offline-rag index inspect --corpus <name> [--index|--point|--chunk] [--json]
offline-rag retrieve --corpus <name> --query "..." [--top-k N] [--json]
offline-rag eval retrieve --dataset <path> --corpus <name> [--json]
```

`query` is implemented in **Slice 8** (grounded generation). Use `retrieve` for retrieval ablation without generation.

Stale chunk sets refuse indexing; stale indexes refuse retrieve/eval.

## Evaluation

Minimal dense eval: chunk Recall@1/5/10, MRR, latency.

Gold datasets must bind to `chunk_set_id` (see `eval/datasets/dense_smoke/` placeholder).

## Reserved next slices (ablation ladder)

Reranking is a first-class planned stage, intentionally **out of Slice 3** so dense
embedding/index gains stay separable from reranker gains.

```text
Slice 3  Dense indexing/retrieval     (done — this document)
Slice 4  Lexical/BM25 retrieval       (done — see docs/slice4_lexical_retrieval.md)
Slice 5  Hybrid retrieval / RRF fusion (done — see docs/slice5_hybrid_retrieval.md)
Slice 6  Cross-encoder reranking      (done — see docs/slice6_cross_encoder_reranking.md)
Slice 7  Parent/neighbor context expansion (done — see docs/slice7_context_expansion.md)
Slice 8  Grounded local generation    (done — see docs/slice8_grounded_generation.md)
```

Ablation path: Dense → +BM25 → +RRF → +reranker → +parent/neighbor expansion → generation.

Slice 6 uses provisioned `BAAI/bge-reranker-v2-m3` plus CI `FakeReranker` (mirrors embedders): config identity, no runtime downloads.
Slice 7 exposes `hybrid-rerank-context` via `HybridRerankContextAssembler` (no ContextState).
Slice 8 exposes `query` via `GroundedAnswerOrchestrator` (no GenerationState).

Also deferred beyond the ladder above: Qdrant server / Edge, reference-aware index GC,
full experiment registry / dashboards, semantic answer/citation quality metrics.
