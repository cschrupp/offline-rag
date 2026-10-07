# Slice 16D-B3 — Conversational Workspace

```text
STATUS: IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
HUMAN ACCEPTANCE: PENDING
INDEPENDENT REVIEW: PENDING

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

Implementation candidate SHA:
adbf2fcd01c4c2db08fe146993c04ce91b9b97c3

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
- Unsafe / empty resolution → `clarification_required` +
  `abstention_reason=ambiguous_request` (no retrieval / no grounded generator)

## Admission ordering

Normative sequence in `run_conversation_turn`:

1. validate request (question + prior_turns bounds/sequence)
2. require runtime ready
3–4. resolve/validate workspace
5–6. capture admitted revision + snapshot id
7–8. resolve logical sources → document scope
9. bind immutable snapshot
10. allocate `conversation_trace_id`
11. resolver (if required)
12. shared grounded query core on admitted binding

Post-admission workspace mutation does **not** upgrade the in-flight turn and
is **not** `workspace_conflict`.

## Trace model

| Trace | Store | Role |
| --- | --- | --- |
| `conversation_trace_id` | `traces/conversation/` | orchestration provenance (hashes, admission, resolver outcome, linked query id) |
| `query_trace_id` | existing product query traces | scientific authority |

Conversation traces never store transcript text.

## Persistence behavior

- Session-local `sessionStorage` key `seneca.conversation.v1:{workspaceId}`
- Max **50** completed user/assistant pairs (drop oldest)
- Client resolver window: newest **6** pairs / **12_000** chars (server
  re-validates; no silent widen)
- `+ New conversation` clears turns/context; preserves sources/selection/workspace

## UI behavior

- Workspace detail is the conversation-dominant three-column surface
- Composer: immediate user turn, clear on Send, duplicate Send blocked while pending
- B2 claim markers / Evidence pane / historical version open preserved
- Current vs Historical badge from `turn.snapshot_id == workspace.current_snapshot_id`

## Responsive behavior

- Desktop: Sources (~18rem) \| Conversation (`1fr`) \| Evidence (~24rem)
- Workspace detail max width ~96rem (`:has(.workspace-page)`)
- Narrow: Conversation primary; Sources/Evidence drawers; mutual exclusion
- Returning to desktop clears drawers / inert

## Tests

Backend (`tests/unit/app/test_slice16d_b3_conversation.py`): first-turn bypass;
follow-up resolution; injection/schema fail-closed; malformed/over-bound
prior_turns; invalid source subset; binding-before-resolver; mutation retains
admitted snapshot; clarification dual-trace rules; fresh retrieval; prior
assistant not evidence; exact subset; `/query` independence; privacy-minimized
conversation trace; query-trace scientific hash.

Frontend: conversation state bounds/window helpers; composer lifecycle; new
conversation; layout/drawer coverage; existing 16D-B / B2 claim suites updated
for conversation/turn.

Validation run (implementation branch):

- backend B3 + 16D-A scope: passed
- `ui` vitest: 84 passed
- `ui` lint / typecheck / production build: passed
- `git diff --check`: clean (at evidence packaging)

## Manual smoke

Environment: local generator + workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d` (10 ingested sources). API restarted onto
B3 code on `127.0.0.1:8080` (prior process lacked `/conversation/turn`; second
port blocked by exclusive local Qdrant lock).

Observed:

1. First turn: `context_used=false`, `retrieval_question` equals user question,
   `conversation_trace_id` + `query_trace_id` present. Scientific outcome
   `model_abstain` (corpus/generation — also seen on `/query`).
2. Follow-up after abstention prior: product `clarification_required` with
   `query_trace_id=null` (fail-closed; no retrieval).
3. Follow-up with substantive synthetic prior assistant text: resolver produced
   standalone `retrieval_question` (“Which machine learning methods are
   supervised?”), `context_used=true`, fresh `query_trace_id`.
4. Explicit source subset turns retained admitted scope fields; changing subset
   on later turn did not rewrite prior response provenance objects.
5. `/query` remained independent (no `conversation_trace_id`).
6. Display-only workspace PATCH left scientific snapshot identity unchanged for
   prior turns (no false Historical from title-only edit).

Not exercised live (to avoid destructive source rebuild on the shared smoke
workspace): publishing snapshot N+1 via source remove/replace, and full
browser narrow citation→Evidence path. Those are covered by automated UI tests
(current/historical + drawer contracts). Vite UI was available; API smoke was
the authoritative live-provider check for dual-question orchestration.

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
