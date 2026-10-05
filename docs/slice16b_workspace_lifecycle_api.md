# Slice 16B — Workspace/source lifecycle API

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING
16B: IMPLEMENTED CANDIDATE / NOT ACCEPTED
16C+: NOT AUTHORIZED / NOT STARTED
```

## Authority binding

| Item | Value |
| --- | --- |
| Authorized baseline / sealed 16A closeout | `155983fec59a3ae6434286276bd34dcfdaaf8968` |
| Accepted 16A implementation | `e73959be508541a1c50d4919606aaf3157a5fa8a` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Prior 16B candidate (rework base) | `852cbdbaa60f2b8b0b295e1803016c772e3cf29b` |
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B only** |

## Independent review rework (F1–F6)

Disposition was REWORK REQUIRED. This candidate hardens durability/idempotency only;
workspace query binding and full-replace projection are preserved.

### F1 — corpus lease spans cross-registry commit

Non-empty path holds `WorkspaceMutationLease` → `CorpusMutationLease` across:

`run_product_replace_ingest` (optional already-held lease) → `publication_observed`
→ workspace commit → lineage/`COMMITTED` → managed-op `SUCCEEDED` → journal drop
→ release corpus → release workspace.

EMPTY final-source path holds the same lease nesting across publication retirement,
EMPTY workspace write, lineage closeout, op success, and journal drop.

`run_product_replace_ingest(..., corpus_lease=...)` reuses an already-held lease
without nested flock acquire; Slice-15 `/v1/ingest` unchanged when omitted.

### F2 — durable synchronous mutation idempotency

`PATCH/DELETE /v1/workspaces/{id}` and `PATCH .../sources/{source_id}` reserve a
managed operation with canonical `{kind, expected_revision, payload}` identity.
Exact retries return the durable receipt (including after later workspace advances).
Conflicting same-key requests return `idempotency_conflict` (not a second revision).

### F3 — scientific idempotency before capacity / worker

HTTP launch sequence:

1. durable spool + fingerprint
2. blocking `WorkspaceMutationLease` + `ManagedOperationStore.reserve`
3. matching existing → 202, no capacity, no worker
4. conflict → 409, no capacity, no worker
5. newly reserved → admit ingest capacity then launch exactly one worker
6. admission failure → terminalize phantom reservation `FAILED` (no queued ghost)

Corrupt idempotency indexes fail closed.

### F4 — durable upload spool before 202

Multipart `files` stream into `/data/staging/ws_upload_*` with per-file and
aggregate limits and SHA-256 digests computed during write. Workers receive
durable `SourceUpload(spool_path=..., content_sha256=...)` references, not
request-memory-only bytes. Startup quarantines orphan spools; never auto-resumes.

### F5 — journal outlives lineage + operation terminalization

Non-empty closeout: workspace committed → lineage/`COMMITTED` retained →
op `SUCCEEDED`+result durable → drop journal.

EMPTY closeout: retirement → EMPTY write → lineage closed → op `SUCCEEDED` →
drop journal. Startup recovery to B completes `SUCCEEDED` idempotently before
journal removal; recovery to A may `INTERRUPTED`/`FAILED` with recovery note.

### F6 — supersession / batch acceptance campaign

HTTP campaign covers `manual_b_v05`/`OLD_MARKER` → replace `v06`/`NEW_MARKER`
with snapshot N→N+1 agreement, version bump, vault/current evidence absence of
OLD, and adversarial query unable to resurrect v05. Batch POST of two files then
remove one republishes remaining desired set from vault without re-upload.

### Query binding (preserved)

`workspace.current_snapshot_id` → internal `resolve_snapshot` → torn-read check
→ shared `run_bound_snapshot_query`. No client `snapshot_id` DTO field.
Does not re-resolve `current.json` inside the bound path.

## HTTP contract

| Method | Path |
| --- | --- |
| GET/POST | `/v1/workspaces` |
| GET/PATCH/DELETE | `/v1/workspaces/{workspace_id}` |
| GET/POST | `/v1/workspaces/{workspace_id}/sources` |
| GET/PUT/PATCH/DELETE | `/v1/workspaces/{workspace_id}/sources/{source_id}` |
| GET | `/v1/workspaces/{workspace_id}/sources/{source_id}/content` |
| POST | `/v1/workspaces/{workspace_id}/query` |
| GET | `/v1/operations/{operation_id}` |

Slice-15 routes remain registered and unchanged.

## Tests run

```text
uv run ruff check <touched 16B Python modules + rework tests>
→ All checks passed

uv run pytest \
  tests/unit/app/test_slice16b_workspace_api.py \
  tests/unit/app/test_slice16b_rework_hardening.py \
  tests/unit/app/test_slice16b_publication_journal.py \
  tests/unit/app/test_slice16b_query_binding.py \
  tests/unit/app/test_slice16a_workspace_foundation.py \
  tests/unit/app/test_slice15a_foundation.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py \
  tests/unit/app/test_slice15d_product_ingest.py -q
→ 146 passed

git diff --check
→ clean
```

Full-repo pytest was not claimed as green; unrelated pre-existing debt is outside
this rework.

## Residual risks / deferred

- HTTP workspace query under FakeEmbedder typically abstains; supersession evidence
  for answer text relies on vault/chunk presence plus snapshot binding assertions
  rather than dense semantic retrieval of markers.
- Crash-point matrix is covered for representative F4/F5 points; not every journal
  phase is re-driven through the HTTP worker in this pass (unit journal recovery
  remains authoritative for A/B).

## Explicit non-scope

16C–16H, UI, Training Mode, Gold Lab, Slice 17/18, 9G, M7 closeout **NOT AUTHORIZED**.
This document does **not** accept 16B.
