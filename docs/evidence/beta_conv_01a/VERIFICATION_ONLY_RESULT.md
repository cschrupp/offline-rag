# BETA-CONV-01A — Deterministic verification-only result

**Scope:** Existing deterministic tests, API-test startup diagnosis, request/handler
coverage inspection, and UI typecheck disposition. No planner model evaluation,
production change, activation, or promotion was performed.

## Accepted implementation

| Field | Value |
| --- | --- |
| Implementation subject | `e243c4d34d8d784ea6b1b67ebfc8088fb129f988` |
| Human-acceptance record | `80b9726e0aab9e258d1c80b46fddda031193a82f` |
| Verification branch | `implementation/beta-conv-01a-llm-task-planning` |
| Canonical `main` | `51fc93a8867f85417b6522632879e7c4c62c8e55` |

## Executed checks

| Command / check | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/unit/app/test_beta_conv_01a_planner.py tests/unit/app/test_beta_conv_01_intent.py` | **99 passed** in 1.14s |
| `npm test -- src/test/beta_conv_01_intent.test.tsx src/test/slice16d_b3_conversation.test.tsx` | **21 passed** across 2 files |
| `npm run typecheck` | **Failed with 5 diagnostics**, all in unchanged `ui/src/test/slice16k_r04_cuda_oom.test.tsx` |
| Targeted `test_summary_followup_model_empty_uses_deterministic_fallback` with a 45-second bound and faulthandler | **Stalled** in Starlette `TestClient.__enter__`; faulthandler showed the test thread awaiting `start_task_soon` at `starlette/testclient.py:516` while the portal thread was idle in the asyncio selector |

The five TypeScript diagnostics are three missing `operation_id` properties
and two missing `retryable` properties in fixture objects in the CUDA OOM test.
That file is unchanged by BETA-CONV-01A.

## Startup-stall diagnosis

The stall is reproducible without Seneca application code in this execution
environment:

- A minimal FastAPI app with an async `/health` route stalls in
  `TestClient.__enter__` before the first request.
- `anyio.from_thread.start_blocking_portal()` starts and yields its portal, but
  a trivial `portal.call(lambda: 42)` does not complete.
- A standalone asyncio loop runs in a worker thread, but a callback scheduled
  from another thread with `loop.call_soon_threadsafe()` does not run within
  the bounded observation period.
- An ordinary `threading.Thread` starts, signals an event, and joins normally.
- Directly driving the minimal FastAPI ASGI lifespan sends
  `lifespan.startup.complete`.

Observed stack/runtime versions were Python 3.14.5, FastAPI 0.142.2, Starlette
1.7.0, HTTPX 0.28.1, and AnyIO 4.15.1. The evidence localizes the observed
failure to cross-thread event-loop scheduling in this test environment, before
the minimal TestClient enters application startup. It does **not** identify
which component or environmental condition causes that scheduling failure, and
does not establish a Seneca `ApplicationRuntime.start()` defect. The result is
not a passing API test and does not explain the prior workstation-level report
independently.

## Request-admission and handler coverage

The 99 Python tests exercise planner validation and conversation orchestration
through direct unit-level calls, including executor suppression on invalid
plans. The existing `test_slice16d_b3_conversation.py` contains HTTP-level
coverage for prior-turn validation before readiness, source-scope admission,
grounded follow-ups, clarification, and snapshot binding, but its shared
`TestClient` fixture cannot enter under the observed portal failure. Therefore
actual HTTP request parsing/admission and route-handler execution have **not**
been verified in this run. The API verification gap remains open.

No test-only harness workaround or repository code change was made. A future
isolated ASGI harness may exercise the real handler/admission path while
explicitly excluding lifespan startup, as allowed by the accepted design, but
it must not be reported as startup/recovery coverage.

## Current gate status

```yaml
deterministic_planner_and_conversation_tests: 99_PASS
conversation_ui_tests: 21_PASS
ui_typecheck: INCOMPLETE_5_UNCHANGED_FIXTURE_ERRORS
conversation_api_route_coverage: OPEN
testclient_lifespan_startup: BLOCKED_IN_CURRENT_ENVIRONMENT
offline_model_evaluation: NOT_AUTHORIZED
planner_activation: NOT_AUTHORIZED
implementation_promotion: NOT_AUTHORIZED
```

The next bounded technical step is to establish a reliable isolated HTTP test
harness and complete actual route/admission coverage. Any required dependency,
startup, or production-code change must be proposed and reviewed separately.
Offline model evaluation remains a distinct future authorization.
