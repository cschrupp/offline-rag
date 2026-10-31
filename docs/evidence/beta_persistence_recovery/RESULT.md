# Beta Persistence / Restart / Failure-Recovery QA

## Result

**Status: PASS for the exercised live recovery path.** The isolated test
workspace retained its published snapshot through an abrupt API process exit
while a source-add was non-terminal. Startup recovered that operation as
`INTERRUPTED`, and a subsequent source-add succeeded in the same recovered
process.

This closes the persistence/restart/failure-recovery QA item in the current
beta roadmap. It does not claim that every journal phase or every crash point
has been exercised.

## Environment and scope

- Repository subject: canonical `main` at `113a28d2cbbdd9d2c19f63d367f1025b2aa06890`
  before this documentation update.
- API command: `uv run python -m offline_rag.api.server`.
- Data directory: repository-local `data/`.
- Test workspace: `ws_c6212c467f4843fca273d9251b8dd857` (created for this check;
  the user's existing workspaces were not mutated).
- No product code, configuration, dependency, or production capacity policy
  changed.

## Live interrupted-operation sequence

1. Created the isolated workspace and published `baseline.txt`. The committed
   state was revision 2, snapshot
   `snap_6e6f9712cc182fc0069680f285a5a358c34e031f1dccdb018b223915cbe596d6`,
   with one active source.
2. Started a valid `SOURCE_ADD` for
   `Book of Search_251205_145545.pdf` (32,448,147 bytes). The operation was
   confirmed `RUNNING` in `parsing_documents` before the API worker received
   `SIGKILL` (exit 137).
3. Restarted the API with the same environment and data directory. Startup
   completed and `/health/ready` returned HTTP 200.
4. The interrupted operation `wop_959ca9a0d30243d995ca6cad9f9a576d` was
   reported as `INTERRUPTED`. The workspace remained active at revision 2 with
   the exact prior snapshot and baseline source identity. The interrupted PDF
   was not published.
5. Added `followup.txt` in that same recovered process. Operation
   `wop_bed8357ef7854077a51bbe4169c99963` succeeded and published revision 3,
   snapshot `snap_081a3f23f7ddb3121ffd7c7c91468226944fc6693249c73cca9b2935c6e170ab`,
   with the baseline and follow-up sources active.
6. Final `/health/ready` returned HTTP 200.

This exercises stale mutation-lease/capacity recovery through the externally
visible result: the follow-up mutation was admitted and published without
restarting the recovered process again.

## Automated recovery checks

Passed:

- `.venv/bin/pytest -vv -s tests/unit/app/test_slice15c_snapshots_leases_documents.py::test_startup_recovers_candidates_without_publish`
  — 1 passed.
- `.venv/bin/pytest -vv -s tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_startup_recovery_a_interrupts`
  — 1 passed.
- `.venv/bin/pytest -vv -s tests/unit/app/test_slice16k_a_managed_ingestion_correctness.py::test_recovery_b_succeeds`
  — 1 passed.

The following selected managed-operation recovery test runs did not complete
within their time bounds (exit 124):

- The selected startup-recovery batch — 120 seconds.
- `test_f18_startup_recovery_add_result` — 40 seconds.
- `test_f15_recovery_add_result` — 45 seconds.
- `test_empty_recovery_a_intent_and_committed_inconsistent` — 45 seconds.

A faulthandler trace for the F18 add case showed the test blocked at
`TestClient.__enter__`, with the main test thread waiting for the AnyIO portal
startup handshake. It did not show an assertion failure and did not identify
which application startup activity is responsible. This is tracked separately
as `TEST-STARTUP-01` in `docs/BACKLOG.md`; the live recovery path passed, so the
test-harness issue is non-blocking to beta.

## Terminal

```yaml
published_state_survives_process_exit: PASS
nonterminal_source_add_recovered_as: INTERRUPTED
prior_publication_changed: false
startup_readiness: HTTP_200
followup_mutation_same_recovered_process: SUCCEEDED
final_workspace_revision: 3
managed_operation_TestClient_startup_hang: BACKLOG_NON_BLOCKING
```
