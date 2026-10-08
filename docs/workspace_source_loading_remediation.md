# Workspace source-loading remediation

```text
STATUS:
COMPLETE / ACCEPTED

Independent review:
PASS

Human acceptance:
ACCEPTED

Accepted implementation:
9dd2b008ebf9feee279dc6d0e58fafb006288ee5

Verified evidence / final remediation tip:
9cd5528ab6c6e22d2dca55aca221b65eac50269e

16E Engineering accepted implementation (unchanged):
3e1ce4c94fc511abb4e1d94bd194736d5497e64f

Remediation class:
PRE-16E-CLOSEOUT INTEGRATION BLOCKER (resolved)

16F–16H / Slice 17 / 18:
NOT AUTHORIZED
```

## Original symptom

Workspace library showed **Active / 10 sources** while Workspace detail
sometimes showed **Empty · 0 / 32** with “This workspace is empty.”

## First remediation

SHA: `a9649222a7584909915a1fcc1d60a3ae75e155bf`

Separated loading / error / empty / ready / inconsistent source-list phases so
a missing or failed `/sources` payload is no longer presented as Empty.

## Persistence investigation (authoritative)

Known workspace: `ws_1f0faad69b9041e7aa6c60190538ba7d`

| Check | Result |
|---|---|
| workspace.json | present |
| status | active |
| revision | 7 |
| active source records | 10 |
| raw workspace vault | intact |
| published snapshot | matches `current_snapshot_id` |
| published corpus documents | 10 |
| dense manifest | complete |
| expected dense children | 41 |
| indexed dense children | 41 |
| current Qdrant collection | present |
| Qdrant point count | 41 |

```text
DATA LOSS: NONE
RAW SOURCE LOSS: NONE
PUBLISHED CORPUS LOSS: NONE
VECTOR LOSS: NONE
```

No re-upload, re-ingest, Qdrant rebuild, vault mutation, or scientific
re-indexing was performed.

## Live API / intended UI

Direct API:

- `GET /v1/workspaces/<id>` → `source_count = 10`
- `GET /v1/workspaces/<id>/sources` → 10 source rows (healthy/fast)

Intended Vite UI on **5173**:

- proxy `/v1/.../sources` → 10 source rows (healthy)

## Primary environmental root cause

A second rogue Vite development server was running on **5174** because port
5173 was already occupied and Vite silently fell back. The browser had been
using the wrong UI instance while the intended UI and API remained healthy.

## Product defects discovered

1. Loading/error were previously conflated with empty (`sources = []`).
2. Mutation gating was insufficient when source state was unknown.
3. Workspace/source invariant handling needed Active/Empty symmetry.
4. Unreadable successful JSON could be admitted as successful `null` via
   `apiRequest()` / `readPayload()`.
5. Vite did not fail closed when the development port was occupied.

## Consolidated Rework 1

Internal phase `inconsistent` is retained as a fail-closed invariant reachable
only after a **valid, parsed, structurally validated** source payload
contradicts the workspace record.

User-facing badge for that phase: **Source issue** (not “Inconsistent”).

Transport/JSON/contract failures remain **source-loading error** with Retry —
never Empty, never Source issue.

Additional guards (Rework 1 entry points):

- Add entry controls gated when source state is unknown;
- Ask disabled until real source records are available;
- `SourceListResponse` runtime validation in `listSources()`;
- JSON parse failures on JSON content-type throw retryable `ApiError`;
- Vite `server.port = 5173` with `strictPort: true`.

## Classification summary

```text
PRIMARY ENVIRONMENTAL ROOT CAUSE:
duplicate Vite development server / wrong browser UI instance

PRODUCT DEFECTS:
loading/error conflated with empty;
insufficient mutation gating;
asymmetric workspace/source badge semantics;
successful JSON parse failure admitted as null;
Vite silent port fallback

SCIENTIFIC MUTATION:
NONE
```

## Final Rework 1 SHAs

- Implementation: `b1da3c076d56bed77bbdc328346ce92220950c8b`
- Documentation: `5f00c148719d9903f12795bececf89a075bc3d3e`
- Docs SHA fill-in: `75ba49dff3d33ef3a76835c67951dcc567234017`

## Rework 2 — mutation-boundary fail-closed gate

**Reason:** Mutation entry controls were gated, but already-open Add / Rename /
Replace / Remove dialogs could still dispatch after source state became
unavailable.

**Permission model (shared for UI disable + dispatch guards):**

- Add Sources: `sourcePhase === "ready" || sourcePhase === "empty"`
- Rename / Replace / Remove: `sourcePhase === "ready"` only

**Guards added:**

- Form submit buttons disable when source state leaves the allowed set
- Submit handlers and `mutationFn` refuse dispatch when permissions fail
- Replace does not enter `uploading` when the existing-source gate fails
- Frozen Add “Retry safely” intent is preserved but not dispatched until Add
  is again allowed
- Compact notice: “Source details changed. Reload the source list before
  continuing.”
- `ConfirmDialog` supports `confirmDisabled` (Cancel remains available)

**Regression coverage:** stale-open-dialog races A–G in
`ui/src/test/workspace_source_loading_state.test.tsx`.

```text
STATUS: COMPLETE / ACCEPTED
Independent review: PASS
Human acceptance: ACCEPTED
Accepted implementation: 9dd2b008ebf9feee279dc6d0e58fafb006288ee5
Verified evidence tip: 9cd5528ab6c6e22d2dca55aca221b65eac50269e
```

### Rework 2 SHAs

- Implementation: `9dd2b008ebf9feee279dc6d0e58fafb006288ee5`
- Documentation: `2449f84f9161dcadad37d7ce71bdbbcc20c2558e`

### Rework 2 validation

```text
Frontend tests: 170 passed (12 files)
Lint: pass
Typecheck: pass
Build: pass
git diff --check: pass
```
