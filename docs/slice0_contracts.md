# Slice 0 — Foundation Contracts

Slice 0 establishes repository contracts only. It does **not** implement
ingestion, parsing, chunking, embeddings, retrieval, reranking, generation, or
evaluation execution.

## Configuration precedence

Later sources win:

```text
built-in defaults
      ↓
YAML (later files override earlier files when multiple are provided)
      ↓
environment variables (OFFLINE_RAG_*)
      ↓
explicit programmatic / CLI overrides
```

Unknown configuration keys are rejected.

Application runtime settings live under `offline_rag.config`. Domain
`ExperimentConfig` is a separate experiment identity contract.

## Identity policy

| Identity | Deterministic? | Notes |
|---|---|---|
| Document ID (`doc_<sha256>`) | Yes | Derived from canonical source bytes |
| Chunk ID (`chunk_<sha256>`) | Yes | Derived from document ID, chunk index, text, optional chunker version |
| Config / experiment hash (`cfg_<sha256>`) | Yes | Canonical JSON with sorted keys |
| Query / evaluation execution IDs | No | Runtime event IDs (UUID-style) are allowed |

A random execution ID must never become the identity of retrieved document or
chunk content.

## Logging

Local stdlib logging only: human console mode or structured JSON. No cloud
telemetry.

## CLI

`offline-rag` exposes `ingest`, `query`, `eval run`, `eval compare`, and
`doctor`. Except for Slice-0-safe `doctor` checks, commands are intentional
placeholders until later slices.
