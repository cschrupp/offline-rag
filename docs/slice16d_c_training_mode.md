# Slice 16D-C — Training Mode

```text
16D-C:
IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING

Authorized baseline:
396aa329e6c0413eb69aacd39067a70d9b478b72

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
- Accepted B3 conversation path + A3 full-viewport/rails remain authoritative

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

- `ui/src/features/training/trainingPrompts.ts` — per-workspace localStorage library
- `ui/src/features/training/revealState.ts` — transient per-turn reveal map
- `ui/src/features/training/TrainingToolbar.tsx` — save/select/delete + presentation control
- `ui/src/features/ask/AskPanel.tsx` — Training Mode composer + reveal controls
- `ui/src/features/ask/ClaimAnswer.tsx` — optional citation visibility
- `ui/src/features/ask/EvidencePanel.tsx` — evidence-hidden placeholder
- `ui/src/pages/WorkspacePage.tsx` — mode entry/exit, reveal wiring, presentation rails
- `ui/src/styles/global.css` — Training Mode / presentation typography & layout

### Confirmation: no second RAG path

- No backend API, schema, query-contract, or scientific-path changes.
- Training Mode Send uses the existing conversation/turn client path only.
- No direct Qdrant access, alternate generator, hidden source expansion, or transcript-as-evidence.

## Saved-prompt persistence

- Key: `seneca.training-prompts.v1:{workspace_id}`
- Browser `localStorage` only; presentation data (`id`, `text`, `createdAt`)
- Per-workspace isolation; corrupt storage fails closed to `[]`
- Selecting a prompt seeds the composer only (no auto-send)
- Prompt library never enters `prior_turns` / model requests

## Reveal-state model

Three independent layers per assistant turn (answered turns):

1. Answer
2. Citations
3. Evidence

Newly completed **answered** Training Mode turns begin fully hidden (fail closed; no answer flash). Non-answered outcomes (`clarification_required`, `model_abstain`, `insufficient_evidence`) keep accepted application copy and do **not** expose a fake Reveal-answer control; evidence is not force-hidden for those outcomes.

Citation activation while Evidence is hidden reveals Evidence and opens the exact citation (A3 desktop auto-expand / narrow drawer preserved).

Reveal state is transient UI state only (not persisted to backend/scientific response).

## Presentation mode

- CSS/application presentation layout is the reliable baseline (`presentation-mode` class).
- Temporarily collapses desktop rails without overwriting persisted rail preference; restores prior preference on exit.
- Browser Fullscreen API is progressive enhancement only (denial/unavailability leaves presentation usable).
- Exit control remains keyboard-reachable.

## Responsive / accessibility

- Narrow layout reuses existing Sources/Evidence drawers (no second modal system).
- Reveal/mode controls are real buttons with `aria-expanded` / accessible labels where applicable.
- Hidden answer/citation/evidence content is omitted from the accessibility tree (not merely visually transparent).

## Tests

Deterministic coverage in `ui/src/test/slice16d_c_training_mode.test.tsx` (entry/exit, saved prompts, B3 reuse, progressive reveal, non-answered outcomes, new conversation, presentation, a11y, narrow). Existing B3/A3 suites remain green.

## Manual smoke

Workspace: `ws_1f0faad69b9041e7aa6c60190538ba7d` (“B1 Upload Smoke”), local Vite + API.

Observed:

- Enter/exit Training Mode without workspace mutation; sources preserved
- Save/select local training prompts; no auto-send
- New conversation clears B3 thread; prompts + Training Mode retained
- Non-answered outcomes: accepted abstention/clarification copy; no Reveal-answer control
- Answered turn: answer/citations/evidence hidden by default; progressive reveal; citation activation opens exact CV evidence (source/version/page)
- Presentation view enter/exit restores rails; no scientific mutation
- Narrow (390px): no horizontal overflow; Sources control present; no stacked dialogs

## Known limitations

- Saved prompts are local-device only (no sync/export)
- No learner accounts / grading / LMS (intentionally out of scope)
- Fullscreen permission is optional; presentation does not depend on it
- Sticky conversation composer can visually overlap reveal controls on short viewports; controls remain keyboard-operable and scrollable

## Implementation candidate SHA

Recorded at packaging tip after push (see completion gate return block).
