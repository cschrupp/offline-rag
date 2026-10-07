# Slice 16D-B3 — Conversational Workspace

```text
STATUS: REWORK 3 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
HUMAN ACCEPTANCE: PENDING
INDEPENDENT REVIEW: REWORK 3 COMPLETE / PENDING RE-REVIEW

Authorized implementation baseline:
28aad06f89e6d00a0b81b51f9c2de38fed06cb22

B2 accepted implementation (substrate):
baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149

Accepted A2 design:
dce3456e519cb6c96570e20f5af800d00cafb5a7

A2 closeout:
f0bdf78d0ae6a79737055d324b22fc35e1e501f5

Amendment A3 (human-approved layout):
docs/slice16_amendment_a3_full_viewport_workspace.md
MATERIALIZATION: da1082d95630c12eaf0ce1a3b8d005aaa60d2f73

Branch:
implementation/16d-b3-conversational-workspace

Original B3 implementation candidate SHA:
adbf2fcd01c4c2db08fe146993c04ce91b9b97c3

Rework 1 implementation candidate SHA:
08622794c3186b3eb3684b1c2efc7529bbdac459

Rework 2 implementation candidate SHA:
b2cdad859e9467fd74dfe801bcdba721137d0afe

Rework 3 baseline (remote tip at authorization):
528e7dbb10fdde24ea1ea7db71a4e35c2a9222e1

Rework 3 implementation candidate SHA:
9c178ffb033cde41849379fc914f321697ff8691

Evidence packaging tip:
625881f3b2bc82fc2af6af9e54ec260c3de526f9

16D-B2: COMPLETE / ACCEPTED / SEALED
16D-B3: REWORK 3 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
Slice 16: IN PROGRESS / NOT COMPLETE
```

This document is the B3 evidence packet and does **not** accept or seal B3.

## A2 / A3 authority used

Primary decisions: A2-D02…D11, A2-D19…D24 (conversation product model,
resolver, dual-question core, admission, traces, persistence, composer,
layout/responsive). Grounded Answer V2 (B2) remains the scientific answer
substrate.

**Amendment A3** (human visual-review trigger) supersedes only B3 desktop
layout assumptions that conflict with full-viewport workbench + collapsible
rails + containment (including the prior ~96rem workspace max-width).

## Architectural approach

- New product surface: `POST /v1/workspaces/{id}/conversation/turn`
- Existing `POST /v1/workspaces/{id}/query` preserved as independent single-turn
- Shared scientific path: `run_bound_snapshot_query` →
  `run_grounded_query_core(retrieval_question, answer_intent, …)`
- No second retriever / generator / Qdrant path
- Conversation text is linguistic context only (never EvidenceUnit)

## Resolver contract

- Prompt / provenance id: `conversation_context_resolver_v1`
- Delimited untrusted `<CONVERSATION_DATA>` / `<CURRENT_USER_TURN>`
- Frozen model JSON: `{ "retrieval_question", "context_used" }`
- Empty `prior_turns` bypasses resolver (`context_used=false`)
- Unsafe / empty / non-exact-JSON resolution → `clarification_required` +
  `abstention_reason=ambiguous_request` (no retrieval / no grounded generator)
- Rework 1 R4: accept only exact top-level JSON object for the allowlisted
  schema; no prose salvage, fences, or embedded-object extraction

## Admission ordering

Normative sequence in `run_conversation_turn` (A2-D05b; Rework 1 R1):

1. validate request (question + prior_turns bounds/sequence)
2. require runtime ready
3–4. resolve/validate workspace
5–6. capture admitted revision + snapshot id
7–8. resolve logical sources → document scope
9. bind immutable snapshot
10. allocate `conversation_trace_id`
11. resolver (if required)
12. shared grounded query core on admitted binding

## Trace model

| Trace | Store | Role |
| --- | --- | --- |
| `conversation_trace_id` | `traces/conversation/` | orchestration provenance |
| `query_trace_id` | existing product query traces | scientific authority |

## Persistence behavior

- Session-local `sessionStorage` key `seneca.conversation.v1:{workspaceId}`
- Max **50** completed user/assistant pairs (drop oldest)
- Client resolver window: newest **6** pairs / **12_000** Unicode code points
- Incomplete/failed turns are **presentation-only transient state** (in-memory)
- Desktop rail collapse preference: session-local `seneca.workspace-rails.v1`
  (UI only; A3-D06)

## UI behavior (including Rework 3 / A3)

- Workspace detail is a **full-viewport** three-pane workbench (A3-D01/D02/D03)
- Desktop rails independently collapsible; Conversation expands into freed space
- Evidence inspection (citation / source preview) auto-expands collapsed Evidence
- Narrow/mobile remains drawer-based (A3-D08); drawers mutually exclusive
- Composer sticky at bottom of conversation pane
- Containment: pane tracks do not grow from long IDs/filenames/PDF embeds
- Assistant visible text and `prior_turns[].text` share
  `assistantPresentationText` (Rework 1 R5)
- Failed-turn chronology via submission `askedAt` timeline (Rework 2)

## Independent review history

| Gate | Disposition |
| --- | --- |
| Initial B3 review | REWORK 1 (R1–R6) |
| Rework 1 review | REWORK 2 (R2 chronology only); R1/R3–R6 closed |
| Rework 2 code review | PASS (superseded for acceptance by human visual review) |
| Human visual acceptance | REWORK 3 authorized + Amendment A3 |

## Rework 3 closure

**Trigger:** human visual acceptance review found remaining desktop UX defects
(centered ~96rem page, non-collapsible rails, Evidence overflow).

**Authority:** Amendment A3 materialized at
`da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`.

| Topic | Closure |
| --- | --- |
| Full-viewport | `.app-main:has(.workspace-page)` max-width none; modest gutter; clamped grid tracks |
| Sources collapse | Accessible Collapse/Expand Sources; compact restore affordance |
| Evidence collapse | Accessible Collapse/Expand Evidence; Conversation expands |
| Citation → collapsed Evidence | Desktop auto-expands Evidence; selection preserved |
| Overflow containment | min-width 0 / max-width 100% / break-all on identifiers; PDF max-width 100% |
| Vertical workbench | Independent scroll for Sources list, Conversation thread, Evidence scroll; sticky composer |

## Tests

Backend (unchanged in Rework 3): focused B3 suite from prior reworks remains the
scientific/API evidence. Rework 3 is frontend-only.

Frontend: prior R2–R6 / chronology / B2 citation / drawer suites preserved;
Rework 3 adds desktop rail collapse/expand + aria-expanded, Evidence auto-open
on citation/source preview, narrow drawer architecture assertions, containment
class hooks.

Validation run (Rework 3 — frontend-only):

- `ui` vitest (full): **94 passed**
- `ui` lint / typecheck / production build: passed
- `git diff --check`: clean (Rework 3 commit paths)
- Backend not re-run (no backend/scientific code changes)

## Manual browser smoke (Rework 3)

Environment: Vite `127.0.0.1:5173` + API `127.0.0.1:8080`, workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d` (“B1 Upload Smoke”, 10 sources).
CDP device metrics used for viewport sizes; layout measured from live DOM.

### ~2048 × 1200 desktop

- `app-main` max-width `none`; padding `16px` gutters
- Tracks ≈ Sources 352 / Conversation 1160 / Evidence 480 (ask share ≈ 0.575)
- No page-level horizontal scrollbar (`scrollWidth == clientWidth == 2048`)
- Both rails expanded by default with Collapse controls
- Both collapsed → Conversation ask share ≈ 0.79; restore affordances present
- Long filename `Carlos_Schrupp_Berkeley_Career_Advising_CV.pdf`: wraps
  (`overflow-wrap: anywhere`); PDF iframe width 447 ≤ Evidence 480
- Hostile synthetic provenance IDs/section path: `maxDdOverhang == 0`, no page
  horizontal overflow
- Live first turn answered with citations; Sources list independently
  scrollable; composer remained visible in viewport
- Evidence collapsed → source preview auto-expanded Evidence

### ~1440 × 900 desktop

- max-width none; no horizontal overflow
- Tracks ≈ 259 / 764 / 346 (ask share ≈ 0.548)

### ~1280 × 800 desktop

- max-width none; no horizontal overflow
- Tracks ≈ 240 / 649 / 320 (ask share ≈ 0.526)

### Narrow ~390 × 844

- Desktop rails `display: none`; mobile Sources/Evidence bar `flex`
- Rail collapse toggles CSS-hidden
- Citation opened exactly **one** Evidence drawer (`role=dialog` count = 1)
- Returning to 1440 desktop: dialogs 0, root not inert, rail toggles displayed

Destructive N+1 live smoke still omitted; automated historical-version coverage
remains the evidence for that contract.

## Known limitations

- Session-local conversation only (no durable chat library) — per A2-D08
- Incomplete/failed turns are not session-persisted (presentation-only)
- Rail preference is session-local UI state only (no server preferences)
- Clarification copy is application-owned; resolver does not answer factually

## Unrelated baseline / test debt

- Pre-existing unrelated local dirt may include `uv.lock`, `data/locks/`,
  `data/traces/`, `data/workspaces/` — kept out of B3 commits
- Legacy `seneca.ask-history.v2` loader retained for B2 integrity unit tests;
  product Ask path uses `seneca.conversation.v1`
