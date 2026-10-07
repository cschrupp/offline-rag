# Slice 16D-B1 — Source upload foundation remediation

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING

Implementation baseline:
6b6524001f063a628505f572e7ca13d954a38260

Governance authority (A2 acceptance closeout):
f0bdf78d0ae6a79737055d324b22fc35e1e501f5

Accepted A2 design:
dce3456e519cb6c96570e20f5af800d00cafb5a7

Branch:
implementation/16d-b1-upload-foundation-remediation

16D-B1 FOUNDATION REMEDIATION:
IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING

16D-B1 product acceptance: WITHHELD (not sealed by this candidate)
16D-B2 / 16D-B3 / 16D-C: NOT AUTHORIZED
Slice 16: IN PROGRESS / NOT COMPLETE
```

## Observed browser failure

On the observed B1 candidate `6b652400…`:

- browser one-file Add Sources succeeded;
- browser two-or-more-file Add Sources could fail with a fetch/network-style error;
- generic `apiRequest(fetch)` mapped all transport rejections to
  `network_error` / “Could not reach OfflineRAG…”, which was false when GETs
  and curl multipart proved the backend healthy;
- Add Sources modal used `busy` while uploading and disabled Cancel/Close,
  trapping the user on a stalled pre-202 transfer.

## Curl / proxy evidence (already established; not re-claimed here)

Manual evidence prior to this remediation:

- curl one-file through Vite → FastAPI returned 202;
- curl two-file through Vite → FastAPI accepted multi-file `source_add` with
  stable revision;
- therefore FormData contract, repeated `files` parts, Vite multi-file proxy,
  FastAPI multipart parsing, and atomic multi-file add were considered
  proven-capable.

This remediation does **not** redesign the multipart backend.

## Transport design

Dedicated browser multipart module: `ui/src/api/upload.ts`.

- XMLHttpRequest multipart POST (authorized preferred choice);
- repeated FormData field name `files`;
- `Idempotency-Key` + `If-Match`;
- AbortSignal / `xhr.abort()`;
- browser-owned `Content-Type` boundary (not set manually);
- canonical JSON success + error-envelope parsing;
- classification:
  - `request_aborted`
  - `upload_transport_interrupted` (retryable)
  - canonical API codes unchanged
- `addSources()` routes through this transport; other API calls remain on fetch.

## Cancellation semantics (pre-202)

While transfer is in flight and no 202 is confirmed:

- **Cancel upload** remains available;
- Close / Escape abort the local transport (Add Sources only; other busy modals
  unchanged);
- abort does not fabricate a local Operation;
- copy: “Upload canceled before Seneca confirmed acceptance.”;
- no automatic retry;
- no durable operation-cancellation architecture.

After 202: modal closes; `rememberActiveOperation()` + existing polling/tray.

## Ambiguity semantics

Transport interruption after submission is treated as **ambiguous**:

- keep frozen `AddSourcesIntent` (files, expected revision, idempotency key);
- expose **Retry safely**;
- do not claim server-down or definite failure/success;
- copy: “Seneca couldn't confirm whether this upload was accepted…”

## Immutable AddSourcesIntent

Captured **before** transport:

- `workspaceId`
- `expectedRevision` (from workspace at submit time)
- `files` (File objects retained for retry)
- `fingerprint`
- `idempotencyKey`

Safe retry reuses that exact identity. Live workspace revision advances must
**not** substitute a new If-Match or key.

## Safe replay

Backend property relied upon (regression-tested):

matching idempotency key → replay existing operation **before** stale
If-Match / revision rejection.

Therefore retry after ambiguity with original revision + key can rediscover an
already-admitted operation without duplicates.

Definitive `workspace_conflict` terminates the old intent; user must submit a
new intent after review.

## Tests

Frontend (`ui/src/test/slice16d_b1_upload.test.tsx` + updated 16D-A Close test):

- N-file single multipart request; no manual Content-Type;
- immutable intent retry keeps If-Match + key;
- ambiguity → replay Operation once;
- conflict on retry without auto revision bump;
- pre-202 cancel; no fabricated operation;
- error copy distinctions.

Backend:

- `test_f3_idempotency_replay_precedes_stale_revision_after_success` in
  `tests/unit/app/test_slice16b_rework_hardening.py`
  (two-file add, succeed, replay same key + stale If-Match 1 → same
  operation_id, source count remains 2).

## Manual browser evidence

Performed against local Vite `:5173` → FastAPI `:8080` on this candidate
working tree (workspace `ws_1f0faad69b9041e7aa6c60190538ba7d`):

| Smoke | Result |
| --- | --- |
| A. one-file Add Sources | PASS (`cancel.txt` admitted as single-file add) |
| B. two-file Add Sources | PASS (`a.txt` + `b.txt` → one durable `source_add`, succeeded) |
| C. four-file Add Sources | PASS (`c1`–`c4.txt` → one durable `source_add`, succeeded) |
| D. no duplicates | PASS (final unique set of 7 display names; no duplicates) |
| E. pre-202 Cancel upload control | PASS observed: while `Uploading...`, **Cancel upload** and **Close** remained enabled (not trapped). Timed cancel click raced a delayed XHR in the automation harness before abort landed; abort semantics covered by automated cancel test. |
| F/G. ambiguity + Retry safely | Covered by automated UI tests (`slice16d_b1_upload.test.tsx`); not separately forced in this manual session. |

## Limitations

- Does not accept or seal 16D-B1 product UX;
- does not implement B2/B3/C;
- does not add durable operation cancellation;
- does not chunk/resume uploads;
- Ask layout ugliness remains deferred to B3;
- backend production code intentionally unchanged in this candidate.
