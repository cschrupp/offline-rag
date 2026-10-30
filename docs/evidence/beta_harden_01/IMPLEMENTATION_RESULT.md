# BETA-HARDEN-01 — Implementation Result

## Authority and subject

- Work item: `BETA-HARDEN-01 — Large-PDF admission and failed-operation recovery`
- Starting canonical `main`: `c6d1b41165a22bd8d80af437543daf3a6e51e798`
- Implementation branch: `implementation/beta-harden-01-large-pdf-recovery`
- Technical implementation commit: `7ebf56796779449090fb85b4a0ac6c944c01f1f1`
- Independent review: pending
- Human acceptance / promotion: not authorized

## Changes

- Removed the transient CUDA effective-free-capacity pre-admission threshold. The qualified profile, host memory checks, telemetry validation, and 8 GB total-VRAM floor remain. Real runtime exhaustion still fails through the existing bounded OOM recovery and atomic publication paths.
- Kept upload and workspace product limits unchanged: PDF 90 MiB, other text files 25 MiB, request 100 MiB.
- Retrieved detached executor Future exceptions after lifecycle terminalization; logs include only operation ID and exception class.
- Synchronized active-operation tray state with stored locators while retaining a terminal card until dismissal, as required by the existing operation-tray contract. Dismissal removes the locator and rendered item; later sync does not restore it.
- Updated Add and Replace limit copy to say “other text files.”
- No CPU fallback, indexing/rebuild change, publication change, or R04 research was introduced.

## Live recovery execution

The candidate API ran in one process against a new isolated workspace. The sequence was:

1. Add a 92-byte text baseline: succeeded, revision 1 → 2, one active source.
2. Add the same content under another filename: terminal `document_invalid` / `document_identity_conflict`; revision stayed 2, the workspace stayed active, and the original source remained the only active source.
3. Add `the_book_of_shupe.pdf` (67,199,839 bytes; SHA-256 `1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54`): succeeded in the same API process, revision advanced to 3, source count became two.
4. `/health/ready` returned HTTP 200 after the sequence.

The API log contained the detached worker’s safe `AppError` classification and did not contain `Future exception was never retrieved`. Full sanitized operation and workspace facts are in [`live_recovery_evidence.json`](live_recovery_evidence.json).

The live sequence validates a managed failure followed by a valid large-PDF recovery add. It did not deliberately force a real CUDA OOM; OOM classification/recovery remains covered by the existing deterministic CUDA recovery tests, and publication code was not changed.

## Validation

- `pytest` capacity + bounded workspace path suites: **46 passed**.
- Dense failure observability + CUDA OOM recovery + detached-Future test: **33 passed**.
- Focused UI operation/recovery suites: **40 passed**.
- Targeted Ruff check: **passed**.
- Targeted ESLint on changed UI files: **passed**.
- `git diff --check`: **passed**.
- Full `tests/unit/app/test_slice16b_workspace_api.py` run exceeded its 45-second bounded run; its focused detached-Future test passed and the live managed-operation flow passed.
- Repository-wide UI lint and TypeScript checks still report existing errors in untouched Gold Lab and test-fixture files; targeted checks for changed UI files passed.
- `ruff format --check` reports pre-existing formatting differences in these legacy files; no broad formatting pass was applied.

## Limits and remaining gates

- Production limits and accepted profile policy remain unchanged except removal of the transient free-VRAM preflight threshold.
- No scientific campaign was run. No deliberate GPU OOM was induced.
- The test workspace `ws_65dee968958340cfb0a671eebfabc44f` is isolated and remains available for inspection.
- Candidate is ready for independent review. Human acceptance and promotion remain pending and unauthorized.
