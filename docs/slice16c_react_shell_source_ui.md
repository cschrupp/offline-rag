# Slice 16C — React shell, design system & source-management UI

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING
16C: IMPLEMENTED CANDIDATE / NOT ACCEPTED
16D+: NOT AUTHORIZED / NOT STARTED
```

## Authorities

| Item | Value |
| --- | --- |
| Authorized baseline / sealed 16B closeout | `a0a8a3f9a38807f40676a9a249cd7c7b186c09cb` |
| Accepted 16B SHA | `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e` |
| Accepted 16A SHA | `e73959be508541a1c50d4919606aaf3157a5fa8a` |
| Locked design authority | `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8` |
| Branch | `implementation/16c-react-shell-source-ui` |

## Frontend architecture

- Location: `ui/` (Vite + React + TypeScript)
- Package manager: npm (`package.json` + `package-lock.json`)
- Routing: React Router (`/`, `/workspaces`, `/workspaces/:workspaceId`, product not-found)
- Server state: TanStack Query only (no Redux)
- HTTP: centralized same-origin relative client in `ui/src/api/*`
- Features: Overview, workspace library, workspace metadata, source add/rename/replace/remove, durable operation UX
- Styling: project-owned CSS tokens/primitives; Inter bundled via `@fontsource/inter`

### Locked dependency versions (from `package-lock.json`)

| Package | Version |
| --- | --- |
| react | 19.3.0 |
| react-dom | 19.3.0 |
| react-router-dom | 7.18.4 |
| @tanstack/react-query | 5.104.1 |
| @fontsource/inter | 5.3.0 |
| lucide-react | 1.52.0 |
| vite | 8.3.2 |
| typescript | 5.9.3 |
| vitest | 5.0.3 |

## Routes implemented (16C only)

- `/` — Overview
- `/workspaces` — workspace library + create
- `/workspaces/:workspaceId` — metadata + source management
- unknown client paths — product not-found

Not implemented / not functional: `/ask`, `/evidence`, `/training`, `/evaluation`, `/architecture`, `/gold`.

## API client / idempotency / ETag

- All browser calls use relative URLs (`/health/ready`, `/v1/...`).
- `IntentHandle.prepare(canonicalFingerprint)` binds an opaque key to a client
  request fingerprint covering the canonical mutation inputs (including expected
  revision where applicable).
- Same fingerprint after transport ambiguity → reuse key.
- Changed fingerprint (edited fields, different files, new revision) → new key.
- Terminal backend success/failure → `reset()` for the next user action.
- TanStack Query mutation `retry: false`.
- Existing-workspace mutations send quoted `If-Match: "<revision>"`.
- `workspace_conflict` explains stale state, invalidates/refetches, and does **not** auto-resubmit.

## Operation persistence / polling

- Active operation locators persisted at `offline-rag.active-operations.v1` (id, workspace, kind, optional label only).
- Upload phase shows **Uploading…** before HTTP 202.
- After 202, polls `GET /v1/operations/{id}` and maps stages honestly (no percentages/ETA).
- No Cancel control; no queue position.
- Application-level **operation tray** (`ActiveOperationsBootstrap`) visibly
  resumes remembered operations after refresh/reconnect:
  - RUNNING: label + durable stage visible
  - SUCCEEDED: Ready surfaced; workspace/source caches invalidated; locator
    cleared; dismissible terminal card retained until acknowledged
  - FAILED / INTERRUPTED: safe message/guidance surfaced before/while locator
    cleared; dismissible (not silent)
  - `operation_unknown` / transport failure: bounded lookup-error card; polling stops

## Overview semantics

- Product identity, readiness from `GET /health/ready`, real workspace/source counts from API DTOs.
- Local/offline wording only; no fabricated metrics/history/benchmarks.
- `workspace.updated_at` labeled **Last workspace change** / **Workspace updated** — never “last successful knowledge update”.
- No Ask / Training Mode actions.

## Source management / EMPTY / deletion wording

- Active sources only; no vault/corpus/path exposure; no source preview.
- Add (multipart repeated `files`), rename (metadata-only), replace (one file / current version), remove (202 op).
- EMPTY is first-class with Add Sources CTA.
- Workspace/source removal confirmation copy states historical artifacts may remain and is not secure permanent deletion.
- Final-source removal uses the stronger EMPTY warning.

## Design tokens / accessibility

- Tokens: `--navy #0B1F33`, `--slate #24384A`, `--surface #F6F7F8`, `--white`, `--text`, `--muted`, `--action #175CD3`, `--critical #B42318`, `--brass #9A6700`, `--success #027A48`.
- Primary actions blue; red reserved for destructive/critical.
- Skip link, landmarks, labels, keyboard dialogs/nav toggle, visible focus, status text+badge (not color-only), ~44px targets, reduced-motion, responsive shell.
- Shared `ModalDialog` primitive (portal + `aria-modal` + `#root` inert + Tab
  cycle + Escape + focus restore) used by ConfirmDialog, rename, and replace.
- Nested interactive controls removed: `Button to="..."` renders a styled
  `Link`, not `<a><button>`.

## Same-origin static serving

- Module: `src/offline_rag/api/frontend.py`
- Env: `OFFLINE_RAG_UI_DIR` (default `/app/ui`)
- Serves `/`, SPA deep links, and `/assets/*`
- Does **not** swallow `/v1/*`, `/health*`, `/openapi.json`, `/docs`, `/redoc`
- Unknown `/v1/*` remains API 404
- Path traversal rejected; API remains usable when UI dir absent

## Docker multi-stage

- `deploy/Dockerfile`: `node:22` UI builder (`npm ci`, `npm run build`) → `python:3.14-slim` runtime
- Copies `ui/dist` to `/app/ui`; sets `OFFLINE_RAG_UI_DIR=/app/ui`
- Preserves UID/GID 10001, CMD, volumes/env contract; no Node in final runtime; no second frontend service
- `.dockerignore` excludes `ui/node_modules/`, `ui/dist/`, data/models, etc.
- `ui/dist` is not committed

## Offline asset proof

- Production HTML references only bundled `/assets/*` and local favicon
- No Google Fonts / CDN icon/CSS/font URLs in source or built index

## Explicit non-scope

- No Ask UI
- No Evidence UI
- No Training Mode
- No source preview
- No `POST /v1/workspaces/{id}/query` from the 16C frontend
- No source-content preview calls
- No 16D+ work started
- No merge / no self-accept

## Independent review rework (F1–F3)

Resolved on this candidate after disposition **REWORK REQUIRED**:

1. **F1** visible resumed-operation tray + terminal/error surfacing
2. **F2** canonical client-intent fingerprint binding for idempotency keys
3. **F3** shared accessible modal primitive + nested interactive cleanup

## Quality gates (executed for rework SHA)

### Frontend

```text
cd ui
npm run lint      -> pass
npm run typecheck -> pass
npm test          -> 23 passed
npm run build     -> pass
```

### Backend

```text
uv run pytest \
  tests/unit/app/test_slice16c_frontend_static.py \
  tests/unit/app/test_slice16b_workspace_api.py \
  tests/unit/app/test_slice16b_rework_hardening.py \
  tests/unit/app/test_slice16b_integrity_rework.py \
  tests/unit/app/test_slice16b_publication_journal.py \
  tests/unit/app/test_slice16b_query_binding.py \
  tests/unit/app/test_slice15b_runtime_health.py \
  tests/unit/app/test_slice15g_container_packaging.py -q
-> 113 passed
```

### Other

```text
git diff --check -> clean
docker build:
  prior candidate 532ce8ac... image build -> pass (exit 0),
  tagged offline-rag:16c-test (d657aac8dce6)
  rework changes are TypeScript/components/tests only (npm build green);
  no fresh docker image build executed for this rework SHA
```

## Manual / browser acceptance

Automated Vitest coverage now includes resumed-operation visibility, failed/
interrupted/lookup-error surfacing, fingerprint same/changed-request key
behavior, modal focus trap/Escape/restore, and no nested `a > button`.
Full desktop/mobile/keyboard/zoom browser walkthrough was not claimed beyond
those tests.

## Residual risks / deferred

- Human manual soak of refresh reconnect under real network ambiguity remains useful.
- Operation poll interval remains aggressive for local single-user UX; tuning only.
- “Last successful knowledge update” remains omitted until a future accepted API exposes that semantic.
- 16D Ask/Evidence/Training surfaces remain unauthorized.
