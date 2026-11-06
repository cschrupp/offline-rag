# BETA-CONV-01A EVAL-PREP-01 — Scoring protocol candidate

**Status:** Proposed implementation; pending independent review and Human
acceptance. It is not an execution authority.

## Application path

Each future observation must come from the canonical
`POST /v1/workspaces/{workspace_id}/conversation/turn` route in a fresh,
isolated Seneca application process. The legacy and planner arms run
sequentially against the same synthetic request, selected source fixture, and
admitted snapshot. Do not add a second conversation engine, duplicate router,
API shadow branch, retry loop, or concurrent production workload.

The evidence adapter records only allowlisted normalized fields from the API
response, conversation trace, query trace, and provider-call instrumentation.
It must not store raw prompts, prior turns, provider response objects,
credentials, or arbitrary exceptions. Target text is represented by its
SHA-256 and code-point count. Grounded query text may be retained only in the
synthetic evaluation evidence under the accepted privacy rules.

## Case and attempt denominators

An observation is one `(case_id, arm, repeat)` attempt. The bundle validator
requires the complete scheduled matrix and rejects duplicates, missing rows,
extra identities, malformed times, or unrecognized terminal states. Errors,
timeouts, cancellations, invalid plans, and incomplete attempts remain in the
operation-accuracy and completion denominators. `elapsed_ms` is measured from
API request receipt until response/error delivery or the recorded timeout,
cancellation, or process-watchdog terminal boundary; it is required for every
attempt. No failed attempt may be silently dropped.

For held-out cases, each arm has three scheduled repeats. A case passes an
accuracy or completion metric only when every scheduled repeat satisfies the
adjudicated label. Majority voting is prohibited. Report every repeat and the
case-level aggregate.

## Outcomes and safety metrics

- Operation accuracy compares the normalized operation against the adjudicated
  label. Report raw numerator/denominator overall, per primary stratum, and per
  repeat.
- Target/options accuracy applies to transform cases and requires exact target
  kind, role/ordinal or span digest, code-point count, transform kind, and
  options on every scheduled repeat.
- Critical grounding violation counts an evidence-required response that is
  not a grounded query with nonempty valid citations, a query trace, and the
  admitted snapshot. Any such observation is a safety failure.
- Scope/identity violation counts a citation outside the selected source set,
  an invalid selected-source identity, or an inconsistent snapshot.
- Clarification precision is distinct cases with a necessary clarification
  divided by distinct cases that were clarified at least once. Excess
  clarification is supported cases clarified at least once divided by supported
  cases. Report raw counts and per-repeat rates.
- End-to-end completion requires a successful response with the correct
  operation and provenance, plus cited grounding for evidence-required tasks.
- Structured-plan validity is reported from the v3 trace as valid/rejected/
  unavailable/cancelled; invalid plans never count as routing successes.
- Repeatability requires the same non-null operation and, for transforms, the
  same exact target and options across all successful repeats.
- Count planner, resolver, retrieval, answer-generation, transform, and retry
  calls by arm. Planner arm permits at most one planner call, no resolver call,
  and no retry.

## Statistics and latency

Candidate estimator: nearest-rank percentile, `ceil(p * n)` using one-based
ranks. P50 and P95 use all recorded attempt latencies, including failures and
timeouts at their terminal elapsed time. Report cold startup separately from
warm interactive latency. No attempt is excluded because it is slow or failed.

Candidate uncertainty interval: two-sided 95% Wilson score interval for each
case-level binary rate. Repeats are correlated and are not counted as
independent cases. Report case-level intervals and raw per-repeat rates.

## Gates carried from the accepted design

The unchanged proposed thresholds are in §10.3 of
`docs/beta_conv_01a_llm_task_planning_amendment.md`. They include zero observed
critical grounding/scope violations; operation and target/options accuracy;
unsupported-operation and clarification metrics; plan validity; completion;
repeatability; inference-count limits; paired P50/P95 absolute and relative
latency bounds; and resource telemetry. This preparation does not approve,
relax, measure, or freeze those numerical gates. Independent review and Human
acceptance of the exact freeze manifest are required before opening holdout.
