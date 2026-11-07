# EVAL-READY-01 — Canonical API Adapter Deterministic Qualification

**Disposition:** Deterministic fake-provider qualification passed. No real
model was called.

The adapter sends evaluation requests only through the existing
`create_app()` application and canonical conversation HTTP route. The full
existing conversation API regression module ran outside the restricted
execution sandbox, where TestClient's cross-thread wake socket is available.
This resolves the earlier sandbox-specific startup stall for this module; no
second application, alternate handler, or startup change was introduced.

## Executed checks

```text
PYTHONPATH=. .venv/bin/pytest -q \
  tests/unit/app/test_beta_conv_01a_eval_prep.py \
  tests/unit/app/test_beta_conv_01a_eval_adapter.py \
  tests/unit/app/test_beta_conv_01a_eval_readiness.py \
  tests/unit/app/test_beta_conv_01a_eval_schedule.py \
  tests/unit/app/test_beta_conv_01a_planner.py
74 passed

PYTHONPATH=. .venv/bin/pytest -q \
  tests/unit/app/test_beta_conv_01_intent.py
70 passed

PYTHONPATH=. .venv/bin/pytest -q \
  tests/unit/app/test_slice16d_b3_conversation.py
38 passed
```

The route-level adapter tests exercised grounded retrieval/citation
normalization and text transformation/target-option capture through the
canonical HTTP endpoint. Synthetic negatives verify that an API response's
query-trace ID must match its persisted conversation trace and that a case's
recorded request hash must match the exact canonical request before API access.
The scorer rejects observation hashes that do not match the corresponding
dataset case and treats an unlinked query trace as an identity and grounding
failure.

The 70 deterministic intent tests also cover the historical linked-source,
prior-turn, malformed-delimiter, unsupported-option, and mixed-obligation
routing regressions referenced by the candidate historical-coverage map.

The earlier sandbox-only `EPERM` stall is therefore not a product or test
failure. The full module passed when run in the compatible environment. Three
Starlette/httpx deprecation warnings remain in the test stack; no dependency
was changed.

This is deterministic adapter qualification only. It does not qualify a real
local model, host resources, held-out custody as blind, the evaluation
methodology, or planner activation.
