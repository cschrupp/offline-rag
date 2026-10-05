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
| Branch | `implementation/16b-workspace-lifecycle-api` |
| Phase | **16B only** |

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

## ETag / If-Match

- Strong quoted decimal revision: `ETag: "7"`
- Existing-workspace mutations require `If-Match`
- Rejects weak / list / wildcard / missing / malformed (`request_invalid`)
- Stale valid revision → `workspace_conflict`

## Idempotency

- `Idempotency-Key` required on mutations
- Canonical identity: kind + expected_revision + payload (file digests for uploads)
- Workspace create uses durable create catalog (same key/title/description → same workspace)

## Managed operations

- Scientific source mutations return **202** + `Location: /v1/operations/{id}`
- Admitted via existing ingest capacity; worker thread owns capacity until terminal
- Progress stages: `preparing` → `processing` → `building_indexes` → `publishing` → `finalizing` → `ready`
- Disconnect after admission does not cancel capacity ownership
- No durable queue; no silent queueing

## Source history

- `SourceHistoryStore` under `workspaces/{id}/history/sources/`
- Superseded/removed versions persist with `active_through_*`
- Active list remains current-only; EMPTY keeps `sources=[]`

## Non-empty publication journal

`NonEmptyPublicationCoordinator` phases:

```text
intent_recorded → publication_observed → workspace_committed
→ lineage_committed → committed
```

Recovery converges to:

- **A** rollback: prior workspace + prior publication (or EMPTY + retired)
- **B** forward: new workspace + new publication

Never delete immutable snapshot manifests. Never auto-resume ingest.
Lock order: workspace lease → corpus lease.

## EMPTY integration

Reuses accepted `EmptyTransitionCoordinator` for final-source removal (no empty ingest).

## Startup recovery

`ApplicationRuntime.start()` after abandoned-candidate recovery and before READY:

1. recover non-empty publication journals
2. recover EMPTY journals
3. mark nonterminal managed operations `interrupted`

Failure → `NOT_READY` / `startup_failed`.

## Workspace query snapshot binding

- Server binds `workspace.current_snapshot_id` via `resolve_snapshot`
- Does **not** re-resolve product `current.json` for workspace queries
- Product `POST /v1/query` still resolves current as before
- No client snapshot/mode/corpus/history fields

## Source content

- Vault bytes with hash verification
- `Content-Disposition: inline`; `nosniff`; `Cache-Control: private, no-store`
- ETag from content hash

## Errors added/reused

`source_unknown` (404) plus existing workspace/operation/idempotency codes.

## Tests run

```text
uv run ruff check <touched 16B Python modules>
→ All checks passed

uv run pytest \
  tests/unit/app/test_slice16b_workspace_api.py \
  tests/unit/app/test_slice16b_publication_journal.py \
  tests/unit/app/test_slice16b_query_binding.py \
  tests/unit/app/test_slice16a_workspace_foundation.py \
  tests/unit/app/test_slice15a_foundation.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py -q
→ 100 passed

git diff --check
→ clean
```

## Residual risks / deferred

- Full supersession OLD_MARKER/NEW_MARKER end-to-end HTTP campaign still thin vs authorization matrix (unit binding + journal recovery covered; expand before acceptance)
- Batch multi-file add path implemented at lifecycle; HTTP multipart multi-file exercised lightly
- Crash-point matrix for every journal phase covered in unit journal tests; expand HTTP/integration coverage if review requires
- Active workspace HTTP query path requires scientific reranker/generator fixtures (covered at app-layer binding tests)

## Explicit non-scope

16C–16H, UI, Training Mode, Gold Lab, Slice 17/18, 9G, M7 closeout **NOT AUTHORIZED**.
This document does **not** accept 16B.
