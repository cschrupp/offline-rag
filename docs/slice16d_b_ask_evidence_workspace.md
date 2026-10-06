# Slice 16D-B — Ask & Evidence Workspace

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING

Authorized baseline:
a952a75bc07191b213a5113eee53cb967fef8326

A1 authority:
5060e2aeb4825f265072a1f870c3c963eace3b30

Accepted prerequisite:
16D-A @ 4f8962f2893ab433e6ea269ad54e46f67771ca70

Branch:
implementation/16d-b-ask-evidence-workspace
```

## Purpose

Transform Seneca from the accepted source-management shell into the grounded
knowledge workspace: Sources | Ask | Evidence, consuming the accepted 16D-A
query-scope substrate without a second query pipeline.

## Source selection

- Per-workspace sessionStorage key: `seneca.source-selection.v1:<workspace_id>`
- Initial state: all active sources selected
- Reconciliation:
  - drop unknown IDs
  - all-selected prior state auto-selects newly added sources
  - explicit subset does not silently broaden
- Checkbox is query-scope only; ⋮ remains CRUD only
- Zero selected disables Ask; request is not sent
- All selected → omit `source_ids` (server all-active semantics)
- Subset → exact `source_ids` list

## Query contract

- `POST /v1/workspaces/{id}/query` via `queryWorkspace`
- Body: `{ question, source_ids? }` only — no history / prior answers / citations
- Mutation `retry: false`
- Frontend DTOs: `WorkspaceCitation`, `WorkspaceQueryResponse`

## Session-local history

- Key: `seneca.ask-history.v1:<workspace_id>`
- Max 25 successful entries
- Stores question, selected scope names/IDs, and public query response
- Never stores raw source bytes
- Malformed session payload discarded
- Display-only; never sent on subsequent Ask

## Desktop layout

- Sources (~16–20rem) | Ask (flexible) | Evidence (~20–26rem)
- Compact workspace header retained (title, capacity, Edit)
- Add sources lives in the Sources rail

## Responsive drawers

- Narrow: Ask primary; Sources / Evidence drawers
- Visible Close, Escape, focus restore, inert background
- Source CRUD from Sources drawer closes the drawer before opening modal /
  confirmation (no nested-modal regression vs F12)

## Answer statuses

- `answered` — escaped text + citation chips (no fabricated inline markers)
- `insufficient_evidence` / `model_abstain` — neutral brass safety outcomes
- Transport/generation failures remain `role=alert` errors
- `workspace_conflict` refreshes sources and requires explicit retry

## Exact-version content route

```text
GET /v1/workspaces/{workspace_id}/sources/{source_id}/versions/{version}/content
  ?workspace_revision=<revision>
```

- Resolves via `SourceHistoryStore` + `RawSourceVault`
- Validates version active at requested revision
  (`active_from_revision` … `active_through_revision`)
- Shared safe response headers with current content route
  (inline disposition, nosniff, no-store, ETag)
- Current ACTIVE content route unchanged

## Evidence preview

- Lazy fetch keyed by workspace_id / source_id / version / workspace_revision
- Citation preview uses citation source_id + source_version + response
  workspace_revision (never “current version”)
- PDF: browser-native iframe + `#page=` when page_start present
- Text/Markdown: escaped text, bounded line window, cited-line highlight
- Unsupported / HTML-capable types: honest unsupported preview (no active HTML)

## Current / Historical

- Compared by `response.snapshot_id` vs `workspace.current_snapshot_id`
- Metadata-only revision bump keeps Current snapshot
- Source mutation / EMPTY → prior answers Historical
- Historical badge text is explicit “Historical snapshot”

## Tests / evidence

Backend:

- `tests/unit/app/test_slice16d_b_source_version_content.py`
- inherited:
  - `tests/unit/app/test_slice16d_a_query_scope.py`
  - `tests/unit/app/test_slice15e_product_query_traces.py`
  - `tests/unit/app/test_slice16b_query_binding.py`

Frontend:

- `ui/src/test/slice16d_b.app.test.tsx` (selection, no-memory, answers,
  historical exact-version fetch, drawer non-nesting)
- prior 16C / 16D-A suites retained green

## Limitations

- No Training Mode (16D-C)
- No conversational backend memory
- No Markdown rendering library / PDF.js
- No fabricated PDF text highlights
- No streaming / cancellation architecture
- Manual browser smoke not claimed in this evidence package unless separately
  recorded

## Explicit non-scope

16D-C Training Mode, 16E–16H, Slice 17/18, 9G, M7 closeout, merge, and
self-acceptance are **not** included.
