# Slice 2 — Structure-Aware Chunking

Slice 2 derives parent/child chunks from immutable Slice 1 `ParsedDocument` artifacts.

**Status:** implemented.

## Flow

```text
CorpusState
    ↓
CorpusManifest
    ↓
ParsedDocument (per document)
    ↓
structure-aware chunker
    ↓
DocumentChunkArtifact     (content-addressed)
    ↓
ChunkSetManifest          (immutable snapshot)
    +
ChunkState                (mutable pointer)
    +
ChunkingReport
```

## Boundary

Chunking consumes only validated `ParsedDocument` / `ContentBlock` objects.

It must not reopen source PDFs, invoke Docling, or re-parse Markdown/TXT.

## Model

Single `Chunk` schema with `ChunkKind.parent` | `ChunkKind.child`.

- Parents: context units; no neighbors; no `parent_chunk_id`
- Children: searchable units; reference one parent when `parent_child=true`; global neighbor chain

## Token budgeting

- `TokenCounter` protocol; default `tiktoken` / `cl100k_base`
- Fake whitespace counter for structural unit tests
- Provision: `uv run python scripts/provision_tiktoken.py`
- Runtime never downloads tokenizer data

Baseline budgets (experimental defaults):

| | target | max |
|---|---:|---:|
| child | 350 | 512 |
| parent | 1200 | 2000 |

## Configuration

```yaml
chunking:
  strategy: structure_aware
  parent_child: true
  tokenizer:
    implementation: tiktoken
    encoding: cl100k_base
  child: { target_tokens: 350, max_tokens: 512 }
  parent: { target_tokens: 1200, max_tokens: 2000 }

paths:
  chunks: data/chunks
  chunk_manifests: data/chunk-manifests
  tokenizer_artifacts: models/tokenizers/tiktoken
```

`chunk_config_hash` includes only output-affecting chunking settings plus
contract version `structure-aware-chunker-v1`.

## CLI

```bash
offline-rag chunk --corpus <name> [--json]
offline-rag chunk inspect --corpus <name> (--chunk <id> | --document <id>) [--json]
```

Not auto-run from ingest. Stale when `ChunkState.source_corpus_id != CorpusState.current_corpus_id`.

## Deferred

- embeddings / Qdrant / retrieve → Slice 3 (done)
- BM25 → Slice 4 (done); hybrid/RRF → Slice 5 (done); rerank → Slice 6
- parent/neighbor expansion at query time → Slice 7
- generation → Slice 8+
