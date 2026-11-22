# Seneca — PR #5 Preflight Contract Reconciliation

## Independent review

Repository: `cschrupp/offline-rag`

Draft PR: [https://github.com/cschrupp/offline-rag/pull/5](https://github.com/cschrupp/offline-rag/pull/5)

Reviewed candidate:\
`17816f4568ba85cf00229f0aaa97b26318e22f62`

Disposition: REVISE — one compatibility conflict.

The principal lifecycle ownership implementation is accepted as a promising review candidate. No redesign of the entire mechanism is requested.

PR #5 must remain draft.

## Task 1 — Resolve preflight error precedence

Compare the accepted design at `76fdf1984ad8b8a0c08893d74d75405f2f8d8625` with the implemented `start_query_preflight()` contract.

The accepted design requires workspace/source/snapshot validation before new query-capacity errors.

The implementation introduces a distinct `query_preflight_capacity_exhausted` response before those validations.

Construct deterministic concurrent tests with the preflight limit saturated by a held request.

Submit a second request with:

- Invalid source scope.
- Unknown workspace.
- Incompatible or unavailable snapshot.
- Valid workspace and snapshot.

Record the exact observed error and precedence for each.

Classify the conflict explicitly.

Determine whether it can be resolved without sacrificing bounded preflight, drain ownership, or the already-established validation behavior.

If preserving all requirements is impossible within the approved implementation boundary, submit a narrowly scoped contract amendment with alternatives and a recommendation.

Do not silently redefine accepted error precedence or weaken existing assertions.

## Task 2 — Recheck terminalization invariants

Preserve the synchronized terminal claim.

Verify races involving:

- Disconnect before successful terminal claim.
- Deadline before successful terminal claim.
- Shutdown before successful terminal claim.
- Disconnect after successful claim but before persistence completes.
- Persistence failure after claim.
- Clarification-only conversation trace.
- Grounded trace committed but conversation projection failed.

Distinguish a committed scientific result from successful HTTP delivery.

Verify no false successful terminal records, duplicate trace commits, or prematurely released query capacity.

Review the opt-in repeated-cancellation behavior in `run_owned_worker()` for unwanted effects on the existing managed query route.

## Task 3 — Integration evidence

Rerun affected deterministic tests and bounded loopback tests.

Verify that the shared query gate remains authoritative and that an abandoned worker continues holding capacity until actual termination.

Confirm exact parent-versus-candidate classification of the eight existing 15F fixture failures.

Do not modify those legacy fixtures merely to turn the candidate test summary green.

Retain the independent frontend correction in PR #4.

## Delivery

Update PR #5 with a narrowly scoped corrective commit if the conflict can be resolved under the accepted contract.

Retain the original implementation evidence.

Record the full authorization and Codex response, modified files, tests, failures, and final compatibility assessment.

Report whether the correction is:

- Fully contract-compatible.
- Compatible only with an explicit contract amendment.
- Blocked by an unresolved design conflict.

Do not run Stage 2, change batching defaults, merge, deploy, or perform VM maintenance.

Stop for independent review.
