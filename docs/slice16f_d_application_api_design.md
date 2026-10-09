# 16F-D0 — Gold Lab Application / API Data Plane

```text
16F-D0 GOLD LAB APPLICATION / API CONTRACT FREEZE
DESIGN MATERIALIZATION — STOP FOR INDEPENDENT DESIGN REVIEW

HUMAN DESIGN ACCEPTANCE:
PENDING

16F-D PRODUCTION IMPLEMENTATION:
NOT AUTHORIZED

16G–16H:
NOT AUTHORIZED

9G:
DEFERRED / NOT AUTHORIZED

SLICE 17 / 18 / M7 CLOSEOUT:
NOT AUTHORIZED
```

## Authority / lineage

| Item | Value |
|---|---|
| Frozen 16F design authority | `4fde40da2458d69f9249b8334210fc84e9f3239c` |
| Accepted / frozen 16F-A | `2e4d51b06763ed04bce8b6e2d60337f61082bc64` |
| Accepted / frozen 16F-B | `f4fe892044f8443594d7629e5b49a3d9f39b6297` |
| Accepted / frozen 16F-C | `646b1f178e10b49d3f39322dff8314dbd4f9987e` |
| Branch | `design/16f-d-application-api-data-plane` |
| Starting HEAD | `646b1f178e10b49d3f39322dff8314dbd4f9987e` |
| Design SHA | `aaa409b0338ceb46bfaeeea18f9b2d5dc6ee5e71` |
| Design SHA fill tip | `982629d25c17f7641688f266785019755aeb8913` |
| Rework 1 starting HEAD | `982629d25c17f7641688f266785019755aeb8913` |
| Rework 1 design SHA | `1082ecb22ba9db5ac691ae3ff2d29016a2906650` |
| Rework 1 tip | `86a3fd6028db4a26567fe8de05a706e7a147685f` |
| Rework 2 starting HEAD | `86a3fd6028db4a26567fe8de05a706e7a147685f` |
| Rework 2 design SHA | `bcd6afc74eb995037da5477d7b3eef8e4ea8545a` |
| Rework 2 tip | `82fef0b71abd341b7a201d91a5eb01fa2b490ee0` |
| Rework 3 starting HEAD | `82fef0b71abd341b7a201d91a5eb01fa2b490ee0` |
| Rework 3 design SHA | `REWORK3_DESIGN_SHA_PENDING` |

Frozen parent decision (must not be reopened):

> Exact HTTP DTOs / errors **MUST** be frozen before implementation of 16F-D.
> (`docs/slice16f_gold_lab_data_plane.md` §16F-D20)

This document freezes that contract. It does **not** authorize implementation.

Do **not** treat this design materialization as human acceptance of 16F-D
implementation.

### Design Rework 1

Hardening only (no route/DTO redesign; no production authorization):

- separate HTTP baseline lookup (`gold_baseline_unknown`) from sealed-campaign
  baseline corruption (`baseline_missing` → `gold_state_unavailable`);
- idempotency error provenance (true caller conflict vs durable catalog integrity);
- durable scientific-identity error provenance;
- exact historical source resolution algorithm and field authority;
- strict authoring-run path/content identity for discovery and campaign create.

### Design Rework 2

Hardening only (preserves Rework 1 + route/DTO surface):

- complete throw-site-accurate error table (`question_check_edit_not_semantic` vs
  durable QC edit invariant; ledger membership / server-derived authorities);
- shared baseline eligibility preflight with consistent 404 / 409 classification;
- historical Gold task read from immutable snapshot/corpus/chunk manifests only
  (no current retrieval-config / Qdrant / lexical / embedder / reranker dependency);
- exact display-only `document_title` authority.

### Design Rework 3

Hardening only (preserves Rework 1 / Rework 2 + route/DTO surface):

- filesystem confinement for the direct historical reader (durable path data is
  untrusted until validated; root-confined snapshot / manifest / chunk reads);
- baseline eligibility class **D** for structurally valid but scientifically
  ineligible pristine-admission failures (`baseline_human_state_present`,
  `baseline_identity_missing` → preflight `gold_conflict`);
- preflight vs post-successful-preflight escape provenance for those reasons.

---

## Scope / non-scope

### In scope (design freeze only)

- Thin product/API adapter over accepted 16F-A / 16F-B / 16F-C services
- Exact `/v1/gold-lab` route set
- Exact request / response DTOs
- Task presentation / historical source-context contracts
- Blind-authority exclusion table
- Idempotency header semantics and mutation ordering
- Product `ErrorCode` additions and exhaustive `GoldLabError` → `AppError` mapping
- Expected future implementation footprint and test matrix

### Explicit non-scope

| Item | Status |
|---|---|
| FastAPI routes / runtime wiring / production code | NOT AUTHORIZED |
| UI / React / Gold Lab pages | NOT AUTHORIZED |
| 16G games / workloads / sessions / leaderboards | NOT AUTHORIZED |
| 16H | NOT AUTHORIZED |
| 9G | DEFERRED / NOT AUTHORIZED |
| Scientific schema changes (GoldDataset-v1, HumanReview, ledger, registration) | FORBIDDEN |
| Retrieval / config / `base.yaml` promotion | FORBIDDEN |
| ManagedOperation / async Gold queue / HTTP 202 | FORBIDDEN |
| Uploading `GoldAuthoringRun` over HTTP | FORBIDDEN |
| Filesystem-path inputs in HTTP bodies | FORBIDDEN |
| Modification of accepted A/B/C evidence docs | FORBIDDEN |
| Modification of `docs/slice16f_gold_lab_data_plane.md` | FORBIDDEN |
| M7 pinned evidence changes | FORBIDDEN |

---

## Architecture layering

```text
HTTP / FastAPI  (/v1/gold-lab)
        ↓
GoldLabApplicationService   (product orchestration only)
        ↓
accepted services:
  GoldLabStore
  GoldCampaignService
  GoldLabMutationService
  GoldLabScientificExportService
  historical chunk/snapshot read access
        ↓
existing persistence / scientific contracts
```

### Hard rules

16F-D **MUST NOT**:

- append the Gold ledger directly;
- calculate supersession itself;
- calculate query fingerprints itself;
- calculate contribution itself;
- finalize `GoldDataset` itself;
- register datasets itself;
- create a second scientific projection authority;
- bypass accepted A/B/C validators.

All scientific writes go through accepted service boundaries.

---

## Proposed application facade

**Name:** `GoldLabApplicationService`  
**Recommended location:** `src/offline_rag/app/gold_lab/application.py`

Owns product orchestration only:

- project views / lifecycle;
- campaign views / creation / lifecycle;
- baseline discovery;
- safe task listing / detail projection;
- exact historical source-context resolution;
- dispatch to accepted idempotent expert mutation service;
- contribution view;
- scientific export;
- registration views.

It **MUST NOT** become another scientific authority.

Recommended companion view/DTO module (implementation later):

`src/offline_rag/app/gold_lab/views.py`

---

## Runtime wiring

Freeze a lazy property analogous to `ApplicationRuntime.workspace_lifecycle`:

```text
ApplicationRuntime.gold_lab  →  GoldLabApplicationService
```

The facade receives the existing runtime and therefore uses:

- `runtime.settings`
- `runtime.publication`
- `runtime.resources.qdrant` where campaign creation already requires it

Do **not** construct new embedding / reranking / generation resources.

No model/provider calls belong to Gold Lab API operations.

All Gold Lab HTTP endpoints call `runtime.require_ready()` before normal service
execution (FastAPI body/header validation may naturally precede route entry).

No special Gold Lab runtime lifecycle. No ManagedOperationKind. No Gold queue.
No HTTP 202.

---

## HTTP route prefix

| Item | Freeze |
|---|---|
| Prefix | `/v1/gold-lab` |
| New API module | `src/offline_rag/api/gold_lab.py` |
| Registration | one router in existing `src/offline_rag/api/app.py` |
| Second FastAPI app | FORBIDDEN |

---

## Exact route table

| Method | Path | Purpose | Authority |
|---|---|---|---|
| GET | `/v1/gold-lab/projects` | List projects | `GoldLabStore` |
| POST | `/v1/gold-lab/projects` | Create project | `GoldLabStore` |
| GET | `/v1/gold-lab/projects/{project_id}` | Get project | `GoldLabStore` |
| POST | `/v1/gold-lab/projects/{project_id}/archive` | Archive project | `GoldLabStore` |
| GET | `/v1/gold-lab/projects/{project_id}/baselines` | Discover eligible baselines | store + workspace + authoring-run scan + 16F-A pristine admission |
| GET | `/v1/gold-lab/projects/{project_id}/campaigns` | List campaigns | `GoldLabStore` |
| POST | `/v1/gold-lab/projects/{project_id}/campaigns` | Create campaign | `GoldCampaignService` |
| GET | `/v1/gold-lab/campaigns/{campaign_id}` | Get campaign | `GoldLabStore` (+ project type) |
| POST | `/v1/gold-lab/campaigns/{campaign_id}/close` | Close campaign | `GoldLabStore` |
| GET | `/v1/gold-lab/campaigns/{campaign_id}/tasks` | List tasks | `GoldLabMutationService` / `BlindTaskView` |
| GET | `/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}` | Task detail | effective state + historical chunk read |
| POST | `/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/question-check` | Question Check mutation | `GoldLabMutationService` ONLY |
| POST | `/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/relevance` | Absolute relevance mutation | `GoldLabMutationService` ONLY |
| POST | `/v1/gold-lab/campaigns/{campaign_id}/preferences` | Auxiliary preference | `GoldLabMutationService` ONLY |
| GET | `/v1/gold-lab/campaigns/{campaign_id}/contribution` | Contribution view | `GoldLabMutationService.contribution` |
| POST | `/v1/gold-lab/campaigns/{campaign_id}/export` | Scientific export/register | `GoldLabScientificExportService` |
| GET | `/v1/gold-lab/campaigns/{campaign_id}/registrations` | List validated registrations | 16F-C authoritative validator |

No other Gold Lab HTTP routes in 16F-D v1.

### Explicitly excluded routes

Do **not** add:

`/rapid-fire`, `/evidence-sweep`, `/question-check-game`, `/chunk-duel`,
`/workload`, `/session`, `/leaderboard`, `/training`.

16G owns workload/game orchestration. 16F-D exposes only deterministic safe task
state from which 16G may later select batch sizes (`1`, `5`, `10`, `25`,
complete case, until stop). No random task selection in 16F-D.

---

## Project contracts

### GET `/v1/gold-lab/projects`

Optional query:

| Field | Type | Default |
|---|---|---|
| `workspace_id` | `string \| null` | absent = all projects |

Ordering: `created_at` ascending, then `project_id` ascending.

Response:

```json
{
  "projects": [/* GoldProjectView */]
}
```

### GoldProjectView

```json
{
  "project_id": "string",
  "workspace_id": "string",
  "title": "string",
  "description": "string",
  "project_type": "benchmark | improvement",
  "status": "active | archived",
  "created_at": "RFC3339 UTC string"
}
```

No filesystem paths.

### POST `/v1/gold-lab/projects`

Request (`extra="forbid"`):

```json
{
  "workspace_id": "string",
  "title": "string",
  "description": "",
  "project_type": "benchmark | improvement"
}
```

- Server allocates `project_id`.
- Client **MUST NOT** provide `project_id`.
- Success: **201** `GoldProjectView`.
- 16F-D v1 does **not** claim durable HTTP idempotency for project creation.
- Do **not** reuse the expert-decision idempotency catalog for project setup.

### GET `/v1/gold-lab/projects/{project_id}`

**200** `GoldProjectView`.

### POST `/v1/gold-lab/projects/{project_id}/archive`

- No request body.
- Success: **200** `GoldProjectView` with `status="archived"`.
- Archive is one-way.
- Repeated archive: **409** `gold_conflict`.
- No unarchive endpoint.

---

## Baseline eligibility resolver (shared)

Freeze one application-level baseline eligibility resolver used by both:

- `GET .../baselines` (discovery scan)
- `POST .../campaigns` (create preflight)

Input: `project_id` + `baseline_authoring_run_id`

It **MUST** perform:

1. safe `authoring_run_id` validation;
2. exact canonical path lookup
   (`default_authoring_run_path(..., authoring_run_id=R)`);
3. `filename stem == loaded run.authoring_run_id`;
4. valid `GoldAuthoringRun`;
5. pristine 16F-A admission;
6. exact current project-workspace snapshot corpus / chunk-set binding.

### Classification (frozen — A/B/C/D)

| Condition | Product projection |
|---|---|
| A. canonical run does not exist | `gold_baseline_unknown` / **404** |
| B. canonical file corrupt, schema invalid, or path/internal identity disagrees | `gold_state_unavailable` / **409** |
| C. otherwise eligible-form run is stale against the project's CURRENT workspace corpus/chunk-set binding | `gold_conflict` / **409** |
| D. canonical `GoldAuthoringRun` is structurally valid but scientifically **INELIGIBLE** for pristine campaign admission | `gold_conflict` / **409** |

Class D includes at minimum:

- `baseline_human_state_present`
- `baseline_identity_missing`

The run exists; it is simply not a valid pristine campaign seed.
Do **not** classify D as 404 or `request_invalid`.

Do **not** use `request_invalid` merely because the user selected a stale or
non-pristine server-owned artifact.

`GoldCampaignService` remains final scientific authority after application
preflight.

### Discovery scanning behavior

`GET .../baselines` returns only successful resolver results.

| Class | Discovery scan |
|---|---|
| A absent | not applicable to a scanned existing file |
| B corrupt / path-identity invalid | do **not** surface |
| C stale | do **not** surface |
| D non-pristine / ineligible | do **not** surface |

Do **not** silently reinterpret an ineligible artifact as another baseline.
Campaign-create direct lookup still returns the exact A/B/C/D product error.

## Baseline discovery

### GET `/v1/gold-lab/projects/{project_id}/baselines`

Purpose: discover **server-owned** `GoldAuthoringRun` artifacts eligible to seed
a campaign.

Rules:

- Do **not** upload `GoldAuthoringRun` through HTTP.
- Do **not** accept arbitrary filesystem paths.
- Resolve `project → workspace → backing corpus`.
- Scan only the existing canonical authoring-run directory for that corpus
  (`default_authoring_runs_dir(settings, corpus_name=...)`).
- Apply the shared baseline eligibility resolver to every candidate file.
- Surface only class-success results (identity + pristine + CURRENT binding);
  suppress B/C/D as above.

Response:

```json
{
  "project_id": "string",
  "baselines": [
    {
      "authoring_run_id": "string",
      "created_at": "RFC3339 UTC string",
      "corpus_id": "string",
      "corpus_name": "string",
      "chunk_set_id": "string",
      "case_count": 0,
      "reviewable_case_count": 0
    }
  ]
}
```

Ordering: `created_at` ascending, `authoring_run_id` ascending.

Must **not** include: model judgments, prelabels, retrieval hits, proposal
rationale, filesystem paths.

---

## Campaign contracts

### GET `/v1/gold-lab/projects/{project_id}/campaigns`

```json
{
  "project_id": "string",
  "campaigns": [/* GoldCampaignView */]
}
```

Ordering: `created_at` ascending, `campaign_id` ascending.

### GoldCampaignView

```json
{
  "campaign_id": "string",
  "project_id": "string",
  "workspace_id": "string",
  "project_type": "benchmark | improvement",
  "snapshot_id": "string",
  "chunk_set_id": "string",
  "corpus_id": "string",
  "corpus_name": "string",
  "baseline_authoring_run_id": "string",
  "workspace_revision_at_creation": 1,
  "status": "open | closed",
  "created_at": "RFC3339 UTC string"
}
```

`project_type` is derived from the owning project's durable `project_type`
(must equal campaign selection-policy project type under accepted coherence).

Must **not** expose: hard_calls, hard-call `reason_code`, retrieval
configuration, ranks/scores, model labels, prelabel information, filesystem
paths.

### POST `/v1/gold-lab/projects/{project_id}/campaigns`

Request (`extra="forbid"`):

```json
{
  "baseline_authoring_run_id": "string",
  "selection_policy_id": "string",
  "selection_policy_parameters": {},
  "hard_calls": [
    {
      "case_id": "string",
      "candidate_chunk_id": "string",
      "reason_code": "string"
    }
  ]
}
```

Defaults: `selection_policy_parameters = {}`, `hard_calls = []`.

Client **MUST NOT** provide:

`campaign_id`, `project_type`, `selection_policy_fingerprint`, `task_id`,
`designation_id`, `snapshot_id`, `chunk_set_id`, `corpus_id`, `corpus_name`,
`workspace_revision`.

#### Campaign create derivation (facade)

1. resolve project;
2. resolve project workspace / backing corpus;
3. run shared baseline eligibility resolver for
   `(project_id, baseline_authoring_run_id)` and apply A/B/C/D classification
   above (do **not** alias one run through another filename);
4. allocate `campaign_id` server-side;
5. derive `project_type` from project;
6. construct `GoldSelectionPolicy` using accepted builder;
7. for each hard-call input:
   - derive absolute `task_id` from `(campaign_id, case_id, candidate_chunk_id)`;
   - derive `hard_call_designation_id`;
8. call accepted `GoldCampaignService.create_campaign()`.

`GoldCampaignService` remains the final scientific validator.
The HTTP adapter **MUST NOT** reproduce campaign-binding logic.

#### Preflight vs post-preflight escape (frozen)

During baseline eligibility **preflight**:

| reason | Preflight class | Product |
|---|---|---|
| `baseline_human_state_present` | D | `gold_conflict` / 409 |
| `baseline_identity_missing` | D | `gold_conflict` / 409 |
| `chunk_set_mismatch` | C | `gold_conflict` / 409 |
| `corpus_id_mismatch` | C | `gold_conflict` / 409 |
| `corpus_name_mismatch` | C | `gold_conflict` / 409 |

If `baseline_human_state_present` or `baseline_identity_missing` somehow
escapes from `GoldCampaignService` **after** that same baseline successfully
passed the shared preflight:

→ `gold_state_unavailable` / 409

because the application preflight and authoritative campaign service then
disagree about the same immutable artifact.

Race / staleness escapes after preflight remain:

| reason | Escape mapping | Why |
|---|---|---|
| `chunk_set_mismatch` | `gold_conflict` / 409 | CURRENT binding race / staleness |
| `corpus_id_mismatch` | `gold_conflict` / 409 | CURRENT binding race / staleness |
| `corpus_name_mismatch` | `gold_conflict` / 409 | CURRENT binding race / staleness |

Never map any of the above as `request_invalid`.

Success: **201** `GoldCampaignView`.

No HTTP idempotency claim for campaign creation in 16F-D v1.
No hidden retry catalog.
No client-provided campaign ID.

### GET `/v1/gold-lab/campaigns/{campaign_id}`

**200** `GoldCampaignView`.

### POST `/v1/gold-lab/campaigns/{campaign_id}/close`

- No request body.
- Success: **200** `GoldCampaignView` with `status="closed"`.
- Repeated close: **409** `gold_conflict`.
- No reopen endpoint.

---

## Task contracts

### GET `/v1/gold-lab/campaigns/{campaign_id}/tasks`

Optional query filters:

| Field | Values |
|---|---|
| `kind` | `question_check` \| `absolute_relevance` \| null |
| `state` | `pending` \| `completed` \| null |
| `active` | `true` \| `false` \| null |
| `case_id` | `string` \| null |

Response:

```json
{
  "campaign_id": "string",
  "tasks": [/* GoldTaskSummary */]
}
```

Ordering **MUST** be the accepted deterministic `project_tasks()` order:

baseline case order → Question Check first → candidate order as preserved by
baseline.

No randomization. No pagination in 16F-D v1.

### GoldTaskSummary

Exact accepted `BlindTaskView` contract:

```json
{
  "task_id": "string",
  "task_kind": "question_check | absolute_relevance",
  "campaign_id": "string",
  "case_id": "string",
  "active": true,
  "state": "pending | completed",
  "candidate_chunk_id": "string | null",
  "effective_query": "string | null"
}
```

Do not add machine/retrieval metadata.

### GET `/v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}`

Return `GoldTaskDetail`:

```json
{
  /* ...GoldTaskSummary fields... */
  "presentation": "object | null",
  "current_result": "object | null"
}
```

---

## Task presentation contracts

### Question Check presentation

When `task_kind == "question_check"`:

```json
{
  "kind": "question_check",
  "proposed_query": "string",
  "proposed_category": "string | null",
  "proposed_tags": ["string"],
  "source": "GoldSourceContext | null"
}
```

Exact Question Check source authority:

- `case.source_seed is None` → `source = null`
- `case.source_seed` present → resolve **exact** `case.source_seed.chunk_id`
  from the campaign historical binding (algorithm below)

No candidate substitution. No CURRENT substitution. No nearest/fuzzy source.

Must **not** expose: proposal rationale, model judgments, prelabel summary /
provenance, retrieval hits, hard-call designation/reason.

### Question Check current result

- No current decision → `current_result = null`
- Otherwise:

```json
{
  "kind": "question_check",
  "decision": "accept | edit | reject",
  "effective_query": "string | null",
  "effective_category": "string | null",
  "effective_tags": ["string"]
}
```

This is the expert's current effective decision, not model advice.

### Absolute relevance presentation

When `task_kind == "absolute_relevance"`:

- If `task.active == false`: `presentation = null`  
  (do **not** expose candidate chunk text for inactive absolute tasks)
- If active:

```json
{
  "kind": "absolute_relevance",
  "effective_query": "string",
  "effective_category": "string | null",
  "effective_tags": ["string"],
  "candidate": "GoldSourceContext"
}
```

Exact absolute source authority:

- `candidate_chunk_id` is already server-derived from stable task authority;
- `presentation.candidate` resolves **exact** `candidate_chunk_id` from the
  campaign historical binding;

No retrieval is run. No neighboring expansion. No source-seed substitution.

### Absolute current result

- No current effective judgment → `null`
- Else:

```json
{
  "kind": "absolute_relevance",
  "relevance": 0
}
```

`relevance` is exactly `0 | 1 | 2`. Only current-query-basis judgment may be
exposed.

---

## Historical source-context resolution

### GoldSourceContext

```json
{
  "chunk_id": "string",
  "document_id": "string",
  "document_title": "string | null",
  "source_name": "string | null",
  "section_path": ["string"],
  "page_start": "integer | null",
  "page_end": "integer | null",
  "line_start": "integer | null",
  "line_end": "integer | null",
  "content_type": "string",
  "text": "string"
}
```

### Historical source resolution algorithm (frozen — Rework 2 + Rework 3)

Historical Gold source presentation **MUST NOT** use normal
`ProductPublicationRegistry.resolve_snapshot(...)` as the final resolver when
that path requires current embedding / dense-index / lexical / fusion /
reranker / context config or live Qdrant / lexical backing.

Path validation for confinement **MUST NOT** accidentally reintroduce that
method's current-readiness semantics.

#### Server-owned path data is untrusted until validated

HTTP clients do not supply historical filesystem paths, but durable Gold /
snapshot metadata **MUST NOT** be blindly trusted for path construction.

Before constructing **any** historical-source filesystem path, validate the
server-owned durable identity / reference. Corrupt durable path metadata →
`gold_state_unavailable` / HTTP **409** / retryable **false**. Never reinterpret
as `request_invalid`.

#### Frozen root hierarchy (only roots allowed)

```text
settings.paths.corpora
  / <validated campaign.corpus_name>
  / product
  / snapshots
  / <validated campaign.snapshot_id>.json

settings.paths.manifests
  / <validated filename-only corpus_manifest>

settings.paths.chunk_manifests
  / <validated filename-only chunk_manifest>

settings.paths.chunks
  / <validated chunk_artifact_id>.json
```

No other roots. No caller-supplied paths. No absolute reference escape.
No symlink policy change is required in 16F-D unless existing repository
policy already mandates one.

#### Frozen immutable-artifact algorithm

1. load server-owned `GoldCampaign`;

2. **before** snapshot-path construction, validate `campaign.corpus_name` with
   existing product corpus-name authority
   `validate_product_corpus_name(...)` (or an exactly equivalent validation
   contract). Reject `/`, `\`, `..`, absolute paths, and any product-invalid
   corpus name. Failure → historical binding corruption →
   `gold_state_unavailable` / 409;

3. **before** snapshot-path construction, require durable
   `campaign.snapshot_id` matches exact canonical grammar:

   ```text
   ^snap_[0-9a-f]{64}$
   ```

   (matches `compute_snapshot_id()` output). Any mismatch →
   `gold_state_unavailable` / 409. Do **not** construct a snapshot path first
   and validate later;

4. derive immutable snapshot-manifest path **only** as:

   ```text
   settings.paths.corpora / validated_corpus_name / "product" / "snapshots"
     / f"{validated_snapshot_id}.json"
   ```

5. load `CanonicalSnapshotManifest` **directly** from that immutable snapshot
   file; parse strictly. Require at minimum:

   ```text
   schema_version == offline-rag-corpus-read-snapshot-v1
   product_mode_id == grounded_v1
   ```

6. recompute snapshot identity and require
   `compute_snapshot_id(identity) == campaign.snapshot_id`;

7. require:

   ```text
   identity.corpus_id == campaign.corpus_id
   identity.chunk_set_id == campaign.chunk_set_id
   ```

8. validate `identity.corpus_manifest` and `identity.chunk_manifest` as
   **filename-only** durable references (canonical construction stores
   `Path(...).name`):

   - non-empty string;
   - `Path(value).name == value`;
   - not absolute;
   - no `/` or `\`;
   - no `..`.

   Absolute or nested manifest references are **not** supported historical
   authority. Failure → `gold_state_unavailable` / 409;

9. resolve corpus manifest **only** beneath `settings.paths.manifests` using
   the validated filename; load the exact file; require
   corpus manifest `corpus_id == campaign.corpus_id`;

10. resolve chunk-set manifest **only** beneath
    `settings.paths.chunk_manifests` using the validated filename; load the
    exact file. Where canonical filename convention permits, require the
    manifest filename to agree with the durable identity it represents
    rather than silently loading an alias. Require:

    ```text
    ChunkSetManifest.chunk_set_id == campaign.chunk_set_id
    ChunkSetManifest.corpus_id == campaign.corpus_id
    ```

    No fuzzy / alternate manifest lookup;

11. for each `ChunkSetDocumentEntry.chunk_artifact_id` used to load chunk
    text, **before** path construction require canonical grammar:

    ```text
    ^chunkartifact_[0-9a-f]{64}$
    ```

    No slash / backslash / `..`. Resolve **only** as:

    ```text
    settings.paths.chunks / f"{validated_chunk_artifact_id}.json"
    ```

    Then require loaded `DocumentChunkArtifact`:

    ```text
    artifact.chunk_artifact_id == entry.chunk_artifact_id
    artifact.document_id == entry.document_id
    artifact.parsed_artifact_id == entry.parsed_artifact_id
    ```

    Failure → `gold_state_unavailable` / 409. Do not allow a corrupted
    chunk-set manifest to redirect historical reads outside the configured
    chunk-artifact root;

12. exact `chunk_id` lookup within the loaded immutable chunk artifacts;

13. construct `GoldSourceContext`.

**NO consultation of:**

`current.json`, CURRENT chunk state, current workspace snapshot, current
retrieval configuration (embedding / dense index / lexical / fusion /
reranker / context), Qdrant, lexical indexes, embedder, reranker,
generator.

No model / provider / retrieval calls.

### Historical artifact error normalization

The following durable / path / integrity failures all normalize through the
Gold application facade to:

`gold_state_unavailable` / HTTP **409** / retryable **false**

- invalid durable `corpus_name`;
- invalid durable `snapshot_id`;
- snapshot manifest missing / corrupt;
- snapshot schema / `product_mode_id` mismatch;
- snapshot identity mismatch;
- absolute / nested `corpus_manifest` reference;
- absolute / nested `chunk_manifest` reference;
- corpus manifest mismatch;
- chunk-set manifest mismatch;
- invalid `chunk_artifact_id`;
- chunk-artifact identity / provenance mismatch;
- requested `chunk_id` absent;
- baseline / historical `document_id` / `section_path` cross-check mismatch
  (adapter reasons `historical_chunk_unavailable` /
  `historical_chunk_mismatch`).

Do **not** leak underlying `CORPUS_NOT_READY`, `SNAPSHOT_UNAVAILABLE`, raw
filesystem exceptions, or filesystem paths as route-specific accidental
behavior. The Gold Lab HTTP contract owns the product projection.

Explicitly **forbid**:

- `ProductPublicationRegistry.resolve_snapshot(...)` for this historical path
  when it invokes current-config `validate_grounded_identity`
- `load_current_corpus_chunk_snapshot()`
- CURRENT chunk state / CURRENT workspace snapshot substitution
- fuzzy / nearest chunk matching
- retrieval during task-detail source resolution
- constructing any historical path from unvalidated durable metadata

### GoldSourceContext field authority

| Field | Authority |
|---|---|
| `chunk_id` | historical Chunk |
| `document_id` | historical Chunk |
| `section_path` | historical Chunk |
| `page_start` / `page_end` | historical Chunk |
| `line_start` / `line_end` | historical Chunk |
| `content_type` | historical Chunk |
| `text` | historical Chunk |
| `source_name` | exact historical corpus manifest |
| `document_title` | display-only (see below) |

Do **not** use baseline retrieval-hit objects to fill scientific/source fields.

### Document-title authority (display-only)

| Task kind | `document_title` source |
|---|---|
| Question Check | `source_seed.document_title` if present, else `null` |
| Absolute relevance | `PoolCandidate.document_title` if present, else `null` |

Do **not** cross-fill from unrelated baseline candidates or CURRENT document
inventory. All scientific/source identity still comes from historical
Chunk/manifests.

### Baseline / historical identity cross-check

For Question Check `source_seed`:

- if `source_seed.document_id` is non-null: require
  `source_seed.document_id == historical_chunk.document_id`
- if `source_seed.section_path` is non-empty: require it equals the historical
  chunk `section_path` (chunk value does **not** silently supersede a
  disagreeing seed; mismatch fails closed)

For absolute `PoolCandidate`:

- if `PoolCandidate.document_id` is non-null: require
  `PoolCandidate.document_id == historical_chunk.document_id`
- if `PoolCandidate.section_path` is non-empty: require equality with historical
  chunk `section_path` under the same rule

Mismatch → adapter reason `historical_chunk_mismatch` →
`gold_state_unavailable`. Do not silently normalize identity disagreement.

### Forbidden source fields

`GoldSourceContext` **MUST NOT** contain:

retrieval_hits, retriever, rank, score, model relevance, model confidence,
model agreement, prelabel result/reason, hard-call designation / reason_code,
embedding score, reranker score.

No neighboring chunk expansion in 16F-D. One task = one authoritative source unit.

---

## Blind-authority exclusion table

16F-D **MUST** preserve S16-D31 / D15.

Before independent expert commitment, **no** task endpoint may expose:

| Forbidden channel | Examples |
|---|---|
| Retrieval method / identity | retriever name, method |
| Rank / score | rank, score, embedding/reranker score |
| Model grades / confidence / agreement | model_judgments, confidence, agreement |
| Prelabel | prelabel_summary, prelabel_provenance, prelabel status |
| Hard Call rationale | reason_code, why selected |
| Reward leakage | score/reward for agreeing with a machine |

Hard Call `reason_code` is accepted only as campaign-admin creation provenance
input. Later task views **never** expose it.

---

## Expert mutation contracts

### Common rules

- Required header on expert mutation endpoints **only**: `Idempotency-Key`
- Reuse existing normalization and accepted 16F-B request fingerprints
- Do **not** introduce: `X-Request-Id`, client request fingerprint, client
  supersedes ID, client judgment ID, client task hash
- No HTTP-adapter idempotency implementation — delegate to
  `GoldLabMutationService`
- Success status for mutations: **200** for both first commit and exact replay
  (no 201 distinction for ledger decisions)

### Mutation receipt (`GoldMutationReceipt`)

```json
{
  "campaign_id": "string",
  "record_id": "string",
  "judgment_id": "string",
  "task_id": "string",
  "record_type": "question_check | absolute_relevance | auxiliary_preference",
  "sequence": 1,
  "created_at": "RFC3339 UTC string",
  "replayed": false
}
```

### Question Check HTTP mutation

`POST /v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/question-check`

Required header: `Idempotency-Key`

#### Frozen Pydantic strategy (discriminated union)

Use a `decision`-discriminated union with `extra="forbid"`:

| Variant | Required keys | Forbidden keys |
|---|---|---|
| `accept` | `decision` | all `effective_*` keys must be **absent** (not null) |
| `reject` | `decision` | all `effective_*` keys must be **absent** (not null) |
| `edit` | `decision`, `effective_query`, `effective_category`, `effective_tags` | — |

Optional on all variants: `game_id: string | null = null`,
`presentation_id: string | null = null` (strict `str | null` only; no coercion).

Adapter constructs the **exact** canonical 16F-B payload:

- accept → `{"decision":"accept"}`
- reject → `{"decision":"reject"}`
- edit → `{"decision":"edit","effective_query":...,"effective_category":...,"effective_tags":...}`
  with already-canonical values produced by accepted command canonicalize helpers
  inside `GoldLabMutationService` (adapter does not invent a second canonicalize).

JSON omission vs explicit null:

- accept/reject: keys omitted entirely (explicit `null` is **invalid** transport);
- edit: all three `effective_*` keys present; `effective_category` may be JSON
  `null`; `effective_tags` must be a JSON array.

#### Task resolution

- Resolve `task_id` against sealed-baseline stable task identity.
- Require: task belongs to campaign; `task_kind == question_check`.
- Do **not** check campaign lifecycle before calling `GoldLabMutationService`.
- Do **not** check current task state before calling the service.

Reason: accepted 16F-B requires idempotency resolution **first**, so exact replay
after campaign close / project archive must still succeed.

`GoldLabMutationService` remains owner of: idempotency, lifecycle gate,
correction target, query fingerprint, ledger append.

### Absolute relevance HTTP mutation

`POST /v1/gold-lab/campaigns/{campaign_id}/tasks/{task_id}/relevance`

Required header: `Idempotency-Key`

Body (`extra="forbid"`):

```json
{
  "relevance": 0,
  "game_id": null,
  "presentation_id": null
}
```

- `relevance` is strict JSON integer `0 | 1 | 2`.
- `bool` **MUST NOT** be accepted as integer relevance.
- Resolve `task_id` against sealed baseline; require
  `task_kind == absolute_relevance`.
- Derive `case_id` and `candidate_chunk_id` server-side from task authority.
- Do **not** accept either from body.
- Do **not** pre-check active/lifecycle before accepted mutation service.

### Auxiliary preference HTTP mutation

`POST /v1/gold-lab/campaigns/{campaign_id}/preferences`

Required header: `Idempotency-Key`

Body (`extra="forbid"`):

```json
{
  "case_id": "string",
  "preferred_chunk_id": "string",
  "other_chunk_id": "string",
  "game_id": null,
  "presentation_id": null
}
```

No canonical relevance is created. No contribution points.
Underlying accepted 16F-B auxiliary mutation is sole authority.

### Mutation error ordering (frozen)

HTTP adapter **MUST NOT** mask accepted 16F-B ordering.

For mutation POSTs:

1. validate transport / body / `Idempotency-Key` shape;
2. resolve stable task membership / kind;
3. call `GoldLabMutationService`;
4. let service resolve durable idempotency **BEFORE** lifecycle / current-state gate.

Therefore:

| Situation | Result |
|---|---|
| Exact committed retry after campaign close | **200** replay |
| Exact committed retry after project archive | **200** replay |
| Same key + different request after close/archive | **409** `idempotency_conflict` |
| New request after close/archive | **409** `gold_conflict` |

---

## Contribution transport

`GET /v1/gold-lab/campaigns/{campaign_id}/contribution`

Response **exactly** (`gold-contribution-v1`):

```json
{
  "contract": "gold-contribution-v1",
  "campaign_id": "string",
  "total_score": 0,
  "expert_judgments": 0,
  "questions_reviewed": 0,
  "cases_completed": 0,
  "gold_finalized": 0,
  "hard_calls_resolved": 0,
  "completed_active_absolute_tasks": 0,
  "total_active_absolute_tasks": 0,
  "coverage_fraction": null,
  "total_question_tasks": 0
}
```

No leaderboard fields. No speed metrics. No model-agreement metrics.

Authority: `GoldLabMutationService.contribution` (registration-backed +15 via
accepted 16F-C).

---

## Export / registration transport

### POST `/v1/gold-lab/campaigns/{campaign_id}/export`

- No body.
- No `Idempotency-Key` in 16F-D v1.
- Do **not** require campaign OPEN.
- Delegate directly to accepted
  `GoldLabScientificExportService.export_and_register()`.

### GoldExportView

```json
{
  "campaign_id": "string",
  "dataset_id": "string",
  "dataset_path": "string",
  "projection_sha256": "string",
  "exported_case_ids": ["string"],
  "dataset_reused": false,
  "registration_replayed": false,
  "registered_at": "RFC3339 UTC string"
}
```

HTTP status:

- **201** when `registration_replayed == false`
- **200** when `registration_replayed == true`

`dataset_path` remains the relative canonical Gold Lab path
(`datasets/<dataset_id>`). No absolute filesystem path.

### GET `/v1/gold-lab/campaigns/{campaign_id}/registrations`

Every returned registration **MUST** pass the accepted 16F-C authoritative
validator. Malformed/corrupt registration → **FAIL CLOSED**.

Response:

```json
{
  "campaign_id": "string",
  "registrations": [
    {
      "dataset_id": "string",
      "dataset_path": "string",
      "baseline_sha256": "string",
      "projection_sha256": "string",
      "exported_case_ids": ["string"],
      "registered_at": "RFC3339 UTC string"
    }
  ]
}
```

Ordering: `registered_at` ascending, `dataset_id` ascending.

---

## Error envelope

Reuse existing canonical API envelope:

```json
{
  "error": {
    "code": "<ErrorCode>",
    "message": "string"
  },
  "retryable": false,
  "trace_id": null,
  "details": null
}
```

No raw `GoldLabError.message` may be returned to clients.

---

## New product error codes (freeze)

Add to the future `ErrorCode` catalog:

| ErrorCode | HTTP | retryable | Default message |
|---|---|---|---|
| `gold_project_unknown` | 404 | false | Gold project not found |
| `gold_campaign_unknown` | 404 | false | Gold campaign not found |
| `gold_task_unknown` | 404 | false | Gold task not found |
| `gold_baseline_unknown` | 404 | false | Gold authoring baseline not found |
| `gold_conflict` | 409 | false | Gold Lab state conflicts with the requested operation |
| `gold_busy` | 409 | true | Gold Lab resource is busy |
| `gold_state_unavailable` | 409 | false | Gold Lab durable state cannot be bound safely |

### Existing codes reused

| ErrorCode | HTTP | Notes |
|---|---|---|
| `request_invalid` | 422 | body/header/shape/domain validation |
| `idempotency_conflict` | 409 | accepted idempotency conflict |
| `runtime_not_ready` | 503 | `runtime.require_ready()` |
| `workspace_unknown` | 404 | workspace authority origin |
| `workspace_not_ready` / `workspace_conflict` | 409 | workspace authority origin |
| `internal_error` | 500 | unmapped programming/transport faults |

### SafeErrorDetails extension

Freeze addition of safe identity fields:

`project_id`, `campaign_id`, `task_id`, `dataset_id`, `case_id`

to `SafeErrorDetails` and the safe untrusted identity allowlist where
appropriate.

Do **not** add: filesystem path, raw exception, selection parameters, hard-call
reason, model/provider payload, free-form internal diagnostics.

`details.reason` carries the **safe closed reason code** (the
`GoldLabError.reason` token when mapped), never raw exception prose.

---

## Gold error translator

Freeze one centralized translator:

```text
GoldLabError → AppError
```

No per-route ad hoc mapping.

Any reachable reason not listed below → `internal_error` with safe reason
`gold_lab_unmapped_error`.

### Provenance principles (Rework 1 + Rework 2 + Rework 3)

Classify each reachable reason by **throw-site provenance through the supported
16F-D route**, not by reason-name similarity alone:

| Provenance class | Product |
|---|---|
| TRANSPORT / HUMAN COMMAND | `request_invalid` / 422 |
| TRUE SAME-KEY DIFFERENT-REQUEST | `idempotency_conflict` / 409 |
| VALID LIFECYCLE / STALENESS / SCIENTIFIC INELIGIBILITY | `gold_conflict` / 409 |
| LEASE CONTENTION | `gold_busy` / 409 |
| PERSISTED / SEALED / LEDGER / REGISTRATION / GENERATED IDENTITY FAILURE | `gold_state_unavailable` / 409 |
| IMPOSSIBLE SERVER PROGRAMMING ESCAPE | `internal_error` / 500 |
| UNKNOWN FUTURE REASON | `internal_error` + `gold_lab_unmapped_error` |

Preserved Rework 1 rules:

1. **Baseline lookup vs sealed corruption**
   - Shared eligibility class A (canonical run does not exist) →
     `gold_baseline_unknown` / **404**.
   - Sealed campaign `baseline_missing` → `gold_state_unavailable` / **409**
     (never 404).

2. **Idempotency**
   - Only `idempotency_conflict` → `idempotency_conflict` / 409.
   - Header shape → `request_invalid` / 422.
   - Catalog/ledger integrity → `gold_state_unavailable` / 409.

3. **Server-owned idempotency programming**
   - `idempotency_command_kind_invalid` → `internal_error` / 500.
   - `invalid_idempotency_path` → `internal_error` / 500.

4. **Transport vs durable identity grammar**
   - Malformed path/body IDs → `request_invalid` / 422.
   - Post-transport durable/generated grammar faults →
     `gold_state_unavailable`.

5. **`registration_missing`**: **NOT REACHABLE IN 16F-D v1**.

6. **`gold_finalize_failed`** → `gold_state_unavailable` / 409 (conservative;
   do not inspect exception text).

Preserved Rework 2 additions:

7. **Question Check edit semantics**
   - Command-input `question_check_edit_not_semantic` → `request_invalid` / 422.
   - Durable ledger/replay `effective_state_qc_edit_not_semantic` →
     `gold_state_unavailable` / 409.

8. **Low-level ledger membership** after mutation-service admission →
   `gold_state_unavailable` (not client JSON blame).

9. **Server-derived campaign authorities**
   (`hard_call_designation_id`, selection-policy `project_type`) →
   durable mismatches → `gold_state_unavailable`.

Rework 3 additions:

10. **Baseline eligibility A/B/C/D**
    - A absent → `gold_baseline_unknown` / 404.
    - B corrupt / path-identity → `gold_state_unavailable` / 409.
    - C stale CURRENT binding → `gold_conflict` / 409.
    - D structurally valid but pristine-ineligible
      (`baseline_human_state_present`, `baseline_identity_missing`) →
      **preflight** `gold_conflict` / 409.
    - Same D reasons escaping **after** successful preflight →
      `gold_state_unavailable` / 409 (application vs service contradiction).
    - Never `request_invalid` for stale / non-pristine server-owned baselines.

11. **Historical durable path confinement**
    - Invalid durable `corpus_name` / `snapshot_id` / manifest filename /
      `chunk_artifact_id`, root escapes, schema/product-mode mismatches →
      `gold_state_unavailable` / 409.
    - Never blame expert JSON for corrupt server-owned historical metadata.

### Adapter-introduced stable reasons

| Adapter reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `gold_task_unknown` | `gold_task_unknown` | 404 | false | yes |
| `gold_task_kind_mismatch` | `request_invalid` | 422 | false | yes |
| `gold_baseline_unknown` | `gold_baseline_unknown` | 404 | false | yes |
| `idempotency_key_required` | `request_invalid` | 422 | false | yes |
| `idempotency_key_invalid` | `request_invalid` | 422 | false | yes |
| `historical_chunk_unavailable` | `gold_state_unavailable` | 409 | false | yes |
| `historical_chunk_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `transport_project_id_invalid` | `request_invalid` | 422 | false | yes |
| `transport_campaign_id_invalid` | `request_invalid` | 422 | false | yes |
| `transport_task_id_invalid` | `request_invalid` | 422 | false | yes |

Unknown task IDs are adapter-resolved as `gold_task_unknown` when the sealed
baseline task set does not contain the path `task_id`.

### Exhaustive `GoldLabError.reason` → product mapping

Columns: reason → ErrorCode → HTTP → retryable → `details.reason` (same token
unless noted) → Reachable in 16F-D v1.

#### NOT FOUND (404 product codes)

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `project_not_found` | `gold_project_unknown` | 404 | false | yes |
| `campaign_not_found` | `gold_campaign_unknown` | 404 | false | yes |
| `registration_missing` | — | — | — | **NOT REACHABLE IN 16F-D v1** |

Caller `case_id` unknown (`case_not_found`) is transport/domain validation →
`request_invalid` / 422 (listed below), not a Gold “unknown campaign/project”
404.

Sealed-campaign `baseline_missing` is durable corruption →
`gold_state_unavailable` / 409 (listed under durable state). Never 404.

#### BUSY → `gold_busy`

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `gold_lab_lease_held` | `gold_busy` | 409 | true | yes |

#### TRUE CALLER IDEMPOTENCY CONFLICT → `idempotency_conflict`

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `idempotency_conflict` | `idempotency_conflict` | 409 | false | yes |

#### REQUEST INVALID → `request_invalid`

Caller/transport scientific request shape only (human command / HTTP body).

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `absolute_relevance_invalid` | `request_invalid` | 422 | false | yes |
| `question_check_payload_invalid` | `request_invalid` | 422 | false | yes |
| `question_check_edit_not_semantic` | `request_invalid` | 422 | false | yes |
| `auxiliary_preference_invalid` | `request_invalid` | 422 | false | yes |
| `auxiliary_pair_not_distinct` | `request_invalid` | 422 | false | yes |
| `candidate_not_in_case` | `request_invalid` | 422 | false | yes |
| `case_not_reviewable` | `request_invalid` | 422 | false | yes |
| `hard_call_reason_empty` | `request_invalid` | 422 | false | yes |
| `hard_call_target_invalid` | `request_invalid` | 422 | false | yes |
| `hard_call_duplicate_target` | `request_invalid` | 422 | false | yes |
| `selection_policy_parameters_invalid` | `request_invalid` | 422 | false | yes |
| `provenance_type_invalid` | `request_invalid` | 422 | false | yes |
| `case_not_found` | `request_invalid` | 422 | false | yes |

Note: malformed transport path/body `project_id` / `campaign_id` / `task_id`
are handled by adapter reasons `transport_*_invalid` before service call.

#### Explicitly NOT client-invalid (audited)

| reason | Classification | Notes |
|---|---|---|
| `effective_state_qc_edit_not_semantic` | durable → `gold_state_unavailable` | ledger/replay invariant |
| `ledger_case_not_found` | durable → `gold_state_unavailable` | low-level sealed-baseline/ledger |
| `ledger_case_not_reviewable` | durable → `gold_state_unavailable` | low-level sealed-baseline/ledger |
| `ledger_candidate_not_in_case` | durable → `gold_state_unavailable` | low-level sealed-baseline/ledger |
| `candidate_chunk_required` | durable → `gold_state_unavailable` | low-level sealed-baseline/ledger |
| `auxiliary_pair_required` | durable → `gold_state_unavailable` | server pair vs payload reconcile |
| `auxiliary_pair_mismatch` | durable → `gold_state_unavailable` | server pair vs payload reconcile |
| `hard_call_designation_id_mismatch` | durable → `gold_state_unavailable` | server-derived designation |
| `selection_policy_project_type_mismatch` | durable → `gold_state_unavailable` | server-derived project_type |
| `question_check_case_not_reviewable` | **NOT REACHABLE IN NORMAL 16F-D v1**; escape → `gold_state_unavailable` | QC tasks only for reviewable cases; mutation service also admits |
| `baseline_human_state_present` | preflight class **D** → `gold_conflict`; post-successful-preflight escape → `gold_state_unavailable` | not request_invalid / not 404 |
| `baseline_identity_missing` | preflight class **D** → `gold_conflict`; post-successful-preflight escape → `gold_state_unavailable` | not request_invalid / not 404 |
| `chunk_set_mismatch` | preflight class C → `gold_conflict`; escape → `gold_conflict` | not request_invalid |
| `corpus_id_mismatch` | preflight class C → `gold_conflict`; escape → `gold_conflict` | not request_invalid |
| `corpus_name_mismatch` | preflight class C → `gold_conflict`; escape → `gold_conflict` | not request_invalid |

#### LIFECYCLE / VALID CONFLICT → `gold_conflict`

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `project_archived` | `gold_conflict` | 409 | false | yes |
| `project_already_archived` | `gold_conflict` | 409 | false | yes |
| `project_unarchive_forbidden` | `gold_conflict` | 409 | false | yes |
| `project_status_invalid` | `gold_conflict` | 409 | false | yes |
| `project_already_exists` | `gold_conflict` | 409 | false | yes |
| `campaign_closed` | `gold_conflict` | 409 | false | yes |
| `campaign_already_closed` | `gold_conflict` | 409 | false | yes |
| `campaign_status_invalid` | `gold_conflict` | 409 | false | yes |
| `campaign_already_exists` | `gold_conflict` | 409 | false | yes |
| `absolute_task_inactive` | `gold_conflict` | 409 | false | yes |
| `workspace_stale` | `gold_conflict` | 409 | false | yes |
| `workspace_revision_changed` | `gold_conflict` | 409 | false | yes |
| `workspace_snapshot_changed` | `gold_conflict` | 409 | false | yes |
| `workspace_not_active` | `gold_conflict` | 409 | false | yes |
| `project_type_changed` | `gold_conflict` | 409 | false | yes |
| `project_workspace_changed` | `gold_conflict` | 409 | false | yes |
| `registration_conflict` | `gold_conflict` | 409 | false | yes |
| `dataset_semantic_conflict` | `gold_conflict` | 409 | false | yes |
| `chunk_set_mismatch` | `gold_conflict` | 409 | false | yes (eligibility C / escape) |
| `corpus_id_mismatch` | `gold_conflict` | 409 | false | yes (eligibility C / escape) |
| `corpus_name_mismatch` | `gold_conflict` | 409 | false | yes (eligibility C / escape) |
| `baseline_human_state_present` | `gold_conflict` | 409 | false | yes (**preflight class D**) |
| `baseline_identity_missing` | `gold_conflict` | 409 | false | yes (**preflight class D**) |

#### DURABLE STATE / CORRUPTION → `gold_state_unavailable`

Includes sealed baseline corruption, durable identity violations, idempotency
catalog/ledger integrity, finalizer collapse, server-owned identity grammar
faults after transport validation, low-level ledger membership after mutation
admission, durable QC replay invariants, and server-derived campaign-authority
mismatches.

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `effective_state_qc_edit_not_semantic` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_case_not_found` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_case_not_reviewable` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_candidate_not_in_case` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_chunk_required` | `gold_state_unavailable` | 409 | false | yes |
| `auxiliary_pair_required` | `gold_state_unavailable` | 409 | false | yes |
| `auxiliary_pair_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `hard_call_designation_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `selection_policy_project_type_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `question_check_case_not_reviewable` | `gold_state_unavailable` | 409 | false | **NOT REACHABLE IN NORMAL 16F-D v1**; escape only |
| `baseline_human_state_present` | `gold_state_unavailable` | 409 | false | yes (**post-successful-preflight escape only**) |
| `baseline_identity_missing` | `gold_state_unavailable` | 409 | false | yes (**post-successful-preflight escape only**) |
| `baseline_missing` | `gold_state_unavailable` | 409 | false | yes |
| `baseline_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `baseline_hash_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `baseline_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `baseline_unreadable` | `gold_state_unavailable` | 409 | false | yes |
| `baseline_authoring_run_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `campaign_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `campaign_identity_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `campaign_staging_missing` | `gold_state_unavailable` | 409 | false | yes |
| `project_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `project_identity_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `export_project_lock_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `hard_calls_missing` | `gold_state_unavailable` | 409 | false | yes |
| `hard_calls_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `hard_calls_campaign_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `hard_calls_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `hard_calls_contract_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `hard_call_target_unknown` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_record_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_record_type_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_semantic_contract_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_filename_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_filename_record_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_filename_sequence_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_sequence_gap` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_duplicate_sequence` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_record_exists` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_append_failed` | `gold_state_unavailable` | 409 | false | yes |
| `ledger_provenance_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `lease_not_held` | `gold_state_unavailable` | 409 | false | yes |
| `lease_campaign_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `task_identity_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `contribution_unknown_finalized_case` | `gold_state_unavailable` | 409 | false | yes |
| `registration_unknown_exported_case` | `gold_state_unavailable` | 409 | false | yes |
| `gold_finalize_failed` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_catalog_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_entry_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_campaign_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_key_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_reservation_exists` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_entry_missing` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_orphan_ledger_key` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_duplicate_ledger_key` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_duplicate_record_id` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_reserved_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_reserved_key_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_reserved_fingerprint_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_command_kind_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_status_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_committed_missing_ledger` | `gold_state_unavailable` | 409 | false | yes |
| `idempotency_finalize_failed` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_project_id` | `gold_state_unavailable` | 409 | false | yes (post-transport durable) |
| `invalid_campaign_id` | `gold_state_unavailable` | 409 | false | yes (post-transport durable) |
| `invalid_task_id` | `gold_state_unavailable` | 409 | false | yes (post-transport durable) |
| `invalid_record_id` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_judgment_id` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_dataset_id` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_query_fingerprint` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_request_fingerprint` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_selection_policy_fingerprint` | `gold_state_unavailable` | 409 | false | yes |
| `invalid_hard_call_designation_id` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_unknown_record_type` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_duplicate_judgment_id` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_supersession_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_supersession_branch` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_supersession_non_current` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_supersession_unknown` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_cross_basis_supersession` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_cross_task_supersession` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_task_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_qc_non_reviewable` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_qc_payload_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_qc_payload_noncanonical` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_qc_fingerprint_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_inactive_question` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_missing_candidate` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_non_reviewable` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_null_fingerprint` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_payload_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `effective_state_absolute_query_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `projection_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `projection_export_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `projection_sha256_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_staging_missing` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_dataset_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_dataset_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_exported_ids_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `canonical_dataset_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `canonical_dataset_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `canonical_dataset_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `canonical_dataset_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `dataset_publish_failed` | `gold_state_unavailable` | 409 | false | yes |
| `registered_dataset_missing` | `gold_state_unavailable` | 409 | false | yes |
| `registration_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `registration_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `registration_path_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_campaign_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_project_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_project_type_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_provenance_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_path_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_missing` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_corrupt` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_schema_invalid` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_chunk_set_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_corpus_id_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_dataset_corpus_name_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `registration_exported_ids_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `candidate_chunk_unresolved` | `gold_state_unavailable` | 409 | false | yes |
| `source_seed_chunk_unresolved` | `gold_state_unavailable` | 409 | false | yes |
| `source_seed_document_mismatch` | `gold_state_unavailable` | 409 | false | yes |
| `chunk_set_unavailable` | `gold_state_unavailable` | 409 | false | yes |
| `workspace_snapshot_missing` | `gold_state_unavailable` | 409 | false | yes |

#### SERVER PROGRAMMING ESCAPES → `internal_error`

| reason | ErrorCode | HTTP | retryable | Reachable |
|---|---|---|---|---|
| `idempotency_command_kind_invalid` | `internal_error` | 500 | false | yes (if escapes) |
| `invalid_idempotency_path` | `internal_error` | 500 | false | yes (if escapes) |

Frozen choice for server-derived campaign authorities
(`hard_call_designation_id_mismatch`, `selection_policy_project_type_mismatch`):
**`gold_state_unavailable` / 409**, not `internal_error`. Rationale: the same
reasons can arise while validating persisted / sealed Gold Lab state against
server-derived designation and project-type authorities; fail closed as durable
state unavailable rather than blaming expert JSON or assuming a pure
programming escape.

`details.reason` for programming escapes remains the original reason token
(closed code), not client-facing prose.

#### Default

Any other / future / unlisted reachable reason:

| reason | ErrorCode | HTTP | retryable | details.reason |
|---|---|---|---|---|
| *(unmapped)* | `internal_error` | 500 | false | `gold_lab_unmapped_error` |

---

## HTTP status matrix (summary)

| Status | Meaning in 16F-D |
|---|---|
| 200 | Successful read; archive/close; mutation commit/replay; export replay |
| 201 | Project/campaign create; first export registration |
| 404 | Unknown project / campaign / task; HTTP baseline lookup unknown |
| 409 | Conflict / busy / durable state unavailable / true idempotency conflict |
| 422 | Request validation / invalid scientific request shape / transport IDs |
| 500 | Unmapped internal faults; escaped server programming invariants |
| 503 | Runtime not ready |

Note: sealed-campaign `baseline_missing` is **409** `gold_state_unavailable`,
never 404.

No 202.

---

## Security / path boundary

HTTP bodies **MUST NEVER** accept:

filesystem paths, baseline file path, dataset directory, registration path,
corpus manifest filename, ledger filename, projection filename.

Only durable IDs.

Baseline `authoring_run_id` used for server lookup **MUST** be validated as a
safe identity token before path construction.

---

## Design acceptance matrix (endpoint → authority)

| Endpoint | Authority |
|---|---|
| project create / get / list / archive | `GoldLabStore` |
| baselines | store + workspace + canonical authoring-run scan + 16F-A pristine admission |
| campaign create | `GoldCampaignService` |
| campaign get / list / close | `GoldLabStore` (+ project for `project_type`) |
| task list / detail | `GoldLabMutationService` effective state / `BlindTaskView` + exact historical chunk read only |
| question / relevance / preference mutation | `GoldLabMutationService` ONLY |
| contribution | `GoldLabMutationService.contribution` |
| export | `GoldLabScientificExportService` |
| registration list | accepted 16F-C registration validator |

### Proof commitments for later implementation review

- no API route writes ledger directly;
- no API route controls supersedes / query fingerprint;
- no API route accepts filesystem paths;
- no pre-commit model / retrieval leakage;
- no 16G workload / game behavior;
- no automatic retrieval / config promotion;
- no scientific semantic changes to GoldDataset-v1 / HumanReview / ledger /
  registration / contribution weights.

---

## No UI / 16G statement

16F-D creates only the backend data plane required by a separately authorized
16G.

Explicitly:

- No React
- No Gold Lab page
- No game layout
- No workload chooser
- No training compiler
- No leaderboard
- No learner mode

---

## No scientific semantic change

16F-D **MUST NOT** modify:

`GoldDataset-v1`, `GoldAuthoringRun`, `HumanReview`, relevance `0/1/2`, task IDs,
query fingerprints, selection-policy fingerprints, ledger semantics, registration
semantics, contribution weights.

The API is projection / transport only.

---

## Expected future implementation footprint

DESIGN ONLY predicts — does **not** create — likely files:

```text
src/offline_rag/app/gold_lab/application.py
src/offline_rag/app/gold_lab/views.py
src/offline_rag/api/gold_lab.py

narrow:
src/offline_rag/api/app.py
src/offline_rag/app/runtime.py
src/offline_rag/app/errors.py

tests/unit/app/test_slice16f_d_gold_lab_api.py
```

No UI files.

---

## Required implementation tests (future 16F-D authorization)

When separately authorized, implementation **MUST** cover at least:

1. Route surface exactly matches this freeze (no extras).
2. Project/campaign DTO field sets exact; no path leakage.
3. Baseline discovery returns only pristine / snapshot-bound runs; rejects path input;
   filename stem == `authoring_run_id` identity rule.
4. Campaign create derives ids/fingerprints server-side; delegates to
   `GoldCampaignService`.
5. Task list order matches `project_tasks()`; filters compose without reshuffle.
6. Task detail blind exclusions (model/rank/score/prelabel/hard-call reason).
7. Inactive absolute tasks expose `presentation=null` (no candidate text).
8. Source context binds to campaign historical snapshot only; CURRENT mismatch fails closed.
9. Question Check accept/reject omit `effective_*`; edit requires all three keys.
10. Relevance rejects bool; derives case/candidate from task authority.
11. Mutation missing/invalid `Idempotency-Key` → 422.
12. Exact mutation replay after close/archive → 200; divergent key → 409
    idempotency_conflict; new key after close → 409 gold_conflict.
13. Contribution JSON exact `gold-contribution-v1` fields.
14. Export delegates to scientific export service; 201/200 by
    `registration_replayed`.
15. Registration list uses 16F-C validator; corrupt registration fails closed.
16. Exhaustive translator coverage for mapped reasons; unmapped →
    `gold_lab_unmapped_error`.
17. SafeErrorDetails may carry project/campaign/task/dataset/case ids; never paths.
18. No ManagedOperation / 202 / queue side effects.
19. Regression: all accepted 16F-A / 16F-B / 16F-C tests remain green.
20. No retrieval/config/`base.yaml` mutation; no UI modules introduced.

### Rework 1 additional tests

21. Requested baseline ID `A` whose file contains run ID `B` → fail closed;
    `B` is not silently imported.
22. Sealed campaign baseline file missing → `gold_state_unavailable`, **not**
    `gold_baseline_unknown`.
23. Corrupted idempotency catalog/ledger relation → `gold_state_unavailable`,
    **not** `idempotency_conflict`.
24. True same-key / different-request → `idempotency_conflict`.
25. `task_identity_mismatch` in durable ledger → `gold_state_unavailable`.
26. Registration exported case absent from sealed baseline →
    `gold_state_unavailable`.
27. Question Check source resolves `source_seed` exact historical chunk.
28. Absolute detail resolves exact candidate historical chunk.
29. Workspace CURRENT advances after campaign creation → task detail still
    returns campaign historical source.
30. Historical snapshot / chunk-set mismatch → `gold_state_unavailable`.
31. Baseline candidate/source `document_id` mismatch →
    `gold_state_unavailable`.
32. No retrieval/model call occurs during task-detail source resolution.

### Rework 2 additional tests

33. Semantic no-op Question Check edit → `request_invalid` / **422**
    (`question_check_edit_not_semantic`).
34. Tampered durable edit that is no longer semantic →
    `gold_state_unavailable` / **409**
    (`effective_state_qc_edit_not_semantic`).
35. Persisted ledger case absent from sealed baseline →
    `gold_state_unavailable` / **409**.
36. Persisted ledger candidate absent from sealed baseline →
    `gold_state_unavailable` / **409**.
37. Auxiliary persisted-pair / server-argument mismatch →
    `gold_state_unavailable`.
38. Stale but otherwise valid server-owned baseline selected for campaign →
    `gold_conflict`, **not** `request_invalid`.
39. Immutable snapshot S remains readable for Gold task detail after current
    embedding / reranker / config changes.
40. Historical task detail does not require Qdrant / lexical index availability.
41. Immutable snapshot-manifest ID mismatch → `gold_state_unavailable`.
42. Immutable chunk-manifest corpus / chunk-set mismatch →
    `gold_state_unavailable`.
43. Question source `document_title` comes only from `source_seed` display
    metadata.
44. Absolute `document_title` comes only from `PoolCandidate` display metadata.

### Rework 3 additional tests

45. Corrupted campaign `corpus_name` containing path elements →
    `gold_state_unavailable`; no out-of-root file access.
46. Malformed durable `snapshot_id` containing path elements →
    `gold_state_unavailable` **before** path construction.
47. Snapshot `corpus_manifest` absolute / nested reference →
    `gold_state_unavailable`.
48. Snapshot `chunk_manifest` absolute / nested reference →
    `gold_state_unavailable`.
49. Corrupted `chunk_artifact_id` path / reference →
    `gold_state_unavailable`; no out-of-root read.
50. Loaded chunk artifact ID / document / parsed identity disagrees with
    manifest entry → `gold_state_unavailable`.
51. Structurally valid baseline containing existing human review state selected
    for campaign → `gold_conflict` / **409** (class D).
52. Structurally valid baseline missing required corpus / chunk scientific
    identity → `gold_conflict` / **409** (class D).
53. Same baseline passes application preflight but authoritative service later
    detects pristine / identity contradiction → `gold_state_unavailable`.
54. Discovery does not surface class-B / C / D baseline artifacts.
55. Historical-read path confinement does not require Qdrant / retrieval /
    current config and preserves Rework-2 independence behavior.

### Regression requirements

- Accepted 16F-A foundation tests
- Accepted 16F-B effective-state tests
- Accepted 16F-C scientific-export tests (including Rework 1)
- Existing Slice-9 finalize / evaluation suites if finalize boundaries are touched
  (they must not be semantically changed)

---

## Governance status

| Gate | Status |
|---|---|
| 16F-D0 design materialization | AUTHORIZED |
| 16F-D0 Design Rework 1 | AUTHORIZED / PRESERVED |
| 16F-D0 Design Rework 2 | AUTHORIZED / PRESERVED |
| 16F-D0 Design Rework 3 | AUTHORIZED (this revision) |
| Independent design review | PENDING |
| Human design acceptance | PENDING (do not claim) |
| 16F-D production implementation | NOT AUTHORIZED |
| 16G–16H | NOT AUTHORIZED |
| 9G | DEFERRED / NOT AUTHORIZED |
| Slice 17 / 18 / M7 closeout | NOT AUTHORIZED |

---

## Design-only change set

This branch changes exactly:

```text
docs/slice16f_d_application_api_design.md
```

No production source, tests, UI, or config files.
