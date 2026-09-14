# Slice 9E — Local Human Review & GoldDataset Finalization

**Status:** implemented under Decisions 9E-1 through 9E-16.

## Commands

```text
offline-rag gold review \
  --run <authoring-run.json> \
  [--host 127.0.0.1] \
  [--port 8765]

offline-rag gold finalize \
  --run <authoring-run.json> \
  [--output <gold-dataset-directory>] \
  [--force]
```

## Review

- Loopback-only stdlib HTTP server + packaged vanilla HTML/CSS/JS
- Persists `SilverCase.human_review` onto the selected silver run in place
- Human grades are authoritative; 9D prelabels remain advisory
- Full candidate coverage required before `accepted` / `edited`
- Semantic query edits hard-clear human grades

## Finalize

- Fail-closed export of valid `accepted` / `edited` cases only
- Default destination:

```text
paths.corpora/<corpus>/gold_authoring/gold/<authoring_run_id>/
```

- GoldDataset v1: `meta.json` + `cases.jsonl`
- Positive-only judgments (`1|2`); human `0` stays on silver
- `GoldCase.id = draft_case_id`
- Lineage from run (`chunk_set_id`, optional corpus fields); `metadata.authoring_run_id` is non-semantic

## Hard stop

Next: Slice **9F** (20-case authoring pilot). Do not start 9F / Label Studio / LAN review / Slice 10 here.
