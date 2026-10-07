# Slice 16 Amendment A2 — Conversational Grounding & Claim-Level Citations

```text
STATUS: DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING
DESIGN AUTHORIZED: YES
IMPLEMENTATION AUTHORIZED: NO
MERGE AUTHORIZED: NO

TITLE:
Slice 16 Amendment A2 —
Conversational Grounding & Claim-Level Citations

Repository:
cschrupp/offline-rag

LAST SEALED IMPLEMENTATION BASELINE:
a952a75bc07191b213a5113eee53cb967fef8326

OBSERVED 16D-B IMPLEMENTATION CANDIDATE:
6b6524001f063a628505f572e7ca13d954a38260
→ useful engineering substrate
→ NOT ACCEPTED as release Ask UX
→ NOT sealed by this design candidate

ORIGINAL SLICE-16 AUTHORITY:
e2e7475076ad18d4c4ae8d939389ceeffdeff6d8

AMENDMENT A1:
ACCEPTED / LOCKED
5060e2aeb4825f265072a1f870c3c963eace3b30

Branch:
design/slice16-amendment-a2-conversational-grounding
```

## Authority being amended

A2 is **supplemental design authority**. If and only if A2 receives human
acceptance, it supersedes **only** the clauses listed in
[Superseded-clause inventory](#superseded-clause-inventory).

Until A2 is accepted:

- S16-D01 … S16-D35 remain effective as locked;
- Amendment A1 remains **ACCEPTED / LOCKED**;
- this document is a **DESIGN CANDIDATE** only.

A2 **MUST NOT** rewrite unrelated locked Slice-16 decisions (workspace identity,
immutable snapshots, lineage, offline controls, Settings, operator locks,
retrieval science, Gold Lab, etc.).

---

## Observed product evidence

Manual use of observed 16D-B candidate
`6b6524001f063a628505f572e7ca13d954a38260` validated important engineering
substrate:

- source selection → server-side source-scoped retrieval;
- exact source/version citation projection;
- Current / Historical semantics;
- exact-version evidence content reads;
- PDF preview;
- Evidence provenance;
- session presentation state.

Product acceptance was **withheld** because the interaction model is
insufficient for release-quality Seneca.

### Observed UX / product findings (open for A2)

| ID | Finding |
| --- | --- |
| F7 | Desktop knowledge workspace constrained by legacy narrow shell (~72rem). |
| F8 | Long generated/dynamic content can visually escape the Ask column. |
| F9 | Composer does not naturally reset to a clean follow-up input after Send. |
| F10 | Independent question + detached answer + Recent Questions is too primitive for the intended Seneca product. |

### Generation-contract observation (architectural)

The current `grounded_v1` generator prompt (sealed scientific stack; also present
under the observed candidate) exposes canonical `ev_…` evidence identifiers to
the model and accepts only a flat response:

```json
{"abstain": false, "answer": "...", "citation_ids": ["ev_..."]}
```

or abstention:

```json
{"abstain": true, "answer": null, "citation_ids": []}
```

This does **not** provide trustworthy claim-to-evidence placement and can leak
internal evidence identifiers into user-facing prose. A2 therefore changes the
**generation contract**, not merely frontend restyling.

### Closed environment findings (NOT product defects)

| Finding | Disposition |
| --- | --- |
| Earlier exact-version 404 during smoke | Stale backend process — **CLOSED** |
| Isolated Week07 Content-Length browser error | Direct FastAPI and Vite-proxied downloads were byte-identical, correct `Content-Length`, identical SHA-256 — **CLOSED** as non-reproduced dev/browser transfer interruption |

---

## Decision inventory

| ID | Title |
| --- | --- |
| A2-D01 | Amendment scope |
| A2-D02 | Product interaction model (conversation) |
| A2-D03 | Conversation is not factual memory |
| A2-D04 | Preserve canonical single-turn `/query` |
| A2-D05 | Conversation turn orchestration |
| A2-D06 | Context resolver |
| A2-D07 | Bounded context |
| A2-D08 | Conversation persistence v1 |
| A2-D09 | New conversation |
| A2-D10 | Composer contract |
| A2-D11 | Source scope per turn |
| A2-D12 | Grounded answer v2 |
| A2-D13 | Response-local evidence handles |
| A2-D14 | Public answer projection |
| A2-D15 | Citation excerpt |
| A2-D16 | Notebook-style claim citation UX |
| A2-D17 | Evidence pane role |
| A2-D18 | Structured abstention |
| A2-D19 | Conversation trace provenance |
| A2-D20 | Current / Historical turns |
| A2-D21 | Desktop workspace layout |
| A2-D22 | Dynamic content containment |
| A2-D23 | Responsive behavior |
| A2-D24 | 16D-B decomposition (B1 / B2 / B3) |
| A2-D25 | 16D-C Training Mode dependency |
| A2-D26 | Downstream phases |

---

## A2-D01 — Amendment scope

A2 supersedes **only** the portions of S16-D17 / S16-D18 / A1 / plan non-scope
that freeze:

- single-turn-only **product** interaction;
- detached citation-set-only UX;
- prohibition on **all** conversational context (including linguistic
  reference resolution layered above the canonical pipeline).

**Preserve (MUST NOT weaken):**

- workspace / source identity;
- immutable snapshot model;
- source version lineage;
- strict-offline controls;
- Settings authority;
- operator locks;
- source-scoped retrieval;
- server-side source→document binding;
- dense / lexical / hybrid / rerank scope invariants;
- evidence / citation fail-closed behavior;
- exact-version historical evidence;
- current / historical snapshot semantics;
- no second RAG pipeline;
- no UI direct access to retrievers / vector DB;
- no fabricated PDF highlighting.

---

## A2-D02 — Product interaction model

Seneca's primary Ask surface becomes a **conversation**.

Conceptual desktop structure:

```text
┌──────────────────┬──────────────────────────────────┬──────────────────────┐
│ SOURCES          │ CONVERSATION                     │ EVIDENCE             │
│                  │                                  │                      │
│ source selection │ user turn                        │ active citation      │
│ source CRUD      │ grounded Seneca turn             │ source preview       │
│ capacity         │ user follow-up                   │ provenance           │
│                  │ grounded Seneca turn             │                      │
│                  │                                  │                      │
│                  │ Ask a follow-up…                 │                      │
└──────────────────┴──────────────────────────────────┴──────────────────────┘
```

The center conversation column is the primary surface.

Seneca retains its own design system. NotebookLM is **behavioral inspiration
only**. Do **NOT** copy Google assets, exact dimensions, styling, proprietary
artwork, or branding.

---

## A2-D03 — Conversation is not factual memory

**Freeze:**

> CONVERSATION PROVIDES LINGUISTIC CONTEXT.  
> RETRIEVED SOURCES PROVIDE FACTUAL AUTHORITY.

Previous assistant answers **MUST NOT** become evidence.

A follow-up such as “Which of those are supervised?” **MAY** use prior visible
turns to resolve what “those” refers to.

The resulting turn **MUST** still perform **fresh retrieval** from the
**current selected source scope**.

Previous assistant claims **MUST NOT** bypass retrieval or grounding.

---

## A2-D04 — Preserve canonical single-turn query API

Existing:

```text
POST /v1/workspaces/{workspace_id}/query
```

remains the canonical independent single-turn grounded query surface.

Preserve it for:

- evaluation;
- regression tests;
- direct API consumers;
- independent queries;
- scientific debugging.

**MUST NOT** convert `/query` itself into hidden conversation semantics.

Conversational orchestration **MUST** be layered above the same canonical
pipeline. **No second retrieval/generation pipeline.**

---

## A2-D05 — Conversation turn orchestration

### Frozen product surface

```text
POST /v1/workspaces/{workspace_id}/conversation/turn
```

### Frozen request DTO (`ConversationTurnRequest`)

```json
{
  "question": "string — current user turn text, trimmed, non-empty",
  "source_ids": ["optional — omit for all-active; exact list for subset"],
  "prior_turns": [
    {
      "role": "user" | "assistant",
      "text": "string — visible plain text of that turn"
    }
  ]
}
```

Rules:

- Backend remains **stateless** w.r.t. durable chat storage in A2 v1.
- Client supplies bounded visible conversation context from the **active**
  conversation only (`prior_turns` already truncated per A2-D07).
- Server **MUST NOT** load hidden older sessions or other workspaces.

### Frozen orchestration pipeline

```text
current user question
+
bounded prior visible conversation
        ↓
conversation-context resolver (A2-D06)
        ↓
standalone retrieval question
        ↓
EXISTING canonical source-scoped query pipeline
        ↓
fresh retrieval / evidence
        ↓
grounded answer v2 (A2-D12 / A2-D13)
        ↓
claim-level citations + public projection (A2-D14…A2-D16)
```

The contextualizer **MUST NOT** create its own retrieval path.

### Frozen response DTO (`ConversationTurnResponse`)

```json
{
  "workspace_id": "string",
  "workspace_revision": 0,
  "snapshot_id": "string",
  "product_mode_id": "grounded_v1",
  "trace_id": "string",
  "status": "answered | insufficient_evidence | model_abstain",
  "abstention_reason": "A2-D18 code | null",
  "question": "string — submitted user question",
  "standalone_question": "string — question used for retrieval",
  "context_used": true,
  "answer": "string | null",
  "answer_blocks": [ { "text": "string", "citation_refs": ["c1"] } ],
  "citations": [ "PublicCitation objects — A2-D14/A2-D15" ]
}
```

`answer` is the deterministic plain-text projection of `answer_blocks` (or
`null` when abstaining / insufficient).

---

## A2-D06 — Context resolver

Separate **versioned** prompt contract for reference resolution only.

### Purpose

Convert context-dependent user language into a **standalone retrieval
question**.

### Example

Conversation:

1. User: “What machine-learning methods are discussed?”
2. Assistant: *(grounded answer…)*
3. User: “Which of those are supervised?”

Resolved retrieval question:

> Which of the machine-learning methods discussed in the previous turn are
> supervised learning methods?

### Inputs

The resolver **MAY** inspect bounded prior USER and ASSISTANT visible turn
text plus the current user question.

### Instructions (normative)

- prior assistant statements are conversational context, **not** factual
  authority;
- do **not** answer the user;
- do **not** invent source facts;
- only resolve references / ellipsis / conversational dependency.

### Frozen resolver output

```json
{
  "standalone_question": "string",
  "context_used": true
}
```

No source evidence is required at this stage.

### Bypass / fail-closed

- First turn (`prior_turns` empty) **MAY** bypass the resolver;
  `standalone_question = question`, `context_used = false`.
- If context resolution fails for a context-dependent follow-up: **FAIL
  CLOSED**. Do **not** silently answer using ambiguous conversation state.
- User-facing outcome: request a clearer / restated question (application-owned
  canned language).

Prompt contract ID for traces: `conversation_context_resolver_v1` (exact string
frozen for provenance; implementation may version with `_vN` under later
accepted amendment).

---

## A2-D07 — Bounded context

Conversation context **MUST** be bounded.

### Frozen bound

| Bound | Value |
| --- | --- |
| Max completed turn pairs | most recent **6** user+assistant completed pairs (≤ **12** role turns) |
| Hard character ceiling | **12_000** Unicode characters across all `prior_turns[].text` concatenated |
| Scope | **current active conversation only** |

Truncation algorithm (deterministic):

1. Keep newest completed pairs first;
2. Drop oldest pairs until pair count ≤ 6;
3. If still over character ceiling, drop oldest remaining pairs until under
   ceiling (never drop the current question — it is not in `prior_turns`).

**MUST NOT:**

- cross-workspace context;
- cross-conversation context;
- account-level memory;
- hidden old sessions;
- unrelated browser history.

**New conversation** resets conversational context (A2-D09).

---

## A2-D08 — Conversation persistence v1

Initial release scope: conversation is **local presentation / product state**.

- Session-local persistence is acceptable for Slice 16.
- A2 **SHOULD** preserve `sessionStorage`-based active conversation state.
- A2 **MAY** retain the current conversation across SPA navigation / refresh in
  the same browser session.

Durable named conversation storage under `/data` is **NOT** required by A2.

**Explicitly deferred** (unless separately authorized later):

- conversation library;
- named persistent chats;
- cross-device sync;
- multi-user conversation storage.

---

## A2-D09 — New conversation

The Conversation UI **MUST** expose:

```text
+ New conversation
```

Semantics:

- clears active conversation context;
- presents a clean composer;
- does **NOT** modify workspace sources;
- does **NOT** rebuild a snapshot;
- does **NOT** change source selection (selection remains as-is);
- does **NOT** delete scientific evidence / vault history.

If the current conversation is non-empty, UX **MAY** require confirmation.

---

## A2-D10 — Composer contract

After Send:

1. user turn becomes immutable display content;
2. composer clears;
3. empty composer is immediately ready for the next question;
4. focus returns to composer when appropriate.

No requirement to manually erase the previous question.

Pending response **MUST NOT** prevent the sent question from becoming visible.

Prevent duplicate sends (disable Send while the turn is in flight).

No fake percentage / ETA.

---

## A2-D11 — Source scope per turn

Each turn binds to the source selection effective **when that turn is
submitted**.

Current source checkboxes govern the **next** turn.

Changing source selection later:

- does **not** rewrite previous turns;
- does **not** rewrite previous provenance;
- affects future turns only.

Each completed turn stores / presents:

- submitted logical source scope;
- workspace revision;
- snapshot ID;
- exact citation source versions.

Historical turns remain inspectable through exact-version evidence.

Selection-mode intent (`all` | `subset`) from product UX **MUST** continue to
govern whether `source_ids` may be omitted (follow-all) vs always sent
(explicit subset). Silent broaden remains forbidden.

---

## A2-D12 — Grounded answer v2

Replace model-facing flat `answer + citation_ids` with a structured claim/block
contract.

### Frozen model-facing schema (`GroundedAnswerV2`)

```json
{
  "abstain": false,
  "blocks": [
    {
      "text": "Linear regression is introduced as an optimization technique.",
      "evidence_handles": ["E1"]
    },
    {
      "text": "KNN is presented as a non-parametric learning method.",
      "evidence_handles": ["E2", "E3"]
    }
  ],
  "abstention_reason": null
}
```

Abstention:

```json
{
  "abstain": true,
  "blocks": [],
  "abstention_reason": "insufficient_support"
}
```

### Validation (fail closed)

Server validator **MUST** fail closed on:

- nonexistent evidence handle;
- duplicate / invalid handle structure;
- answered block without ≥ 1 evidence handle;
- empty `text` on an answered block;
- malformed schema;
- `abstain: false` with empty `blocks`;
- `abstain: true` with non-empty `blocks` or non-null unsupported answer text;
- `abstention_reason` outside the closed enum (A2-D18) when abstaining.

Each answered block **MUST** have one or more supporting evidence handles.
Unsupported answer blocks are **not** permitted.

Prompt contract ID: `grounded_answer_v2` (replace model-facing use of flat
`citation_ids` + raw `ev_…` citation language for product generation).

---

## A2-D13 — Response-local evidence handles

The generator **MUST NOT** receive canonical `ev_…` IDs as its citation
language.

Before generation, the application assigns short **response-local** handles:

```text
E1, E2, E3, …
```

Prompt evidence becomes:

```text
[EVIDENCE E1]
…
[/EVIDENCE E1]
```

The application owns:

```text
E1 → canonical evidence_unit_id
```

Generator returns `E1` / `E2` / ….

After validation the server resolves handles back to canonical evidence units.

Canonical `ev_…` IDs remain **internal / provenance** identities and **MUST
NOT** be required in user-facing answer prose.

---

## A2-D14 — Public answer projection

Backward-compatible public projection where practical.

### Frozen public shapes

**`answer`** — deterministic plain-text projection of `answer_blocks` joined by
blank lines (or `null` when not answered).

**`answer_blocks`:**

```json
[
  {
    "text": "…",
    "citation_refs": ["c1", "c2"]
  }
]
```

**`citations`:** resolved public citation objects (existing public fields plus
A2-D15 excerpt). Each `citation_refs` value is an **application-owned** stable
ref within the response (e.g. `c1`), **not** a model-invented public number.

### Numbering

UI numbering (`¹`, `²`, … or `1`, `2`, …) is **presentation**, not model
authority. The application assigns display indices from the ordered unique
citation set referenced by blocks.

Existing `answer` / `citations` consumers **SHOULD** remain viable: consumers
that only read `answer` + `citations[]` continue to work; consumers that need
claim binding read `answer_blocks`.

---

## A2-D15 — Citation excerpt

Claim citation hover / focus requires a bounded evidence excerpt without
loading an entire PDF.

### Frozen excerpt rules

| Rule | Value |
| --- | --- |
| Source | exact `EvidenceUnit` used for that answer (accepted context evidence) |
| Form | plain text only |
| Max length | **400** Unicode characters |
| Markup | no executable markup; strip/ignore HTML-like tags if present in unit text |
| Clipped | boolean `excerpt_clipped` when truncated |
| Provenance | same source_id / version / page / line / section fields as citation |

Excerpt **MUST** come from accepted context evidence, **not** from
model-generated citation prose.

### Public citation object (additive fields)

Existing citation identity / location fields remain. A2 adds:

```json
{
  "citation_ref": "c1",
  "excerpt": "plain text…",
  "excerpt_clipped": false
}
```

---

## A2-D16 — Notebook-style claim citation UX

Render citation markers immediately after the supported answer block / claim:

```text
Linear regression is optimized with gradient descent.¹
```

### Desktop

- hover **OR** keyboard focus on `¹` → compact evidence card.

Card **SHOULD** show:

- source display name · page (when present);
- section title / path (when present);
- bounded evidence excerpt;
- “Open evidence →”.

Click / Enter:

- select exact citation;
- right Evidence pane opens / updates;
- exact source version;
- exact page / context.

### Touch

- tap citation marker → accessible evidence interaction;
- **no hover dependency**.

Hover **MUST NOT** be the only accessible path. Keyboard focus + Enter / Space
equivalence is required.

---

## A2-D17 — Evidence pane role

The right Evidence pane becomes **deep inspection**.

| Surface | Role |
| --- | --- |
| Claim citation card | quick evidence check |
| Evidence pane | deep exact-version inspection |

**Preserve:**

- PDF cited page navigation;
- exact historical source version;
- text line context;
- section / page / line provenance;
- Current / Historical state;
- trace provenance;
- safe source preview.

**MUST NOT** fabricate PDF text highlights.

Provenance **MUST** match the active evidence mode (citation / query evidence
vs direct current-source inspection) so Current / Historical labels cannot
contradict within one Evidence state.

---

## A2-D18 — Structured abstention

`model_abstain` alone is too opaque for release UX.

### Frozen closed reason codes

| Code | Meaning |
| --- | --- |
| `no_evidence` | no usable evidence units in scoped retrieval |
| `insufficient_support` | evidence present but does not support an answer |
| `conflicting_evidence` | scoped evidence conflicts materially |
| `ambiguous_request` | question / context dependency cannot be resolved safely |
| `model_declined` | model abstained under grounded-answer-v2 policy |

Rules:

- Deterministic application states are **application-owned** (e.g. empty scope,
  context-resolver fail-closed → `ambiguous_request`).
- Where a reason originates from the model, the model **MUST** choose from this
  closed validated enum.
- UI uses application-owned canned language.
- **MUST NOT** expose arbitrary provider / model error prose as an explanation.
- **MUST NOT** invent a reason the system cannot support.

Public field: `abstention_reason` (nullable; required non-null when
`status = model_abstain` or application fail-closed abstention paths that
surface as abstention).

`insufficient_evidence` remains a distinct successful safety status for
retrieval/context emptiness where already defined; it **MAY** map UI copy via
`no_evidence` / `insufficient_support` as appropriate without collapsing
scientific status enums incorrectly.

---

## A2-D19 — Conversation trace provenance

Backend scientific / product traces **MUST** remain privacy-minimized.

**MUST NOT** persist complete conversation text into `ProductTrace` merely
because the UI is conversational.

**Record sufficient provenance**, such as:

- conversation-context resolver invoked: yes / no;
- prior-turn count used;
- original current-question hash;
- standalone resolved-question hash;
- source scope;
- workspace revision / snapshot;
- normal retrieval / generation provenance;
- prompt contract IDs (`conversation_context_resolver_v1`,
  `grounded_answer_v2`).

**MUST NOT** record:

- API secrets;
- raw full conversation transcript;
- raw source bytes;
- filesystem paths.

---

## A2-D20 — Current / Historical turns

Each assistant turn is bound to its query snapshot.

```text
turn.snapshot_id == workspace.current_snapshot_id
  → Current snapshot
else
  → Historical snapshot
```

Display-only metadata changes do **not** make a turn historical if the snapshot
is unchanged.

Source mutation publishing N+1 makes prior N turns Historical.

Clicking an old citation **MUST** still inspect the exact historical source
version.

---

## A2-D21 — Desktop workspace layout

Manual use proved the legacy ~72rem shell inadequate for the knowledge
workspace.

- Workspace detail becomes a **wide product surface**.
- Overview / Settings retain readable standard width.

### Frozen desktop target

| Item | Target |
| --- | --- |
| Max content width (workspace detail) | **96rem** (viewport-responsive; may use `min(96rem, 100%)`) |
| Sources track | **18rem** (allowed band 17–20rem) |
| Conversation track | `minmax(0, 1fr)` — dominant |
| Evidence track | **24rem** (allowed band 22–28rem) |

A2 freezes **behavior**, not pixel-copy of another product.

---

## A2-D22 — Dynamic content containment

No user / model / source / provenance string may force a grid track wider than
its allocation.

Design **MUST** require:

- `min-width: 0` through nested flex / grid containers;
- overflow-wrap for dynamic prose / identifiers;
- preserved readable answer newlines.

**MUST NOT** use `overflow: hidden` to conceal answer / evidence content.

Must safely handle long model strings, questions, filenames, section paths, and
trace / evidence identities.

---

## A2-D23 — Responsive behavior

| Viewport | Behavior |
| --- | --- |
| Desktop | Sources \| Conversation \| Evidence |
| Narrow | Conversation primary; Sources and Evidence use drawers |

Preserve the accepted **no-stacked-modal** rule.

Opening source preview from Sources drawer:

```text
close Sources → open Evidence
```

Citation on narrow layout: open **exactly one** Evidence drawer.

Viewport becoming desktop: close responsive drawer state / clear modal inert.

---

## A2-D24 — 16D-B decomposition

### Revised implementation sequence (frozen by A2 candidate)

```text
16D-A
Product foundation + safe source-scoped retrieval
ACCEPTED / SEALED
        │
        ▼
16D-B1
Observed Ask/Evidence engineering substrate
6b6524001f063a628505f572e7ca13d954a38260
OBSERVED IMPLEMENTATION CANDIDATE
PRODUCT ACCEPTANCE WITHHELD
NOT SEALED
        │
        ▼
16D-B2
Grounded Answer V2
claim → evidence binding
citation popovers
structured abstention
NOT AUTHORIZED
        │
        ▼
16D-B3
Conversational workspace
context resolution
fresh retrieval every turn
New conversation
release-grade layout
NOT AUTHORIZED
        │
        ▼
16D-C
Training Mode
NOT AUTHORIZED
        │
        ▼
16E → 16F → 16G → 16H
```

### 16D-B1 — Engineering foundation

Observed candidate: `6b6524001f063a628505f572e7ca13d954a38260`

```text
STATUS:
OBSERVED IMPLEMENTATION CANDIDATE
PRODUCT ACCEPTANCE WITHHELD
NOT SEALED
```

Useful substrate preserved as engineering input (not accepted release UX):

- source selection;
- source-scoped query;
- exact-version source evidence;
- PDF / text preview;
- Evidence panel;
- snapshot status;
- session-state primitives.

**MUST NOT** accept B1 merely through A2 design authorization or acceptance.

### 16D-B2 — Grounded Answer V2 & claim citations

Future **separately authorized** implementation scope:

- response-local E1/E2 evidence handles;
- grounded-answer-v2 structured blocks;
- strict block→evidence validation;
- backward-compatible answer projection;
- bounded evidence excerpts;
- claim citation numbering;
- hover / focus / tap citation card;
- citation→Evidence navigation;
- structured abstention reasons;
- eliminate raw canonical evidence IDs as generator citation language.

**NO** conversational orchestration yet.

```text
16D-B2: NOT AUTHORIZED
```

### 16D-B3 — Conversational workspace

Future **separately authorized** implementation scope:

- conversation turn orchestration;
- context resolver;
- bounded prior visible context;
- fresh retrieval every turn;
- New conversation;
- clean / resetting composer;
- conversational thread presentation;
- per-turn source / snapshot provenance;
- Current / Historical turn status;
- wide workspace layout;
- overflow containment;
- final responsive drawer behavior.

```text
16D-B3: NOT AUTHORIZED
```

**16D-B overall** remains incomplete until B2 + B3 are reviewed and human
accepted. Monolithic “accept 16D-B” is retired in favor of B1 (observed) /
B2 / B3 gates.

---

## A2-D25 — 16D-C Training Mode

16D-C remains **required** Slice-16 scope.

Training Mode builds on the **conversational** workspace:

| Training concept | Operates on |
| --- | --- |
| saved prompt | seed / start a conversation turn |
| hide / reveal answer | grounded assistant turn |
| hide / reveal evidence | claim citations / Evidence pane |
| presentation typography / fullscreen | conversation presentation |

Training Mode **MUST NOT** restore the obsolete isolated-question UX.

Still **MUST NOT**:

- LMS;
- accounts;
- grading;
- certification.

```text
16D-C: NOT AUTHORIZED
```

---

## A2-D26 — Downstream phases

Do **NOT** redesign unrelated later phases merely because A2 exists.

Preserve sequence:

```text
16D-C — Training Mode
16E   — Engineering Evidence
16F   — Gold Lab data plane
16G   — Gold Lab games / pedagogical training compiler
16H   — Integration / accessibility / portfolio acceptance
```

16H acceptance **MUST** eventually include:

- conversational workflow;
- claim citation accessibility;
- citation hover / focus / tap equivalence;
- exact historical evidence;
- wide desktop workspace;
- responsive drawer behavior;
- 200% zoom;
- keyboard operation.

Slices 17 / 18 remain **NOT AUTHORIZED**.

---

## Explicit non-goals

A2 **MUST NOT** authorize:

- global ChatGPT-style memory;
- cross-workspace memory;
- cross-conversation memory;
- multi-user chat;
- cloud conversation sync;
- autonomous agents;
- web search;
- arbitrary tool calling;
- second RAG pipeline;
- using prior assistant answers as evidence;
- hidden source expansion outside selected source scope;
- fabricated inline citation positions;
- fabricated PDF highlights;
- durable named-chat library unless separately authorized;
- implementation of B2 / B3 / C;
- merge.

---

## Superseded-clause inventory

A2 **proposes** to supersede the following **if and only if** A2 is human
accepted. Until then, existing authority remains effective.

| Prior clause | Prior freeze | A2 supersession |
| --- | --- | --- |
| **S16-D17** Query experience | Backend/product framed as single-turn only; conversational memory deferred; UI history must not be sent as query context | Product Ask becomes conversation; linguistic context **may** be sent to the **context resolver** only; factual authority remains fresh retrieval via canonical pipeline; `/query` stays single-turn (A2-D04) |
| **S16-D18** Citations and evidence | Citation chips open evidence; flat chip-centric UX implied | Claim-level markers + hover/focus/tap card + Evidence deep pane (A2-D16/A2-D17); chips alone are insufficient |
| **S16-D18** abstention | `insufficient_evidence` / `model_abstain` as safety outcomes | Retained as statuses; **augmented** with closed `abstention_reason` codes (A2-D18) |
| **S16-D19** Training Mode (interaction assumptions) | Hide/reveal answer/citations on isolated question UX | Operates on conversational turns + claim citations (A2-D25) |
| **S16-D35** deferral “conversational memory / multi-turn RAG” | Blanket Slice-16 deferral | Narrowly superseded: **linguistic** multi-turn context + resolver is in scope; **factual conversational memory** and using prior answers as evidence remain **forbidden** (A2-D03) |
| **A1-D02** Sources \| Ask \| Evidence framing | Ask as question/answer workspace | Center column becomes Conversation (A2-D02) |
| **A1-D13** source-selection UI state | Must not send as hidden conversational history | Selection still not chat memory; conversation context is a separate bounded prior-turns channel (A2-D05/D07) |
| **A1 §16D-B** scope | Single-turn Ask; citation chips; no conversational memory; session-local visual history | Replaced by B1 observed / B2 claim citations / B3 conversation (A2-D24) |
| **Implementation plan §16D-B** | Same single-turn Ask decomposition | Same B1/B2/B3 replacement |
| **Implementation plan “Explicit non-scope”** | “multi-turn conversational RAG” | Replaced by A2’s narrower forbid: no factual memory / no second pipeline; linguistic conversation turns authorized by A2 |
| **ROADMAP / M7 pointers** stating product query remains single-turn only / 16D-B not authorized without nuance | Status pointers | Updated to A2 candidate + B1 observed / B2/B3 not authorized |

**Not superseded:** S16-D01…D16, D20…D34; A1-D01, A1-D03…A1-D12, A1-D14…A1-D17
capacity/settings/query-scope science; 16D-A sealed implementation.

---

## Governance status (while A2 is candidate)

```text
LAST SEALED IMPLEMENTATION BASELINE:
a952a75bc07191b213a5113eee53cb967fef8326

OBSERVED 16D-B CANDIDATE (B1 substrate):
6b6524001f063a628505f572e7ca13d954a38260
PRODUCT ACCEPTANCE WITHHELD / NOT SEALED

A2:
DESIGN CANDIDATE / HUMAN ACCEPTANCE PENDING

16D-B:
PRODUCT ACCEPTANCE WITHHELD PENDING A2

16D-B2: NOT AUTHORIZED
16D-B3: NOT AUTHORIZED
16D-C:  NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
Slice 17/18: NOT AUTHORIZED
M7 closeout: NOT AUTHORIZED

Slice 16: IN PROGRESS / NOT COMPLETE
```

Original locked design and A1 remain valid except where A2 would explicitly
supersede them **IF AND ONLY IF** A2 receives human acceptance.

---

## Authorization note

```text
DESIGN WORK ONLY
NO IMPLEMENTATION
NO MERGE
NO 16D-B2
NO 16D-B3
NO 16D-C
```
