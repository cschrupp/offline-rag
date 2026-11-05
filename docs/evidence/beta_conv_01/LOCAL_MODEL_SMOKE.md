# BETA-CONV-01 Local Model Functional Smoke

**Run date:** 2026-11-04
**Result:** PASS
**Scope:** Strict-offline functional check against the configured local
generation endpoint using synthetic text only.

This smoke checks that the configured model performs three representative
operations. It is not a model-quality benchmark or a scientific qualification.
The test validates a small set of task-specific properties and prints the
observed outputs so the result can be reviewed.

Command:

```bash
SENECA_RUN_LOCAL_MODEL_TEST=1 .venv/bin/pytest -q -s \
  tests/integration/test_beta_conv_01_local_model.py
```

## Synthetic cases and observed outputs

| Operation | Functional check | Observed output |
| --- | --- | --- |
| Summary | Shorter than the input; preserves the pump and six-hour duration | The pump stopped at noon, restarted at 12:15, and ran for six hours. |
| Rewrite | Changes presentation while retaining the operator, valve, and closing action | The operator shut the red valve. |
| Spanish translation | Contains the Spanish terms for pump and ready | La bomba está lista. |

The prompts used only the following synthetic source text:

- Summary: “The pump stopped at noon. The operator restarted it at 12:15. It then ran for six hours.”
- Rewrite: “The operator closed the red valve.”
- Translation: “The pump is ready.”

```text
BETA_CONV_01_LOCAL_MODEL_RESULT={"rewrite": "The operator shut the red valve.", "summary": "The pump stopped at noon, restarted at 12:15, and ran for six hours.", "translation_es": "La bomba está lista."}
1 passed in 7.81s (repeat after IR-002 router corrections)
```

These checks establish functional behavior for the selected examples only. They
do not establish general factuality, translation quality, or behavior across
other models and prompts.
