# Slice 7 — Context expansion / evidence assembly

Slice 7 converts ranked **hybrid-rerank** child anchors into a bounded,
deterministic evidence context for later generation (Slice 8).

**Status:** implemented.

## Architecture

```text
HybridRerankRetriever(top_k=context.anchor_k)
        │
        ▼
   ranked child anchors
        │
        ▼
   ContextExpander
   (strategy + dedup + containment + clip + budget)
        │
        ▼
   EvidenceUnit[]
        │
        ▼
   plain-evidence-v1
        │
        ▼
   assembled_text
```

Package: `src/offline_rag/context/`

Public orchestrator: `HybridRerankContextAssembler`

Public method: `hybrid-rerank-context`

Dependency direction:

```text
context → rerank → hybrid → dense + lexical
```

No reverse imports. `retrieve hybrid-rerank` never auto-expands.

## Configuration

```yaml
context:
  enabled: true
  strategy: parent
  anchor_k: 5
  max_context_tokens: 6000
  neighbor_window: 0
```

Code-owned contracts (not YAML):

| Contract | ID |
|---|---|
| Assembly | `rank-priority-hard-budget-v1` |
| Clip | `anchor-preserving-v1` |
| Dedup | `first-anchor-owns-v1` |
| Containment | `suppress-contained-children-v1` |
| Neighbors | `neighbor-window-v1` |
| Render | `plain-evidence-v1` |

## Strategies

| Strategy | Behavior |
|---|---|
| `child-only` | Atomic child evidence only |
| `parent` | Parent expand + anchor-preserving clip (default) |
| `neighbors` | ±`neighbor_window` child walk, document order |
| `parent+neighbors` | Parent first, then neighbors with containment suppression |

Validation:

```text
child-only / parent       → neighbor_window = 0
neighbors / parent+neighbors → neighbor_window >= 1
```

## Token budget

Reuses Slice 2 `TokenCounter` (`tiktoken` / `cl100k_base` / `tiktoken-cl100k-v1`).

Authoritative count:

```text
TokenCounter.count(assembled_text)
```

including exact `"\n\n"` joiners. Hard limit `max_context_tokens` (baseline 6000).

Slice 8 may introduce a separate generator window budget later.

## Clipping (`anchor-preserving-v1`)

1. Emit full parent if it fits.
2. Else start at unique structural anchor span in parent text.
3. If full anchor cannot fit → stop (no partial child).
4. Else grow in balanced rounds: try left +1 char, then right +1 char.
5. Emit clipped parent and terminate assembly.

Locator: Python `str` half-open `[start_char, end_char)`.

## Identity

`context_config_hash` prefix: `ctxcfg_`

Hashes effective strategy-conditional semantics only (not `enabled`, paths, or upstream index IDs).

`evidence_unit_id` (`ev_…`) identifies the emitted representation (`full` vs `clipped` + offsets + `text_hash`).

## Result

Evidence-first `HybridRerankContextResult`:

- primary: `evidence_units`, `assembled_text`, `context_token_count`
- provenance: `anchors[]`, fusion/reranker/context hashes, diagnostics, latency

Derived units never invent reranker/RRF/dense/BM25 scores.

## Readiness

Derived only (no ContextState):

```text
Hybrid-rerank READY
+ context.enabled
+ valid ContextConfig
+ strategy-required chunk structure
+ offline TokenCounter
→ Context READY
```

## CLI

```bash
offline-rag retrieve hybrid-rerank-context \
  --corpus <name> \
  --query "..." \
  [--json]
```

No policy overrides / aliases in Slice 7.

## Evaluation

```bash
offline-rag eval retrieve \
  --method hybrid-rerank-context \
  --dataset <path> \
  --corpus <name>
```

Reports:

1. `anchor_ranking` Recall@1/5 + MRR on `anchors[]` only (depth = `anchor_k`)
2. assembly diagnostics (tokens, clipping, stop reasons, …)

No invented “context Recall@k” / evidence-quality metrics yet.

## Ladder

```text
dense → lexical → hybrid → hybrid-rerank → hybrid-rerank-context → Slice 8 generation
```

## Out of scope

- generation / Ollama / citations
- generator tokenizer budgeting
- evidence-quality gold metrics
- ContextState / context index / caches
- CLI strategy overrides
- sentence/paragraph snap, knapsack, GraphRAG, LangGraph
