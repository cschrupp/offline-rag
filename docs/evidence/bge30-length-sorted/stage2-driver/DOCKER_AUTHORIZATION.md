# Seneca — Complete Stage 2 Driver and Restoration Qualification

## Independent review decision

**Accept the partial Stage 2 driver preparation at:**

`31432d61fd6aed840047028589c46448859af8a4`

Retain the accepted integrated application source:

`1f79eca0e30eb1afb79a5aa9bb0dcff5f0ac2e0e`

Diagnostic image identity:

`sha256:669932995e62fa53616fbfe0551c442077caa0496f86fba49d5f4a1ba6f48d04`

The existing scheduler, image verification, and negative host-preflight results are accepted as local evidence.

**The 36-submission VM experiment remains unauthorized.**

## Task A — Implement the real Docker/HTTP adapter

Complete the adapter required by `stage2-driver/driver.py`.

It must use the existing workspace conversation HTTP route, not substitute the managed query endpoint.

Provide real implementations of:

- `open(strategy)`
- `submit(case, timeout)`
- `abort()`
- `close()`

Require deterministic identification of the diagnostic session and container.

For every submission, correlate:

- Client ordinal and actual socket send.
- HTTP response or transport termination.
- Server operation identity and admission decision.
- Scientific query and conversation trace identities.
- Terminal outcome.
- Underlying worker completion.
- Actual query-slot release.

Do not treat HTTP completion, disconnect or timeout as evidence that the worker terminated.

Reject missing, contradictory or duplicate correlation records.

Do not weaken the existing validation assertions to accommodate incomplete observations.

## Task B — Prove independent container termination

Extend the watchdog and adapter so that an external timeout or memory-limit breach causes a bounded, deterministic abort.

Require:

1. Stop all new submissions.
2. Identify only the authorized diagnostic container.
3. Request graceful termination.
4. Escalate to forced termination if necessary.
5. Confirm the container has actually exited.
6. Confirm no diagnostic process retains the scratch Qdrant backing.
7. Preserve attempted-submission evidence.
8. Invoke independent restoration.
9. Verify the original service before declaring restoration successful.

The watchdog must remain effective if the driver crashes, hangs, loses its HTTP connection, or is forcibly terminated.

Killing the Docker client process alone is insufficient.

Exercise those failures during the local synthetic rehearsal.

## Task C — Complete lifecycle-driver integration

Connect the forward observer and lifecycle barriers to the approved diagnostic route.

Preserve actual model inputs, outputs, candidate ordering, scoring semantics and scientific fingerprints.

Test the four approved lifecycle cases for both strategies:

- Disconnect before reranking.
- Disconnect during held inference.
- Cooperative deadline recognized after inference returns.
- Shutdown drain beyond transport grace.

Ensure barrier timing does not contaminate ordinary load-performance measurements. Report injected hold time separately.

For the final VM protocol retain the 180-second server deadline and 195-second client watchdog.

Use accelerated deterministic fixtures for local testing only where their limitations are explicit.

Do not claim that a locally accelerated timeout proves the native 180-second case.

## Task D — Full local synthetic rehearsal

Execute the complete scheduler through the real adapter against a disposable local Docker application with synthetic backing and controlled fake inference.

Require:

- Exactly 28 load and eight lifecycle submissions.
- Zero retries.
- Both strategies exercised.
- Correct 1/2/4-client wave behavior.
- Complete request-to-operation correlation.
- Distinct preflight and query-capacity rejection reasons.
- Exact scientific trace accounting.
- Cancellation and deadline truthfulness.
- Worker ownership until actual return.
- Bounded watchdog behavior.
- Full container cleanup.
- Verified restoration of a disposable baseline service.

Inject at least one failure each for missing terminal evidence, forced adapter termination, container nonresponsiveness, and incomplete restoration.

Every failed rehearsal must fail closed, without a success summary.

Retain the complete raw observations, not just aggregate PASS results.

## Task E — Finalize read-only host verification

Prepare a credential-free, sanitized settings manifest that represents the actual scientific configuration.

Do not print or commit secrets.

Verify that the image receives the expected settings through its existing supported configuration path, without introducing a second configuration implementation.

The read-only host preflight must confirm:

- Exact approved OCI image and offline archive identities.
- Both frozen workspace and snapshot bindings.
- Recipes' exact logical source scope.
- Rich's sole-document scope.
- Complete immutable publication backing.
- Pinned model and tokenizer digests.
- Frozen ONNX representation.
- Four effective CPUs and prescribed Torch/ONNX policies.
- Non-Docker as well as Docker scratch-storage ownership.
- Sufficient memory, disk and restoration time.
- No active conflicting operation or experiment.

Allow read-only host inspection only after the local adapter rehearsal passes. It must not stop, restart, or replace the original service, open live Qdrant for concurrent access, or perform experimental queries.

If any gate cannot be verified without modifying production state, stop and return for review.

## Task F — Deliver the final execution-readiness evidence

Provide the exact:

- Driver revision and Git commit.
- Real Docker/HTTP adapter code.
- Successful complete synthetic rehearsal.
- Failure-injection and recovery evidence.
- Independent watchdog test results.
- Container-exit and storage-release proof.
- Sanitized effective-settings comparison.
- Host preflight outcome, if authorized and completed.
- Remaining limitations.
- Proposed single-window 36-submission execution authority.

Preserve this authorization and the complete Codex response.

Keep all PRs in draft and all production configuration unchanged.

Do not merge, deploy, enable sorted-eight, perform maintenance or execute native Stage 2 workloads.

**Stop at the final driver qualification checkpoint.**