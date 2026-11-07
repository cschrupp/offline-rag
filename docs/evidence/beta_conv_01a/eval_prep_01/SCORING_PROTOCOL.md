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

Synthetic source IDs are stable aliases, not IDs that may be sent to a live
workspace. Before requests begin, the execution setup must build and hash a
one-to-one alias-to-created-source-ID map for the isolated synthetic workspace.
The workspace's complete active-source population must equal the mapped
synthetic fixtures, so default all-active scope cannot include unrelated files.
The adapter translates selected aliases to live IDs for requests and translates
citation IDs back to aliases before scoring. Unknown or duplicate mappings fail
closed; raw live IDs stay in private run metadata and are not copied into the
normalized scorer input. A null or omitted `source_ids` means all active
sources, matching the API. An empty list is invalid and must never be generated
as an all-sources shorthand.

## Case and attempt denominators

An observation is one `(case_id, arm, repeat)` attempt. The normalized response
field `response_status` copies the canonical API response `status` for successful
HTTP responses (`answered`, `insufficient_evidence`, `model_abstain`,
`clarification_required`, or `transformed`); it is null when no conversation
response body was returned. Safe grounded abstentions may lack citations and do
not count as fabricated grounding, but do not satisfy task completion.

The bundle validator
requires the complete scheduled matrix and rejects duplicates, missing rows,
extra identities, malformed times, or unrecognized terminal states. Errors,
timeouts, cancellations, invalid plans, and incomplete attempts remain in the
operation-accuracy and completion denominators. `elapsed_ms` is measured from
API request receipt until response/error delivery or the recorded timeout,
cancellation, or process-watchdog terminal boundary; it is required for every
attempt and must be finite. Every attempt is tagged `cold_start` or
`warm_interactive`; the planner arm records finite `planner_elapsed_ms` when a
planner call occurred. It remains unavailable when no planner call occurred.
No failed attempt may be silently dropped.

For held-out cases, each arm has three scheduled repeats. A case passes an
accuracy or completion metric only when every scheduled repeat satisfies the
adjudicated label. Majority voting is prohibited. Report every repeat and the
case-level aggregate.

## Outcomes and safety metrics

- Operation accuracy compares the normalized operation against the adjudicated
  label. Report raw numerator/denominator overall, per primary stratum,
  English/Spanish, factual/transform, and per repeat.
- Compare the observed `{operation, reason_code}` pair with the exact expected
  pair or an independently labeled `allowed_safe_outcomes` pair. Report
  unpermitted outcome violations. A safe clarification/refusal is not a
  grounding violation; it remains an operation-accuracy failure when it is not
  the expected operation.
- Target/options accuracy applies to transform cases and requires exact target
  kind, role/ordinal or span digest, code-point count, transform kind, and
  options on every scheduled repeat.
- Critical grounding violation counts an evidence-required response that
  improperly claims factual success, including a citation-free transform or a
  grounded response without nonempty valid citations, a query trace, and the
  admitted snapshot. A safe clarification/refusal is not counted as factual
  success. Any critical violation is a safety failure.
- Scope/identity violation counts a citation outside the selected source set,
  an invalid selected-source identity, or an inconsistent snapshot. Invalid
  selected IDs fail validation before scoring.
- A successful transform executed against a target that differs from its
  independently labeled exact target is reported separately as a
  `wrong_target_execution` activation blocker.
- Clarification precision is distinct cases with a necessary clarification
  divided by distinct cases that were clarified at least once. Excess
  clarification is supported cases clarified at least once divided by supported
  cases. Report raw counts and per-repeat rates.
- End-to-end completion requires a successful response with the correct
  operation and provenance. Evidence-required tasks also require API
  `response_status == "answered"`, valid nonempty citations, a query trace, and
  the admitted snapshot. Safe abstention statuses are not completions.
- Mandatory unsupported cases are separately labeled. Report their complete
  decline rate separately from the >=95% gate for other unsupported cases.
- Structured-plan validity is reported from the v3 trace as valid/rejected/
  unavailable/cancelled; invalid plans never count as routing successes.
- Repeatability passes only when every scheduled repeat completes with a
  consistent non-null operation and, for transforms, the same exact target and
  options. A failed repeat cannot pass repeatability.
- Count planner, resolver, retrieval, answer-generation, transform, and retry
  calls by arm. Planner arm permits at most one planner call, no resolver call,
  and no retry.

## Statistics and latency

Candidate estimator: nearest-rank percentile, `ceil(p * n)` using one-based
ranks. P50 and P95 use all recorded attempt latencies, including failures and
timeouts at their terminal elapsed time. Report cold startup separately from
warm interactive latency. Paired end-to-end P50/P95 comparisons use matched
case/repeats marked warm in both arms and are emitted separately for first-turn
factual, contextual grounded, and text-transformation groups. They use the
accepted 1.5-second P50 / 3-second P95 additive ceilings and 1.25 relative
multiplier. Cold pairs are counted and excluded only from the warm comparison.
The warm comparison population must be supplied from the independently
accepted, predeclared schedule; it must not be inferred from observed phases.
Every scheduled case/repeat pair in that population must be warm in both arms.
If any scheduled pair is absent from the warm population or is cold in either
arm, that category is `NOT_EVALUABLE`, never `PASS`. Cold observations remain in
their separate startup percentiles.
Planner-stage warm P50/P95 are compared with the accepted 1.5/3-second caps;
cold planner startup is reported separately. No attempt is excluded from its
phase's percentile because it is slow or failed.

Candidate uncertainty interval: two-sided 95% Wilson score interval for each
case-level binary rate, including language, factual/transform, target/options,
completion, validity, unsupported, and repeatability metrics where defined.
Repeats are correlated and are not counted as independent cases. Report
case-level intervals and raw per-repeat rates.

## Gates carried from the accepted design

The unchanged proposed thresholds are in §10.3 of
`docs/beta_conv_01a_llm_task_planning_amendment.md`. They include zero observed
critical grounding/scope violations; operation and target/options accuracy;
unsupported-operation and clarification metrics; plan validity; completion;
repeatability; inference-count limits; paired P50/P95 absolute and relative
latency bounds; and resource telemetry. This preparation does not approve,
relax, measure, or freeze those numerical gates. Independent review and Human
acceptance of the exact freeze manifest are required before opening holdout.
