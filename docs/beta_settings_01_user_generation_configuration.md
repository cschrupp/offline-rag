# BETA-SETTINGS-01 — User-editable generation configuration

## Decision

Generation configuration has an explicit deployment-owned mode:

- `operator` is the backward-compatible default. Environment values remain
  authoritative and corresponding Settings controls stay locked.
- `user` treats generation environment values as first-run bootstrap values.
  Saved generation Settings take precedence after restart. Explicit
  programmatic overrides remain highest priority.

The ownership switch applies only to generation configuration. Other
environment and product-setting precedence remains unchanged. Saved changes
remain pending until restart; no runtime hot swap was introduced.

User mode is intended for trusted local installations. Exposing the
unauthenticated Settings API to untrusted network clients is unsafe. Strict
offline endpoint validation and API-key secrecy remain in force.

## Implementation result

**Authority:** BETA-SETTINGS-01 bounded implementation authorization

**Starting subject:** `8db8fe7d2595d176cd7dd159303aaed05e2c8ae5`

**Branch:** `implementation/beta-settings-01-user-generation`

**Accepted technical subject:** `3841e70db09b7fd12512a2502729a27512cad446`

**Independent review:** IR-002 — ACCEPT; F001 and F002 CLOSED

**Human acceptance:** ACCEPTED

**Promotion:** COMPLETE — pure fast-forward to `main`

The implementation adds `OFFLINE_RAG_GENERATION_SETTINGS_MODE`, defaulting to
`operator`, and applies user-mode bootstrap precedence to generation
environment fields only. The existing Settings API and UI are reused. In user
mode, generation fields are editable; keep/set/clear API-key behavior remains
secret-safe, and persisted clear suppresses a bootstrap key after restart.
Explicit generation overrides are retained as private, non-serialized metadata.
The API locks those fields—including model or endpoint selection when only its
approval list is overridden—so Pending does not promise a value that an
explicit override will replace after restart. Compose passes the mode through,
while retaining `operator` as its fallback.

### Changed files

- `.env.example`, `deploy/docker-compose.example.yml` — document and pass the
  mode.
- `src/offline_rag/app/product_settings.py` — validate the mode and report
  field locks according to ownership and explicit overrides.
- `src/offline_rag/config/loader.py`, `src/offline_rag/config/models.py` —
  implement generation-only bootstrap precedence and retain private metadata
  identifying explicit generation overrides.
- `src/offline_rag/api/settings.py` — retain the effective key for a `keep`
  connection probe without persisting a bootstrap key.
- `tests/unit/app/test_slice16d_a_settings_capabilities.py` — cover default,
  user/operator precedence, API-key actions, restart, strict-offline behavior,
  pending state, and unrelated environment settings.
- `ui/src/test/slice16d_a.app.test.tsx` — cover editable fields, connection
  probe, and save in user mode.
- `README.md`, `ROADMAP.md`, `docs/BACKLOG.md` — register the bounded slice and
  its review status.
- This file — preserve the concise decision and implementation record.

### Validation

- Backend settings/config tests after corrective: **37 passed, 16 skipped**.
  The named `test_user_mode_bootstrap_save_restart_and_api_key_actions` passed
  independently using the actual Settings endpoint functions, a fake ready
  runtime, temporary configuration, and no provisioned tokenizer/model assets.
  Other skips still require tokenizer assets. A Starlette deprecation warning
  was reported.
- Focused Settings UI tests: **17 passed**.
- Targeted ESLint: **passed**.
- Ruff lint: **passed** after automatic import/order fixes.
- `git diff --check`: **passed**.
- Full UI typecheck remains blocked by existing errors in the unchanged
  `ui/src/test/slice16k_r04_cuda_oom.test.tsx` (`operation_id` and `retryable`
  fields missing from test fixtures).
- Ruff formatting check reports pre-existing formatting drift in
  `src/offline_rag/api/settings.py`, `src/offline_rag/app/product_settings.py`,
  and `tests/unit/app/test_slice16d_a_settings_capabilities.py`. The new
  loader logic and added test block are formatted; no unrelated reformatting
  was applied.

### Limitations and boundaries

A live Settings save/restart smoke was not run because it would modify the
user's active installation settings. Automated API tests use temporary
configuration directories and fake probes; the focused API tests call the
route handlers directly because the unrelated TestClient lifespan startup
hang remains tracked separately. No private data or credentials were
accessed. No runtime hot swap, Gold Lab changes, or compute ownership changes
are included. Slice 17 remains unauthorized.
