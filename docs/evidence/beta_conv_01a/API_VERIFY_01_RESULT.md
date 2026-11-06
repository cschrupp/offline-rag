# BETA-CONV-01A API VERIFY-01 — Result

## Current disposition

```yaml
review: API_VERIFY_01_IR-001
reviewed_subject: 5b165d4bc796a5d5a51a3fa6084d744a20903f50
independent_review: ACCEPT
human_acceptance: ACCEPTED
api_verification: COMPLETE
planner_model_evaluation: NOT_AUTHORIZED
planner_activation: NOT_AUTHORIZED
implementation_promotion: NOT_AUTHORIZED
```

The original execution handoff below remains as historical provenance. Human
acceptance applies to API VERIFY-01 and does not authorize planner model
evaluation, activation, or promotion.

## Historical execution record

**Execution disposition at handoff:** HTTP verification executed; stop for independent review.

**Starting subject:** `170ccd4fd149b23755262fdd879a927676109666`

**Accepted implementation preserved:**
`e243c4d34d8d784ea6b1b67ebfc8088fb129f988`

**Scope:** canonical FastAPI inventory, TestClient diagnosis, and bounded HTTP
conversation regressions. No production code, dependency, planner activation,
model evaluation, or promotion change was made.

## FastAPI pipeline inventory

Repository inspection found one production `FastAPI(...)` construction in
`src/offline_rag/api/app.py`, exposed through the existing `create_app()`
factory. The conversation route is registered once at
`POST /v1/workspaces/{workspace_id}/conversation/turn` in
`src/offline_rag/api/workspaces.py` and uses the existing controller, workspace
admission, snapshot binding, retrieval, transformation, and trace paths.

No second production application or duplicate conversation pipeline exists in
the repository, so nothing was removed. The minimal FastAPI app used in the
earlier diagnosis was a disposable external diagnostic, not a Seneca component.
Existing `httpx.ASGITransport` cases in ingestion/query/admission tests cover
in-loop concurrency and cancellation situations against the same canonical app;
they do not define another maintained HTTP-testing architecture.

## TestClient diagnosis

The documented runtime versions were inspected: Python 3.14.5, FastAPI
0.142.2, Starlette 1.7.0, HTTPX 0.28.1, and AnyIO 4.15.1.

Inside this execution sandbox, an isolated minimal FastAPI `TestClient` also
stalled. Ordinary threads and direct ASGI lifespan startup worked, but a
cross-thread asyncio event-loop wake attempted to write to its wake socket and
received `PermissionError: [Errno 1] Operation not permitted`. The callback
remained queued while the selector was not woken, which left AnyIO's portal
call waiting. This reproduces the failure without Seneca startup code and
identifies the sandbox restriction as the cause of the observed stall.

The same minimal TestClient request, cross-thread callback, and Seneca
TestClient conversation suite were then run outside the sandbox. They
completed successfully. This is evidence against a Seneca startup or dependency
failure; no fixture lifecycle, dependency, or production startup change was
justified. Starlette emitted its existing HTTPX TestClient deprecation warning;
no migration was made as part of this scope.

This finding is specific to the sandbox event-loop wake restriction. It does
not resolve the separately tracked managed-operation recovery test startup
hang (`TEST-STARTUP-01`).

## HTTP regression coverage

The canonical existing `TestClient` suite now exercises planner mode through
the actual conversation route, with deterministic fake provider responses and
the normal application admission and response-validation path. Added route
coverage verifies:

- legacy mode preserves the resolver path and does not invoke the planner;
- grounded planner requests preserve the selected source set and admitted
  snapshot, return citations tied to the selected source, and persist linked
  conversation/query traces;
- current-message and prior-assistant transforms preserve the exact validated
  target, avoid retrieval and citations, and return the transformation
  provenance fields;
- a reference to an unselected source returns a safe clarification without
  retrieval and records rejected source-reference validation;
- malformed planner output returns a safe clarification without legacy
  fallback, retrieval, or a second model interpretation call;
- request parsing/readiness ordering, workspace/source admission, snapshot
  binding, grounded response, clarification, and trace contracts remain covered
  by the existing route tests.

Cancellation before planner execution and provider failure are covered by the
existing planner/controller tests; they are not claimed as new HTTP-cancellation
route tests. External model responses and scientific resources are faked; no
live model or scientific experiment was run.

## Validation performed

The relevant bounded Python suite completed under an explicit 60-second
faulthandler timeout:

```text
.venv/bin/python -m pytest -q -o faulthandler_timeout=60 \
  tests/unit/app/test_beta_conv_01a_planner.py \
  tests/unit/app/test_beta_conv_01_intent.py \
  tests/unit/app/test_slice16d_b3_conversation.py
135 passed, 1 warning
```

The five newly added HTTP-level planner scenarios (including the two transform
parameter cases) also completed as a focused selection: `5 passed`.

Conversation UI tests completed:

```text
npm test -- --run src/test/beta_conv_01_intent.test.tsx \
  src/test/slice16d_b3_conversation.test.tsx
21 passed across 2 files
```

`npm run typecheck` remains blocked by five existing diagnostics in the
out-of-scope `ui/src/test/slice16k_r04_cuda_oom.test.tsx` fixture (three missing
`operation_id` fields and two missing `retryable` fields). That file was not
modified.

Targeted Ruff lint passes for the changed Python test file. Four unused local
bindings present in the base file were marked unused; a fifth binding is now
used to assert the legacy router mode explicitly. Ruff's
`format --check` still reports formatting drift that is already present at the
starting commit; the file was not globally reformatted to avoid mixing broad
format-only changes into this test addition.

`git diff --check` passed for the candidate before commit.

## Final boundaries

```yaml
canonical_fastapi_pipeline: ONE
duplicate_pipeline_found: false
canonical_http_tests: EXECUTED
testclient_sandbox_stall: SANDBOX_WAKE_SOCKET_PERMISSION_DENIAL
seneca_testclient_outside_sandbox: PASS
conversation_python_suite: 135_PASS
conversation_ui_suite: 21_PASS
typescript_typecheck: 5_PREEXISTING_OUT_OF_SCOPE_ERRORS
planner_model_evaluation: NOT_RUN
planner_activation: NOT_AUTHORIZED
implementation_promotion: NOT_AUTHORIZED
```
