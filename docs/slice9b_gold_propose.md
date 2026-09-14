# Slice 9B — Deterministic source sampling & local question proposal

Slice 9B is the first real end-to-end offline gold-authoring path: sample
eligible child chunks, call an approved local authoring model under
`question-proposal-v1`, apply deterministic quality gates, and persist a
silver `offline-rag-gold-authoring-v1` run via `offline-rag gold propose`.

**Status:** implemented.

## Architecture

```text
CURRENT ChunkSet
        ↓
eligible children (child ∧ ¬heading ∧ nonempty)
        ↓
source-sampling-random-v1
        ↓
proposal-context-seed-provenance-v1
        ↓
Authoring READY + privacy dual-gate
        ↓
openai-compatible-authoring-v1  (POST /chat/completions, json_object)
        ↓
question-proposal-v1 parse/normalize
        ↓
proposal-quality-gates-v1
        ↓
pending SilverCases + structured seed failures
        ↓
persist offline-rag-gold-authoring-v1
```

Package: `src/offline_rag/gold_authoring/`

Orchestrator: `run_gold_propose`

## CLI

```bash
offline-rag gold propose \
  --corpus <name> \
  [--count 20] \
  [--seed 0] \
  [--output <path>] \
  [--force]
```

`--count` = selected seeds / max attempts (not guaranteed SilverCase count).
Defaults live under `<corpus>/gold_authoring/runs/<authorrun_…>.json`.

Exit codes: `2` pre-run failure, `1` zero usable proposals, `0` ≥1 SilverCase
(partial seed failures still `0`).

## Sampling (`source-sampling-random-v1`)

Eligibility: `kind == child` ∧ `content_type != heading` ∧ nonempty text.
Canonicalize by `chunk_id` ascending → seeded SplitMix64 Fisher–Yates → first N.
No balancing, no replacement seeds, oversized/invalid N fails closed.

## Context (`proposal-context-seed-provenance-v1`)

```text
DOCUMENT: <resolve_document_title_v1>
SECTION: <render_section_path_v1>   # omitted if empty

<exact seed Chunk.text>
```

Internal `chunk_id` / `document_id` are not model-visible.

## Output (`question-proposal-v1`)

```json
{"query": "...", "category": "...|null", "tags": [], "rationale": "...|null"}
```

## Quality gates (`proposal-quality-gates-v1`)

Deixis patterns, conservative seed-copy overlap, same-run exact/near lexical
duplicates. No LLM/embedding judges. One attempt per seed (`proposal-attempt-once-v1`).

## Persistence privacy

Artifact stores IDs, titles/sections, normalized proposals, and attempt outcomes.
Does **not** store seed body, raw model response, or credentials. Reconstruct
seed text only from recorded immutable `chunk_set_id` + `chunk_id`.

`authorcfg_` remains the Slice 9A hash; pipeline contracts + seed/count are
run provenance only (no `proposecfg_`).

## Boundaries

- No pooling / prelabel / review / finalize / GoldDataset export
- No production generation prompt or `gencfg_` reuse
- No Arm H / query-prompt / provenance-v2 promotion

## Next

Slice **9C** — multi-retriever candidate pooling — done:
[`slice9c_candidate_pooling.md`](slice9c_candidate_pooling.md).

Slice **9D** — relevance prelabel / blind judging prep.
