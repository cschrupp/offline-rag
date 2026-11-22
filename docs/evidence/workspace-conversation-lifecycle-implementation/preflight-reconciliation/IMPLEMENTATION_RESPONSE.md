# Preflight reconciliation

**Compatible only with an explicit contract amendment. Hold PR #5.**
The reviewed production source is unchanged at `17816f45`.
The accepted design at `76fdf198` puts workspace, source and snapshot
validation ahead of new query-capacity errors. The current handler
validates turn shape and checks readiness, then calls
`start_query_preflight()` before it performs those three validations.
The early 503 is distinguishable from shared query-slot exhaustion,
but still hides the validation result. This is an observable compatibility
conflict, even though it requires preflight saturation.

## Deterministic HTTP reproduction

A first valid request was held in snapshot resolution with a threading
event. Each second request was submitted while the guard was still
occupied. The resolver was invoked exactly once throughout this phase.
The same inputs were replayed with the guard idle. Snapshot failure was
injected only at the real backing-resolution boundary.

| Input | Held preflight | Idle preflight |
| --- | --- | --- |
| Invalid source scope | 503 service_overloaded, query_preflight_capacity_exhausted | 404 source_unknown |
| Unknown workspace | 503 service_overloaded, query_preflight_capacity_exhausted | 404 workspace_unknown |
| Unavailable snapshot | 503 service_overloaded, query_preflight_capacity_exhausted | 409 snapshot_unavailable |
| Valid workspace and snapshot | 503 service_overloaded, query_preflight_capacity_exhausted | 200 answered |

Once a preflight is admitted, existing validation errors still precede
shared query-slot exhaustion. The existing scope and stale-snapshot
assertions are preserved. The held-request test characterizes the
current conflict and should be revised if a different boundary is approved.

## Proposed amendment for independent review

Permit the existing retryable 503 with reason
`query_preflight_capacity_exhausted` only when the protected preflight
guard is full. Its precedence is **after request shape/sequence, question
and readiness checks, before workspace/source/snapshot preparation**.
When a preflight guard is available, keep the accepted order and do not
return `query_capacity_exhausted` until workspace, scope and snapshot
backing validation succeeds. Keep the current bounds and shared execution
gate. Admission or rejection at either bound allocates no scientific
trace until execution begins. This is the smallest amendment that
preserves a drain-safe bound and an immediate overload response.

Moving cheap workspace and scope checks ahead of the guard would narrow
the exception but still mask dynamic snapshot-backing errors under
saturation. It would also require careful ownership or capture of that
stage to preserve race behavior. A finite wait queue only postpones the
same precedence exception to its overflow or timeout and changes latency
and admission policy. Unbounded waiting or overflow backing validation
violates the resource bound, and backing checks outside drain ownership
risk using closed resources. The current contract cannot guarantee both
immediate bounded rejection and a prior answer from a backing check
that cannot safely start. No amendment has been adopted in this revision.

## Terminal and ownership review

- A pre-claim disconnect, expired deadline or drain produces a single
  grounded error record after allocation and no conversation success.
  The connected synthetic disconnect uses the existing 500 projection
  for a non-HTTP terminal code; the deadline returns 504.
- A disconnect injected immediately after the claim and before persistence
  leaves one grounded success and one conversation record. The test
  establishes scientific outcome; it does not prove HTTP delivery to a
  disconnected socket.
- A grounded write failure after claim produces one write attempt, no
  answered record or conversation record, and HTTP 500. A separate
  admission probe still sees the shared slot occupied inside the write.
- The clarification test writes a conversation-only trace. Failure in
  citation enrichment or conversation persistence leaves one truthful
  grounded record and HTTP 500, without a conversation success.
- Three cancellations of the workspace transport task left capacity
  occupied until the held worker returned. Loopback independently
  reproduced 503 for contenders while a disconnected worker was held,
  and confirmed shared capacity with managed query, cooperative timeout,
  and resource retention past Uvicorn transport grace. The managed route
  does not select the opt-in repeated-cancellation path. Its default
  worker branch was unchanged in this reconciliation.

## Verification and delivery

Focused ownership tests: 17 passed. The five-suite run before the final
repeat-cancel fixture had 104 passed and eight legacy 15F failures. The
exact parent `f2dd2bda1890fb86ddb055ef101c2e5e098eba43` had 14 passed
and the same eight failures in 15F. Both fail on stale fixture signatures
such as an unexpected `retrieval_question` argument. The test identities
were compared mechanically. No legacy fixture was changed.

Run `pytest -q -s tests/unit/app/test_workspace_turn_ownership.py`
with the local provisioned tokenizer. The five-suite check additionally
runs `test_slice16d_b3_conversation.py`,
`test_query_failure_observability.py`,
`test_slice15f_admission_deadlines_shutdown.py`, and
`test_slice15c_snapshots_leases_documents.py` in the same directory.
The bounded loopback command and original evidence remain in the
parent evidence directory. Ruff and Git whitespace checks passed.

Only ownership tests and this evidence package are added on a separate
review branch. PR #5 remains draft at its original production candidate.
PR #4 remains separate. No Stage 2, VM maintenance, default change,
deployment or merge was performed.
