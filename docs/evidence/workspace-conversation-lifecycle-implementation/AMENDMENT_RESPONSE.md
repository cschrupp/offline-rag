# Amendment implementation response

The dated [normative amendment](AMENDMENT_2026-11-22.md) records the
independent acceptance and preserves the original design history.
[Authorization and review disposition](AMENDMENT_AUTHORIZATION.md)

The existing lifecycle source already implements the amended contract.
The delta from `17816f4568ba85cf00229f0aaa97b26318e22f62` changes only
the ownership test file and adds amendment evidence. PR #5 stays draft
on the initialization integration branch. The independent frontend fix
remains in PR #4.

The imported reconciliation tests now require exact idle results for
unknown source (404), unknown workspace (404), unavailable snapshot
(409), and answered valid turn (200). With preflight held each returns
503 and the preflight-specific reason. The same held test proves
malformed history returns 422 and unready runtime returns the
runtime-not-ready response. Rejections create no scientific traces and
invoke no resolver, scorer or generator. Query-slot competition and
terminalization coverage remain intact.

Local focused ownership, conversation and query observability suites
passed 74 tests. The bounded loopback run passed held-worker capacity,
the cooperative deadline and shutdown past transport grace. It retains
the expected canceled transport case, distinct from worker termination.
The only warning in the focused run was the existing TestClient
deprecation. Ruff lint, format and Git whitespace checks passed.

## Prerequisites for a separate CPU Stage 2 authorization

- Final acceptance of the exact PR #5 head, including the normative
  precedence amendment. Resolve the shared integration CI disposition
  separately, retaining PR #4's isolated frontend repair and the known
  15F fixture debt as explicitly classified in the broader test evidence.
- Freeze and independently review one integrated diagnostic image with
  the approved lifecycle correction and the exact PR #3 batching code.
  Use the same route, workload identities and scientific configuration
  in both arms. Vary only batching strategy. Keep consecutive as the
  production default. Use a verified local provider fixture.
- Freeze the CPU, resource, per-submission and maintenance limits, the
  exact Recipes and Rich snapshot/source bindings, FP32 2/2 policy,
  checkpoint and frozen embedding profile. Verify isolated writable
  backing, exclusive Qdrant ownership, read-only models, disabled external
  networking, and capacity to execute and restore within the VM window.
- Explicitly authorize the bounded campaign. The plan allows 28 load
  submissions and eight lifecycle submissions, no retries. Require
  scientific/trace and lifecycle checks, report workloads separately,
  and verify restoration of health, original image, mounts, restart
  policy and both publications.

No merge, deployment, VM maintenance, activation or Stage 2 execution
occurred.

The amended five-suite run recorded 105 passes and eight failures.
The eight failed identities match the exact-parent 15F run
(`f2dd2bda1890fb86ddb055ef101c2e5e098eba43`). They remain failures caused
by stale fixture signatures in that lane. No legacy fixture was edited.
[Exact local results](AMENDMENT_RESULTS.txt)
