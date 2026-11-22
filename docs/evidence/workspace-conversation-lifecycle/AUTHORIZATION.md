# Seneca — Workspace Conversation Lifecycle Contract Reconciliation

## Independent review disposition

Accept Stage 2 preflight stop and credential remediation at:

`37e78228ad9c39c09a06698c4ca14ddd95eab66f`

Zero Stage 2 campaign submissions occurred. No production behavior changed.

**New priority:** Resolve the workspace conversation lifecycle contract before resuming the CPU batching HTTP qualification.

PR #3 remains draft. BGE-30 consecutive remains the production default.

## 1. Establish the exact current contract

Inspect the current source and tests governing:

- `src/offline_rag/api/workspaces.py`
- `src/offline_rag/app/conversation/turn.py`
- `src/offline_rag/app/query.py`
- `src/offline_rag/api/query.py`
- `src/offline_rag/api/workers.py`
- `src/offline_rag/app/operations.py`
- `src/offline_rag/app/runtime.py`
- Existing conversation validation, trace, admission and shutdown tests.

Produce a source-referenced lifecycle map from HTTP arrival through input validation, readiness, workspace and snapshot binding, resolver, reranking, generation, trace persistence and response delivery.

Explicitly identify which stages are owned by the operation registry and which are not.

Preserve the accepted A2-D05b validation and immutable-snapshot semantics.

## 2. Characterize the unchanged route

Develop bounded, isolated HTTP integration tests against the **existing** workspace conversation route.

Do not modify the handler, inject an operation handle, monkeypatch its lifecycle to appear safer, or substitute `/v1/query`.

Use a real local ASGI server for transport-disconnect observations, with controlled non-generative provider fixtures and external process-level safety limits.

Determine the actual behavior for a normal request, competing requests, client disconnect during a held worker, and shutdown while work is active.

Distinguish HTTP response termination from actual worker termination.

Report the absence of server-side deadline enforcement as an existing contract limitation, not as a successful deadline test.

Do not execute unbounded or potentially destructive shutdown experiments. Keep the current investigation local and isolated.

## 3. Design the lifecycle corrective

Propose the smallest contract-consistent correction that gives workspace conversation requests:

- Bounded query-capacity admission.
- An owned worker whose lifetime remains tracked through completion.
- Cooperative cancellation and deadline checkpoints.
- Disconnect signaling and truthful terminal outcomes.
- Shutdown drain participation without premature resource release.
- Preserved request-validation and error precedence.
- Preserved workspace revision, source scope and immutable snapshot binding.
- Preserved conversation and grounded-query trace semantics.
- No duplicate terminal records or falsely completed answers.

The design must address where admission occurs relative to input validation, readiness, source-scope validation and snapshot binding.

Do not insert admission before validation merely for implementation convenience.

Document whether capacity should be shared with `/v1/query`, what happens when it is exhausted, and how simultaneous workspace conversations are rejected or serialized.

Preserve existing HTTP request/response schemas unless a separately authorized contract revision is unavoidable.

## 4. Define a precise lifecycle test matrix

Specify deterministic tests for the current and proposed behaviors, including invalid request precedence, overload, disconnect before and during reranking, deadline recognition at checkpoints, shutdown during inference, thread completion, slot release, immutable bindings and trace persistence.

Distinguish cooperative deadline recognition from a hard wall-clock execution limit.

Require independent evidence that no second request acquires reserved capacity while an abandoned first worker still runs.

Assess whether existing conversation actions and workspace query endpoints have comparable uncovered lifecycle risks. Record them separately; do not expand the corrective scope silently.

## 5. Keep batching qualification independent

Preserve Stage 1 results:

Recipes: 44.15% paired median assembler improvement and exact scientific parity.

Rich: parity passed, performance screen missed, 45.731-second outlier retained.

Once a lifecycle correction is independently accepted, Stage 2 should compare both batching strategies **on the same corrected route**.

Do not use lifecycle modifications in only one arm.

Do not introduce BGE-15, a runtime workload selector, new precision settings or a new checkpoint.

## 6. Deliverable and stop gate

Produce a reviewable design with:

- Current versus proposed lifecycle diagrams.
- Identified contract conflicts and compatibility decisions.
- The smallest proposed implementation boundary.
- A reproducible unchanged-route baseline characterization.
- A regression-test plan.
- An updated bounded Stage 2 protocol.
- Exact implementation authorization proposed for the next step.

Preserve the complete authorization prompt and Codex response in the repository.

Commit and push the design and local evidence on a dedicated reviewable branch.

**Do not deploy, merge, execute a VM maintenance campaign or change production behavior. Stop at the lifecycle design checkpoint.**