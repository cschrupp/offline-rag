# Slice 16D-C — Training Mode

```text
16D-C:
REWORK 2 IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING

AMENDMENT A4:
HUMAN-APPROVED / LOCKED
IMPLEMENTED CANDIDATE / ACCEPTANCE PENDING
DOC: docs/slice16_amendment_a4_workspace_portability_shell.md

INDEPENDENT REVIEW:
REWORK 1 CLOSED
REWORK 2 AUTHORIZED → IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING

Authorized baseline (original 16D-C):
396aa329e6c0413eb69aacd39067a70d9b478b72

Rework 2 baseline:
18bc60da038e210b1b8f2f9aa26884e962a15f8f

A4 materialization:
d12f6322ef13915002b49dcc8f1211052a66dcc5

Branch:
implementation/16d-c-training-mode

16D-B3:
COMPLETE / ACCEPTED / SEALED
9c178ffb033cde41849379fc914f321697ff8691

AMENDMENT A3:
ACCEPTED / LOCKED / SEALED

16E–16H:
NOT AUTHORIZED

SLICE 16:
IN PROGRESS / NOT COMPLETE
```

## Authority clauses used

- S16-D19 — Training Mode (primary)
- Amendment A1 — 16D-C decomposition (saved prompts; reveal; presentation typography/layout)
- A2-D25 — saved training prompts seed/start accepted B3 conversation flow (no new query architecture)
- Amendment A3 — full-viewport workspace / rails (sealed; preserved)
- Amendment A4 — compact Question Bank, local portability, conversation export, full-width header
- Accepted B3 conversation path remains authoritative

## Live visual acceptance findings (pre-A4)

Human live-product review after Rework 1 withheld 16D-C acceptance because:

1. permanently expanded saved-question list consumed increasing vertical workspace;
2. instructors needed portable Question Banks and conversation exports;
3. global Seneca header remained centered `--max-width` while the workspace body was A3 full-width.

A4 / Rework 2 addresses those presentation/integration findings only.

## Implementation architecture

Training Mode is a **frontend/presentation layer** over the accepted B3 conversational workspace.

```text
Training question
      ↓
existing active conversation
      ↓
POST /v1/workspaces/{workspace_id}/conversation/turn
      ↓
accepted B3 admission / resolver
      ↓
shared grounded query core
      ↓
Grounded Answer V2
      ↓
claim citations / exact Evidence
```

Primary UI modules:

- `ui/src/features/training/trainingPrompts.ts` — per-workspace localStorage library (`PROMPT_MAX = 100`)
- `ui/src/features/training/questionBankIo.ts` — JSON/Markdown Question Bank serializers/parsers/merge plan
- `ui/src/features/training/QuestionBankPanel.tsx` — compact closed-by-default bank surface
- `ui/src/features/training/revealState.ts` — transient per-turn reveal map (Rework 1 closed)
- `ui/src/features/training/TrainingToolbar.tsx` — presentation control only (A4-D03)
- `ui/src/features/ask/conversationExport.ts` — conversation Markdown/JSON serializers
- `ui/src/features/ask/ExportConversationMenu.tsx` — Normal + Training export menu
- `ui/src/lib/downloadFile.ts` / `safeFilename.ts` — thin Blob download + filenames
- `ui/src/features/ask/AskPanel.tsx` — composer-adjacent Save / Question bank; export header
- `ui/src/styles/global.css` — A4 header viewport shell + Question Bank popover
- `ui/src/pages/WorkspacePage.tsx` — mode entry/exit, reveal wiring, presentation rails

### Confirmation: no second RAG path

- No backend API, schema, query-contract, or scientific-path changes.
- Training Mode Send uses the existing conversation/turn client path only.
- Question Bank / conversation export are browser-local only.
- No automatic source promotion from conversation export.

## Question Bank redesign (A4)

Normal Training composer chrome:

```text
[Send] [Save question] [Question bank (N)]
```

- Bank closed by default; rows are not in permanent document flow.
- Desktop: bounded popover with internal scroll (`.question-bank-popover`).
- Narrow: existing `ModalDialog` pattern; disabled while Sources/Evidence drawers open.
- Search is presentation-only case-insensitive substring filter.
- Selection seeds composer only (no auto-Send).
- Delete remains a compact accessible row action inside the bank.
- Presentation Mode retains compact bank access; does not permanently expand rows.

### JSON / Markdown contracts

- Canonical: `seneca-question-bank` v1 JSON (text only; no local IDs / workspace / traces / answers).
- Markdown: optional heading + top-level `- ` bullets only.
- Import = Merge only; trim + exact duplicate skip; capacity `PROMPT_MAX = 100`.
- Parse → confirmation preview → explicit commit; corrupt/wrong format leaves bank untouched.
- File-size guard: 256 KiB.

## Conversation export (A4)

- Available in Normal Mode and Training Mode conversation headers.
- Formats: Markdown (source-ready notes) and JSON (`seneca-conversation` v1 archive).
- Export ignores Training reveal state; hidden answers still serialize.
- Pending turns disable export.
- Markdown includes mandatory derived-Seneca / not-primary-evidence warning.
- JSON retains scientifically meaningful B3 fields when present.
- **Hard invariant:** export ≠ source ingestion. No Save-as-source / auto-promote bridge.
- Manual later Add Sources of an exported `.md` uses ordinary ingestion (A4-D18).

## Full-width application header (A4)

- `.app-header-inner` tracks the application viewport (no centered `--max-width` dead space).
- Brand near left gutter; primary nav near right gutter; modest padding gutters.
- Header width is global across routes; page bodies remain route-specific (Overview/Settings constrained; workspace A3 full-width).
- Mobile menu toggle / primary-nav a11y preserved.

## Reveal-state model (Rework 1 preserved)

Three independent layers per assistant turn (answered turns):

1. Answer
2. Citations
3. Evidence

Missing answered-turn reveal defaults remain `HIDDEN_REVEAL` (C-R1). Reveal Evidence binds the selected turn’s active/citation/evidence context (C-R2).

## Presentation mode

- CSS/application presentation layout (`presentation-mode` class).
- Temporarily collapses desktop rails without overwriting persisted rail preference.
- Browser Fullscreen API remains progressive enhancement only.

## Tests

- `ui/src/test/slice16d_c_training_mode.test.tsx` — original Training Mode + Rework 1
- `ui/src/test/slice16d_c_rework2_a4.test.tsx` — compact bank UX, bank IO, conversation export, header shell

Existing B3/A3 suites remain green.

## Manual smoke

Workspace: `ws_1f0faad69b9041e7aa6c60190538ba7d` (“B1 Upload Smoke”), local Vite + API.

Observed (Rework 2 / A4):

- Compact `Question bank (20)` closed by default; no permanent `.training-prompt-list`
- Open bank: bounded `.question-bank-popover` (max-height ~352px); list `overflow: auto` with scrollHeight ≫ visible height; `.knowledge-ask` top unchanged
- Selecting Smoke question 1 seeded composer without auto-Send; workspace revision remained 7
- `Export conversation` present in Normal + Training; Markdown export invoked with answer still hidden on screen
- Application header: `.app-header-inner` `max-width: none`; brand ~16px from left gutter; primary nav near right gutter
- Automated Vitest covers search/import preview/merge/JSON+Markdown IO/header a11y contracts

Source-ready Markdown ingestion smoke (human-mediated Add Sources of an exported `.md`) remains an optional follow-up check; no automatic promote bridge was added.

## Known limitations

- Question Bank is local-device only (no cloud sync)
- Conversation import not implemented (export only)
- No learner accounts / grading / LMS (intentionally out of scope)
- Replace-import for Question Bank not authorized in A4
- JSDOM cannot prove pixel geometry; vertical containment is manual smoke

## Implementation candidate SHA

```text
ORIGINAL IMPLEMENTATION CANDIDATE:
2266d7b16bf01e11c5ca69b2ffe4d7f4e0e821ab

REWORK 1 IMPLEMENTATION:
4489d6fb295271c65dae2c9f38e3f53bab456ff8

REWORK 2 BASELINE:
18bc60da038e210b1b8f2f9aa26884e962a15f8f

A4 MATERIALIZATION:
d12f6322ef13915002b49dcc8f1211052a66dcc5

REWORK 2 IMPLEMENTATION:
3bac1f8dc1a7d0aa8ea46ec4ceb832e63f570aff

FINAL BRANCH TIP:
0d19c81e4e0cb0098238f18349fcb29c03980aac
```
