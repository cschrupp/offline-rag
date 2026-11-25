# Seneca — Adopt Preflight Contract Amendment and Finalize PR #5

## Independent review disposition

**Decision: ACCEPT the proposed narrow preflight error-precedence amendment.**

Reviewed evidence:\
`f2e02a235608330b850c3fb2943af4673718ceaa`

Lifecycle implementation:\
`17816f4568ba85cf00229f0aaa97b26318e22f62`

Draft PR:\
[https://github.com/cschrupp/offline-rag/pull/5](https://github.com/cschrupp/offline-rag/pull/5)

The reviewer accepts bounded preflight admission as the authoritative protection boundary.

This approval replaces only the conflicting precedence requirement in the original design at `76fdf198`.

Do not treat it as approval to merge or deploy.

## 1. Record the precise contract amendment

Create an explicitly dated, append-only amendment decision referencing:

- Original design `76fdf198`.
- PR #5 implementation `17816f45`.
- Reconciliation evidence `f2e02a23`.
- The independent review decision supplied in this authorization.

Do not backdate the decision or rewrite historical evidence as though the amended contract had always applied.

Normative contract:

1. Validate HTTP request shape, prior-turn sequence and question before admission.
2. Check runtime readiness.
3. Attempt admission to the bounded, drain-aware preflight registry.
4. If the guard is exhausted, return the established HTTP 503 service-overloaded response with reason `query_preflight_capacity_exhausted`.
5. When preflight is admitted, preserve workspace, source-scope and snapshot-backing validation semantics.
6. Only after successful preparation may the shared execution gate return `query_capacity_exhausted`.
7. Preserve immutable snapshot binding and the existing owned-worker lifecycle.
8. Allocate no scientific execution trace for a request rejected before execution begins.

The preflight-overload outcome explicitly takes precedence over workspace, source and snapshot validation errors when the guard is full.

Do not extend this amendment to other endpoints.

## 2. Integrate the reconciliation tests

Bring the approved tests from `f2e02a23` into PR #5's implementation branch without incorporating unrelated changes.

Strengthen the regression assertions to require the exact idle-preflight outcomes:

| Input                | Required result when guard is available |
| -------------------- | --------------------------------------- |
| Invalid source scope | 404 `source_unknown`                    |
| Unknown workspace    | 404 `workspace_unknown`                 |
| Unavailable snapshot | 409 `snapshot_unavailable`              |
| Valid request        | 200 `answered`                          |

When the preflight guard is held, all four must instead produce HTTP 503 with `query_preflight_capacity_exhausted`.

Add explicit contention tests proving that malformed conversation history still wins over preflight saturation, and runtime-not-ready is not silently mapped to overload.

Assert that rejected requests allocate no scientific traces or reach the resolver, scorer or generator.

## 3. Preserve lifecycle correctness

Retain the existing tests proving:

- Preflight ownership through shutdown.
- Atomic promotion into the shared query slot.
- Cross-route query-capacity competition.
- Cancellation before and after terminal claim.
- Successful terminal persistence after disconnect.
- Failure handling for trace writes and citation projection.
- Capacity retention after repeated transport cancellation.
- Cooperative deadline enforcement.
- Resource preservation beyond transport shutdown grace.

Do not change the current lifecycle implementation unless a regression exposes a concrete defect.

## 4. Reconcile integration evidence

Run focused ownership tests, conversation regressions, bounded loopback tests, and applicable backend CI.

Preserve the eight known parent-reproducible 15F failures as separately classified baseline debt. Do not silently waive them as successful tests.

Keep the independent frontend assertion correction in PR #4.

Ensure the updated PR #5 head contains the final normative amendment and tests. Record the new commit SHA and hosted CI status.

## 5. Delivery

Retain:

- Full authorization prompt.
- Independent review disposition.
- Amendment decision and provenance.
- Exact updated test results.
- Complete Codex implementation response.
- Any unresolved release blockers.

Commit and push the amendment and test updates to the PR #5 implementation branch.

Do not merge, deploy, alter batching defaults, or execute a VM campaign.

Return the revised PR for final acceptance and provide the exact prerequisites for separately authorizing CPU Stage 2.

**Stop at the amended PR #5 review checkpoint.**
