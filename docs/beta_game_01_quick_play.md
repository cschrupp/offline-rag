# BETA-GAME-01 — Quick Play implementation memory

**State:** implementation authorized; candidate pending independent review.

**Branch:** `implementation/beta-game-01-quick-play`

**Base:** `6ff215702056b5708547cdc3a275aad08b0d75dc`

## Product boundary

Quick Play is a workspace-first orchestration layer over existing Gold Lab
projects, baseline runs, campaigns, tasks, managed operations, and append-only
judgments. It is an expert annotation workflow. Its improvement-oriented
selection policy is versioned and must not be described as a representative
benchmark. Only production-approved Question Check and Rapid Fire judgments are
offered. Gold Lab administration remains available under Advanced Gold Lab.

## Identity and recovery

The deterministic project identity includes workspace ID, current published
snapshot ID, corpus ID, chunk-set ID, baseline-generation version, proposal
configuration, and the fingerprint of the versioned improvement selection
policy. A publication change therefore creates a new Quick Play identity; old
campaigns and judgments stay bound to their original snapshot.

The additive `GET /v1/gold-lab/quick-play/workspaces/{workspace_id}` route is
read-only. `POST .../prepare` accepts `start` or explicit `replenish` plus the
existing required `Idempotency-Key` header. Project and campaign IDs are
deterministic from their scientific inputs. Baseline generation uses the
existing durable managed-operation idempotency and workspace bootstrap slot.
After an ambiguous response, the service reads persisted baselines, campaigns,
and operation state before starting another generation. A fresh key is used
only for a user-requested retry after a terminal failure.

## State behavior

- `needs_generation`: no matching Quick Play project/deck exists.
- `generating`: an existing baseline operation is pending; the UI resumes the
  durable operation by ID after refresh.
- `generation_failed`: terminal failure is visible and retry is explicit.
- `baseline_available`: a valid unused baseline can be reused.
- `campaign_ready`: the baseline is ready and a deterministic campaign can be
  reconciled.
- `playable`: only active pending Question Check and/or Rapid Fire tasks count.
  Question Check is next while its tasks remain; Rapid Fire follows the frozen
  activation rules.
- `complete`: no active pending approved-game tasks remain; replenishment is
  explicit and creates additional work without deleting prior judgments.
- `blocked` / `not_ready`: no game is presented as playable.

No Gold dataset schema, selection semantics, judgment scale, publication
authority, retrieval behavior, or ledger contract is changed by this slice.
