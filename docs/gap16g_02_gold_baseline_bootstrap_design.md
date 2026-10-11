# GAP-16G-02 — Gold Baseline Bootstrap / Candidate-Generation Product Flow

## D0 Detailed Design (candidate authority)

```text
GAP-16G-02 GOLD BASELINE BOOTSTRAP / CANDIDATE-GENERATION PRODUCT FLOW
D0 DETAILED DESIGN — CANDIDATE AUTHORITY

STATUS:
DESIGN OPEN / IMPLEMENTATION NOT AUTHORIZED

Authority:
GAP-16G-02-D0-AUTH-002
GAP16G02-D0-WRITE-GATE-01

Starting product tip:
35ec9be5647d41c887eb280146c05b9688dea685

Branch:
design/gap-16g-02-gold-baseline-bootstrap

Design deliverable:
docs/gap16g_02_gold_baseline_bootstrap_design.md

Production ALLOW_PRODUCTION:
UNCHANGED / EMPTY

9G:
DEFERRED / NOT AUTHORIZED

16G-I6:
NOT AUTHORIZED

GAP-16G-01:
UNCHANGED / NOT REOPENED

Human acceptance:
PENDING

Implementation:
NOT AUTHORIZED
```

This document is the **GAP-16G-02 D0 candidate design authority**. It becomes
binding only after independent design review and Human acceptance. It does
**not** authorize implementation.

It does **not** contain language that self-authorizes production work.
Phrases such as “implement now”, “proceed to I1”, “authorized next”, or
“implementation may begin after commit” are **not** operative under this
document unless a separate Human-issued implementation authority exists.

Unresolved design issues under this D0: **NONE**.

---

## 1. Authority inventory

| Item | Value |
|---|---|
| Design authority | `GAP-16G-02-D0-AUTH-002` |
| Write gate | `GAP16G02-D0-WRITE-GATE-01` |
| Starting product tip (Human-accepted 16G-I5) | `35ec9be5647d41c887eb280146c05b9688dea685` |
| Source branch | `implementation/16g-i5-training-compiler` |
| Design branch | `design/gap-16g-02-gold-baseline-bootstrap` |
| Design deliverable | `docs/gap16g_02_gold_baseline_bootstrap_design.md` |
| Frozen 16G-D0 blob | `edc2be739621dbedfc44ed77861119a35f8f6d18` |
| Canonical GAP registration commit | `1c4e62a16f7e6b3f8cbf1efada2bafce7bc0f0d8` |
| Canonical GAP registry blob | `e1e537bf40d9988b1c2a4ea8676666ebc70464cb` |
| Slice 9B design blob | `50dcafbe2566064207815f31542f8114b7797851` |
| Slice 9C design blob | `f7bb589cb1696887eb8f3f6cf4618b5929bd304c` |
| Slice 9D design blob | `cb62f11c710f9d98966ae497eb2016c833736387` |

### Locked D0 decisions

| ID | Title |
|---|---|
| `GAP16G02-D0-ENTRY-01` | Gold Lab–primary, workspace-bound product entry |
| `GAP16G02-D0-ORCH-01` | One server-owned async ManagedOperation orchestration |
| `GAP16G02-D0-PUBLISH-01` | Usable-baseline publication with fail-closed integrity |
| `GAP16G02-D0-REQUEST-01` | Minimal project-scoped bootstrap request |
| `GAP16G02-D0-PROPOSAL-COUNT-01` | `proposal_count` product bound `1..40` |
| `GAP16G02-D0-CONCURRENCY-01` | Workspace-scoped scientific single-flight |
| `GAP16G02-D0-SEED-01` | Deterministic operation-bound sampling seed |
| `GAP16G02-D0-STAGING-01` | Private staging → atomic canonical promotion |
| `GAP16G02-D0-OBSERVATION-01` | Typed bootstrap observation on `/v1/operations` |
| `GAP16G02-D0-HANDOFF-01` | Explicit baseline → existing campaign-create handoff |
| `GAP16G02-D0-CRASH-01` | Startup reconciliation before generic interrupt |
| `GAP16G02-D0-BINDING-01` | Exact captured-publication scientific binding |
| `GAP16G02-D0-STAGING-RETENTION-01` | Bounded private staging retention |
| `GAP16G02-D0-NONSCOPE-01` | Comprehensive non-scope + non-authorizing I1–I4 sketch |
| `GAP16G02-D0-ADMISSION-01` | Finite global bootstrap capacity (default 1) |

### Existing authorities that MUST be reused

| Authority | Role |
|---|---|
| Slice 9B | Deterministic source sampling + local question/case proposal |
| Slice 9C | Multi-retriever candidate evidence pooling |
| Slice 9D | Optional advisory local prelabeling |
| `GoldAuthoringRun` | Existing schema + persistence |
| Gold Lab pristine-baseline eligibility resolver | Admission of usable baselines |
| Workspace publication | Exact snapshot / corpus / chunk-set identity |
| ManagedOperation | Durable execution / idempotency / progress / recovery envelope |
| Existing campaign-create flow | Post-success human adjudication entry |

No second authoring pipeline.

---

## 2. Problem statement

Gold Lab currently:

```text
CAN:
  discover eligible pristine GoldAuthoringRun baselines
  create campaigns from those baselines
  perform human Gold adjudication
```

but the Seneca browser UI currently:

```text
CANNOT:
  create the pristine baseline that Gold Lab requires
```

Today the operator must leave Seneca and use the existing CLI:

```text
offline-rag gold propose
offline-rag gold pool
optional: offline-rag gold prelabel
```

This is a **product-orchestration gap**, not a missing scientific subsystem.

Canonical registration: GAP registry blob
`e1e537bf40d9988b1c2a4ea8676666ebc70464cb`
(`docs/slice16g_gap_registry_addendum.md` on main
`1c4e62a16f7e6b3f8cbf1efada2bafce7bc0f0d8`).

---

## 3. Purpose

Design one Gold Lab product flow that:

1. starts from a Gold Project,
2. binds scientifically to that project's workspace publication,
3. reuses accepted 9B → 9C → optional 9D science,
4. publishes exactly one canonical pristine `GoldAuthoringRun`,
5. exposes that run through the existing baseline resolver,
6. hands off explicitly to existing campaign creation,

while preserving:

```text
machine-proposed cases remain Silver
no automatic Gold
prelabels remain advisory
no GoldDataset-v1 semantic change
no ALLOW_PRODUCTION change
no 9G
no second authoring pipeline
```

---

## 4. End-to-end architecture

```text
Gold Lab project baseline surface
        ↓
POST /v1/gold-lab/projects/{project_id}/baseline-bootstrap
Idempotency-Key: ...
{ proposal_count, prelabel_enabled }
        ↓
202 Accepted
Location: /v1/operations/{operation_id}
        ↓
ManagedOperation kind = gold_lab_baseline_bootstrap
        ↓
workspace single-flight + global bootstrap capacity
        ↓
capture exact workspace publication ONCE
reserve authoring_run_id
derive sampling_seed from operation_id
        ↓
private operation staging
        ↓
9B against exact captured ChunkSet
        ↓
9C against same historical identity
        ↓
optional advisory 9D
        ↓
require >=1 is_reviewable_case()
        ↓
persist expected_final_artifact_sha256
short WorkspaceMutationLease → GoldLabProjectLease
revalidate captured publication
        ↓
atomic canonical promotion
  <corpus>/gold_authoring/runs/<authoring_run_id>.json
        ↓
existing pristine-baseline resolver admission
        ↓
ManagedOperation SUCCEEDED
+ GoldLabBaselineBootstrapResult
        ↓
refresh project baseline surface
        ↓
explicit existing campaign-create flow
```

Product ownership:

```text
Gold Lab owns the command semantically
ManagedOperation owns durable execution / idempotency / progress / recovery
```

They must not be conflated.

Scientific product result:

```text
canonical GoldAuthoringRun
```

Durable request proof:

```text
ManagedOperation record
```

---

## 5. Locked decision freeze

### 5.1 ENTRY-01 — Product entry ownership

```text
PRIMARY ENTRY:
  Gold Lab project / baseline area

PRIMARY USER INTENT:
  Create a pristine authoring baseline for this Gold Lab project

SCIENTIFIC BINDING:
  GoldProject
  → workspace_id
  → ACTIVE workspace
  → exact current publication
  → snapshot_id
  → corpus_id
  → chunk_set_id

SECONDARY ENTRY:
  OPTIONAL workspace CTA / deep-link
  → navigate to Gold Lab bootstrap surface
  → select/use existing Gold project bound to this workspace

SECONDARY SCIENTIFIC AUTHORITY:
  NONE

SECONDARY ORCHESTRATION:
  NONE

SECOND PIPELINE:
  FORBIDDEN

WORKSPACE-ONLY PRIMARY:
  REJECTED

DUAL-PRIMARY:
  REJECTED
```

Primary UI states:

```text
No eligible baseline exists
[Create baseline from workspace]

Eligible baselines
...
[Create another baseline from workspace]
```

Command scope:

```text
POST /v1/gold-lab/projects/{project_id}/...
```

not workspace-scoped.

The browser must **not** submit a competing workspace / snapshot / corpus /
chunk-set identity.

If no Gold project exists for a workspace CTA, creating/selecting a project is a
separate product interaction. The workspace CTA must not silently create a
project and bootstrap in one hidden operation.

### 5.2 ORCH-01 — Orchestration model

```text
One project-scoped bootstrap command
→ one durable ManagedOperation
→ one server-owned 9B → 9C → optional 9D sequence
→ one reserved GoldAuthoringRun identity
→ zero canonical intermediate artifacts
→ one final canonical baseline publication

Browser:
  start operation
  observe operation
  render progress/result
  refresh baseline discovery after success

Client-side scientific orchestration:
  NONE
```

Initiating HTTP is short-lived:

```text
POST → 202 Accepted
Location: /v1/operations/{operation_id}
```

The POST must not wait for 9B→9C→9D completion.

Rejected:

```text
Fully synchronous single POST
Client-stepwise multi-POST propose/pool/prelabel
Raw CLI-equivalent /gold/propose|/pool|/prelabel product APIs
Separate BootstrapJob framework
```

`prelabel_enabled` is selected at operation start. The server must not pause
after pooling to ask the browser whether to run 9D.

Scientific identity:

```text
ONE GoldAuthoringRun
```

Canonical baseline artifacts:

```text
ONE
```

Intermediate baseline-discoverable artifacts:

```text
ZERO
```

The same reserved `authoring_run_id` may have staged intermediate
representationsations during execution; only the final validated artifact becomes
visible at the canonical path.

### 5.3 PUBLISH-01 — Publish / success criteria

```text
Publish iff one valid, pristine, current-publication-bound,
Gold-Lab-usable baseline exists.

PARTIAL SCIENTIFIC-STAGE FAILURE:
  PERMITTED where already permitted by accepted 9B/9C/9D semantics

INTEGRITY / AUTHORITY FAILURE:
  FAIL CLOSED

ZERO REVIEWABLE CASES:
  FAIL CLOSED

ManagedOperation SUCCEEDED only after:
  atomic canonical publication
  AND existing baseline-resolver admission
```

Stage rules:

| Stage | Rule |
|---|---|
| 9B | `>=1` SilverCase to continue; `0` → FAILED, no canonical |
| 9B partial seed failures | ALLOWED |
| 9C | `>=1` pooled/reviewable case; per-case pool failures ALLOWED |
| 9C zero reviewable | FAIL CLOSED |
| 9D disabled | skipped |
| 9D enabled, valid start, per-case failures | ALLOWED; no invented grades |
| 9D enabled but cannot validly start | FAIL CLOSED |
| schema / provenance / historical identity failure | FAIL CLOSED |
| workspace/project/publication drift before commit | FAIL CLOSED / conflict |
| final resolver rejects | FAIL CLOSED; success MUST NOT be reported |

Decisive publication predicate:

```text
reviewable_case_count =
  sum(1 for case in run.cases if is_reviewable_case(case))

reviewable_case_count >= 1
```

plus:

```text
GoldAuthoringRun validates
reserved authoring_run_id matches
captured corpus_name/id/chunk_set_id match
assert_pristine_baseline(run)
historical source/candidate identity validation
project still valid
workspace still ACTIVE
workspace revision unchanged
current_snapshot_id unchanged
resolved publication identity unchanged
canonical destination safe for exact promotion/reconciliation
```

No new `PARTIAL_SUCCESS` ManagedOperation status. Partial stage outcomes are
telemetry on a `SUCCEEDED` result or bounded safe-error diagnostics on
`FAILED`.

### 5.4 REQUEST-01 — Request contract

```text
POST /v1/gold-lab/projects/{project_id}/baseline-bootstrap
Idempotency-Key: <required>

{
  "proposal_count": <int>,
  "prelabel_enabled": <bool>
}
```

Forbidden request fields:

```text
workspace_id
workspace_revision
snapshot_id
corpus_name
corpus_id
chunk_set_id
corpus manifest/path
output path
authoring_run_id
sampling_seed
retriever/top-k configuration
model/provider/endpoint override
force
campaign parameters
Gold labels
```

Client fingerprint includes:

```text
project_id
proposal_count
prelabel_enabled
```

plus existing ManagedOperation envelope fields as required.

After first admission, durable execution authority binds:

```text
workspace_id
workspace_revision
snapshot_id
corpus_id
corpus_name
chunk_set_id
reserved authoring_run_id
derived sampling_seed
```

Exact same-key retry recovers the original frozen execution authority and must
**not** recapture today's publication.

```text
same key + same request → recover same operation
same key + different request → IDEMPOTENCY_CONFLICT
new key + same visible request → new bootstrap intent
```

No `force`.

Observation remains solely:

```text
GET /v1/operations/{operation_id}
```

Route-count delta: **+1** Gold Lab command route.

### 5.5 PROPOSAL-COUNT-01 — Workload bounds

```text
proposal_count:
  integer
  1..40 inclusive

UI preset:
  20

POST:
  proposal_count MUST be explicit

Meaning:
  selected source seeds / maximum 9B proposal attempts
  (== Slice 9B --count)

NOT:
  guaranteed SilverCase count
  guaranteed pooled-case count
  guaranteed Gold case count
  production-Gold target
```

Runtime:

```text
proposal_count < 1     → REQUEST_INVALID
proposal_count > 40    → REQUEST_INVALID
proposal_count > eligible_source_population
                       → FAIL CLOSED under existing 9B semantics
silent clamp           → FORBIDDEN
auto-retry smaller     → FORBIDDEN
```

Authority boundary:

```text
Slice 9B scientific hard ceiling: UNCHANGED (none new)
GAP-16G-02 browser product maximum: 40
CLI may still accept counts >40 when population supports them
9G target influence: NONE
```

Basis for 40: existing 9F operational evidence
(`requested_proposal_count: 40`).

### 5.6 CONCURRENCY-01 — Scientific single-flight

```text
API command scope: project_id
Scientific single-flight key: resolved project.workspace_id
Max non-terminal bootstraps per workspace: 1
```

Active / non-terminal:

```text
PENDING
PREPARING
RUNNING
```

Terminal (do not block new intent):

```text
SUCCEEDED
FAILED
INTERRUPTED
```

Admission order:

1. Validate Idempotency-Key / request.
2. Same key + same request → recover that operation (skip single-flight reject).
3. Resolve project → workspace.
4. Another non-terminal bootstrap on that workspace → semantic conflict.
5. Otherwise continue to global capacity (ADMISSION-01).
6. Reserve/admit.

No queue. No global scientific singleton across workspaces.

### 5.7 SEED-01 — Deterministic sampling seed

```text
contract:
  baseline-bootstrap-sampling-seed-v1

material:
  "baseline-bootstrap-sampling-seed-v1|" + operation_id

digest:
  SHA-256(UTF-8(material))

sampling_seed:
  int.from_bytes(digest[0:8], "big") % (2**63)

range:
  0 <= sampling_seed < 2**63

persistence:
  GoldAuthoringRun.sampling_seed
```

Additional semantics:

```text
operation_id consumed in canonical persisted representation
  (no case-folding / trim / UUID reformatting)

missing/invalid operation_id → fail closed
  never fallback to 0 / clock / process RNG / hash() / Idempotency-Key

same operation_id ⇒ same sampling_seed
different operation_id ⇒ independently derived
  (no uniqueness guarantee; 63-bit)

retry/resume reuses persisted seed;
recomputation only as integrity check and must match

does not modify source-sampling-random-v1
Idempotency-Key is not sampling identity
constant seed 0 for all product bootstraps: REJECTED
```

### 5.8 STAGING-01 — Staging / canonical publication

```text
INTERMEDIATE STORAGE:
  SERVER-PRIVATE / OPERATION-BOUND

BINDING:
  operation_id
  + reserved authoring_run_id
  + workspace authority

INTERMEDIATE BASELINE DISCOVERY:
  ZERO

9B → 9C → optional 9D:
  ENRICH SAME STAGED GoldAuthoringRun IDENTITY

CANONICAL LOCATION:
  existing <corpus>/gold_authoring/runs/<authoring_run_id>.json

IDENTITY REWRITE ON PROMOTION:
  FORBIDDEN

FINAL PROMOTION:
  ATOMIC

CANONICAL COLLISION:
  EXACT RECONCILIATION OR FAIL CLOSED

BROWSER FILE/PATH INPUT:
  NONE

SECOND SCIENTIFIC NAMESPACE:
  NONE
```

Conceptual private layout (exact path follows existing conventions):

```text
<workspace-private>/operations/<operation_id>/gold-bootstrap/
    authoring_run.json
```

Before commit, canonical `<authoring_run_id>.json` must be absent.

Canonical collision:

```text
absent → normal promotion
present + exact reserved id + exact bytes/hash for this operation
  → crash-reconciliation case
present + differing content/provenance
  → FAIL CLOSED
  never overwrite via force
```

HTTP authoring-run upload: NONE.

### 5.9 OBSERVATION-01 — Observation / result contract

```text
ManagedOperationKind += gold_lab_baseline_bootstrap
ManagedOperationStatus: UNCHANGED
Observation endpoint: GET /v1/operations/{operation_id}
Bootstrap-specific status machine: NONE
New status resource: NONE
```

Advisory progress stages (presentation only):

```text
preparing
proposing
pooling
prelabeling
publishing
finalizing
ready
```

Suggested mapping:

| Durable status / phase | progress_stage |
|---|---|
| PENDING | null or preparing |
| PREPARING | preparing |
| RUNNING / 9B | proposing |
| RUNNING / 9C | pooling |
| RUNNING / 9D | prelabeling |
| RUNNING / canonical commit | publishing |
| RUNNING / eligibility verification | finalizing |
| SUCCEEDED | ready |
| FAILED / INTERRUPTED | last safely persisted stage |

Typed successful result: `GoldLabBaselineBootstrapResult`

```json
{
  "project_id": "gproj_...",
  "workspace_id": "ws_...",
  "workspace_revision": 17,
  "authoring_run_id": "authorrun_...",
  "snapshot_id": "...",
  "corpus_id": "...",
  "chunk_set_id": "...",
  "proposal_count": 20,
  "sampling_seed": 1738291042,
  "prelabel_enabled": false,
  "proposal_attempted": 20,
  "proposal_succeeded": 17,
  "proposal_failed": 3,
  "pool_targeted": 17,
  "pool_succeeded": 15,
  "pool_failed": 2,
  "prelabel_targeted": 0,
  "prelabel_succeeded": 0,
  "prelabel_failed": 0,
  "reviewable_case_count": 15,
  "baseline_eligible": true
}
```

Notes:

```text
corpus_name: not exposed in product result
prelabel counters: explicit zeros when disabled
baseline_eligible: MUST be true on SUCCEEDED
FAILED: result = null; ManagedOperationSafeError
INTERRUPTED: result = null unless CRASH-01 proves success
```

Counter semantics:

| Field | Meaning |
|---|---|
| `proposal_count` | original requested workload |
| `proposal_attempted` | actual 9B attempts performed |
| `proposal_succeeded` | SilverCases created by 9B |
| `proposal_failed` | attempted − succeeded |
| `pool_targeted` | cases 9C attempted |
| `pool_succeeded` | cases with complete valid candidate pool |
| `pool_failed` | targeted − succeeded |
| `prelabel_targeted` | pooled cases targeted by 9D |
| `prelabel_succeeded` | complete valid advisory prelabels |
| `prelabel_failed` | targeted − succeeded |
| `reviewable_case_count` | `is_reviewable_case()` count in final canonical run |

Never expose in operation result/error:

```text
raw provider exception / model response / prompt text
seed passage body / candidate body
filesystem / staging paths
credentials
Gold/prelabel grades / prelabel rationales
```

### 5.10 HANDOFF-01 — Post-success product handoff

```text
AFTER SUCCEEDED:
  remain on Gold Project baseline surface
  refresh existing baseline discovery
  surface newly eligible authoring_run_id
  offer explicit campaign creation
  optionally offer another baseline bootstrap

AUTOMATIC CAMPAIGN CREATION: NONE
AUTOMATIC GOLD WORK: NONE
AUTOMATIC GAME/SESSION START: NONE
```

Intended UX:

```text
Baseline ready
  N reviewable cases
  Snapshot: <safe provenance summary>

  [Create campaign from this baseline]
  [Create another baseline from workspace]
```

Campaign creation uses the **existing** campaign-create flow. Baseline
preselection is preferred UI convenience, not new scientific authority. If
navigation state cannot safely preselect, operator selects from refreshed list.

Failed/interrupted operations remain on the same surface with safe errors and
must not invent a baseline from staging.

### 5.11 CRASH-01 — Crash reconciliation

```text
RECOVERY MECHANISM:
  STARTUP-TIME DETERMINISTIC RECONCILIATION

RECOVERY ORDER:
  1. recover publication/workspace journals
  2. reconcile non-terminal gold_lab_baseline_bootstrap ops
  3. generic interrupt_all_nonterminal()
  4. runtime may become READY

RECONCILE-ON-GET:
  FORBIDDEN

GET /v1/operations/{id}:
  READ-ONLY
```

Pre-promotion durable proof MUST include at least:

```text
operation_id
project_id
workspace_id
captured workspace_revision
snapshot_id
corpus_id
chunk_set_id
reserved authoring_run_id
proposal_count
sampling_seed
prelabel_enabled
expected_final_artifact_sha256
```

`expected_final_artifact_sha256` must be durably committed **before** atomic
canonical promotion.

Final sequence:

```text
final staged GoldAuthoringRun validated
→ serialize exact final canonical bytes
→ compute SHA-256
→ durably persist expected final hash + frozen authority
→ acquire WorkspaceMutationLease → GoldLabProjectLease
→ final revalidation
→ atomic canonical promotion of those exact bytes
→ existing baseline resolver verification
→ ManagedOperation SUCCEEDED + result
```

Reconciliation matrix:

| Condition | Disposition |
|---|---|
| canonical absent | do not promote staging; generic INTERRUPTED |
| canonical present + exact hash/identity + PUBLISH-01 still holds | SUCCEEDED + reconstructed result |
| canonical present + exact artifact but eligibility no longer holds | NOT SUCCEEDED; preserve historical artifact; INTERRUPTED-class recovery disposition; no deletion |
| canonical present + hash/provenance conflict | FAIL CLOSED; no overwrite; no delete |
| staging alone | NEVER proves success |

```text
INTERRUPTED → SUCCEEDED transition: NOT REQUIRED / NOT AUTHORIZED
AUTOMATIC SCIENTIFIC RESUME: NONE
BROWSER FORCE-RECOVERY: NONE
```

Success-result reconstruction prefers durable authority + canonical run fields
where accepted 9B/9C/9D outcome data already exists; must not guess counts.

### 5.12 BINDING-01 — Scientific publication binding

```text
COMMAND ACCEPTANCE:
  resolve current project/workspace publication once

FROZEN EXECUTION AUTHORITY:
  workspace_revision
  snapshot_id
  corpus_name
  corpus_id
  chunk_set_id

9B: EXECUTE AGAINST EXACT CAPTURED HISTORICAL CHUNKSET
9C: EXECUTE AGAINST SAME run.chunk_set_id
9D: EXECUTE AGAINST SAME run.chunk_set_id

CURRENT RE-RESOLUTION DURING SCIENTIFIC PIPELINE: FORBIDDEN
CURRENT FALLBACK: FORBIDDEN
MIXED-PUBLICATION RUN: FORBIDDEN
```

Architectural separation (names illustrative):

```text
run_gold_propose(...)
  CLI convenience wrapper → resolves CURRENT

run_gold_propose_on_snapshot(...)
  reusable scientific core / product path
  receives exact snapshot/chunk-set authority
```

No scientific semantic changes to:

```text
source population semantics
deterministic seed sampling
proposal_count / sampling_seed semantics
prompt contract / parser / quality gates
attempt-once behavior
SilverCase construction
GoldAuthoringRun schema
```

Mid-run workspace republish does **not** retarget scientific execution. Final
commit revalidation fails closed on publication drift.

CLI public contract:

```text
offline-rag gold propose|pool|prelabel
UNCHANGED
```

### 5.13 STAGING-RETENTION-01 — Staging retention

```text
FAILED / INTERRUPTED + canonical absent:
  TEMPORARY PRIVATE RETENTION ALLOWED

SCIENTIFIC AUTHORITY OF STAGING:
  NONE

BASELINE DISCOVERY:
  ZERO

AUTOMATIC PROMOTION:
  FORBIDDEN

RETENTION:
  BOUNDED FINITE TTL

EXACT TTL VALUE:
  IMPLEMENTATION DETAIL / NOT PRODUCT CONTRACT
  not browser-tunable

CLEANUP OPPORTUNITIES:
  - startup scavenging of terminal staging older than TTL
  - next bootstrap admission for same workspace
  - ordinary post-terminal cleanup where practical

NEW BOOTSTRAP:
  NEVER REUSES PREVIOUS STAGING

SUCCEEDED:
  canonical is sole scientific artifact
  staging cleanup after durable success
  cleanup failure does not revoke success

PERMANENT FAILED-STAGING ARCHIVE:
  FORBIDDEN

BROWSER/API ACCESS TO STAGING:
  NONE
```

### 5.14 ADMISSION-01 — Global runtime capacity

```text
PER-WORKSPACE SCIENTIFIC SINGLE-FLIGHT:
  1 non-terminal bootstrap (CONCURRENCY-01)

GLOBAL BOOTSTRAP CAPACITY:
  FINITE / REQUIRED
  default = 1
  server/runtime configurable
  not hard-coded forever
  not browser-tunable

CAPACITY EXHAUSTED:
  SERVICE_OVERLOADED / RETRYABLE BUSY
  NOT GOLD_CONFLICT

SAME-WORKSPACE ACTIVE BOOTSTRAP:
  SEMANTIC CONFLICT

QUEUEING:
  NONE

SAME-KEY RETRY:
  RECOVER EXISTING OPERATION
  DOES NOT REQUIRE NEW CAPACITY

DEDICATED AUTHORING/BOOTSTRAP ADMISSION CLASS:
  PREFERRED
  MUST NOT inherit ingest semantics accidentally
```

Admission order:

```text
same-key replay? → recover
same-workspace active? → semantic conflict
global capacity available? → else SERVICE_OVERLOADED
admit/reserve → execute → terminal → release
```

Global capacity protects expensive authoring/retrieval resources; it is not a
workspace locking mechanism. Bootstrap continues against immutable captured
publication while workspace may mutate; commit-time revalidation decides
publishability.

### 5.15 NONSCOPE-01 — Explicit non-scope

See §14. Includes non-authorizing I1–I4 sketch (§15).

---

## 6. HTTP / DTO contracts

### 6.1 New command route

```text
POST /v1/gold-lab/projects/{project_id}/baseline-bootstrap
```

Headers:

```text
Idempotency-Key: required (existing normalization rules)
```

Request body:

```json
{
  "proposal_count": 20,
  "prelabel_enabled": false
}
```

Success response:

```text
202 Accepted
Location: /v1/operations/{operation_id}
```

Body may follow existing ManagedOperation creation projection conventions
already used by other async workspace/Gold Lab commands; D0 requires that the
operation identity be recoverable from `Location` and/or response fields
consistent with current `/v1/operations` observation.

### 6.2 Observation route

```text
GET /v1/operations/{operation_id}
```

Existing envelope. Bootstrap adds:

```text
kind = "gold_lab_baseline_bootstrap"
progress_stage ∈ {
  preparing, proposing, pooling, prelabeling,
  publishing, finalizing, ready
} ∪ existing advisory stages as applicable
result = GoldLabBaselineBootstrapResult | null
error = ManagedOperationSafeError | null
```

### 6.3 Routes deliberately not added

```text
GET /baseline-bootstrap/{id}
GET /bootstrap-runs/{id}
POST /gold/propose
POST /gold/pool
POST /gold/prelabel
POST /v1/workspaces/{id}/baseline-bootstrap
HTTP GoldAuthoringRun upload
```

### 6.4 Existing routes reused without redesign

```text
GET /v1/gold-lab/projects/{project_id}/baselines
POST /v1/gold-lab/projects/{project_id}/campaigns   (existing campaign create)
GET /v1/operations/{operation_id}
```

Exact campaign-create DTO remains the sealed 16F/16G contract; bootstrap does
not invent a second campaign API.

---

## 7. Lifecycle / state model

### 7.1 ManagedOperation status (unchanged)

```text
PENDING → PREPARING → RUNNING → SUCCEEDED
                              → FAILED
                              → INTERRUPTED (via startup recovery)
```

Bootstrap does not invent additional durable statuses.

### 7.2 Scientific lifecycle (server-owned)

```text
ADMITTED
→ PUBLICATION_CAPTURED
→ AUTHORING_RUN_RESERVED
→ SEED_DERIVED
→ STAGED_9B
→ STAGED_9C
→ STAGED_9D_OPTIONAL
→ FINAL_BYTES_HASHED
→ COMMIT_LOCKED
→ CANONICAL_PUBLISHED
→ RESOLVER_ADMITTED
→ OPERATION_SUCCEEDED
```

These are internal orchestration phases, not a second public state machine.
Browser-visible progress uses OBSERVATION-01 advisory stages only.

### 7.3 Product lifecycle

```text
No eligible baseline
→ operator starts bootstrap
→ observes operation
→ SUCCEEDED → baseline list refreshed → explicit campaign create
→ or FAILED/INTERRUPTED → remain on baseline surface
```

---

## 8. Idempotency matrix

| Condition | Result |
|---|---|
| Valid key + first request | Admit new operation; freeze execution authority |
| Same key + identical request fingerprint | Recover existing operation; no new capacity slot |
| Same key + different `proposal_count` / `prelabel_enabled` / project | `IDEMPOTENCY_CONFLICT` |
| Missing/invalid Idempotency-Key | request invalid per existing rules |
| New key + identical visible body | New bootstrap intent; new `operation_id`; new seed |
| `force=true` | NOT SUPPORTED |

Client fingerprint authority:

```text
project_id + proposal_count + prelabel_enabled
```

Server-resolved publication identities are **not** client fingerprint fields.

---

## 9. Concurrency / admission matrix

| Condition | Class | Outcome |
|---|---|---|
| Same key replay while op active | recovery | return existing operation |
| Different key; same workspace active | semantic conflict | reject; no queue |
| Different key; different project; same workspace active | semantic conflict | reject |
| Different workspace; global capacity free | admit | may start |
| Different workspace; global capacity exhausted | runtime busy | `SERVICE_OVERLOADED` / retryable |
| Prior op terminal SUCCEEDED/FAILED/INTERRUPTED | free | new key may start |
| INTERRUPTED counts as active | no | terminal |

```text
scientific single-flight key = workspace_id
global capacity default = 1
queue = NONE
```

---

## 10. Publication-race matrix

| Event | Scientific execution | Commit |
|---|---|---|
| Workspace republishes after capture | continues on captured ChunkSet | FAIL CLOSED if revision/snapshot/chunk identity drifted |
| Project deleted/invalid before commit | n/a | FAIL CLOSED |
| Workspace no longer ACTIVE | n/a | FAIL CLOSED |
| CURRENT moves but captured ChunkSet still loadable | continue on captured | subject to commit revalidation |
| Captured ChunkSet unloadable | FAIL CLOSED | no canonical |
| Mixed ChunkSet across stages | FORBIDDEN | must never occur |

No stage-by-stage CURRENT equality checks as a condition for scientific
execution.

---

## 11. Crash-reconciliation matrix

| Evidence | Action |
|---|---|
| Non-terminal bootstrap; canonical absent | do not promote staging; later generic INTERRUPTED |
| Non-terminal; canonical present; hash matches expected; PUBLISH-01 holds now | startup → SUCCEEDED + result |
| Non-terminal; canonical present; hash matches; eligibility no longer holds | preserve artifact; NOT SUCCEEDED; INTERRUPTED-class recovery |
| Non-terminal; canonical present; hash/provenance conflict | FAIL CLOSED; no overwrite/delete |
| Staging complete validators pass; canonical absent | still not success |
| GET observation during ambiguity | read-only; no mutation |
| After generic interrupt already applied | no INTERRUPTED→SUCCEEDED transition authorized |

Recovery order is mandatory: bootstrap reconciliation **before**
`interrupt_all_nonterminal()`.

---

## 12. Persistence / staging matrix

| Artifact | Location class | Baseline discoverable | Durable scientific |
|---|---|---|---|
| Staged authoring run | operation-private | NO | NO |
| Canonical authoring run | existing corpus runs path | YES if resolver admits | YES |
| ManagedOperation record | existing operations store | N/A | durable request/proof |
| expected_final_artifact_sha256 | private operation metadata | NO | recovery proof |
| Failed staging after TTL/scavenge | deleted | NO | NO |
| Success staging after SUCCEEDED | deleted best-effort | NO | NO |

```text
reserved authoring_run_id = X throughout 9B/9C/9D/canonical
canonical filename = X.json
identity rewrite on promote = FORBIDDEN
```

---

## 13. Privacy matrix

| Data | Browser/API | Staging/private ops | Canonical run |
|---|---|---|---|
| Seed passage body | NO | may exist transiently only as needed by 9B science in memory/reconstruction | NO (existing 9B privacy: reconstruct from chunk ids) |
| Raw model responses | NO | NO durable product exposure | NO (existing authoring privacy) |
| Prelabel rationales | NO | only inside accepted silver run fields if 9D wrote them | may exist as silver advisory fields only |
| Filesystem paths | NO | server-only | server-only |
| Credentials / endpoints | NO | NO | NO |
| Gold labels | N/A (bootstrap creates none) | none | none |
| Operation telemetry counts | YES (bounded) | YES | derived where available |
| Historical source text via Gold Lab task APIs | unchanged existing contracts; bootstrap itself does not add source-exposing routes | — | — |

Bootstrap performs **no human Gold mutation** and creates **no Gold truth**.

---

## 14. Explicit non-scope

Under `GAP-16G-02-D0-AUTH-002`, none of the following are authorized:

### Production execution

```text
Python/source implementation
HTTP route implementation
ManagedOperation schema/model implementation
worker/admission implementation
filesystem/staging implementation
React/UI implementation
production configuration changes
production tests as implementation evidence
```

### Adjacent 16G work

```text
16G-I6 (entirely)
16G-I6 integration/regression/a11y acceptance
16H
GAP-16G-01 changes or reopening
```

### Gold science / dataset

```text
GoldDataset-v1 semantic changes
GoldAuthoringRun semantic/schema changes unless separately authorized
HumanReview semantic changes
Gold ledger mutation
human Gold creation during bootstrap
contribution mutation
training-package writes
training truth mutation
```

### Production policy

```text
ALLOW_PRODUCTION changes
approved-presentations changes
calibration disposition
retrieval/model production promotion
```

### 9G

```text
adaptive top-up
automatic replacement sampling
resampling until target
proposal multipliers
automatic 100–150 Gold target generation
active-learning expansion
stopping-rule automation
split/freeze policy
any other 9G production-Gold expansion work
```

### Alternate authoring interfaces

```text
HTTP GoldAuthoringRun upload
browser filesystem path input
browser corpus/snapshot/chunk-set override
browser authoring_run_id control
raw CLI-equivalent /propose|/pool|/prelabel APIs
client-stepwise scientific orchestration
```

### Parallel infrastructure

```text
BootstrapJob framework / store
second generic job queue
second authoring-run repository
second baseline-discovery mechanism
second scientific authoring pipeline
```

### Post-bootstrap automation

```text
automatic campaign creation/publication
automatic Question Check / Evidence Sweep / Chunk Duel launch
automatic human work-session entry
```

### Other product surfaces

```text
learner/Training consuming bootstrap as a new workflow
Training package generation from bootstrap
NEXT-MILESTONE-CANDIDATE-01 answer-feedback work
```

### Later milestones

```text
Slice 17
Slice 18
M7 closeout/promotion
```

### CLI boundary

```text
offline-rag gold propose|pool|prelabel
PUBLIC CONTRACT: UNCHANGED
AVAILABILITY: PRESERVED
CLI behavior change: NONE
CLI removal: NONE
new required CLI arguments: NONE
internal reuse/refactor: MAY BE DESIGNED; NOT IMPLEMENTED UNDER D0
```

### Secondary workspace CTA

```text
DESIGN-ALLOWED
NAVIGATION ONLY
Separate API/orchestration/scientific authority: NONE
Required in first implementation slice: NO
```

---

## 15. Future implementation decomposition — planning only / not authorized

```text
These slice names/scopes are planning artifacts only.

They do not:
  authorize branch creation for implementation
  authorize code changes
  authorize tests
  authorize implementation
  imply sequencing acceptance
  imply Human acceptance
  imply downstream I6 authority

Future implementation still requires:
  Human accepts exact D0 design tip
  → separate GAP-16G-02 implementation authority issued
  → only then may production code change
```

### GAP-16G-02-I1 — Core contracts and exact scientific binding

Possible future scope:

- ManagedOperation kind/result contracts
- durable bootstrap execution authority
- deterministic operation-bound seed
- reserved `authoring_run_id`
- private staging contract
- reusable exact-captured-snapshot 9B entry
- preserve CLI contract
- no HTTP/UI yet

### GAP-16G-02-I2 — Server orchestration and publication

Possible future scope:

- Gold Lab bootstrap application service
- workspace-scoped single-flight
- bounded runtime admission
- 9B → 9C → optional 9D orchestration
- partial-stage semantics (PUBLISH-01)
- short final lock boundary
- atomic canonical promotion
- resolver verification
- terminal result persistence

### GAP-16G-02-I3 — Recovery and HTTP product surface

Possible future scope:

- startup crash reconciliation
- expected-final-artifact hash proof
- staging scavenging
- `POST .../baseline-bootstrap` route
- existing `/v1/operations` observation integration
- safe error/result DTO projection

### GAP-16G-02-I4 — Gold Lab browser integration and closure tests

Possible future scope:

- project baseline UI
- generate-baseline controls
- operation progress
- baseline refresh
- explicit campaign handoff
- retry/race/crash/integration tests
- optional workspace navigation CTA if separately included

---

## 16. Test / acceptance matrix (design-level; not authorizing tests)

Future implementation authorities must prove at least:

| Area | Required proof |
|---|---|
| Entry | Project-scoped command; browser cannot supply competing publication ids |
| Idempotency | same-key recover; same-key different body conflict; new-key new seed |
| Concurrency | second workspace intent conflicts; different workspace may proceed |
| Admission | capacity exhausted → overloaded/retryable; not gold_conflict |
| Binding | 9B/9C/9D use captured ChunkSet; CURRENT drift does not retarget science |
| Publish | zero reviewable → no canonical; partial 9C/9D permitted; pristine holds |
| Staging | intermediate never in baseline discovery |
| Success | SUCCEEDED only after canonical + resolver admission; `baseline_eligible=true` |
| Handoff | no auto campaign/games; refresh baselines; explicit create CTA |
| Crash | startup reconcile before interrupt; GET read-only; staging alone ≠ success |
| Privacy | no paths/raw model/seed bodies in API result |
| Policy | ALLOW_PRODUCTION unchanged/empty |
| CLI | propose/pool/prelabel public contract preserved |
| Network/product | no client-stepwise propose/pool/prelabel product API |

---

## 17. Registration-level invariants (preserved)

From canonical GAP registration, preserved and operationalized by this D0:

```text
1. Machine-proposed questions/cases remain Silver.
2. No proposed case becomes Gold automatically.
3. Model prelabels remain advisory only.
4. Prelabels MUST NOT establish human relevance truth.
5. Baseline bootstrap performs no human Gold mutation.
6. Result MUST satisfy existing pristine-baseline eligibility.
7. Snapshot/corpus/chunk-set identity remains exact.
8. No filename/fuzzy/similarity migration.
9. No arbitrary browser filesystem path input.
10. No GoldDataset-v1 semantic change.
11. No automatic retrieval/model promotion.
12. No adaptive top-up / resampling policy for future 9G
    unless separately designed and authorized.
```

---

## 18. Relationship to deferred Slice 9G

```text
Slice 9G:
DEFERRED / NOT AUTHORIZED
```

This D0 does **not** reopen 9G.

When 9G is eventually authorized, the intended product path remains:

```text
stable publication corpus
→ sufficiently large pristine candidate baseline
→ Gold Lab campaign
→ Question Check
→ complete 0/1/2 evidence adjudication
→ ~100–150 finalized production Gold cases
→ dev / held-out freeze
→ formal 9H
```

Do **not** freeze a proposal-count multiplier here.
`proposal_count` max 40 is a GAP-16G-02 v1 product bound only.

---

## 19. Relationship to frozen 16G-D0 and I5

```text
Frozen 16G-D0 blob:
edc2be739621dbedfc44ed77861119a35f8f6d18
PRESERVED

Human-accepted I5 tip:
35ec9be5647d41c887eb280146c05b9688dea685
STARTING PRODUCT TIP ONLY

Training / calibration / contribution surfaces:
OUT OF SCOPE for bootstrap
```

Bootstrap produces a pristine baseline for Gold Lab campaign creation. It does
not alter Training compiler package truth or contribution semantics.

---

## 20. Unresolved design issues

```text
NONE
```

All product forks required for a coherent D0 were closed under:

```text
ENTRY ORCH PUBLISH REQUEST PROPOSAL-COUNT
CONCURRENCY SEED STAGING OBSERVATION HANDOFF
CRASH BINDING STAGING-RETENTION NONSCOPE ADMISSION
```

Exact staging pathname, exact TTL hours, and exact internal function names remain
implementation details constrained by the visibility/ownership/reuse contracts
frozen above.

---

## 21. Stop condition

```text
STOP — GAP-16G-02 D0 design handoff

Authority:
GAP-16G-02-D0-AUTH-002

Branch:
design/gap-16g-02-gold-baseline-bootstrap

Starting product tip:
35ec9be5647d41c887eb280146c05b9688dea685

Design tip:
650ed772ea7f0b710f504af84ae59b16796d51a9

Frozen 16G-D0 blob:
edc2be739621dbedfc44ed77861119a35f8f6d18
PRESERVED

Canonical GAP registry blob:
e1e537bf40d9988b1c2a4ea8676666ebc70464cb
PRESERVED

9B/9C/9D design blobs:
PRESERVED

Implementation:
NOT AUTHORIZED

16G-I6:
NOT AUTHORIZED

9G:
DEFERRED / NOT AUTHORIZED

ALLOW_PRODUCTION:
UNCHANGED / EMPTY

FINAL ACTION:
STOP FOR INDEPENDENT GAP-16G-02 D0 DESIGN REVIEW
```
