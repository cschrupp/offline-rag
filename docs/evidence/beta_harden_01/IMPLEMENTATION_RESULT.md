# BETA-HARDEN-01 — Implementation Result

## Authority and subject

- Work item: `BETA-HARDEN-01 — Large-PDF admission and failed-operation recovery`
- Authorization: user-authorized bounded implementation GO for BETA-HARDEN-01.
- Starting canonical `main`: `c6d1b41165a22bd8d80af437543daf3a6e51e798`
- Implementation branch: `implementation/beta-harden-01-large-pdf-recovery`
- Technical implementation commit: `7ebf56796779449090fb85b4a0ac6c944c01f1f1`
- Independent review: IR-001 — ACCEPT (review handoff tip `793ef6d75388052d3790864b218acdcb3953ffd5`)
- Human acceptance: ACCEPTED for technical subject `7ebf56796779449090fb85b4a0ac6c944c01f1f1`.
- Promotion: pure fast-forward from `c6d1b41165a22bd8d80af437543daf3a6e51e798` to `793ef6d75388052d3790864b218acdcb3953ffd5`.
- Additional implementation/result commits: `d0735d6ae0321b7f842c81c2a6aae4c2ff9d8a6b` (durable evidence and live projection)

## Changed paths

```text
src/offline_rag/api/workspaces.py
src/offline_rag/app/workspace/capacity.py
tests/unit/app/test_slice16b_workspace_api.py
tests/unit/app/test_slice16k_c_capacity_model.py
tests/unit/app/test_slice16k_l2_bounded_workspace_path.py
ui/src/features/operations/ActiveOperationsBootstrap.tsx
ui/src/pages/WorkspacePage.tsx
ui/src/test/slice16d_a.app.test.tsx
ui/src/test/slice16h_integration_acceptance.test.tsx
ROADMAP.md
docs/BACKLOG.md
docs/evidence/beta_harden_01/IMPLEMENTATION_RESULT.md
docs/evidence/beta_harden_01/live_recovery_evidence.json
```

## Changes

- Removed the transient CUDA effective-free-capacity pre-admission threshold. The qualified profile, host memory checks, telemetry validation, and 8 GB total-VRAM floor remain. Real runtime exhaustion still fails through the existing bounded OOM recovery and atomic publication paths.
- Kept upload and workspace product limits unchanged: PDF 90 MiB, other text files 25 MiB, request 100 MiB.
- Retrieved detached executor Future exceptions after lifecycle terminalization; logs include only operation ID and exception class.
- Synchronized active-operation tray state with stored locators while retaining a terminal card until dismissal, as required by the existing operation-tray contract. Dismissal removes the locator and rendered item; later sync does not restore it.
- Updated Add and Replace limit copy to say “other text files.”
- No CPU fallback, indexing/rebuild change, publication change, or R04 research was introduced.
- No migrations, configuration, capabilities schema, API schema, or admission ordering changes were made. The existing stable error classifications and atomic publication semantics remain in force.
- Product limits before/after: PDF 90 MiB; other supported text files 25 MiB; request 100 MiB — unchanged.

## Live recovery execution

The candidate API ran in one process against a new isolated workspace. The sequence was:

1. Add a 92-byte text baseline: succeeded, revision 1 → 2, one active source.
2. Add the same content under another filename: terminal `document_invalid` / `document_identity_conflict`; revision stayed 2, the workspace stayed active, and the original source remained the only active source.
3. Add `the_book_of_shupe.pdf` (67,199,839 bytes; SHA-256 `1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54`): succeeded in the same API process, revision advanced to 3, source count became two.
4. `/health/ready` returned HTTP 200 after the sequence.

The API log contained the detached worker’s safe `AppError` classification and did not contain `Future exception was never retrieved`. Full sanitized operation and workspace facts are in [`live_recovery_evidence.json`](live_recovery_evidence.json).

The live sequence validates a managed failure followed by a valid large-PDF recovery add. It did not deliberately force a real CUDA OOM; OOM classification/recovery remains covered by the existing deterministic CUDA recovery tests, and publication code was not changed.

Scientific campaign executions: **NONE**.

## Validation

- `.venv/bin/pytest -q tests/unit/app/test_slice16k_c_capacity_model.py tests/unit/app/test_slice16k_l2_bounded_workspace_path.py` — **46 passed**.
- `.venv/bin/pytest -q tests/unit/app/test_slice16b_workspace_api.py::test_detached_worker_exception_is_retrieved_without_logging_private_message tests/unit/test_dense_failure_observability.py tests/unit/dense/test_cuda_oom_recovery.py` — **33 passed**.
- `cd ui && npm test -- --run src/test/slice16d_a.app.test.tsx src/test/slice16h_integration_acceptance.test.tsx src/test/slice16_gold_operations_ux.test.tsx` — **40 passed**.
- `cd ui && npx eslint src/features/operations/ActiveOperationsBootstrap.tsx src/pages/WorkspacePage.tsx src/test/slice16h_integration_acceptance.test.tsx src/test/slice16d_a.app.test.tsx` — **passed**.
- `.venv/bin/ruff check src/offline_rag/api/workspaces.py src/offline_rag/app/workspace/capacity.py tests/unit/app/test_slice16b_workspace_api.py tests/unit/app/test_slice16k_c_capacity_model.py tests/unit/app/test_slice16k_l2_bounded_workspace_path.py` — **passed**.
- `git diff --check` — **passed**.
- `timeout 45s .venv/bin/pytest -q tests/unit/app/test_slice16b_workspace_api.py` — timed out (exit 124); its focused detached-Future test passed and the live managed-operation flow passed.
- `cd ui && npm run lint` — existing failures: 4 errors and 2 warnings, all in untouched Gold Lab files.
- `cd ui && npm run typecheck` — existing errors in untouched `p4_human_uat_duplicate_message.test.ts` and `slice16k_r04_cuda_oom.test.tsx`; targeted ESLint and all focused UI tests passed.
- `.venv/bin/ruff format --check` on the five changed Python paths reports pre-existing formatting differences in legacy sections; no broad formatting pass was applied.

## Limits and remaining gates

- Production limits and accepted profile policy remain unchanged except removal of the transient free-VRAM preflight threshold.
- No scientific campaign was run. No deliberate GPU OOM was induced.
- The test workspace `ws_65dee968958340cfb0a671eebfabc44f` is isolated and remains available for inspection.
- BETA-HARDEN-01 is closed. The closeout projection is documentation-only; no additional production code or scientific execution occurred.
- Tracked worktree is clean; unrelated pre-existing untracked artifacts and local data were left untouched.
