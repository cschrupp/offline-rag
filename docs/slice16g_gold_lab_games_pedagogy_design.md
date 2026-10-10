# 16G — Gold Lab Games & Pedagogical Training Compiler

## D0 Detailed Design (candidate authority)

```text
16G GOLD LAB GAMES & PEDAGOGICAL TRAINING COMPILER
D0 DETAILED DESIGN — CANDIDATE AUTHORITY

STATUS:
DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED
REWORK 1 APPLIED (16G-D0-REWORK-AUTH-001)

Authority:
16G-D0-AUTH-001
16G-D0-REWORK-AUTH-001

Starting SHA:
1610f9282d1edbd4dfc8ae76d7644a1b9ea4e75e

Prior candidate tip:
0fdbdd3235ab675b513464e1ac7400b008b9bd2f

Branch:
design/16g-gold-lab-games-pedagogy

Locked Slice-16 authority:
e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
PRESERVED

16F:
COMPLETE / ACCEPTED / SEALED
PRESERVED

16F API surface:
17 /v1/gold-lab routes for Gold Mode
DEFAULT: NO NEW GOLD MUTATION ROUTES
BOUNDED READ GAP: GAP-16G-01 (immutable training/calibration package)
  — registered only; NOT AUTHORIZED to implement under D0

F001 / F002 / F003:
CLOSED IN THIS REWORK (design level)

16H / 9G / Slice 17 / 18 / M7 closeout:
NOT AUTHORIZED
```

This document is the **16G-D0 candidate design authority**. It becomes binding
only after independent design review and Human acceptance. It does **not**
authorize implementation.

---

## 0. Purpose and non-scope

### Purpose

Design the Seneca Gold Lab **games**, **workload presentation**, **calibration
gate**, **contribution dashboard**, and **gold-derived pedagogical training
compiler** over the sealed 16F `/v1/gold-lab` data plane without creating a
second scientific authority.

### Non-scope (this D0)

```text
NO src/** changes
NO ui/src/** changes
NO tests/** changes
NO config/** changes
NO API changes
NO new backend routes
NO Gold scientific changes
NO M7 evidence re-pin
NO 16H implementation
NO 9G activation
NO Slice 17 / 18
NO M7 closeout
NO PORTFOLIO_DEMO promotion
```

---

## 1. Governing authorities

| Authority | Status | Role for 16G |
|---|---|---|
| S16-D23 … S16-D35 | LOCKED at `e2e7475…` | Product/scientific invariants |
| 16F-A/B/C/D | COMPLETE / ACCEPTED / SEALED | Scientific + transport contracts |
| Frozen 16F design | `4fde40da…` | Gold Lab data-plane intent |
| Frozen 16F-D0 API design | `7df8a151…` | Exact 17-route HTTP contract |
| Existing Seneca Training Mode | `ui/src/features/training/` | Reuse evaluation surface only |

16G **consumes** sealed 16F A/B/C/D contracts. It **MUST NOT** redefine:

```text
GoldDataset-v1
GoldAuthoringRun / HumanReview
0/1/2 relevance
question fingerprint / task identities
selection-policy identities
append-only ledger / supersession
contribution weights
registration semantics
historical source binding
16F route/DTO/error semantics
```

---

## 2. Architectural premise

```text
Seneca React UI / pedagogical presentation
                ↓
sealed /v1/gold-lab API  (exactly 17 routes)
                ↓
accepted 16F GoldLabApplicationService
                ↓
accepted A/B/C scientific authorities
```

### Backend expansion rule

```text
DEFAULT:
NO NEW GOLD MUTATION ROUTES

BOUNDED READ GAP:
GAP-16G-01 registered in Matrix M for immutable Training/Calibration packages

NEW BACKEND CONTRACT IMPLEMENTATION:
NOT AUTHORIZED BY D0
```

Gaps are recorded only in **Matrix M — Backend gap register**. A registered
gap is **not** permission to implement it.

---

## 3. Sealed 16F route catalog (consumed as-is)

| # | Method | Path | 16G use |
|---|---|---|---|
| 1 | GET | `/v1/gold-lab/projects` | Project list |
| 2 | POST | `/v1/gold-lab/projects` | Create project |
| 3 | GET | `/v1/gold-lab/projects/{project_id}` | Project detail |
| 4 | POST | `/v1/gold-lab/projects/{project_id}/archive` | Archive |
| 5 | GET | `/v1/gold-lab/projects/{project_id}/baselines` | Campaign create baseline picker |
| 6 | GET | `/v1/gold-lab/projects/{project_id}/campaigns` | Campaign list |
| 7 | POST | `/v1/gold-lab/projects/{project_id}/campaigns` | Campaign create |
| 8 | GET | `/v1/gold-lab/campaigns/{campaign_id}` | Campaign shell |
| 9 | POST | `/v1/gold-lab/campaigns/{campaign_id}/close` | Close campaign |
| 10 | GET | `/v1/gold-lab/campaigns/{campaign_id}/tasks` | Workload filter / task queue |
| 11 | GET | `/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}` | Game shell + source |
| 12 | POST | `.../tasks/{task_id}/question-check` | Question Check commit |
| 13 | POST | `.../tasks/{task_id}/relevance` | Rapid Fire / Evidence Sweep commit |
| 14 | POST | `.../preferences` | Chunk Duel auxiliary preference |
| 15 | GET | `.../contribution` | Contribution dashboard |
| 16 | POST | `.../export` | Expert export (non-game) |
| 17 | GET | `.../registrations` | Export provenance |

Task list filters already available: `kind`, `state`, `active`, `case_id`.
Workload chooser **MUST** be a client presentation boundary over this list.

---

## 4. Gold Mode vs Training Mode (fundamental)

### Gold Mode

```text
ROLE: expert creates scientific truth
```

Preserves (**MUST**):

- blind pre-commit judgment via sealed BlindTaskView / task DTOs;
- sealed historical `GoldSourceContext`;
- exact campaign/task authority;
- accepted 0/1/2 and Question Check discriminated contracts;
- accepted idempotent mutation authority;
- `game_id` + `presentation_id` on every relevant mutation;
- no score/rank/model/prelabel leakage before commit.

### Training Mode

```text
ROLE: learner consumes expert-validated truth
```

Learner interactions (**MUST**):

```text
NEVER become Gold automatically
NEVER append canonical Gold judgments
NEVER alter GoldDataset truth
NEVER receive Gold contribution points
NEVER call Gold mutation endpoints for learner commits
```

### Explicit data-flow boundary

```text
GOLD MODE (production-eligible presentations only)
  sealed GET tasks/detail
       ↓
  expert commit via sealed POST mutations
       ↓
  append-only ledger / effective state / contribution
       ↓
  optional POST export → GoldDataset registration

CALIBRATION MODE (candidate presentations; non-Gold)
  GAP-16G-01 immutable package (registration + GoldDataset + historical source)
       ↓
  candidate presentation UI
       ↓
  LOCAL calibration response only
       ↓
  local comparison / metrics / evidence export
       ✗  NO Gold mutation endpoint
       ✗  NO ledger write
       ✗  NO contribution

TRAINING MODE
  GAP-16G-01 immutable package
       ↓
  client-side training compiler (deterministic)
       ↓
  learner activity (local/ephemeral presentation state)
       ↓
  source-grounded feedback / debrief
       ✗  (no path back to ledger / GoldDataset)
```

**MUST NOT** reconstruct Training or Calibration truth from live campaign task
DTOs. Export does not freeze the campaign; later corrections can change
effective task state after a registration exists. Only the immutable registered
dataset (+ validated historical binding) is training/calibration truth.

### Existing Training Mode reuse

Evaluate reuse of `ui/src/features/training/` patterns (question bank panel,
reveal state, toolbar) for **learner surfaces only**. Do **not** dual-purpose
those components as Gold mutation shells. Gold Lab gets
`ui/src/features/goldLab/` (see §18).

---

## 5. Canonical game semantics

### 5.1 Rapid Fire

| Axis | Contract |
|---|---|
| Scientific semantic | absolute relevance `0 \| 1 \| 2` |
| Presentation | one active absolute task at a time |
| API | `GET .../tasks` (`kind=absolute_relevance`, `state=pending`, `active=true`) → `GET .../tasks/{task_id}` → `POST .../relevance` |
| Controls | three distinct labeled controls (not color-only); keyboard `1`/`2`/`3` or `0`/`1`/`2` with visible mapping |
| Commit | Idempotency-Key per attempt; disable controls while in-flight |
| Pending/completed | pending queue from server filters; completed tasks leave queue |
| Correction | after commit, optional reveal; new key + superseding mutation via same endpoint (service owns supersession) |
| Post-commit feedback | MAY show committed relevance + historical source already on task detail; **MUST NOT** invent rationale |
| Progression | advance to next pending task in stable server order (filter **MUST NOT** reorder) |
| IDs | `game_id=goldgame_rapid_fire_v1`; `presentation_id` per §9 |

### 5.2 Evidence Sweep

| Axis | Contract |
|---|---|
| Scientific semantic | **identical** absolute relevance `0 \| 1 \| 2` |
| Presentation | spatial/batch of N candidates (default N=5; configurable presentation constant) |
| API | same relevance endpoint; one mutation per candidate/task |
| Candidate set | active absolute tasks for current case (or workload window) from sealed task list |
| Batch size | presentation constant; **MUST NOT** change scientific task membership |
| Keyboard-accessible equivalent | linear list with same controls; spatial layout optional enhancement |
| Partial completion | each task commits independently; batch may be incomplete |
| Submission granularity | one POST per task (not a batch scientific commit) |
| Correction / resumability | same as Rapid Fire; resume via sealed task state |

Evidence Sweep is a **presentation variant** of absolute relevance, not a new
semantic contract.

### 5.3 Question Check

| Axis | Contract |
|---|---|
| Scientific semantic | accept / edit / reject (sealed discriminated union) |
| API | `POST .../question-check` |
| Accept/reject | `effective_*` keys **absent** (explicit null invalid) |
| Edit | all three `effective_*` present; non-empty query; category nullable; tags array |
| Source | task detail `presentation.source` (`GoldSourceContext`) |
| Blind exclusions | no model grade/confidence/agreement/prelabel |
| No-op edit | transport/service reject (`question_check_edit_not_semantic`) — UI surfaces as invalid |
| IDs | `game_id=goldgame_question_check_v1` |

### 5.4 Chunk Duel

| Axis | Contract |
|---|---|
| Authority | **AUXILIARY PAIRWISE PREFERENCE ONLY** |
| API | `POST .../preferences` |
| MUST NOT | create absolute relevance; convert to canonical Gold; award absolute contribution; alter GoldDataset |
| UI messaging | persistent non-dismissible framing: “Preference only — does not create Gold relevance” |
| Pair selection | expert chooses preferred vs other among case candidates known to campaign (server validates membership) |
| IDs | `game_id=goldgame_chunk_duel_v1` |

---

## 6. Workload chooser

Locked sizes (**MUST** support):

```text
1, 5, 10, 25, complete case
```

Also permit “until stop” as a continuous session mode (S16-D24) without a
numeric cap.

| Decision | Design |
|---|---|
| Selection mechanism | **Client view/filter** over `GET .../tasks` |
| Server contract | **None new** — uses existing filters |
| Fewer tasks remain | show remaining count; allow starting with smaller set |
| Resume | reopen campaign → same filters → pending active tasks in sealed order |
| Progress | derived from contribution DTO + task pending/completed counts |
| Campaign close | close remains expert action; workload does not auto-close |
| Completed/inactive | excluded by default filters; inactive absolute: no candidate presentation |
| Scientific membership | workload **MUST NOT** mutate task membership or selection policy |

Workload size is a **human-work presentation boundary**, not a second
task-selection authority.

---

## 7. Presentation identity

### Canonical game IDs (compile-time constants)

```text
goldgame_rapid_fire_v1
goldgame_evidence_sweep_v1
goldgame_question_check_v1
goldgame_chunk_duel_v1
```

### Presentation ID format

```text
goldpres_<game_snake>_<presentation_slug>_v<major>
```

Examples:

```text
goldpres_rapid_fire_single_card_v1
goldpres_evidence_sweep_spatial_grid_5_v1
goldpres_evidence_sweep_linear_list_5_v1
goldpres_question_check_source_panel_v1
goldpres_chunk_duel_side_by_side_v1
```

### Versioning policy

| Change | Action |
|---|---|
| Cosmetic CSS-only | same `presentation_id` |
| Control layout, batch size, keyboard mapping, reveal timing, wording that could bias | **new** `presentation_id` |
| Scientific semantic change | **forbidden** in 16G; requires design authority change |

### Generation

- IDs are **compile-time constants** in the client (and mirrored in calibration
  records).
- Client attaches them on every mutation body.
- Server stores them; server does **not** invent game semantics from them.

### Calibration binding

Calibration runs record `(game_id, presentation_id, registration/dataset
identity, case set, metrics, disposition)`. A presentation is
production-eligible only after Human disposition **and** inclusion in the
versioned approved-presentations policy (see §8).

### Gold Mode presentation eligibility (F003)

```text
candidate presentation
        ↓
calibration evidence (non-mutating)
        ↓
Human disposition
        ↓
versioned approved-presentations policy
        ↓
Gold Mode exposes ONLY ALLOW_PRODUCTION presentations
```

| Mode | Presentations exposed |
|---|---|
| Calibration Mode | candidate / unapproved presentations **MAY** |
| Gold Mode | **ONLY** presentations listed as `ALLOW_PRODUCTION` in the versioned policy |

The approved-presentations policy is **version-controlled product governance**,
not browser preference:

- shipped as a static compile-time / repository artifact (e.g.
  `ui/src/features/goldLab/policy/approvedPresentations.v1.json` or equivalent
  TypeScript constant module);
- changes require an explicit governed commit + Human acceptance;
- Gold Mode **MUST** refuse to mount mutation UI for non-approved
  `(game_id, presentation_id)`;
- campaign/project notes alone are **insufficient** as the eligibility authority.

---

## 8. Calibration gate (S16-D27)

### Non-mutation invariant (F002) — CRITICAL

```text
immutable prior Gold truth (GAP-16G-01 package)
        ↓
candidate presentation
        ↓
LOCAL calibration response
        ↓
local comparison / metrics
        ↓
calibration evidence export
        ✗
NO POST .../question-check
NO POST .../relevance
NO POST .../preferences
NO ledger write
NO contribution
```

Calibration responses are **ephemeral local records**. They **MUST NEVER** call
normal Gold mutation endpoints. Only after a presentation receives
`ALLOW_PRODUCTION` and is listed in the versioned policy may that presentation
be used in Gold Mode, where the sealed mutation endpoints apply.

### Protocol (concrete, threshold-light)

```text
1. Load immutable prior truth via GAP-16G-01 package for a chosen registration
   (not live campaign task DTOs).
2. Expert works those cases under the candidate (game_id, presentation_id)
   WITHOUT seeing prior answers (blind).
3. Capture LOCAL calibration responses only (no Gold POST).
4. Compare locally to package labels; compute observational metrics.
5. Export calibration evidence JSON (download).
6. Human disposition: ALLOW_PRODUCTION | REPAIR_REQUIRED | DISALLOW
7. If ALLOW_PRODUCTION: update versioned approved-presentations policy via
   governed commit (not localStorage / notes alone).
```

### Observables (SHOULD collect; not frozen pass thresholds)

```text
agreement with immutable package truth
0/1/2 distribution vs package distribution
unsure / skip rate (if UI exposes skip — v1: no skip; abandon = leave session)
local revision rate within the calibration session (not Gold supersession)
completion time per task
abandonment (session leave before workload complete)
```

Note: “correction rate” in calibration means **local response revisions inside
the calibration session**, not Gold ledger supersession (which must not occur).

### Population

Minimum eligible calibration population is **not** frozen numerically in D0.
If population is insufficient for statistical confidence, disposition **MUST**
be Human-review (`REPAIR_REQUIRED` or provisional disallow) rather than a
fabricated numeric gate.

### Storage / reporting

v1 calibration **evidence** archive is client-exported JSON (download) for
Human review. Production eligibility itself is recorded only by updating the
versioned approved-presentations policy after Human disposition.

---

## 9. Blindness contract

### Field-level visibility matrix

| Field / signal | Before judgment | After commit | After correction | Training Mode |
|---|---|---|---|---|
| `task_id` / kind / case_id | YES | YES | YES | YES (drill meta) |
| `active` / `state` | YES | YES | YES | N/A |
| `effective_query` (QC) | YES (proposed) | YES | YES | YES (as prompt) |
| Candidate text / source | YES (if active) | YES | YES | YES |
| Model judgment / grade | **NO** | NO (not in DTO) | NO | NO |
| Retrieval score / rank | **NO** | NO | NO | NO |
| Prelabel / confidence / agreement | **NO** | NO | NO | NO |
| Proposal rationale (forbidden) | **NO** | NO | NO | NO |
| Hard-call reason/designation | **NO** | NO | NO | NO |
| Contribution points | NO (not on task) | Campaign dash only | Campaign dash only | **NO** |
| Prior absolute label | **NO** | YES (current_result) | YES | YES (answer key) |

Authority:

- **Gold Mode:** sealed BlindTaskView / Gold task DTOs only.
- **Calibration Mode:** GAP-16G-01 package items rendered through the same
  blind presentation adapters; prior labels remain hidden until local commit
  of the calibration response; package answer keys used only for local
  scoring after response.

Browser **MUST NOT** reconstruct blindness from richer unsafe payloads.

---

## 10. Source-grounded pedagogical feedback (S16-D32)

```text
recall → commit → corrective/source-grounded feedback
      → authoritative source → occasional self-explanation
      → application/scenario → debrief
```

| Stage | Gold Mode v1 | Training Mode v1 |
|---|---|---|
| recall | required (task presentation) | required |
| commit | required (mutation) | required (local learner commit) |
| corrective/source-grounded feedback | optional after-action | required |
| authoritative source | from sealed historical context | from compiler-bound source |
| self-explanation | optional / deferred prompt | optional |
| application/scenario | deferred / light v1 pattern §14 | required bounded pattern |
| debrief | optional | required |

**MUST NOT** fabricate highlights, rationales, or source interpretations.
Unavailable historical source → fail closed (show integrity error; no fake text).

---

## 11. Gold-derived drills (training compiler)

### Required direction

```text
immutable registered Gold (GAP-16G-01)
   ↓
training/drill compiler
   ↓
learner activity
```

### Forbidden

```text
learner activity → canonical Gold
live campaign task DTOs → training truth
browser reads of /data or dataset_path → training truth
```

### Immutable package dependency (F001)

Sealed registration listing returns metadata (`dataset_id`, `dataset_path`,
hashes, exported case IDs). `dataset_path` is **not** browser-readable, and
the SPA has no `/data` static exposure. Therefore Training **and** Calibration
require the bounded read-only gap **GAP-16G-01** (Matrix M).

Until GAP-16G-01 is separately authorized and implemented, Training/Calibration
**MUST NOT** ship against live task DTOs as a substitute truth source.

### Compiler rules

| Topic | Design |
|---|---|
| Eligible input | GAP-16G-01 package derived from registration + exact registered GoldDataset + campaign historical binding |
| Transformation | deterministic: grade 2 → direct; grade 1 → supporting; hard 0 → distractors (S16-D33) |
| Exercise identity | `goldex_<dataset_id>_<case_id>_<template_id>_v1` |
| Source provenance | exact historical source contexts inside the package (server-validated); fail closed if unavailable |
| Answer authority | labels from the registered GoldDataset only |
| Correction/debrief | compare learner choice to package label; show package source text |
| Superseded Gold | package identity is the registration/dataset pin; do not silently follow later campaign effective-state |
| Persistence | compiler output may be ephemeral/session; package fetch is read-only |

Compiler runs in the client over the GAP-16G-01 payload. No general filesystem
endpoint. No Gold mutation from Training.

---

## 12. Scenario / debrief (bounded v1)

Pattern:

```text
scenario statement (from case query / source-grounded stem)
 → learner decision/task (select evidence grade or choose chunk)
 → evidence reveal (learner choice)
 → authoritative source (compiled GoldSourceContext text)
 → corrective explanation boundary (label mismatch only; no invented prose)
 → debrief (counts + source pointer)
```

Prefer **deterministic/source-grounded compilation**. Model-generated pedagogical
content is **not required for v1**; if later introduced, it **MUST** be labeled
non-authoritative and **MUST NOT** become scientific truth.

---

## 13. Visual pedagogy (S16-D33)

Preferred: manual diagrams, figures, source pages, incident-command charts,
relevant photographs from corpus artifacts when available in source context.

Forbidden as decoration: cognitive-load fire imagery, fake urgency, reward
animations implying scientific correctness, happy/sad relevance faces.

Align with Seneca tokens/layout (existing CSS variables / shell). Neutral
semantic icons for 0/1/2.

---

## 14. Contribution dashboard (S16-D34)

### Authority

```text
GET /v1/gold-lab/campaigns/{campaign_id}/contribution
```

Browser **MUST NOT** recompute contribution from ledger rows.

### Display fields (API-provided)

```text
total_score
expert_judgments
questions_reviewed
cases_completed
gold_finalized
hard_calls_resolved
completed_active_absolute_tasks / total_active_absolute_tasks
coverage_fraction
total_question_tasks
contract: gold-contribution-v1
```

### Placement

| Surface | v1 |
|---|---|
| Gold Lab campaign view | **required** |
| Overview summary | **optional** aggregate of open campaigns via repeated GET (display-only; no local formula) |
| Competitive ranking | **forbidden** |

Frame as **personal/progress contribution**, not gamification.

Forbidden: leaderboards, speed bonuses, model-agreement bonuses, competitive
rankings, raw append-event scoring.

---

## 15. Information architecture / routes

Canonical client routes (freeze):

```text
/gold-lab
/gold-lab/projects/:projectId
/gold-lab/campaigns/:campaignId
/gold-lab/campaigns/:campaignId/work
/gold-lab/campaigns/:campaignId/contribution
/gold-lab/campaigns/:campaignId/training
/gold-lab/campaigns/:campaignId/training/scenario
/gold-lab/campaigns/:campaignId/calibration
```

| Concept | Route vs mode |
|---|---|
| Project list / create | `/gold-lab` |
| Project detail / baselines / campaigns | `/gold-lab/projects/:projectId` |
| Campaign shell / workload chooser / game picker | `/gold-lab/campaigns/:campaignId` |
| Expert task execution | `/work` — **common task shell**; game is presentation mode |
| Contribution | dedicated route |
| Training / drills | `/training` |
| Scenario/debrief | nested under training |
| Calibration | dedicated; expert/admin framing (no auth system — local trust) |

Do **not** create four top-level game routes; games are modes inside `/work`.

Query params (client route state):

```text
?game=rapid_fire|evidence_sweep|question_check|chunk_duel
&workload=1|5|10|25|case
&task=<task_id>
```

---

## 16. UI architecture footprint (design only)

Proposed namespace:

```text
ui/src/features/goldLab/
  api/           # thin wrappers over sealed /v1/gold-lab
  queryKeys.ts
  types.ts       # mirror public DTOs; no unsafe enrichments
  state/         # workload + game selection (non-scientific)
  shell/         # ProjectList, CampaignShell, WorkloadChooser
  games/         # RapidFire, EvidenceSweep, QuestionCheck, ChunkDuel adapters
  contribution/
  training/      # compiler + drills + scenario (separate from features/training)
  calibration/
  errors/
  a11y/
```

Pages:

```text
ui/src/pages/GoldLabPage.tsx
ui/src/pages/GoldLabProjectPage.tsx
ui/src/pages/GoldLabCampaignPage.tsx
ui/src/pages/GoldLabWorkPage.tsx
...
```

Router registration in `ui/src/app/router.tsx` (implementation later).

Reuse patterns from `ui/src/api/client.ts`, React Query keys, existing error
envelope handling. Do **not** implement during D0.

---

## 17. State authority classification

| State | Class |
|---|---|
| Project/campaign/task DTOs | SERVER / PRODUCT + SCIENTIFIC AUTHORITY |
| Committed judgment / contribution | SERVER / SCIENTIFIC AUTHORITY |
| GAP-16G-01 immutable package | SERVER / PRODUCT READ AUTHORITY (proposed; not yet implemented) |
| Approved-presentations policy (`ALLOW_PRODUCTION` set) | **VERSIONED PRODUCT GOVERNANCE** (repo/compile-time artifact; not local preference) |
| Calibration evidence export JSON | CLIENT EPHEMERAL / downloaded artifact (review input only) |
| Calibration local responses | CLIENT EPHEMERAL PRESENTATION STATE (never Gold) |
| Selected game | CLIENT ROUTE STATE |
| Workload size | CLIENT ROUTE STATE |
| Current task id (Gold Mode) | CLIENT ROUTE STATE (must match server membership) |
| Answer draft (uncommitted Gold) | CLIENT EPHEMERAL PRESENTATION STATE |
| Reveal / after-action open | CLIENT EPHEMERAL PRESENTATION STATE |
| presentation_id / game_id constants | CLIENT COMPILE-TIME; Gold Mode sends only policy-approved IDs on commit |
| Drill progress | CLIENT EPHEMERAL PRESENTATION STATE |
| Scenario step | CLIENT EPHEMERAL PRESENTATION STATE |

Browser **MUST NOT** become a parallel scientific database.
Browser **MUST NOT** treat localStorage/notes as production-presentation
eligibility authority.

---

## 18. Idempotency and retry UX

| Topic | Design |
|---|---|
| Key creation | `crypto.randomUUID()` (or equivalent) at first submit intent |
| Lifetime | retained for in-flight + explicit retry of **same** body; cleared after confirmed terminal success UI |
| Uncertain request | retry **same** key + same body; never mint new key on unknown transport outcome |
| Double submit | disable controls; ignore secondary clicks |
| Divergent replay | map `idempotency_conflict` → blocked; show “request changed after prior attempt” |
| Closed/archived | exact replay → success replayed; new key → `gold_conflict` |
| Correction | new Idempotency-Key for superseding judgment |
| Reload | lose ephemeral draft; resume from server task state |

Network retry **MUST NEVER** convert uncertainty into a second ledger append
with a new key for the same intended first commit.

---

## 19. Error-state design

| API code | User-facing class | UX |
|---|---|---|
| `request_invalid` | user-correctable input | inline form errors; keep draft |
| `not_found` / `gold_*_unknown` | missing resource | navigate to list; no retry of mutation |
| `gold_baseline_unknown` | missing baseline | campaign create blocked |
| `gold_conflict` | campaign/project state conflict | explain closed/archived/stale; offer refresh |
| `gold_state_unavailable` | historical/provenance integrity | **fail closed**; “cannot bind evidence safely”; no continue |
| `idempotency_conflict` | divergent retry | block; instruct restart with new key only for intentional correction |
| `gold_busy` | temporary lease | retry later |
| `internal_error` | unexpected | generic failure; no raw prose |

Never surface raw backend exception strings.

---

## 20. Accessibility (prepares 16H)

Design now for later WCAG 2.2 AA acceptance:

- complete keyboard operation for all four games;
- visible focus rings;
- 0/1/2 distinguished by text + icon + value, not color alone;
- semantic buttons/radiogroups;
- aria-labels for candidate/source regions;
- live region for commit/replay status;
- dialog focus traps if used (prefer non-modal where possible);
- `prefers-reduced-motion`;
- narrow/mobile layouts; 200% zoom;
- Evidence Sweep **linear list** as first-class accessible equivalent to spatial grid.

16H remains the formal integration/accessibility gate.

---

## 21. Required design matrices

### A. Game → scientific semantic mapping

| Game | Semantic |
|---|---|
| Rapid Fire | absolute relevance 0/1/2 |
| Evidence Sweep | absolute relevance 0/1/2 |
| Question Check | accept / edit / reject |
| Chunk Duel | auxiliary pairwise preference only |

### B. Game → API endpoint mapping

| Game | Read | Write |
|---|---|---|
| Rapid Fire | tasks + task detail | `POST .../relevance` |
| Evidence Sweep | tasks + task detail | `POST .../relevance` (per task) |
| Question Check | tasks + task detail | `POST .../question-check` |
| Chunk Duel | tasks (context) + case candidates via active absolute tasks | `POST .../preferences` |

### C. Game → game_id / presentation_id mapping

| Game | game_id | Default presentation_id |
|---|---|---|
| Rapid Fire | `goldgame_rapid_fire_v1` | `goldpres_rapid_fire_single_card_v1` |
| Evidence Sweep | `goldgame_evidence_sweep_v1` | `goldpres_evidence_sweep_spatial_grid_5_v1` (+ linear alt id) |
| Question Check | `goldgame_question_check_v1` | `goldpres_question_check_source_panel_v1` |
| Chunk Duel | `goldgame_chunk_duel_v1` | `goldpres_chunk_duel_side_by_side_v1` |

### D. Pre/post-commit visibility matrix

See §9.

### E. Gold Mode vs Training Mode vs Calibration authority matrix

| Action | Gold Mode | Calibration Mode | Training Mode |
|---|---|---|---|
| Call Gold mutation APIs | YES (approved presentations only) | **NO** | **NO** |
| Append ledger | YES (via API) | **NO** | **NO** |
| Affect GoldDataset | via export only | **NO** | **NO** |
| Earn contribution | YES | **NO** | **NO** |
| See model/prelabel pre-commit | **NO** | **NO** | N/A |
| Truth source | live sealed task DTOs | GAP-16G-01 package | GAP-16G-01 package |
| Use unapproved presentation | **NO** | YES | N/A (learner UI) |
| Create drills from Gold | N/A | N/A | YES (compiler) |

### F. Client/server state ownership matrix

See §17.

### G. Route / page / feature-component map

See §15–§16.

### H. Mutation / idempotency matrix

| Mutation | Header | Replay after close | New key after close |
|---|---|---|---|
| question-check | Idempotency-Key required | 200 replay | 409 gold_conflict |
| relevance | Idempotency-Key required | 200 replay | 409 gold_conflict |
| preferences | Idempotency-Key required | 200 replay | 409 gold_conflict |

### I. Calibration lifecycle

```text
draft presentation_id (candidate)
 → fetch GAP-16G-01 immutable package for chosen registration
 → calibration session (LOCAL responses only; no Gold POST)
 → local metrics vs package truth
 → calibration evidence export
 → Human disposition
 → ALLOW_PRODUCTION | REPAIR_REQUIRED | DISALLOW
 → if ALLOW_PRODUCTION: governed commit to versioned
   approved-presentations policy
 → Gold Mode may then expose that presentation
```

### J. Training compiler provenance flow

```text
GET registrations (metadata index)
 → GET GAP-16G-01 immutable package for chosen registration
      (registration + exact GoldDataset + historical source contexts)
 → deterministic exercise build from package only
 → learner session (local commits)
 → feedback from package labels + package source
 → (terminates; no Gold writeback; no live task-DTO truth)
```

### K. Error-state matrix

See §19.

### L. Accessibility interaction matrix

| Interaction | Keyboard | SR | Reduced motion | Narrow |
|---|---|---|---|---|
| 0/1/2 commit | YES | labeled radiogroup | YES | stacked |
| QC accept/edit/reject | YES | tabs/buttons | YES | stacked |
| Evidence Sweep | linear mode first-class | list | no forced motion | list |
| Chunk Duel choose A/B | YES | described pair | YES | stacked |
| Workload chooser | YES | listbox | YES | YES |

### M. Backend gap register

```text
16G BACKEND GAP REGISTER
STATUS: ONE BOUNDED READ-ONLY GAP REGISTERED
IMPLEMENTATION OF ANY GAP: NOT AUTHORIZED BY D0
```

| Gap ID | Capability | Why 17 routes insufficient? | Missing info/mutation | Presentation vs scientific | UI-only alternative | Authority owner | Blindness impact | Gold semantics impact | Provenance impact | Min contract extension |
|---|---|---|---|---|---|---|---|---|---|---|
| **GAP-16G-01** | Immutable Training/Calibration package read | Registration list exposes metadata/`dataset_path` only; SPA cannot read `/data`; live task DTOs are not equivalent to registered GoldDataset (campaign may still receive corrections after export) | Read-only validated package: dataset identity/hashes, exported cases, accepted queries/labels, exact historical source contexts bound to campaign snapshot/chunk-set | **Presentation / pedagogy input** (not a scientific mutation) | Manual authenticated import of exact Gold artifacts with full hash/provenance validation is an allowed alternative design; **not** preferred; no general filesystem endpoint | Product transport over accepted 16F-C registration + historical reader; **MUST NOT** invent new Gold truth | Package must omit model/prelabel/rank; serve only fields needed for blind presentation + post-response scoring | **None** — read-only; no ledger/contribution/GoldDataset writes | Pins training/calibration to registration-time immutable dataset rather than later effective-state | e.g. `GET /v1/gold-lab/campaigns/{campaign_id}/registrations/{dataset_id}/training-package` (name illustrative) returning a fail-closed validated DTO; **no** arbitrary path read |

**GAP-16G-01 minimum semantics (design freeze; implementation unauthorized):**

```text
Input authority:
  existing registration record
  + exact registered GoldDataset bytes/identity
  + campaign historical binding (snapshot_id / chunk_set_id / corpus)

Output (read-only):
  dataset_id / hashes / registration identity
  exported cases with accepted queries + absolute/QC labels as registered
  exact historical GoldSourceContext (or equivalent) per needed chunk
  fail closed on any integrity mismatch

MUST NOT:
  expose /data paths to the browser
  accept arbitrary filesystem paths
  mutate ledger / contribution / registration
  substitute current campaign task effective-state for registered truth
```

**Deferred non-blocking product notes (not additional scientific gaps):**

- Cross-campaign Overview rollup → repeated per-campaign GET contribution
  (display aggregation only).

Gold Mode expert games remain fully supported by the sealed 17 routes.
GAP-16G-01 is required for Training + Calibration provenance only.

### N. Implementation slice proposal

Hypothesis (not frozen until D0 acceptance):

| Slice | Scope | Starting authority | Expected files (future) | Tests | Acceptance | Non-scope |
|---|---|---|---|---|---|---|
| **16G-I1** | API client + IA + project/campaign shell + workload chooser (no commits) | accepted D0 + sealed 16F | `ui/src/features/goldLab/**`, pages, router | route/render/API mocks | navigate projects→campaign→workload | no mutations; no training |
| **16G-I2** | Expert work shell + Rapid Fire + Question Check; enforce approved-presentations policy | I1 accepted | games/rapidFire, questionCheck, policy module, idempotency UX | mutation/a11y/blindness/policy gate | commit+replay+blind; refuse non-approved presentation in Gold Mode | no Sweep/Duel |
| **16G-I3** | Evidence Sweep + Chunk Duel | I2 accepted | games/evidenceSweep, chunkDuel | batch/a11y/auxiliary framing | Sweep==absolute semantic; Duel auxiliary only | no training compiler |
| **16G-I4** | Contribution dashboard + calibration surface (local responses only) | I3 accepted **and** GAP-16G-01 separately authorized/implemented for live package fetch; contribution UI may land earlier on sealed GET contribution alone | contribution/, calibration/, policy wiring | contribution DTO-only; **assert zero Gold mutation calls** during calibration; package-hash binding | calibration evidence export; policy update remains governed docs/code commit | no drills; no Gold POST from calibration |
| **16G-I5** | Training compiler + drills + scenario/debrief over GAP-16G-01 | I4 accepted + GAP-16G-01 available | training/ under goldLab | no Gold writeback; package-only truth; fail closed | learner never hits mutations; no live task-DTO truth | no spaced repetition |
| **16G-I6** | 16G integration / regression / a11y preflight | I5 accepted | tests + harness | keyboard paths; error matrix; calibration non-mutation; policy gate | ready for 16H handoff | **not** 16H seal |

Each slice: independent review stop. GAP-16G-01 requires **separate**
authorization before implementation; D0 only registers the gap.

---

## 22. Product surfaces checklist (locked scope coverage)

| Surface | Designed |
|---|---|
| Rapid Fire | YES §5.1 |
| Evidence Sweep | YES §5.2 |
| Question Check | YES §5.3 |
| Chunk Duel | YES §5.4 |
| Calibration mode | YES §8 |
| presentation_id tracking | YES §7 |
| Workload chooser | YES §6 |
| Gold contribution dashboard | YES §14 |
| Source-grounded pedagogy | YES §10 |
| Gold-derived evidence drills | YES §11 |
| Scenario / debrief | YES §12 |

No locked 16G item is omitted.

---

## 23. Scientific invariants (restated)

16G **MUST NOT** alter GoldDataset-v1, authoring/finalizer, HumanReview,
relevance semantics, fingerprints, task/selection identities, ledger/supersession,
contribution weights, registration, historical binding, or 16F API authority.

No retrieval/embedding/reranker/generation/`base.yaml` promotion.

---

## 24. Explicit deferrals (inherit S16-D35 + 16G-specific)

Deferred:

- authN/Z / multi-user tenancy;
- LMS / gradebook / certification;
- personalized spaced repetition / mastery;
- automatic training/fine-tune/promotion from gold;
- model-generated scenario engines as authority;
- new Gold backend routes;
- distributed/multi-worker Gold state;
- 16H / 9G / Slice 17 / 18 / M7 closeout.

---

## 25. Open design questions (Human-resolvable later; defaults recommended)

| ID | Question | D0 recommended default |
|---|---|---|
| OQ-1 | Evidence Sweep default batch size | 5 |
| OQ-2 | Calibration numeric thresholds | **None frozen**; Human disposition |
| OQ-3 | Overview contribution aggregation | Optional multi-GET display |
| OQ-4 | Training package delivery | Prefer GAP-16G-01 read API; manual import only as explicit fallback design |
| OQ-4b | Approved-presentations artifact format | Compile-time JSON/TS module under `features/goldLab/policy/` |
| OQ-5 | Chunk Duel candidate pairing UX | Side-by-side from two active candidates |

These defaults are part of the D0 candidate; changing them after acceptance
requires design amendment, not silent UI drift.

---

## 26. Acceptance criteria for this D0 document

Independent design review should verify:

1. All locked 16G surfaces are designed.
2. Gold Mode / Training Mode / Calibration Mode boundaries are airtight.
3. Games map onto sealed 17 routes for Gold Mode mutations.
4. Backend gap register records GAP-16G-01 for immutable Training/Calibration
   reads; no general filesystem endpoint; gap implementation not authorized by D0.
5. Matrices A–N are present and consistent (I/J/M reworked).
6. Blindness uses sealed DTOs (Gold) / package blind adapters (Calibration).
7. Contribution is API-authoritative.
8. Chunk Duel remains auxiliary.
9. Calibration does not invent fake statistical thresholds.
10. Calibration responses never call Gold mutation endpoints (F002).
11. Production presentation eligibility is versioned governance, not local
    preference (F003).
12. Training/Calibration truth is never live campaign task effective-state (F001).
13. Implementation decomposition is reviewable and gated.
14. No production code changed under D0.

---

## 27. Rework disposition (16G-D0-REWORK-AUTH-001)

```text
F001 CLOSED (design):
IMMUTABLE TRAINING/CALIBRATION READ PATH → GAP-16G-01

F002 CLOSED (design):
CALIBRATION RESPONSES NEVER MUTATE GOLD

F003 CLOSED (design):
PRODUCTION PRESENTATION ELIGIBILITY IS VERSIONED GOVERNANCE,
NOT LOCAL USER PREFERENCE
```

Game design, IA, idempotency, contribution semantics, and I1–I6 ordering remain
stable aside from the narrow I4/I5 dependency on GAP-16G-01 and the Gold Mode
policy gate in I2.

## 28. Status

```text
16G-D0:
DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED
REWORK 1 APPLIED

16G implementation:
NOT AUTHORIZED

GAP-16G-01 implementation:
NOT AUTHORIZED

16H:
NOT AUTHORIZED

9G:
DEFERRED / NOT AUTHORIZED

Slice 17 / 18 / M7 closeout:
NOT AUTHORIZED
```

FINAL ACTION FOR THIS DOCUMENT:
STOP FOR INDEPENDENT DESIGN REVIEW
