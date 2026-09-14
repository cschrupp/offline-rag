# Slice 9E — Local Human Review & GoldDataset Finalization

**Status:** implemented under Decisions 9E-1 through 9E-16 (plus a narrow post-implementation corrective patch for fail-closed publication/evidence and strict mutation parsing).

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
- Hosts: `127.0.0.1` / `localhost` (IPv4) or literal `::1` (IPv6 loopback when the platform supports it); never `0.0.0.0` / LAN / `::`
- Persists `SilverCase.human_review` onto the selected silver run in place
- Human grades are authoritative; 9D prelabels remain advisory
- Full candidate coverage required before `accepted` / `edited`
- Semantic query edits hard-clear human grades
- `query_override` equal to canonical `proposed_query` canonicalizes to `null` on load (no second “unchanged override” state)
- Historical evidence is exact child text from `run.chunk_set_id`; unresolved evidence fails closed (`evidence_unavailable`) — no placeholder text, CURRENT substitution, parent/neighbor fill, or silent candidate omission
- Mutation JSON is strict: `clear` / `clear_override` must be JSON booleans when present; empty `{}` does not mutate category/tags
- HTTP mutations are transactional with their evidence-backed success response: response/view construction (including historical evidence) runs on the prospective run before any durable write; if that step fails, `--run` is unchanged

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
- Publication writes a temporary sibling directory, validates the complete GoldDataset there (including expected `dataset_id`), then promotes; validation failure leaves a missing destination absent and an existing `--force` destination unchanged

## Hard stop

Next: Slice **9F** (20-case authoring pilot). Do not start 9F / Label Studio / LAN review / Slice 10 here.
