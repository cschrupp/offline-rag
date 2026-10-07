# Slice 16D-B3 — Conversational Workspace

```text
STATUS: IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
HUMAN ACCEPTANCE: PENDING
INDEPENDENT REVIEW: REWORK 2 COMPLETE / PENDING RE-REVIEW

Authorized implementation baseline:
28aad06f89e6d00a0b81b51f9c2de38fed06cb22

B2 accepted implementation (substrate):
baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149

Accepted A2 design:
dce3456e519cb6c96570e20f5af800d00cafb5a7

A2 closeout:
f0bdf78d0ae6a79737055d324b22fc35e1e501f5

Branch:
implementation/16d-b3-conversational-workspace

Original B3 implementation candidate SHA:
adbf2fcd01c4c2db08fe146993c04ce91b9b97c3

Rework 1 implementation candidate SHA:
08622794c3186b3eb3684b1c2efc7529bbdac459

Rework 2 baseline (remote tip at authorization):
7ddd9babece94df3f6a3f3332bfec4ffdc6b26ff

Rework 2 implementation candidate SHA:
b2cdad859e9467fd74dfe801bcdba721137d0afe

Evidence packaging tip:
4cfae97d4e5c81626d00893773877550c2e188e4

16D-B2: COMPLETE / ACCEPTED / SEALED
16D-B3: IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
Slice 16: IN PROGRESS / NOT COMPLETE
```

This document is the B3 evidence packet and does **not** accept or seal B3.

## A2 authority used

Primary decisions: A2-D02…D11, A2-D19…D24 (conversation product model,
resolver, dual-question core, admission, traces, persistence, composer,
layout/responsive). Grounded Answer V2 (B2) remains the scientific answer
substrate.

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

Normative sequence in `run_conversation_turn` (A2-D05b; Rework 1 R1 restores
HTTP adapter to this order):

1. validate request (question + prior_turns bounds/sequence)
2. require runtime ready
3–4. resolve/validate workspace
5–6. capture admitted revision + snapshot id
7–8. resolve logical sources → document scope
9. bind immutable snapshot
10. allocate `conversation_trace_id`
11. resolver (if required)
12. shared grounded query core on admitted binding

HTTP `workspace_conversation_turn` must not call `require_ready()` before
`run_conversation_turn`. Post-admission workspace mutation does **not** upgrade
the in-flight turn and is **not** `workspace_conflict`.

## Trace model

| Trace | Store | Role |
| --- | --- | --- |
| `conversation_trace_id` | `traces/conversation/` | orchestration provenance (hashes, admission, resolver outcome, linked query id) |
| `query_trace_id` | existing product query traces | scientific authority |

Conversation traces never store transcript text. Product Evidence UI labels
these distinctly (Rework 1 R3); no generic aliased `trace_id` in B3 product
presentation.

## Persistence behavior

- Session-local `sessionStorage` key `seneca.conversation.v1:{workspaceId}`
- Max **50** completed user/assistant pairs (drop oldest)
- Client resolver window: newest **6** pairs / **12_000** Unicode code points
  (server re-validates; no silent widen)
- `+ New conversation` clears turns/context; preserves sources/selection/workspace
- Failed/incomplete submissions keep the sent user turn visible but are excluded
  from resolver `prior_turns` (Rework 1 R2)
- Incomplete/failed turns are **presentation-only transient state** (in-memory);
  they are not written to `sessionStorage`. Reload clears them. Completed pairs
  remain session-persisted as before.
- Visible thread merges completed + incomplete items by immutable submission
  `askedAt` (Rework 2), not by completion time or collection grouping

## UI behavior

- Workspace detail is the conversation-dominant three-column surface
- Composer: immediate user turn, clear on Send, duplicate Send blocked while pending
- Assistant visible text and `prior_turns[].text` share
  `assistantPresentationText` (Rework 1 R5)
- Per-turn source scope presents frozen `all` | `subset` intent with submitted
  names (Rework 1 R6), e.g. `Selected sources · Alpha.pdf`
- B2 claim markers / Evidence pane / historical version open preserved
- Current vs Historical badge from `turn.snapshot_id == workspace.current_snapshot_id`

## Responsive behavior

- Desktop: Sources (~18rem) \| Conversation (`1fr`) \| Evidence (~24rem)
- Workspace detail max width ~96rem (`:has(.workspace-page)`)
- Narrow: Conversation primary; Sources/Evidence drawers; mutual exclusion
- Returning to desktop clears drawers / inert

## Independent review — Rework 1

Disposition at tip `c4a3c1a7c754a15b4b9a529479b2851915da74e3`:
**REWORK REQUIRED** (R1–R6). Architecture accepted; boundary/presentation
defects closed as follows:

| ID | Finding | Closure |
| --- | --- | --- |
| R1 | HTTP adapter `require_ready` before B3 validation | Removed premature readiness check from `workspace_conversation_turn`; validation inside `run_conversation_turn` runs first |
| R2 | Failed request erased pending user turn | `incompleteTurns` retain sent question on error; excluded from `prior_turns` |
| R3 | Generic aliased `trace_id` in Evidence | Distinct Conversation / Query trace ID labels; clarification shows null query trace |
| R4 | Resolver salvaged embedded JSON via regex | `parse_resolver_content` exact `json.loads` only; malformed → clarification |
| R5 | Synthetic prior assistant text ≠ visible copy | Shared `assistantPresentationText`; 12k window uses Unicode code points |
| R6 | Source mode dropped; count-only provenance | Persist/present `selectionMode` + frozen submitted names |

## Independent review — Rework 2

Disposition at tip `7ddd9babece94df3f6a3f3332bfec4ffdc6b26ff`:
**REWORK 2 REQUIRED** — R2 chronology only (R1/R3–R6 closed).

Defect: completed pairs and incomplete/failed turns rendered as separate
groups, so after Q1 fails then Q2 succeeds the thread could show Q2 before Q1.

Closure: every submission stamps immutable `askedAt`;
`buildConversationTimeline` merges completed + pending/failed into one
submission-ordered thread. Completed-pair `askedAt` uses the submission stamp
(not completion time). Resolver `prior_turns` unchanged (completed pairs only).

## Tests

Backend (`tests/unit/app/test_slice16d_b3_conversation.py`): first-turn bypass;
follow-up resolution; injection/schema fail-closed; malformed/over-bound
prior_turns; invalid source subset; binding-before-resolver; mutation retains
admitted snapshot; clarification dual-trace rules; fresh retrieval; prior
assistant not evidence; exact subset; `/query` independence; privacy-minimized
conversation trace; query-trace scientific hash; **R1** malformed prior vs
unready → `request_invalid` (no resolver/model/conversation trace) and valid
vs unready → `runtime_not_ready`; **R4** exact JSON only (prose/fence/suffix/
empty question/extra keys → clarification).

Frontend (`ui/src/test/slice16d_b3_conversation.test.tsx` + related): **R2**
failed send retains question / cleared composer / excluded from next
`prior_turns`; **R2 Rework 2** submission-order timeline (failure then success;
Q3 prior_turns = only completed Q2; pending at chronological end); **R3** dual
trace labels; **R5** presentation text parity + Unicode 12k; **R6** frozen
source-scope labels across selection changes.

Validation run (Rework 1):

- backend focused: `test_slice16d_b3_conversation` + `test_slice16d_a_query_scope`
  + `test_slice16b_workspace_api` + `test_slice16b_query_binding` +
  `test_grounded_answer_v2`: **85 passed**
- broader unrelated suites (`test_slice15e_product_query_traces`,
  `test_grounded_generation`) showed pre-existing/env failures when batched;
  not treated as B3 Rework 1 regressions (focused B3/API/scope suite green)
- `ui` vitest: **91 passed**
- `ui` lint / typecheck / production build: passed
- `git diff --check`: clean (Rework 1 commit paths)

Validation run (Rework 2 — frontend-only):

- `ui` vitest (full): **92 passed**
- `ui` lint / typecheck / production build: passed
- `git diff --check`: clean (Rework 2 commit paths)
- Backend not re-run (no backend changes)

## Manual smoke (Rework 1)

Environment: local generator + workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d`. API restarted onto Rework 1 code on
`127.0.0.1:8080`.

Observed:

1. Malformed prior pair → `request_invalid` /
   `prior_turns_incomplete_pair` (bounds before scientific work).
2. First turn: `context_used=false`, dual
   `conversation_trace_id` + `query_trace_id`, scientific `model_abstain`.
3. Follow-up after abstention prior: `clarification_required`,
   `query_trace_id=null`, conversation trace present.
4. Follow-up with substantive synthetic prior: resolver path exercised;
   conversation vs query identities remain distinct when a scientific query runs.
5. R4 parser checked in-process: prose/fenced JSON → clarification.
6. R2 / R3 / R5 / R6 product UI behaviors covered by automated browser tests;
   live browser failed-send / frozen source-scope not re-run interactively this
   rework (Vite available; automated coverage authoritative for those).

Destructive N+1 live smoke still omitted; automated historical-version coverage
remains the evidence.

## Known limitations

- Session-local conversation only (no durable chat library) — per A2-D08
- Clarification copy is application-owned; resolver does not answer factually
- Live scientific answered/citation outcomes depend on corpus + generator
  quality; B3 does not retune generator/reranker

## Unrelated baseline / test debt

- Pre-existing unrelated local dirt may include `uv.lock`, `data/locks/`,
  `data/traces/`, `data/workspaces/` — kept out of B3 commits
- Legacy `seneca.ask-history.v2` loader retained for B2 integrity unit tests;
  product Ask path uses `seneca.conversation.v1`
