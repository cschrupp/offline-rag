# BETA-CONV-01A EVAL-PREP-01 — Preparation implementation acceptance

**Decision:** HUMAN ACCEPTED
**Accepted technical subject:** `bece868ba7210a154d14f6d900fe49a8a12e4a99`
**Independent review:** EVAL-PREP-01 IR-004 — ACCEPT
**Parent:** `a1fe88ad8d803f775ae1c3876869b23a90db60c8`
**Branch:** `implementation/beta-conv-01a-llm-task-planning`
**Scope:** Preparation implementation and source-scope scoring correction.

The accepted scorer enforces the independently labeled `required_source_ids`
as the allowed evidence-source set for successful grounded answers, in addition
to API-selected source scope, citation validity, and admitted-snapshot checks.
Safe grounded abstentions without citations remain non-violations and do not
count as completed answers.

This acceptance applies to the preparation implementation only. It does not
freeze or accept the evaluation dataset, labels, safety challenge set, held-out
custody, environment, thresholds, or freeze manifest. Independent annotation,
challenge-set authorship, and the remaining readiness checks are pending.

```yaml
preparation_implementation:
  subject: bece868ba7210a154d14f6d900fe49a8a12e4a99
  independent_review: IR-004_ACCEPT
  human_acceptance: ACCEPTED

evaluation_package:
  frozen: false
  model_execution: NOT_AUTHORIZED
  planner_activation: NOT_AUTHORIZED
  promotion: NOT_AUTHORIZED
```
