# Slice 16D-B1 — Source upload foundation remediation

```text
STATUS: ACCEPTED / SEALED
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT IMPLEMENTATION REVIEW: PASSED
INDEPENDENT CLOSEOUT REVIEW: PASSED

ACCEPTED IMPLEMENTATION:
c68cc3f8f16a2588ba093886f3e48e1c7037f83f

VERIFIED CLOSEOUT:
b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90

Acceptance applies exactly to the accepted implementation SHA
(upload-foundation remediation only). Closeout verification applies to
the docs-only acceptance closeout SHA.

Implementation baseline:
6b6524001f063a628505f572e7ca13d954a38260

Previous candidate (pre-R1; did not pass acceptance):
855fd6440ed5b9be18b7fe2cc303bb2700bc9f4f

Governance authority (A2 acceptance closeout):
f0bdf78d0ae6a79737055d324b22fc35e1e501f5

Accepted A2 design:
dce3456e519cb6c96570e20f5af800d00cafb5a7

Branch:
implementation/16d-b1-upload-foundation-remediation

16D-B1 FOUNDATION REMEDIATION:
ACCEPTED / SEALED
IMPLEMENTATION: c68cc3f8f16a2588ba093886f3e48e1c7037f83f
CLOSEOUT: b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90

16D-B1 product acceptance (legacy Ask/Evidence UX):
PRODUCT ACCEPTANCE WITHHELD / NOT SEALED

16D-B2 / 16D-B3 / 16D-C: NOT AUTHORIZED
Slice 16: IN PROGRESS / NOT COMPLETE
```

## Acceptance disposition

Human decision: **ACCEPT** the 16D-B1 foundation remediation implementation at
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`.

Independent implementation review: **PASS**.

This acceptance applies specifically to the upload-foundation remediation:

- multi-file browser upload;
- pre-202 cancellation;
- honest transport classification;
- ambiguity-safe idempotent retry;
- R1 cancellation reconciliation fix.

It does **not** accept the legacy B1 Ask/product UX. Known A2 product findings
F7/F8 (layout spilling) and F9/F10 (composer lifecycle / single-turn
interaction) remain intentionally deferred to **16D-B3** where applicable.

Do **not** rewrite history to imply the initial candidate (`855fd644…`) passed
without rework. R1 was required after independent review.

### Findings — CLOSED

| ID | Finding | Disposition |
| --- | --- | --- |
| B1-U1 | Browser multi-file source-upload reliability | **CLOSED** |
| B1-U2 | Pre-202 upload cancellation | **CLOSED** |
| B1-U3 | Honest transport-error classification | **CLOSED** |
| B1-U4 | Transport-ambiguity-safe retry | **CLOSED** |
| B1-R1 | Canceled-upload fresh-intent duplicate hazard | **CLOSED** |

---

## Accepted product / transport contract (frozen)

### Browser Add Sources

- XMLHttpRequest multipart transport;
- browser-owned multipart `Content-Type` boundary;
- repeated `files` parts;
- one Add Sources action → one `source_add` operation;
- explicit `AbortController` / `xhr.abort()` pre-202 cancellation;
- no automatic mutation retry.

### Transport interruption

`upload_transport_interrupted`
→ acceptance unknown
→ frozen files
→ frozen expected revision
→ frozen idempotency key
→ explicit **Retry safely**

### Explicit cancel

`request_aborted`
→ no **Retry safely**
→ old intent/key abandoned
→ selected files cleared
→ native file input reset/remounted
→ workspace + source state reconciled
→ Add blocked during reconciliation
→ new submission requires explicit new file selection

### 202 boundary

- before 202 → browser transport semantics
- after 202 → durable managed-operation semantics

---

## Idempotency replay contract (accepted dependency)

Matching existing idempotency identity is replayed **before** stale workspace
revision rejection.

Regression proof:

`test_f3_idempotency_replay_precedes_stale_revision_after_success`

Accepted behavior:

same files + same key + original stale `If-Match`
→ same operation replay
→ no duplicate logical sources
→ no `workspace_conflict`

Do **not** broaden this into generic automatic retry authority.

---

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
- no **Retry safely** for `request_aborted` (that is only for
  `upload_transport_interrupted`);
- after cancel: abandon submission identity, **clear selected files**, remount
  file input, invalidate/refetch workspace + sources, and block Add until
  reconciliation settles — so the user cannot one-click resubmit the same
  files under a freshly reset idempotency key while acceptance is unknown;
- no durable operation-cancellation architecture.

After 202: modal closes; `rememberActiveOperation()` + existing polling/tray.

### R1 — cancel must not leave a one-click fresh duplicate intent

Independent review finding B1-R1 (against `855fd644…`): cancel reset the
idempotency handle while leaving `selectedFiles` populated, enabling
immediate Add under a new key even though the aborted request may already
have been admitted. R1 closes that gap as above. Finding **B1-R1** is
**CLOSED** at the accepted SHA.

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
- cancel clears selection; Add disabled until re-selection; no Retry safely;
  new explicit selection uses a new key;
- error copy distinctions.

Backend:

- `test_f3_idempotency_replay_precedes_stale_revision_after_success` in
  `tests/unit/app/test_slice16b_rework_hardening.py`
  (two-file add, succeed, replay same key + stale If-Match 1 → same
  operation_id, source count remains 2).

## Manual browser evidence (frozen acceptance smoke)

Performed against local Vite `:5173` → FastAPI `:8080` on the remediation
candidate working tree (workspace `ws_1f0faad69b9041e7aa6c60190538ba7d`):

| Smoke | Result |
| --- | --- |
| A. one-file Add Sources | PASS (`cancel.txt` admitted as single-file add) |
| B. two-file Add Sources | PASS (`a.txt` + `b.txt` → one durable `source_add`, succeeded) |
| C. four-file Add Sources | PASS (`c1`–`c4.txt` → one durable `source_add`, succeeded) |
| D. no duplicates | PASS (final unique set of 7 display names; no duplicates) |
| E. pre-202 Cancel upload (R1) | See Rework 1 manual abort section below (must land abort before response). |
| F/G. ambiguity + Retry safely | Covered by automated UI tests (`slice16d_b1_upload.test.tsx`); not separately forced in this manual session. |

Frozen acceptance summary:

- single-file upload **PASS**
- two-file upload **PASS**
- four-file upload **PASS**
- one atomic `source_add` per batch
- no duplicates
- actual pre-202 `xhr.abort()` observed
- cancel returned UI to usable state
- canceled selection cleared
- no **Retry safely** after explicit cancel
- canceled test files not observed in resulting source set

### Rework 1 manual abort smoke

Recorded against this R1 candidate working tree on workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d` (Vite `:5173` → FastAPI `:8080`):

Two ~1.4 MiB files selected; XHR `send` held open long enough that Cancel
could land before any 202. Instrumentation recorded `xhr.abort()` (readyState
OPENED).

| Check | Result |
| --- | --- |
| Uploading visibly in progress | PASS (`Uploading…` + **Cancel upload**) |
| Cancel upload clicked before response | PASS |
| Request canceled/aborted | PASS (`xhr.abort()` logged; no 202 observed for this attempt) |
| UI exits uploading; modal not trapped | PASS (Close/Cancel enabled; cancel alert shown) |
| Selected files cleared; Add not one-click ready | PASS (selection list gone; **Add sources** disabled; no **Retry safely**) |
| No fabricated local Operation / no admit of canceled files | PASS (source count remained 7; no `r1-cancel-*.bin` sources) |

**Caveat (preserved):** browser abort does **not** logically prove the server
could never have won an acceptance race. The reconciliation + cleared-selection
contract is what prevents unsafe one-click duplicate resubmission.

## Limitations

- Does not accept or seal 16D-B1 product UX;
- does not implement B2/B3/C;
- does not add durable operation cancellation;
- does not chunk/resume uploads;
- Ask layout ugliness (F7/F8) and composer/single-turn findings (F9/F10)
  remain deferred to B3 where applicable;
- backend production code intentionally unchanged in this candidate.
