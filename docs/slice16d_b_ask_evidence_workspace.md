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
- Explicit presentation intent: `{ knownSourceIds, selectedSourceIds, mode }`
  where `mode` is `"all"` | `"subset"`
- Initial / EMPTY workspace: `mode = all` (follow-all)
- Semantics:
  - `mode = all` → every active source selected; newly appearing sources auto-selected
  - `mode = subset` → intersect with active IDs; newly appearing sources not added
  - uncheck any / uncheck all → `mode = subset`
  - Select all → `mode = all`
  - if all selected sources disappear, retain `mode` (do not lose intent)
- Legacy session payloads without `mode` are migrated (empty known → `all`;
  otherwise inferred from whether every known ID was selected); malformed discarded
- Checkbox is query-scope only; ⋮ remains CRUD only
- Zero selected disables Ask; request is not sent
- Query scope honors `mode` (not list-equality alone):
  - `mode = all` and every currently known active source selected → may omit
    `source_ids`
  - `mode = subset` → always send explicit `selectedSourceIds`, even when every
    currently visible checkbox is checked (prevents silent broaden if the
    backend has a source the UI has not yet observed)
- React state retains `selectionMode` alongside `selectedSourceIds`

## Query contract

- `POST /v1/workspaces/{id}/query` via `queryWorkspace`
- Body: `{ question, source_ids? }` only — no history / prior answers / citations
- Mutation `retry: false`
- Submitted Ask captured immutably at click time (question, selected IDs/names,
  mode, effective `source_ids`); history is built from that submit object, not
  from React state at `onSuccess`
- Frontend DTOs: `WorkspaceCitation`, `WorkspaceQueryResponse`

## Session-local history

- Key: `seneca.ask-history.v1:<workspace_id>`
- Max 25 successful entries
- Stores question, selected scope names/IDs, and public query response
- Never stores raw source bytes
- Malformed whole payload removed; individual malformed entries dropped
  (deterministic filter). Guards cover entry fields, response status/answer
  shape (`answered` requires string answer), and citation presentation fields
  so loaded history cannot crash Ask / Evidence rendering
- Display-only; never sent on subsequent Ask

## Desktop layout

- Sources (~16–20rem) | Ask (flexible) | Evidence (~20–26rem)
- Compact workspace header retained (title, capacity, Edit)
- Add sources lives in the Sources rail

## Responsive drawers

- Narrow layout signal: `matchMedia("(max-width: 960px)")` (same breakpoint as CSS)
- Desktop: citation / source preview update the Evidence column only —
  `ResponsiveDrawer` is not mounted; `evidenceDrawerOpen` stays false; no inert root
- Narrow: Ask primary; Sources / Evidence drawers (mounted only while narrow)
- Visible Close, Escape, focus restore, inert background
- Narrow Sources → source preview: close Sources first, then open Evidence
  (exactly one modal drawer; same close-then-open discipline as CRUD)
- Narrow → desktop while a drawer is open: close responsive drawers and clear
  modal/inert state
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
- Citation preview identity is immutable: source_id + source_version + query
  workspace_revision + query snapshot_id (never “current version” bytes)
- Direct source-name preview means “inspect the current source”: live-bound to
  current `Source.version` / workspace revision; cleared if source_id disappears
- Provenance matches evidence mode:
  - citation / answer: query snapshot status, snapshot ID, query revision,
    trace ID, citation location fields
  - direct current-source: Current snapshot + source version + current workspace
    revision only (no prior Trace ID / query Snapshot ID)
- PDF: browser-native iframe + `#page=` when page_start present
- Text/Markdown: escaped text, bounded line window, cited-line highlight
- Unsupported / HTML-capable types: honest unsupported preview (no active HTML)

## Current / Historical

- Derived on every relevant render from query/entry `snapshot_id` vs
  `workspace.current_snapshot_id` — not a frozen boolean on PreviewTarget
- Citation preview: pinned bytes stay on original version/revision; badge flips
  Current → Historical when the workspace advances (no re-click required)
- Direct current-source preview: always Current while the source exists; after
  replace, rebinds to new version (never superseded v1 labeled Current)
- Metadata-only revision bump keeps Current snapshot
- Source mutation / EMPTY → prior answers Historical
- Historical badge text is explicit “Historical snapshot”

## Independent review rework 1 (F1–F3)

Disposition received: REWORK REQUIRED against candidate
`f0f27ea3b2ef6ac68ed8ae63b3a13f99f7bd05bf`.

Addressed:

- **F1** — explicit `mode: all | subset` source-selection intent; EMPTY → first
  source auto-selected; legacy migration
- **F2 / F2B** — drawers only on narrow layout; desktop Evidence column only;
  Sources→Evidence close-then-open; viewport widen closes drawers
- **F3 / F3B** — derive snapshot badge; rebind/clear direct source preview

## Independent review rework 2 (F4–F6)

Disposition received: REWORK REQUIRED against candidate
`d4817315610de12b84719bb70e5e801f8381bbbe`.

Addressed:

- **F4 / F4B** — `sourceIdsForQuery(..., mode)`; subset always sends explicit
  IDs; React retains `selectionMode`; Ask history built from immutable submit
- **F5** — strict session-history validation (answer/citation/status shapes)
- **F6** — provenance gated by citation vs direct-source evidence mode

Backend exact-version content contract unchanged (accepted 16D-B backend evidence
retained). Scientific retrieval/generation stack untouched. No merge / no 16D-C.

## Tests / evidence

Backend:

- `tests/unit/app/test_slice16d_b_source_version_content.py`
- inherited:
  - `tests/unit/app/test_slice16d_a_query_scope.py`
  - `tests/unit/app/test_slice15e_product_query_traces.py`
  - `tests/unit/app/test_slice16b_query_binding.py`

Frontend:

- `ui/src/test/slice16d_b.app.test.tsx` (selection mode / EMPTY→first,
  mode-aware query scope, submitted-scope capture, malformed history rejection,
  citation vs source provenance, derived historical badge, current-source
  rebind/clear, desktop no-drawer, mobile one-drawer transition)
- prior 16C / 16D-A suites retained green

## Validation (rework 2)

Frontend gates (run from `ui/`):

- `npm run lint`
- `npm run typecheck`
- `npm test`
- `npm run build`

Also: `git diff --check`

Unrelated dirty state excluded from commit: `uv.lock`, `data/locks/`,
`data/workspaces/`, `data/traces/`.

## Limitations

- No Training Mode (16D-C)
- No conversational backend memory
- No Markdown rendering library / PDF.js
- No fabricated PDF text highlights
- No streaming / cancellation architecture
- Manual browser smoke recommended for responsive/interaction behavior (jsdom
  only partially represents drawer/inert UX); not claimed in this package

## Explicit non-scope

16D-C Training Mode, 16E–16H, Slice 17/18, 9G, M7 closeout, merge, and
self-acceptance are **not** included.

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING
```
