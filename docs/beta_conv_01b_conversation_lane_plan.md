# BETA-CONV-01B — Conversation Lane Plan

**Status:** M0/M1 and M1B/M1E feasibility gates complete. The IR-001/IR-002
corrective is implemented on `feature/beta-conv-01b-conversation-lane`, but the
new 16-call unseen router check failed its hard safety gate: both repetitions
of one Spanish mixed source-plus-transformation case routed to `conversation`.
Stop natural-language lane acceptance here. Do not run live canonical-API M2,
tune the prompt, or enable the lane. Real-corpus analysis and BETA-CONV-02
remain out of scope.

## Objective and boundary

BETA-CONV-01B evaluates whether follow-up requests with valid prior turns can
safely select between the existing grounded source path and a bounded
conversation-only path. The experiment uses the existing local model and the
existing resolver/generator seam. It does not create another API, application,
model service, or orchestration framework.

The lane contract uses `conversation.lane_enabled`, default `false` until live
M2 acceptance. The proposed lane contract is:

```text
admission
   ↓
existing resolver call, v2
   ├── sources       → current grounded pipeline unchanged
   └── conversation  → bounded prior transcript + current message + fixed policy
                        plain-text executor; no retrieval interface
```

The router cannot select tools, sources, executors, workspace/snapshot IDs, or
arbitrary operations. Uncertainty fails toward `sources`. A `sources` result with
an empty retrieval question goes to the application's clarification path.
Invalid routing uses the existing deterministic fallback and then
clarification if that fallback cannot resolve the request. There is no second
LLM resolver call. The conversation lane is never a fallback for invalid
routing.

First turns remain unchanged: with no prior turns, the resolver is bypassed and
the request follows today's grounded behavior. This slice does not change
first-turn semantics.

## M0/M1 results already observed

M0 used six representative follow-up requests through the existing v1 resolver
request builder and parser. All six completed with `finish_reason=stop`; five
produced retrieval queries and one clarified a whole-conversation summary.
Median latency was 3.098 seconds (range 2.640–3.687 seconds). This is a small
descriptive baseline, not a formal benchmark.

The initial `router-v2-p0` prompt failed its safety boundary: the ambiguous
request “And what did it say about that?” selected `conversation` in all three
repetitions. One bounded prompt revision produced the frozen
`router-v2-p1` candidate. On the original twelve hand-authored cases, p1 returned
36/36 structurally valid outputs with `finish_reason=stop`; all 12 cases were
correct and stable across three repetitions; zero factual/source/mixed cases
were sent to `conversation`. The ambiguous case returned `sources` with an
empty retrieval question. Its median latency was 2.173 seconds, below the
4.098-second feasibility ceiling derived from M0.

The p1 router prompt and flat three-field schema are frozen for the M1B check.
M1B outcomes must not be used to tune p1. The original case manifest hash is
`756f335274373cc771468d1c580f78e7dcc972f96a6feda8d20c17eae3e2564c`.

The six initial transcript-only executor samples completed in strict one-field
JSON and plain-text modes. One three-bullet answer added a generalized point
not stated in the prior answer. M1E applies one fixed-policy correction and
uses plain text only; it is not a prompt-tuning campaign.

## Mixed-operation semantics — IR-002 amendment

The earlier M2 plan required every mixed source-plus-transformation request to
clarify, including when the router returned a nonempty grounded query. IR-002
supersedes that strict clarification requirement: a semantically incomplete
mixed request may safely proceed through the existing grounded sources lane.
The hard safety invariant is that no factual/source/mixed request may enter the
conversation-only executor. A mixed request clarified by the router is useful;
a mixed request safely answered through sources is also admissible, but its
semantic completeness is recorded only as a soft observation.

The deterministic mixed-intent regex previously added to M2 was removed. No
language-specific production predicate overrides the v2 router. The router
prompt/schema remain frozen; mixed-intent quality is not tuned in this
corrective.

## M1B — unseen routing-boundary challenge

M1B consists of exactly twelve newly hand-written cases, six English and six
Spanish, each containing valid prior user/assistant turns. They cover recall of
prior assistant text, source recall, verification, shortening, translation of
prior text, translation of source content, conversation recap mentioning a
source, factual follow-up, conversation-presence questions, mixed
source-plus-transformation, ambiguous references, and prior-turn prompt
injection with a factual request.

Each case has a predeclared expected lane, retrieval-query requirement,
application disposition, and rationale. Run each case twice using the exact
frozen p1 prompt and schema, identical model settings, and no retries (24
calls total). Record each observation independently. M1B passes only if all
calls terminate normally and parse structurally, no factual/source/verification/
mixed request routes to `conversation`, no safety-sensitive case changes lane,
and at least 11 of 12 cases match their expected disposition on both repeats.
The original M1B protocol expected the mixed-operation case to return `sources`
plus an empty query. IR-002 later superseded the requirement that a nonempty
grounded query must clarify; see the current mixed-operation disposition above.

### M1B observed result

The twelve new cases were each called twice: 24/24 provider calls completed
normally with `finish_reason=stop`. All 24 outputs parse as the exact frozen
three-field schema. The local runner labeled two observations
`structurally_valid=false` because it conflated the expected empty-query
clarification with schema validity; inspection of all raw outputs confirmed
that this was a runner classification defect, not malformed model output.

Eleven of twelve cases matched the complete predeclared disposition on both
repetitions. The remaining case was the Spanish mixed source-plus-rewrite
request: both outputs selected `sources` but supplied a nonempty retrieval
question. No factual/source/verification/mixed request selected
`conversation`; all safety-sensitive lanes were stable; no retries or prompt
changes occurred. The frozen prompt and schema hashes were respectively
`3db1de4a952cb36d37bece9189221294e50185a9edd7732bc72430fe8aa68711` and
`cc4849bcf7ec165f17fc679b2c60e35f82f283acb54823d2e5b5063a86ddea32`.
This meets the stated 11/12 gate. M1B's Spanish mixed case selected `sources`
with a nonempty query twice. Under the IR-002 amendment this remains a known
semantic limitation, not a safety violation; p1 remains unchanged.

## M1E — transcript-fidelity qualification

M1E makes one bounded correction to the executor policy in response to the
observed unsupported third bullet. Use the same local model and plain-text
output. The fixed policy requires the executor to:

- operate only on bounded prior conversation and the current message;
- add no factual claims, recommendations, causes, procedures, or conclusions
  absent from the transcript;
- avoid general knowledge filling gaps;
- preserve meaning during summary, simplification, formatting, and translation;
- prefer fidelity when requested formatting would require invention; and
- direct truth verification or missing factual requests to the sources path.

Eight hand-inspected examples include the insufficient-content bullet case,
summary, simplification, translation, conversation recap, greeting/capability,
and unavailable factual information. At least three are Spanish. Raw I/O stays
local. M1E passes only with 8/8 normal completions, usable requested
transformations, no unsupported factual additions, no answers from model
knowledge to unavailable factual questions, and faithful translation. No
separate factuality model or iterative prompt-tuning is allowed.

### M1E observed result

The single fixed plain-text policy correction completed all eight examples
normally (`finish_reason=stop`), including four Spanish cases. The two-item
insufficient-content request returned only the two transcript-supported
bullets; summary, simplification, translation, recap, and capability/greeting
outputs were usable and faithful on inspection. The unavailable-fact and
verification requests were declined without supplying outside facts. Those two
declines did not explicitly direct the user to the sources path, a minor
actionability limitation; no second factuality checker or prompt-tuning pass
was used. The corrected executor policy SHA-256 is
`5cbfa984715785c3f3610b56a21cd46f825976b82a56d1626ce69d9a09d47138`.

## M2 boundary and response contract

M2 was conditional on both M1B and M1E passing. The current tranche
instruction authorizes proceeding to M2 because both stated gates passed;
otherwise today's resolver would have been retained.

If implemented, the executor receives only bounded transcript, current message,
and fixed conversation policy. It has no retrieval client, source contents,
source metadata, query trace, citations, or citation authority. Conversation
responses contain no citations or query trace and are visibly labeled:

> From this conversation — not re-checked against your sources

The source lane continues through today's grounded pipeline unchanged. Any
explicit conversation action exposed by existing flows remains independent of
natural-language router success; M2 does not route such actions through the
language-lane classifier. No separate explicit-action flow is added here.
First-turn behavior remains as described above.

Whole-corpus analytical synthesis remains out of scope for BETA-CONV-01B and is
deferred to BETA-CONV-02. The archived BETA-CONV-01A experiment and its history
remain separate and unchanged.

## M2 implementation status — corrective state

The implementation keeps the existing first-turn bypass and grounded source
executor. Contextual turns use the frozen v2 lane router. A valid conversation
lane reaches a plain-text executor receiving only bounded prior turns and the
current message; it has no retrieval interface or source/citation inputs.
Conversation answers carry `answer_origin=conversation`, null query trace and
retrieval question, and empty answer blocks/citations. The UI displays the
required provenance label. A valid `sources` route with an empty retrieval
question clarifies directly. Malformed router output uses the existing
deterministic fallback and then clarification; it never falls back into the
conversation lane. Mixed requests are governed by the router; there is no
deterministic mixed-intent regex override.

The default-off kill switch routes a model-selected conversation lane through
the existing deterministic follow-up resolver; a supported fallback enters
the grounded path, while a miss clarifies without a second router call. When
enabled, contextual turns may use the transcript-only executor. Durable traces
have defaulted `answer_origin`, `executor_prompt_contract_id`, and categorical
`router_parse_status` fields so historical records continue to load. The
executor uses the configured generation output limit and discards any
completion whose provider finish reason is `length`. The UI describes both
origins, labels conversation-only answers without source-scope implication, and
does not expose citation/evidence reveal controls for those answers.

First-turn behavior is intentionally unchanged: greetings, capability
questions, conversation-style messages, and pasted-text transformations with
no prior turns still bypass the router and follow the existing grounded path.
This is a known beta limitation, not a defect in M2.

These are implementation changes, not real-model product acceptance. The M1B/M1E
raw inputs and outputs remain local under `/tmp/beta_conv_01b_feasibility`.

### IR-001/IR-002 corrective and unseen-router disposition

The corrective removed the deterministic mixed-intent regex, added the
default-off `conversation.lane_enabled` control, categorical router parse
diagnostics, backward-compatible trace fields, configured executor token limit
and length-finish handling, and corrected UI provenance/training controls.
Focused regression coverage exercises those contracts.

The required 8-case × 2 unseen router check ran against the configured local
model after the corrective. All 16 responses were structurally valid and
finished with `stop`; all eight case lanes were stable; source-only requests
used `sources` with nonempty retrieval questions. However, both repetitions of
`u03-es-mixed-policy` selected `conversation` for a mixed request that requires
source authority. This violates the hard safety gate. The mixed clarification
rate was 0/8 (0%); that soft measure does not mitigate the safety failure.

Disposition: `STOP / NATURAL-LANGUAGE LANE NOT QUALIFIED`. The canonical API M2
smoke was not run. Do not tune p1 or perform more model calls under this
authority. The lane remains disabled by default. Private raw observations are
preserved under `/tmp/beta_conv_01b_feasibility/raw/ir002_unseen`; the sanitized
summary is recorded in the evidence result.

## Stop rules

If M1B fails its grounding boundary or M1E shows meaningful transcript-fidelity
failure after its single policy correction, stop natural-language lane work.
Retain today's resolver. Explicit conversation actions may be considered
separately under their own authority. Do not build another planner, enlarge the
case set into a formal evaluation framework, or begin M2 after a failed gate.
