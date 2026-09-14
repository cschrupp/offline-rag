# Slice 9D — Local blind relevance pre-labeling

Slice 9D enriches pooled SilverCases with local-model relevance prelabels under
`relevance-prelabel-v1`: candidate-at-a-time judging, two deterministic blind
execution orders (`blind-order-v1`), strict `{grade, rationale}` responses, and
`prelabel-agreement-v1` review aids. Results remain silver-only.

**Status:** implemented.

## Architecture

```text
pooled SilverCase
        ↓
historical candidate reconstruction (run.chunk_set_id)
        ↓
relevance-judge-context-v1 envelope
        ↓
2N candidate-at-a-time model requests
        ↓
pass 1 + pass 2 (blind-order-v1)
        ↓
prelabel-agreement-v1
        ↓
enriched offline-rag-gold-authoring-v1
```

Package additions under `src/offline_rag/gold_authoring/`:

- `prelabel.py` — orchestrator
- `blind_order.py` — `blind-order-v1`
- `judge_context.py` — `relevance-judge-context-v1`
- `prelabel_schema.py` — response parse/validate
- `agreement.py` — `prelabel-agreement-v1`
- `prelabel_models.py` — judgments / summaries / outcomes

## CLI

```bash
offline-rag gold prelabel \
  --run <authoring-run.json> \
  [--output <path>] \
  [--force]
```

## Exit codes

| Code | Meaning |
|---|---|
| 2 | Could not start (preflight / no targets / force required) |
| 1 | Valid run; zero new successful complete prelabels |
| 0 | ≥1 new successful complete prelabel |

## Next

Slice **9E** — human review / GoldDataset finalization — done:

See [`slice9e_human_review.md`](slice9e_human_review.md).

Next: Slice **9F** — 20-case authoring pilot.
