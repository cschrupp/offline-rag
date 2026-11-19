# 18D-R HTTP Idempotency UUID Corrective — Implementation Result

## Disposition

```yaml
base: c76d487b38a599c474cdb3a4470600d24d2876be
branch: corrective/18d-r-http-idempotency-uuid
implementation_commit: 872419079b2a709522eb9bf8a2dcc5f03bb815b3
implementation_status: COMPLETE
http_review_vm_qualification: INCOMPLETE_VM_UNREACHABLE
promotion: NOT_AUTHORIZED
```

## Change

`ui/src/api/idempotency.ts` now uses native `crypto.randomUUID()` when
available and otherwise generates an RFC 4122 UUID v4 from
`crypto.getRandomValues()`. It does not use `Math.random()`. Fingerprint binding,
retry reuse, and reset semantics in `IntentHandle` are unchanged.

`ui/src/test/idempotency.test.ts` covers native UUID selection, secure random
fallback, UUID v4 format/version/variant bits, distinct fallback keys, and
IntentHandle same-fingerprint, changed-fingerprint, and reset behavior.

## Validation

- Focused tests: `npm test -- --run src/test/idempotency.test.ts src/test/slice16c.rework.test.tsx src/test/slice16c.app.test.tsx` — **27 passed**.
- Full UI suite: `npm test` — **477 passed, 1 failed** across 52 files. The
  failure is the pre-existing `slice16h_integration_acceptance.test.tsx`
  assertion expecting the superseded heading “Engineering summary”; current
  base `c76d487` renders “Engineering”. This corrective does not change either
  the Engineering page or that assertion.
- `npm run build` — PASS; TypeScript and Vite production build completed.
- `npm run lint` — PASS.
- Docker UI builder — PASS on the exact implementation tree:
  `docker build --target ui-builder -f deploy/Dockerfile -t seneca-18dr-http-idempotency-ui-buildcheck .`
- Full CPU-release image — PASS on implementation commit
  `872419079b2a709522eb9bf8a2dcc5f03bb815b3`, after one retry when the first
  locked OpenCV wheel fetch timed out.
- Image inspection:
  - ID: `sha256:64c811c6ce17423e6f61d33e6c898ba2fbe5a6f1c5cb00d0f0365b7b32191f5b`
  - Size: `2,346,862,572` bytes
  - `org.opencontainers.image.revision`:
    `872419079b2a709522eb9bf8a2dcc5f03bb815b3`
  - `io.seneca.dependency-profile`: `cpu-release`
- `git diff --check` — PASS.

## HTTP review VM

The VM was initially unavailable, then came online during the follow-up smoke.
The live results are:

- `GET http://34.123.133.92/workspaces`: **200**.
- The page references `index-D07EKBCI.js`; its SHA-256 exactly matches the
  candidate build at `ui/dist/assets/index-D07EKBCI.js`:
  `b3c789c7105944f34b0bc23f6189d91645caab4100007e9d40c6d9daf6098aa4`.
- Headless Firefox loaded the actual plain-HTTP page with
  `isSecureContext=false`, `typeof crypto.randomUUID === "undefined"`, and
  `typeof crypto.getRandomValues === "function"`. The Create workspace UI was
  visible alongside the existing Recipes workspace.
- Submitting the Create workspace form succeeded. A fresh
  `GET /v1/workspaces` returned the new empty workspace:
  `workspace_id=ws_f2ceb4b3793f4c539bf60896da320bf5`, title
  `HTTP Idempotency Smoke 87241907`, revision 1. The existing Recipes workspace
  remained present.

The workspace library was not empty, so the “No workspaces yet” empty-state
copy was not applicable. The QA workspace is left in place; no user workspace
was removed. One WebDriver-side asynchronous list assertion did not serialize
its fetch result; the independent API GET above confirmed the creation.

## Scope

This corrective changes only the UI idempotency utility and its focused test,
plus this evidence record. It does not alter the Docker packaging corrective,
API behavior, workspace semantics, or scientific evidence.
