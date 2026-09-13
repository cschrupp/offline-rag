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

Implemented through Slice 8:

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
offline-rag query ...
offline-rag eval retrieve [--method dense|lexical|hybrid|hybrid-rerank|hybrid-rerank-context] ...
offline-rag eval compare --a <result-a.json> --b <result-b.json> [--json]
offline-rag eval query ...
offline-rag doctor ...
```

Still deferred: generic `eval run`, Milestone 4 `offline-rag gold pool|prelabel|review|finalize` (9C+; **9A**/**9B** done including `gold propose`), and Milestone 5 / Slice 10 semantic answer/citation quality metrics.
Retrieval ablation ladder through expansion is complete; grounded generation is baseline.
Slice 9 provides GoldDataset v1 + comparable retrieval-eval-result-v1 artifacts.
Slice 9 notes: `docs/slice9_retrieval_evaluation.md`.
Gold authoring: `docs/slice9a_gold_authoring.md`, `docs/slice9b_gold_propose.md`, plan `docs/milestone4_offline_gold_authoring.md`.
