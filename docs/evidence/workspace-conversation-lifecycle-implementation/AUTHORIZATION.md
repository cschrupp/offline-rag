# Seneca — Implement Workspace Conversation Lifecycle Ownership

## Independent design review

**Disposition:** Design direction accepted, with mandatory concurrency and terminalization requirements.

Reviewed commit:
`76fdf1984ad8b8a0c08893d74d75405f2f8d8625`

Canonical design:
`docs/evidence/workspace-conversation-lifecycle/DESIGN.md`

Repository: `cschrupp/offline-rag`

Authorize implementation and local verification of the workspace conversation lifecycle corrective only.

Do not merge, deploy, modify production defaults, run VM maintenance, or resume BGE Stage 2.

## 1. Establish implementation baseline

Inspect the current integration branch, code contracts, scientific identity constraints, and existing tests.

Preserve the independent status of draft PR #3 (length-sorted batching) and PR #4 (Engineering heading correction).

Create a dedicated lifecycle implementation branch from an explicitly recorded and appropriate application baseline.

Do not silently absorb unrelated research or corrective work.

## 2. Preserve conversation validation and binding

Refactor the workspace conversation turn into a reusable preparation phase and owned execution phase.

The preparation phase must preserve the existing order:

1. Validate prior-turn sequence and question.
2. Check runtime readiness.
3. Validate the active workspace.
4. Capture workspace revision and immutable snapshot ID.
5. Resolve and validate selected source scope.
6. Resolve scientific snapshot backing.
7. Transition into query admission and owned execution.

Perform each validation once.

Preserve the original request-invalid precedence over runtime-not-ready and capacity errors.

Do not re-read workspace state to upgrade the admitted snapshot after concurrent mutation.

Maintain direct app-layer caller compatibility and existing public response schemas.

## 3. Resolve preflight ownership

Implement a drain-aware ownership mechanism protecting preparation that accesses runtime-backed resources before query admission.

Requirements:

- No snapshot access against already-closed resources.
- No event-loop blocking on potentially slow preparation.
- No unbounded preflight accumulation.
- No admission after drain begins.
- Atomic, race-safe handoff between preflight ownership and the admitted query operation.
- Guaranteed ownership release on success, validation failure, disconnect, timeout and shutdown.
- Shutdown must account for active preflight work before closing resources.

Prefer a minimal registry-compatible mechanism. Do not add a new public operation type unless required.

Write deterministic race tests for preflight versus shutdown and admission versus drain.

If the existing registry architecture cannot support this safely without a larger contract change, stop and submit the precise conflict for independent review rather than introducing an improvised workaround.

## 4. Implement owned workspace execution

Use the existing shared query-capacity gate and `run_owned_worker` mechanism.

Preserve `max_concurrent_query=1` as the existing default.

The worker must:

- Own the same operation handle throughout the prepared conversation turn.
- Check cancellation/deadline at the specified cooperative boundaries.
- Participate in the shared admission limit alongside `/v1/query`.
- Retain capacity through native inference, cancellation, deadline expiry and shutdown until the underlying worker actually terminates.
- Release capacity exactly once.
- Preserve query snapshot and source bindings.
- Avoid duplicated scorer, generator or trace execution.

Do not implement an unapproved queue or change capacity defaults.

Do not claim a hard inference timeout: model forward and other blocking calls remain cooperative-cancellation boundaries.

## 5. Define terminalization precisely

Specify and implement the linearization point at which successful grounded execution becomes committed terminal evidence.

Synchronize that transition sufficiently to resolve races with disconnect, deadline and shutdown signals.

Before successful terminalization, a winning cancellation must not yield an answered trace.

After successful terminalization, transport disconnect alone must not fabricate a failed scientific result.

Preserve the existing successful grounded trace and conversation trace schemas, clarification semantics, source citation validation and persistence-error handling.

Do not invent a cancellation status in the conversation schema.

Distinguish these outcomes in internal evidence:

- Canceled before grounded trace allocation.
- Canceled after allocation but before terminalization.
- Successful grounded terminalization followed by conversation projection.
- Failed citation enrichment or trace persistence.
- Successful scientific completion with failed HTTP delivery.

Require no duplicate terminal records and no misleading answered result.

## 6. Execute deterministic regression suite

Include:

- Invalid question/prior turns versus unready runtime.
- Invalid scope/stale snapshot versus exhausted capacity.
- Successful first-turn response.
- Context-dependent follow-up and resolver path.
- Clarification without a grounded query trace.
- Shared capacity competition across `/v1/query` and workspace conversation.
- Two simultaneous workspace conversations.
- Client disconnect before reranking.
- Client disconnect during an intentionally held scorer.
- Deadline expiry during held inference, recognized at the next checkpoint.
- Shutdown during held inference, including beyond grace expiry.
- Preflight/shutdown and admit/drain races.
- Concurrent workspace revision or source mutation.
- Cancellation competing with terminal trace commit.
- Citation projection and trace persistence failures.
- Exact worker completion and capacity release.
- No worker resource closure while still borrowed.

Use deterministic barriers and controlled fake providers for unit tests. Use bounded real-loopback HTTP tests for transport behavior.

For the abandoned-worker regression, independently verify that a third valid request receives the established capacity-exhaustion response while the original disconnected worker remains in flight.

Only after that worker terminates may capacity become available again.

Run relevant backend regression suites, lint, formatting, compilation, and applicable hosted checks.

Do not weaken scientific or lifecycle assertions to make tests pass.

## 7. Keep other execution paths separate

Audit, but do not silently modify:

- Workspace single-turn `/query`.
- Workspace explicit `/conversation/action`.
- Managed `/v1/query`.

Record comparable ownership gaps for separate disposition.

The current corrective is specifically for `/v1/workspaces/{workspace_id}/conversation/turn`.

## 8. Evidence and delivery

Preserve the original unchanged-route HTTP baseline.

Produce:

- Exact source diff.
- Final operation-lifecycle diagram.
- Preflight ownership proof.
- Admission/drain race evidence.
- Cancellation/terminalization race evidence.
- Worker and capacity accounting tests.
- HTTP behavior and error mapping.
- Regression test results.
- Known limitations.
- Explicit proposed conditions for resuming CPU Stage 2.

Retain this authorization prompt and the complete Codex implementation response, including intermediate failures and corrective actions.

Commit and push the implementation, tests and evidence on a dedicated branch, then prepare a draft PR for independent review.

**Stop after the implementation review candidate. No production deployment, merge, BGE activation or VM campaign is authorized.**