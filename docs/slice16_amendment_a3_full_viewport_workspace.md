# Slice 16 Design Amendment A3 — Full-Viewport Conversational Workspace & Collapsible Desktop Rails

```text
SLICE 16 DESIGN AMENDMENT A3

STATUS: ACCEPTED / LOCKED / SEALED
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT REVIEW: PASSED

MATERIALIZATION:
da1082d95630c12eaf0ce1a3b8d005aaa60d2f73

IMPLEMENTED BY ACCEPTED 16D-B3:
9c178ffb033cde41849379fc914f321697ff8691

AUTHORIZED REWORK 3 BASELINE:
528e7dbb10fdde24ea1ea7db71a4e35c2a9222e1

REWORK 2 IMPLEMENTATION:
b2cdad859e9467fd74dfe801bcdba721137d0afe

ORIGINAL SLICE-16 AUTHORITY:
ACCEPTED / LOCKED
e2e7475076ad18d4c4ae8d939389ceeffdeff6d8

AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30

AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7
  closeout f0bdf78d0ae6a79737055d324b22fc35e1e501f5

16D-B2: COMPLETE / ACCEPTED / SEALED
  baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149

16D-B3: COMPLETE / ACCEPTED / SEALED
  9c178ffb033cde41849379fc914f321697ff8691
16D-C: NOT AUTHORIZED / NOT STARTED
16E–16H: NOT AUTHORIZED

SLICE 16 OVERALL:
IN PROGRESS / NOT COMPLETE
```

## Authority relationship

Amendment A3 **modifies only B3 desktop workspace presentation**. It
supersedes only previously frozen B3 desktop layout assumptions where they
conflict with the decisions below (including the prior ~96rem desktop max-width
assumption for workspace detail).

A3 does **not** alter:

- backend conversation semantics;
- resolver semantics;
- admission ordering;
- snapshot binding;
- scientific retrieval/generation;
- B2 answer/citation semantics;
- conversation/query traces;
- session conversation semantics;
- mobile/narrow drawer architecture;
- Training Mode;
- later Slice-16 gates.

A3 supplements accepted A1/A2 and the Slice-16 design authority for the
workspace-detail product surface only. Acceptance of B3 Rework 3 remains a
separate human gate; this document materializes the human-approved amendment
text for implementation.

---

## A3-D01 — Workspace detail is a full-viewport application surface

The workspace-detail route must no longer behave as a centered document/page
constrained to approximately 96rem.

For workspace detail only:

- remove the effective desktop max-width constraint;
- use substantially the full available viewport width;
- retain only a modest horizontal application gutter;
- avoid large decorative empty margins on wide displays.

Overview, Settings, ordinary forms and other reading-oriented screens may
retain their normal readable centered width.

Do not globally remove max-width constraints from the whole application.

At a wide desktop viewport (approximately 1920–2048 px), Sources |
Conversation | Evidence must occupy most of the usable width beneath
application navigation — not large blank margins flanking a centered three-pane
card.

---

## A3-D02 — Conversation remains the dominant elastic surface

Desktop open-state proportions should be approximately:

| Pane | Target share |
| --- | --- |
| Sources | ~18–22% |
| Conversation | ~50–60% |
| Evidence | ~22–28% |

These are design targets, not fixed pixel ratios. Use responsive/clamped tracks
rather than rigid percentages.

Illustrative (not mandatory exact CSS):

```css
grid-template-columns:
  clamp(15rem, 18vw, 22rem)
  minmax(0, 1fr)
  clamp(20rem, 24vw, 30rem);
```

Invariants:

- center remains dominant;
- Sources gets enough width for filenames/actions;
- Evidence gets enough width for real document inspection;
- no horizontal page overflow;
- tracks adapt naturally across desktop widths.

Do not solve the problem by simply changing 96rem to another arbitrary large
max-width.

---

## A3-D03 — Use the available viewport height

On desktop, the conversational workspace should behave as an application
workbench rather than a short card stack floating near the top of a long page.

The workspace region should make effective use of the available vertical
viewport beneath application/workspace headers.

Desired behavior:

- Sources can scroll independently when its source list is long;
- Conversation can scroll independently when thread history is long;
- Evidence can scroll independently when preview/provenance is long;
- the composer remains readily accessible near the bottom of the conversation
  work area;
- long content must not force unrelated panes to become unusably tall.

A sticky conversation composer inside the conversation pane is permitted and
preferred if it can be implemented without overlap or accessibility regressions.

Avoid brittle hard-coded viewport-height arithmetic when the existing shell can
provide a flex/grid solution.

---

## A3-D04 — Sources and Evidence are independently collapsible

On desktop only, Sources and Evidence must each have an accessible
collapse/expand control.

Default state:

- Sources: expanded
- Evidence: expanded

Supported states: both expanded; Sources collapsed / Evidence expanded; Sources
expanded / Evidence collapsed; both collapsed.

When a rail collapses, Conversation expands into the released space.
Collapsed rails must retain a compact, obvious affordance for restoration.
Do not completely remove the user's ability to reopen the rail.

---

## A3-D05 — Accessible rail controls

Collapse controls must be real buttons.

Required semantics include:

- accessible label such as Collapse Sources / Expand Sources;
- accessible label such as Collapse Evidence / Expand Evidence;
- `aria-expanded`;
- `aria-controls` where appropriate;
- keyboard activation;
- visible focus state.

Do not use click-only decorative glyphs. Icon-only visual presentation is
permitted if an accessible name is supplied.

---

## A3-D06 — Rail collapse state is UI state only

Desktop rail state is presentation preference.

It must not:

- mutate workspace revision;
- mutate source state;
- create snapshots;
- create traces;
- enter conversation `prior_turns`;
- require a backend API.

It may be held in React state or session-local browser storage. If persisted,
keep it browser/session UI state only. No durable server-side preference system
is authorized.

---

## A3-D07 — Evidence interactions override collapsed Evidence rail

If Evidence is collapsed and the user performs an action whose purpose is to
inspect evidence, the Evidence rail must automatically become visible on
desktop.

Examples:

- clicking a claim citation;
- activating a citation with Enter/Space;
- opening a source preview that targets Evidence.

Required behavior: Evidence expands and the exact selected evidence is visible.
Do not leave the user with an invisible successful selection.
Preserve exact B2 historical-version behavior.

---

## A3-D08 — Narrow/mobile behavior remains drawer-based

Do not replace the accepted narrow-screen architecture with collapsing desktop
rails.

At narrow viewport:

- Conversation remains primary;
- Sources uses the Sources drawer;
- Evidence uses the Evidence drawer;
- drawers remain mutually exclusive;
- citation opens exactly one Evidence drawer;
- source preview closes Sources before opening Evidence;
- returning to desktop clears drawer/inert modal state.

Desktop rail-collapse state may be remembered when transitioning through narrow
mode, but narrow drawers must remain independent transient UI state.

---

## A3-D09 — No dynamic content may enlarge a pane track

All nested Evidence and Sources content must respect the track assigned by the
workspace grid.

Audit the complete containment chain (layout → panels → preview → provenance →
identifiers → filenames → previews). Every grid/flex descendant that can impose
an intrinsic width must be made shrinkable where required.

Use appropriate combinations of `min-width: 0`, `max-width: 100%`,
`overflow-wrap: anywhere`, `word-break: break-word` / `break-all`, and
`box-sizing: border-box`.

Do not rely on `overflow: hidden` to discard substantive information.

---

## A3-D10 — Embedded preview containment

PDF/text preview surfaces must never force the Evidence track wider than its
grid allocation.

For embedded document elements:

- width must fit the pane;
- maximum width must not exceed the pane;
- intrinsic content/toolbars must remain contained inside the preview surface;
- internal scrolling is preferable to expanding the outer layout.

The browser's PDF viewer may scroll internally. Do not horizontally expand the
entire application to accommodate embedded preview content.

---

## A3-D11 — No page-level horizontal scrollbar

At supported desktop and narrow widths, normal workspace use must not produce
horizontal overflow on the overall page, including with deliberately hostile
content (long trace IDs, section paths, filenames, questions, paragraphs).

A pane may have an intentionally local scroll surface where appropriate, but
the workspace/page itself must not horizontally scroll because of content.

---

## Visual direction

Use NotebookLM only as a spatial reference for application-surface utilization.
Do not clone its branding or exact UI. Preserve Seneca typography, tokens, and
visual identity unless a minor adjustment is necessary for this layout.

---

## Strict non-scope

A3 / Rework 3 does not authorize: Training Mode; fullscreen presentation;
saved prompts; answer hide/reveal; 16E–16H; dark-mode or branding redesign;
durable account layout preferences; draggable/resizable splitters; multi-window
UI; backend preference APIs; second RAG pipeline; retrieval/generation tuning;
scientific configuration changes.

Collapsible rails are authorized. Arbitrary draggable/resizable panes are not.

---

## Implementation / seal note

Rework 3 on
`implementation/16d-b3-conversational-workspace` implemented this amendment.
Accepted product implementation: `9c178ffb033cde41849379fc914f321697ff8691`.
Amendment A3 is **ACCEPTED / LOCKED / SEALED** with **16D-B3**. Scope remains
bounded to workspace-detail presentation (full-viewport workbench, collapsible
desktop Sources/Evidence rails, Evidence auto-expand on inspection,
containment, viewport-height workbench, responsive drawer preservation). Do not
broaden A3 after acceptance. **16D-C** remains **NOT AUTHORIZED**.
