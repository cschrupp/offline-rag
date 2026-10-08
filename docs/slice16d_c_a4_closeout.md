# 16D-C / Amendment A4 — Governance Closeout

```text
16D-C / A4 CLOSEOUT

STATUS:
COMPLETE / ACCEPTED / SEALED

ACCEPTED IMPLEMENTATION:
0381e0461f68c5fc09e7be2c7699d434e8b8a9cb

A4 MATERIALIZATION:
d12f6322ef13915002b49dcc8f1211052a66dcc5

INDEPENDENT REVIEW:
PASSED

HUMAN ACCEPTANCE:
ACCEPTED

BRANCH:
implementation/16d-c-training-mode

16D-B3 / A3:
COMPLETE / ACCEPTED / SEALED

16E–16H:
NOT AUTHORIZED

SLICE 16:
IN PROGRESS / NOT COMPLETE

SLICE 17 / 18 / M7 CLOSEOUT:
NOT AUTHORIZED
```

## Implementation lineage

Earlier SHAs remain historical candidates. They are not rewritten as if each
were individually accepted as final.

```text
ORIGINAL 16D-C AUTHORIZED BASELINE:
396aa329e6c0413eb69aacd39067a70d9b478b72

ORIGINAL IMPLEMENTATION:
2266d7b16bf01e11c5ca69b2ffe4d7f4e0e821ab

REWORK 1 IMPLEMENTATION:
4489d6fb295271c65dae2c9f38e3f53bab456ff8

A4 MATERIALIZATION:
d12f6322ef13915002b49dcc8f1211052a66dcc5

REWORK 2 IMPLEMENTATION:
3bac1f8dc1a7d0aa8ea46ec4ceb832e63f570aff

REWORK 3 IMPLEMENTATION:
63517eeb98a8065df526925a1f6995339cb19b4f

FINAL REWORK 4 / ACCEPTED PRODUCT STATE:
0381e0461f68c5fc09e7be2c7699d434e8b8a9cb
```

### Rework dispositions

```text
C-R1: CLOSED
C-R2: CLOSED

A4-R1: CLOSED
A4-R2: CLOSED
A4-R3: CLOSED

REWORK 1: COMPLETE
REWORK 2: COMPLETE
REWORK 3: COMPLETE
REWORK 4: COMPLETE
```

## Accepted product scope

### Training Mode (16D-C)

```text
Training Mode
├── ordinary B3 grounded conversation path
├── saved/reusable training questions
├── compact Question Bank
│   ├── search
│   ├── JSON import/export
│   └── Markdown import/export
├── progressive disclosure
│   ├── Answer
│   ├── Citations
│   └── Evidence
├── presentation-friendly typography
├── Presentation view
├── responsive desktop/mobile behavior
└── local-only presentation state
```

Training Mode remains a frontend/presentation layer over the sealed B3
conversation path. It does not introduce a second RAG pipeline.

### Amendment A4

Accepted additive presentation/integration scope:

- Question Bank portability (JSON / Markdown; merge-only import)
- Conversation Markdown / JSON export
- Human-mediated source promotion only
- Full-width global application header

## Human-mediated source-promotion invariant

```text
Conversation export ≠ source ingestion
```

An exported conversation may produce a source-compatible Markdown file.
It MUST NOT be automatically:

- uploaded;
- added as a source;
- added to the current workspace;
- made retrievable;
- included in a snapshot.

Only an explicit later human action through existing Add Sources may promote
that artifact into workspace knowledge.

## Evidence pointers

- Training Mode evidence: [`docs/slice16d_c_training_mode.md`](slice16d_c_training_mode.md)
- A4 design authority: [`docs/slice16_amendment_a4_workspace_portability_shell.md`](slice16_amendment_a4_workspace_portability_shell.md)
- B3 conversational workspace: [`docs/slice16d_b3_conversational_workspace.md`](slice16d_b3_conversational_workspace.md)
- Slice 16 plan / design: [`docs/slice16_implementation_plan.md`](slice16_implementation_plan.md), [`docs/slice16_design_authority.md`](slice16_design_authority.md)

## Documentation reconciliation (this closeout)

This closeout also authorizes a bounded refresh of current engineering
documentation so the repository front door matches the accepted Seneca product
state. Publication packaging remains gated.

### Updated current-state docs

Governance / evidence:

- `docs/slice16d_c_a4_closeout.md` (this file)
- `docs/slice16d_c_training_mode.md`
- `docs/slice16_amendment_a4_workspace_portability_shell.md`
- `docs/slice16_implementation_plan.md`
- `docs/slice16_design_authority.md`
- `docs/milestone7_performance_ui.md`
- `ROADMAP.md`

Engineering front-door refresh (separate docs-only commit in the same
authorized sequence):

- `README.md`
- `PROJECT_STRUCTURE.md`
- `DEVELOPMENT_GUIDE.md`
- `project_description.md`
- `detailed_implementation_slices.md` (status/sequence surfaces only)
- `EVALUATION_HARNESS.md` (introductory readiness only)
- `ARCHITECTURE_DECISIONS.md` (ADR-008 current disposition)
- `STARTER_PACKAGE_CONTENTS.md` (historical banner only)
- `docs/known_limitations.md` (present-tense Slice 10 readiness)
- `docs/offline_runtime_contract.md` (present-tense Slice 10 readiness)
- `docs/slice16_design_authority.md` (stale present-tense 16D-C gate language)

### Historical docs intentionally preserved

Accepted slice evidence under `docs/slice*.md`, sealed amendments A1–A3, B3
evidence, and other historical acceptance records retain their original wording
where explicitly historical.

### Explicitly gated docs intentionally untouched

- `PORTFOLIO_DEMO.md` — Milestone-7 publication/portfolio-claims artifact; update
  not authorized by this closeout.

### No code/config/dependency changes

Confirmed: this closeout sequence is documentation-only. No changes under
`src/`, `ui/`, `tests/`, `config/`, `deploy/`, package manifests, or runtime data.
