# Seneca — One-Shot Browser-to-Server Request Qualification

**Disposition:** Read-only incident diagnosis accepted. Authorize exactly one controlled browser query, with correlated client and server observations.

Repository: `cschrupp/offline-rag`

Deployed application baseline: `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`

## 1. Objective

Determine whether an isolated Seneca workspace conversation request completes successfully at the HTTP transport boundary and identify where its latency is incurred.

Do not perform corrective implementation during this experiment.

## 2. Fixed request identity

Workspace: workspace R-01

Revision: 2

Snapshot: `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`

Question: `Describe the naturalistic decision method`

Source scope: all-active, one document.

Prior conversation turns: empty list.

Use the existing browser UI and deployed application, with no modifications to scientific settings.

## 3. Preflight

Before submitting the question:

- Verify the expected deployment image, VM status, container identity and health.
- Verify workspace revision and snapshot.
- Verify sufficient time remains before automatic VM shutdown.
- Confirm no active user requests, competing diagnostics or performance experiments.
- Establish the current query-admission, CPU and memory state.
- Confirm logs and trace storage can be read without exposing credentials or document content.

If the system is not idle, stable and correctly identified, do not execute.

## 4. Browser observation

Coordinate with the operator to prepare Firefox Developer Tools before the request.

Use a fresh conversation so `prior_turns` is empty.

Enable Network log preservation and capture the single `conversation/turn` POST.

Record:

- Browser-side UTC request initiation time.
- HTTP status or network failure classification.
- Time to first response byte, if available.
- Request completion or failure time.
- Total elapsed time.
- Relevant network timing phases.
- Whether the UI displayed an answer with citations.
- Whether the UI remained pending or displayed a transport error.

The operator must submit the question exactly once.

No automatic or manual resubmission is authorized, even if the first attempt appears stalled.

Do not retain request payloads, authorization headers or private document content in published evidence.

## 5. Server observation

During the same single request, correlate:

- Request admission timestamp.
- Workspace and snapshot identity.
- Conversation trace ID.
- Query trace ID.
- Context retrieval and assembly time.
- Generation time.
- Terminal status and citation count.
- HTTP response completion, if observable.
- Client disconnect or transport-close event, if observable.
- Process and host CPU utilization at regular intervals.
- RSS, available memory and swap activity.
- Concurrent request count.

Use existing diagnostics and non-invasive operating-system observations.

Do not restart or redeploy the service, change code, or enable payload-level network capture.

Distinguish absence of an HTTP access entry from affirmative evidence of a disconnect.

## 6. Analysis and decision

Classify the outcome.

**A — HTTP 200, answer rendered:** Transport works for this isolated request. Assess whether unacceptable isolated retrieval time remains and whether previous overlap amplified latency.

**B — Backend answered, browser failed:** Investigate the exact observed transport-close boundary and request lifecycle before proposing a server correction.

**C — Backend did not finish:** Identify the blocking or failed execution stage, supported by available trace and resource evidence.

**D — HTTP error:** Report the precise error classification and responsible stage.

Do not claim concurrency causality from this one idle request.

If deeper stage timings remain unavailable, specify the minimum additional diagnostic needed to separate dense retrieval and BGE cost.

## 7. Candidate corrective design — analysis only

Review whether the workspace conversation route should adopt the existing `run_owned_worker()` infrastructure used by `/v1/query`.

Assess:

- Admission capacity and overload handling.
- Safe disconnect signaling.
- Capacity ownership until actual worker completion.
- Cooperative cancellation limitations during PyTorch forward passes.
- Query deadline behavior.
- Immutable workspace snapshot binding.
- Conversation and query trace compatibility.
- Successful cited-answer rendering.
- Regression tests and rollback.

Do not implement this design during the present authorization.

## 8. Deliverables

Produce a separate incident report containing:

1. Complete correlated client/server timeline.
2. Observed outcome and failure classification.
3. Retrieval-versus-generation latency.
4. CPU and memory observations.
5. Confirmed facts versus remaining hypotheses.
6. Recommendation for the smallest corrective change.
7. Proposed validation and rollback plan.

Retain the complete authorization prompt, Codex response and redacted evidence.

**Exactly one browser conversation turn is authorized. No production code changes, additional queries, or deployment changes are authorized.**

Stop after the report.