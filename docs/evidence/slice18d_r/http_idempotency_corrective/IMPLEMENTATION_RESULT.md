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

`GET http://34.123.133.92/v1/workspaces` returned `200 []` once, confirming an
empty workspace list before any create request. Subsequent checks of
`/workspaces` and `/v1/workspaces` failed to connect. The VM was therefore not
available for browser rendering or a create-workspace mutation. No workspace
was created. These live-VM checks remain pending; automated tests and Docker
build do not substitute for them.

## Scope

This corrective changes only the UI idempotency utility and its focused test,
plus this evidence record. It does not alter the Docker packaging corrective,
API behavior, workspace semantics, or scientific evidence.
