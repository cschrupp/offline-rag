# Workspace source-loading remediation

```text
16E Engineering:
HUMAN ACCEPTED at 3e1ce4c94fc511abb4e1d94bd194736d5497e64f

16E closeout / seal:
PAUSED

Remediation class:
PRE-16E-CLOSEOUT INTEGRATION BLOCKER

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

Additional guards:

- source mutations allowed only when `sourcePhase` is `ready` or `empty`;
- Ask disabled until real source records are available;
- `SourceListResponse` runtime validation in `listSources()`;
- JSON parse failures on JSON content-type throw retryable `ApiError`;
- Vite `server.port = 5173` with `strictPort: true`.

## Validation

See STOP report for Rework 1 SHAs and `npm test` / lint / typecheck / build
results.

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
```

## Final Rework 1 SHAs

- Implementation: 
- Documentation: (this commit)

