# Slice 0 — Foundation Contracts

Slice 0 established repository contracts: configuration, domain schemas, deterministic
IDs, local logging, and the CLI shell.

Later slices implement the pipelines; Slice 0 contracts remain the shared foundation.

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
| Chunk ID (`chunk_<sha256>` / `parent_<sha256>`) | Yes | Content- and config-derived (see Slice 2) |
| Config / experiment hash (`cfg_<sha256>`) | Yes | Canonical JSON with sorted keys |
| Chunk / embedding / index / lexical config hashes | Yes | Prefixed `chunkcfg_`, `embcfg_`, `idxcfg_`, `lexcfg_` |
| Query / evaluation execution IDs | No | Runtime event IDs (UUID-style) are allowed |

A random execution ID must never become the identity of retrieved document or
chunk content.

## Logging

Local stdlib logging only: human console mode or structured JSON. No cloud
telemetry.

## CLI (current)

Implemented through Slice 7:

```text
offline-rag ingest ...
offline-rag chunk ...
offline-rag chunk inspect ...
offline-rag provision embedding
offline-rag provision reranker
offline-rag index ...
offline-rag index inspect ...
offline-rag index lexical ...
offline-rag index lexical inspect ...
offline-rag retrieve ...
offline-rag retrieve lexical ...
offline-rag retrieve hybrid ...
offline-rag retrieve hybrid-rerank ...
offline-rag retrieve hybrid-rerank-context ...
offline-rag eval retrieve [--method dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context] ...
offline-rag doctor ...
```

Still deferred: full `query` (generation, Slice 8+), generic `eval run` / `eval compare`.
Retrieval ablation ladder through expansion is complete; next is grounded generation.
