#

# PRIORITY — Seneca Cross-Workspace Query Failure

**Incident:** Seneca is no longer returning answers through the UI, including a one-source workspace.

**Priority:** Restore end-to-end functionality before further performance work.

Repository: `cschrupp/offline-rag`

Deployed application: `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`

Latest batching evidence: `cf6dab622be22305f96883fa2465619e77bbd835`

## Observed failure

Workspace: `workspace R-01`

Workspace revision: 2

Selected source: `source R-01`

Source size: approximately 58 KiB, 16 PDF pages.

Question: `Describe the naturalistic decision method`

The UI remains at `Searching your selected sources…` and subsequently times out without providing an answer.

The user reports that other workspaces have also stopped answering, whereas the application previously worked.

## Task 1 — Establish the actual failure boundary

Use read-only VM and container diagnostics first.

Correlate the failing UI attempt with:

- Container logs and server access logs.
- Query and conversation traces.
- Request admission and completion.
- CPU, memory, swap and active operations.
- Docker uptime, restart history and image identity.
- VM STOP events and the 7,200-second shutdown policy.
- Reverse-proxy timeouts and connection-close events.

Determine whether the POST to `/v1/workspaces/{workspace_id}/conversation/turn`:

1. Reached the backend.
2. Entered retrieval.
3. Entered BGE reranking.
4. Completed context assembly.
5. Reached generation.
6. Returned a response or failed.
7. Continued executing after the browser connection closed.

Identify the observed HTTP response status and request duration when available.

Do not infer a timeout cause from the UI's pending message alone.

## Task 2 — Inspect the tiny-source workload

Using the existing workspace and source metadata, determine the number of eligible passages and the expected BGE candidate count.

Do not assume a small PDF produces a small reranking workload.

Compare the request with existing Recipes traces, but keep their snapshot identities separate.

## Task 3 — Investigate effective generation configuration

Read the safe, non-secret effective generation settings.

Check:

- Enabled state.
- Selected provider and model.
- Endpoint and model authorization.
- Configured generation timeout.
- Credential presence as a boolean only.
- Provider readiness using the existing non-generative probe.
- Any change in effective configuration after restart.
- Existing provider failure and `model_abstain` records.

Never print API keys or private provider response bodies.

Do not change model, endpoint, or credentials.

## Task 4 — Examine HTTP request lifetime

Inspect the deployed HTTP serving configuration, any reverse proxy, and relevant connection timeouts.

The frontend uses `fetch()` for conversation turns and does not automatically retry failed submissions.

Determine whether a backend request can continue after the browser or proxy has terminated its connection.

Compare request termination timestamps with backend trace completion timestamps.

## Task 5 — Produce a root-cause report

Classify the incident as one of:

- Transport/proxy timeout.
- Slow or blocked retrieval execution.
- Generation/provider failure.
- Runtime configuration or restart regression.
- Query admission/resource exhaustion.
- Other, with supporting evidence.
- Inconclusive.

Report the smallest justified corrective intervention, with validation and rollback requirements.

If existing traces are insufficient, propose exactly one controlled end-to-end query using the known workspace, preserving source scope and recording both client and server timings. **Do not execute it without separate authorization.**

## Restrictions

Read-only diagnosis only.

No container restart, deployment, configuration edits, model changes, workspace mutation, new ingestion, experimental inference or repeated query submissions.

Do not merge the batching experiment or alter the frozen scientific configuration.

Retain this full authorization prompt and Codex's response as separate incident evidence.

**Stop after the diagnosis and corrective recommendation.&#x20;**

# Incident Update — Intermittent Timeouts, Not Total Failure

A new observation changes the incident classification.

The previously failing question, "Describe the naturalistic decision method," eventually returned a valid `answered` response with citations in workspace R-01.

Therefore, the end-to-end query path is demonstrably functional at least some of the time.

**Reframe the incident as excessive query latency with intermittent timeouts.**

Continue the authorized read-only investigation, prioritizing:

1. Correlate successful and failed conversation-turn requests with their HTTP status, elapsed time, query traces and server-side completion status.
2. Determine whether failed requests cluster around a specific duration, such as 60, 90 or 120 seconds. Inspect actual reverse-proxy and server timeouts; do not assume a value.
3. Check whether server-side work continues after client or proxy disconnection.
4. Identify BGE candidate count, actual retrieval latency, model-warming state and concurrent request load for the small-source workspace.
5. Check whether requests overlap, saturate CPU resources or exhaust query admission capacity.
6. Compare successful versus timed-out attempts to determine whether their differences arise in retrieval, generation or transport.
7. Check the VM lifecycle and container restoration history for correlation with failures.

Use existing logs and traces first. Do not submit repeated diagnostic questions.

Keep the finding that OpenRouter generation and response rendering succeeded at least once. Do not classify generation as universally unavailable.

Do not change production settings or deploy sorted-eight batching as an incident workaround without its separate review and promotion process.

Report the observed failure boundary and propose the smallest justified corrective action.
