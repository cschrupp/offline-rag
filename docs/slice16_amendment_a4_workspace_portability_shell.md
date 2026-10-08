# Slice 16 Design Amendment A4 — Workspace UX Portability & Shell Integration

```text
SLICE 16 DESIGN AMENDMENT A4

STATUS: HUMAN-APPROVED / LOCKED FOR IMPLEMENTATION
ACCEPTANCE / SEAL: PENDING

AUTHORIZED REWORK 2 BASELINE:
18bc60da038e210b1b8f2f9aa26884e962a15f8f

ORIGINAL 16D-C IMPLEMENTATION:
2266d7b16bf01e11c5ca69b2ffe4d7f4e0e821ab

REWORK 1 IMPLEMENTATION:
4489d6fb295271c65dae2c9f38e3f53bab456ff8

ORIGINAL SLICE-16 AUTHORITY:
ACCEPTED / LOCKED
e2e7475076ad18d4c4ae8d939389ceeffdeff6d8

AMENDMENT A1: ACCEPTED / LOCKED
  5060e2aeb4825f265072a1f870c3c963eace3b30

AMENDMENT A2: ACCEPTED / LOCKED / SEALED
  dce3456e519cb6c96570e20f5af800d00cafb5a7

AMENDMENT A3: ACCEPTED / LOCKED / SEALED
  da1082d95630c12eaf0ce1a3b8d005aaa60d2f73

16D-B3: COMPLETE / ACCEPTED / SEALED
  9c178ffb033cde41849379fc914f321697ff8691

16D-C: REWORK 2 AUTHORIZED / HUMAN ACCEPTANCE PENDING
16E–16H: NOT AUTHORIZED

SLICE 16 OVERALL:
IN PROGRESS / NOT COMPLETE
```

## Authority relationship

Amendment A4 is **additive** presentation/integration authority for 16D-C
Rework 2. It supplements accepted A1/A2/A3 and S16-D19 Training Mode.

A4 does **not** reopen or alter:

- sealed B3 conversation/scientific contracts;
- sealed A3 full-viewport workspace / collapsible rails;
- `/conversation/turn`, resolver, prior turns, traces;
- B2 citation semantics;
- ingestion pipeline;
- later Slice-16 gates (16E–16H).

Human live-product review after Rework 1 identified three acceptance blockers
addressed here: Question Bank vertical growth, portable bank/conversation
export, and global header vs full-width workspace shell misalignment.

---

## A4-D01 — Compact Question Bank

The permanently expanded saved-question list is rejected. Saved questions become
a compact **Question Bank**, closed by default. Saved rows MUST NOT remain in
normal document flow. Bank size MUST NOT progressively push the conversation
workbench downward.

---

## A4-D02 — Question Bank surface

**Desktop:** `Question bank (N)` opens a bounded anchored panel/popover with
fixed/max height and internal scrolling. Opening MUST NOT materially resize the
workspace. Closing returns focus to the trigger.

**Narrow/mobile:** reuse an existing Seneca dialog/drawer pattern. Do not invent
a second inaccessible modal system. Do not stack over open Sources/Evidence drawers.

Minimum content: title + count, search, scrollable rows with compact actions,
Import / Export JSON / Export Markdown.

Search is presentation-only case-insensitive substring filter. Searching MUST
NOT mutate stored prompts.

---

## A4-D03 — Composer-adjacent Save

Move **Save question** beside the composer with Send and Question bank:

```text
question being composed
        ↓
[Send] [Save question] [Question bank (N)]
```

Presentation view remains a Training Mode-level control. Save semantics remain
local, per-workspace, no network, no auto-Send, no scientific mutation.

---

## A4-D04 — Question selection

Selection seeds the composer only. MUST NOT auto-Send. Selected text enters
`prior_turns` only after ordinary B3 submission.

---

## A4-D05 — Question Bank delete

Delete remains supported via compact accessible row action inside the bank
(e.g. `Delete saved question: <question>`). Do not show large permanent Delete
controls in the main workspace chrome.

---

## A4-D06 — Question Bank JSON format

JSON is the canonical interchange format (`seneca-question-bank` v1):

```json
{
  "format": "seneca-question-bank",
  "version": 1,
  "title": "…",
  "exported_at": "…",
  "questions": [{ "text": "…" }]
}
```

Do NOT export browser-local IDs, workspace IDs, traces, answers, or model data.
Import creates fresh local IDs. Wrong format/version fails clearly without
mutating the existing bank.

---

## A4-D07 — Question Bank Markdown format

Human-readable interchange. Export uses optional title heading and top-level
`- ` bullets. Import recognizes optional headings, blank lines, and top-level
bullets only. Do not infer questions from prose, tables, nested lists, or code
blocks. JSON remains lossless canonical. Extensions: `.json`, `.md`, `.markdown`.

---

## A4-D08 — Question Bank import = Merge

V1 is Merge only (no Replace). Preserve `PROMPT_MAX = 100`. Duplicate detection:
trim then exact text equality. Classify: new / duplicate / invalid /
capacity-skipped.

---

## A4-D09 — Import preview / confirmation

Parse first; confirm before mutate. Show new/duplicate/invalid counts. Commit
only on explicit confirmation. Zero importable → no commit. Corrupt files leave
bank untouched. Reasonable deterministic file-size guard authorized.

---

## A4-D10 — Question Bank IO is local only

Import/export MUST NOT call backend APIs, mutate revision/sources/snapshots,
create traces, send the bank to the model, or enter `prior_turns`.

---

## A4-D11 — Conversation export in both modes

`Export conversation` in Conversation / Training conversation headers with
Export as Markdown and Export as JSON. Download only. No conversation import.
No backend conversation-save APIs.

---

## A4-D12 — Export ignores Training reveal state

Hidden-on-screen answers still export. Do not serialize `revealMap`.

---

## A4-D13 — Conversation Markdown is source-ready

Markdown MUST include a mandatory derived-Seneca / not-primary-evidence warning
and be usable as human notes or later deliberate Add Sources upload. No
ingestion change authorized.

---

## A4-D14 — Markdown citation representation

Prefer reconstructing readable markers from `answer_blocks` / citations with a
Sources section (display name, version, page/line, section path). Do not needlessly
reproduce full evidence excerpts. Full citation objects remain in JSON.

---

## A4-D15 — Non-answered turn export

Preserve clarification / insufficient_evidence / model_abstain with accepted
application copy. Failed/incomplete turns marked explicitly. Prefer disabling
export while a turn is pending.

---

## A4-D16 — Conversation JSON archive

Versioned `seneca-conversation` v1 retaining scientifically meaningful B3 fields.
`exported_from_view` is `normal` | `training` (UI view at export only).

---

## A4-D17 — Human-mediated source promotion — hard invariant

```text
Export conversation ≠ source ingestion
```

Export MUST NOT add sources, call Add Sources, upload, mutate revision/snapshot,
or create scientific traces. Only a later explicit human Add Sources action may
promote an exported artifact.

Forbidden: Save as source / Export and add / Promote to source equivalents.

---

## A4-D18 — No special trust for re-ingested conversations

Manual re-upload uses ordinary ingestion. No special weighting or scientific
document class. Derived warning survives as artifact text. Do not modify
ingestion for A4.

---

## A4-D19 — Browser download implementation

Blob + temporary `<a download>` is sufficient. Prefer pure serializers returning
filename / mime / content plus a thin download adapter. No new dependency.
No File System Access API requirement.

---

## A4-D20 — Safe filenames

Human-readable sanitized names (workspace title slug). Do not place workspace
IDs or trace IDs in filenames by default.

---

## A4-D21 — Global application header alignment

Application header MUST use the application viewport (not centered
`--max-width` dead space). Brand near left gutter; primary nav near right
gutter; modest gutters; no edge-touching.

---

## A4-D22 — Header is global; content width is route-specific

Header full-width on all routes. Overview/Settings/forms may retain max-width
bodies. Workspace detail remains A3 full-width workbench.

---

## A4-D23 — Mobile header preservation

Desktop header width changes MUST NOT regress mobile menu toggle, a11y, Settings
link, focus, or horizontal overflow.

---

## Presentation Mode integration

Presentation Mode MUST NOT reintroduce permanently expanded Question Bank rows.
Compact bank access remains; export may remain; no scientific changes.

---

## Rework 1 remains closed

Preserve C-R1 (missing answered reveal defaults hidden) and C-R2 (Reveal evidence
binds the selected turn). Do not regress.

---

## Decision index

| ID | Topic |
| --- | --- |
| A4-D01 | Compact Question Bank |
| A4-D02 | Question Bank surface |
| A4-D03 | Composer-adjacent Save |
| A4-D04 | Question selection |
| A4-D05 | Question Bank delete |
| A4-D06 | Question Bank JSON |
| A4-D07 | Question Bank Markdown |
| A4-D08 | Import merge |
| A4-D09 | Import preview/confirm |
| A4-D10 | Local-only bank IO |
| A4-D11 | Conversation export both modes |
| A4-D12 | Export ignores reveal state |
| A4-D13 | Source-ready Markdown |
| A4-D14 | Markdown citations |
| A4-D15 | Non-answered export |
| A4-D16 | Conversation JSON |
| A4-D17 | Human-mediated source promotion |
| A4-D18 | No special re-ingest trust |
| A4-D19 | Browser download |
| A4-D20 | Safe filenames |
| A4-D21 | Global header alignment |
| A4-D22 | Header vs body width |
| A4-D23 | Mobile header preservation |

---

## Authorization note

```text
AMENDMENT A4:
HUMAN-APPROVED / LOCKED FOR IMPLEMENTATION
ACCEPTANCE / SEAL PENDING

16D-C REWORK 2:
AUTHORIZED from 18bc60da038e210b1b8f2f9aa26884e962a15f8f

16D-B3 / A3:
COMPLETE / ACCEPTED / SEALED

16E–16H:
NOT AUTHORIZED
```
