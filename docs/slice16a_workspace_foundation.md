# Slice 16A — Workspace contracts & persistence foundation

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING
16A: IMPLEMENTED CANDIDATE / NOT ACCEPTED
IMPLEMENTATION: CANDIDATE UNDER REVIEW
16B+: NOT AUTHORIZED / NOT STARTED
```

## Authority binding

| Item | Value |
| --- | --- |
| Authorized baseline | `9f4b98f983a353f19c8e9f7e343cf8958ea8c525` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Branch | `implementation/16a-workspace-foundation` |
| Phase | **16A only** |

## Implementation summary

16A adds the durable application-layer substrate for future workspace lifecycle
work (16B), without HTTP routes, UI, ingest orchestration, or query adapters.

Introduced under `src/offline_rag/app/workspace/`:

- domain contracts: `WorkspaceRecord`, `SourceVersionRecord`, revisions,
  managed-operation records;
- `WorkspaceStore` — atomic workspace catalog persistence;
- `RawSourceVault` — private raw-object store with server-generated physical IDs;
- `ManagedOperationStore` — durable idempotency/operation records (not a queue);
- publication retirement primitives preserving immutable snapshot manifests;
- `EmptyTransitionCoordinator` — journaled cross-registry EMPTY transition /
  recovery to legal states A or B.

Slice-15 `ProductPublicationRegistry` publish/resolve semantics are unchanged.
Empty scientific ingest was **not** introduced.

## Storage layout

Under `settings.paths.workspaces` (DATA_DIR/`workspaces`):

```text
workspaces/
  ws_<hex>/
    workspace.json
    vault/
      objects/vobj_<hex>          # raw bytes (server name)
      meta/vobj_<hex>.json        # display name + hash metadata
    operations/
      by_id/wop_<hex>.json
      by_idempotency/idem_<sha256>.json   # points at operation_id
    journal/
      empty_transition.json       # present only while EMPTY transition in flight
```

Product publication retirement (per backing corpus):

```text
corpora/<backing_corpus>/product/
  current.json          # removed on retirement
  retired.json          # last_snapshot_id provenance
  snapshots/<snap>.json # immutable; never deleted by retirement/recovery
```

## Contracts introduced

- Workspace status: `active` | `empty` | `tombstoned`
- EMPTY invariant: `sources == []` and `current_snapshot_id == null`
- ACTIVE invariant: ≥1 active source and `current_snapshot_id != null`
- Revision: monotonic positive int; `serialize_revision()` for future If-Match
- Source lineage: stable `source_id`, advancing `version`, content-derived
  `document_id` (changes iff content identity changes)
- Managed op statuses: pending/preparing/running/succeeded/failed/interrupted
- Request fingerprint: `reqfp_<sha256(canonical_json)>`

## Depublication / retirement semantics

`retire_current_publication(settings, corpus_name)`:

1. writes `product/retired.json` with last current snapshot id (if any);
2. unlinks `product/current.json`;
3. leaves `product/snapshots/*` intact.

After retirement, `resolve()` fails as unpublished (`corpus_unknown` /
`not_published`). Ordinary Slice-15 republish / pointer restore can establish a
future current snapshot.

## Crash-recovery mechanism

`EmptyTransitionCoordinator` persists an atomic journal before cross-registry
mutation:

```text
intent_recorded → publication_retired → workspace_emptied → committed
```

`recover(workspace_id)` is idempotent and lands in:

- **A** — prior non-empty workspace + prior publication current; or
- **B** — EMPTY workspace + no active current publication.

Rule of thumb: if workspace is already EMPTY, complete to B (ensure retired);
otherwise restore prior workspace JSON + current pointer (A). Historical
snapshot manifests are never deleted.

## Error code additions

| Code | HTTP (frozen for 16B) | Meaning |
| --- | --- | --- |
| `workspace_unknown` | 404 | Missing / tombstoned (active resolution) |
| `workspace_not_ready` | 409 | Empty / not query-ready |
| `workspace_conflict` | 409 | Revision / state conflict |
| `operation_unknown` | 404 | Managed op missing |
| `idempotency_conflict` | 409 | Same key, different fingerprint |
| `workspace_state_unavailable` | 409 | Corrupt / unreadable durable state |

`SafeErrorDetails` extended with `workspace_id`, `source_id`, `operation_id`.

## Tests run

```text
uv run ruff check src/offline_rag/app/workspace src/offline_rag/app/paths.py \
  tests/unit/app/test_slice16a_workspace_foundation.py
→ All checks passed

uv run pytest \
  tests/unit/app/test_slice16a_workspace_foundation.py \
  tests/unit/app/test_slice15a_foundation.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py \
  tests/unit/app/test_slice15g_container_packaging.py -q
→ 86 passed
```

## Known limitations / deferred to 16B+

- No workspace HTTP CRUD / multipart upload / query adapter
- No end-to-end add/remove/replace orchestration or ingest invocation
- No UI / Training Mode / Gold Lab
- No automatic EMPTY transition from product APIs (primitives only)
- Journal recovery is local/filesystem; no multi-worker redesign

## Explicit non-scope confirmation

16B, 16C–16H, Slice 17, Slice 18, 9G, and Milestone 7 closeout were **not**
started and remain **NOT AUTHORIZED**. This document does **not** accept 16A.
