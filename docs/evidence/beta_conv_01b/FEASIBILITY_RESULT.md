# BETA-CONV-01B — Feasibility and M1B/M1E Result

**Current disposition:** M1B and M1E meet their bounded feasibility gates.
Conditional M2 implementation is authorized by the attached tranche decision
and is recorded below. This is not model activation, corpus analysis, or
promotion acceptance.

**Historical checkpoint:** The M0/M1 findings below preserve the earlier
feasibility record. The initial executor usability gate was later resolved by
the one fixed M1E policy correction and eight hand-inspected examples.

## Scope and provenance

- Branch: `feature/beta-conv-01b-conversation-lane`
- Starting commit: `7377871a5b96758129d2eb4e504a6b50c8d5162c`
- Production code, API, UI, schemas, dependencies, and first-turn behavior:
  unchanged
- M0/M1 used the existing configured generator and the existing v1 request
  builder; no application/API pipeline was started.
- The twelve hand-authored cases were frozen before inference at SHA-256
  `756f335274373cc771468d1c580f78e7dcc972f96a6feda8d20c17eae3e2564c`.
  M0, p1, and executor raw prompts/completions/provider payloads remain local
  under `/tmp/beta_conv_01b_feasibility`; none are committed. Original p0
  per-call payloads were lost to the filename mistake described below.
- Every case has a valid prior user/assistant pair. The set is six English and
  six Spanish cases. First-turn behavior is unchanged and was not tested; first
  turns continue to bypass the resolver under the accepted contract.

## Local model/server characterization

`GET /props` returned HTTP 200 on the configured private LAN endpoint. The
response identifies:

- llama.cpp build: `b11669-378a347ce`
- model alias: `qwen3.6-35b-a3b`
- model file basename: `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`
- reported model file type: `Q4_K - Medium`
- context size: 65,536 tokens
- chat-template SHA-256: `55d4931433fe502b794226ee7f4d206a6bdd436ac9f80eb7d8ebb4c639f9ea0c`
- endpoint-specific props object: not exposed (`false`)
- hardware identity: not exposed; no hardware claim is made

The effective application setting is strict-offline, with the selected model
above and a 300-second request timeout. The existing adapter sent
`chat_template_kwargs.enable_thinking=false`. In the retained M0, p1, and
executor records, no `<think>` marker or separate `reasoning_content` field
was observed. The original p0 per-call records were lost, so this statement
does not cover p0. This is empirical evidence for the retained calls, not
proof that every server path suppresses reasoning.

## M0 — Existing v1 resolver

Six representative follow-up requests used the canonical
`build_resolver_request()` and `parse_resolver_content()` functions with
temperature 0 and a 512-token cap.

| Measure | Result |
|---|---:|
| Calls completed | 6/6 |
| `finish_reason=stop` | 6/6 |
| Parsed as resolved retrieval query | 5/6 |
| Parsed as clarification | 1/6 (whole-conversation summary) |
| Median wall time | 3.098 s |
| Range | 2.640–3.687 s |
| Prompt / completion / total tokens | 2,281 / 197 / 2,478 |

These are descriptive observations, not a formal latency benchmark.

## M1 — Router feasibility

The strict flat schema placed `lane` first, followed by
`retrieval_question` and `context_used`. The same 12 cases were each run three
times with temperature 0, the same model/configuration, and no in-observation
retry.

### p0 result

The initial prompt produced valid JSON/schema-shaped outputs and `stop` finishes
for all 36 calls, but all three repetitions of the intentionally ambiguous
“And what did it say about that?” case selected `conversation`. This violates
the fail-toward-grounding requirement. p0 was rejected and motivated one
permitted prompt revision. p0 prompt SHA-256:
`29a0b6963713aa55a980fe03b02501e7cd25ddfc4db271623862cd297d95885b`.

### p1 result

The p1 change made continuity questions requesting factual content explicitly
remain in `sources`, and made multiple plausible antecedents resolve to
`sources` with an empty retrieval question for application clarification.
Prompt SHA-256: `3db1de4a952cb36d37bece9189221294e50185a9edd7732bc72430fe8aa68711`.
Schema SHA-256:
`cc4849bcf7ec165f17fc679b2c60e35f82f283acb54823d2e5b5063a86ddea32`.

| Gate | p1 result |
|---|---:|
| Structurally valid outcomes | 36/36, including the specified empty-query clarification |
| `finish_reason=stop` | 36/36 |
| Cases correct in all three repetitions | 12/12 |
| Factual/source/mixed request routed to `conversation` | 0 |
| Ambiguous case | `sources` + empty query in 3/3 |
| Lane instability | 0 cases |
| Median / range | 2.173 s / 1.380–6.163 s |
| Prompt / completion / total tokens | 13,860 / 1,203 / 15,063 |

The latency ceiling is `3.098 + max(1.000, 0.20 × 3.098) = 4.098 s`.
The p1 median is below that descriptive feasibility threshold.

| Case | Language | Expected | p1 observed, repeats 1–3 |
|---|---|---|---|
| Factual named-source question | EN | sources | sources ×3; nonempty query |
| Contextual factual follow-up | ES | sources | sources ×3; nonempty query |
| Whole-conversation summary | EN | conversation | conversation ×3 |
| Previous-answer three-bullet summary | ES | conversation | conversation ×3 |
| Simplify previous answer | EN | conversation | conversation ×3 |
| Translate previous answer | ES | conversation | conversation ×3 |
| Follow-up greeting | EN | conversation | conversation ×3 |
| Follow-up capability question | ES | conversation | conversation ×3 |
| Verify prior claim against report | EN | sources | sources ×3; nonempty query |
| Rewrite using named manual | ES | sources | sources ×3; nonempty query |
| Ambiguous reference with multiple prior topics | EN | sources + empty query | sources + empty query ×3 |
| Prior-turn injection plus current policy question | ES | sources | sources ×3; nonempty query |

No p2 prompt was attempted.

### Evidence-handling limitation

The p1 runner initially used a p0 filename prefix and overwrote the local p0
per-call raw files and summary. The p0 aggregate above is reconstructed from
the summary printed at execution time; its original per-call raw provider
payloads are no longer available. No p0 inference was repeated. The p1
per-call records were preserved separately after detection. This limitation
does not change the observed p0 ambiguity failure, but it reduces p0 raw-output
auditability and is retained here rather than obscured.

## Initial transcript-only conversation executor — historical M1 finding

Six representative requests were sent to the same model. The probe supplied
only bounded prior transcript, current message, and a fixed conversation-only
policy; it had no retrieval client, source contents, document IDs, workspace
metadata, or citation mechanism.

| Output mode | Samples | Valid/nonempty | Finish |
|---|---:|---:|---:|
| One-field strict JSON (`{"text": ...}`) | 3 | 3/3 | stop 3/3 |
| Plain text | 3 | 3/3 | stop 3/3 |

The samples covered whole-conversation summary, three-bullet prior-answer
summary, simplification, Spanish translation, greeting, and capability
response. Outputs were fluent and usable overall. One three-bullet answer added
a third point (“follow the report recommendations”) beyond the two explicit
items in the prior assistant text. This is a possible transcript-fidelity
issue; the Human must inspect the actual local output and judge whether the
sample is usable before M2 is considered. JSON and plain text both worked in
these small samples; the six requests were not paired on identical inputs, so
this is not a controlled output-format comparison.

## M1B — Unseen routing-boundary challenge

Exactly twelve new cases (six English, six Spanish), each with valid prior
turns, were frozen before inference at SHA-256
`d89475f1cfb2b5c1a47ff18032a940d1379b0a33bfde3701a50b8b0072516c78`. The
frozen p1 prompt and schema hashes were
`3db1de4a952cb36d37bece9189221294e50185a9edd7732bc72430fe8aa68711` and
`cc4849bcf7ec165f17fc679b2c60e35f82f283acb54823d2e5b5063a86ddea32`.
Every case ran twice (24 calls, no retry, no prompt change). The raw requests
and responses remain local under `/tmp/beta_conv_01b_feasibility/raw/m1b`.

| Gate | Result |
|---|---:|
| Normal provider completions / stop finishes | 24/24 |
| Exact three-field outputs parse structurally | 24/24 |
| Cases matching expected full disposition on both repeats | 11/12 |
| Lane-stable cases | 12/12 |
| Safety-sensitive lane flips | 0 |
| Factual/source/verification/mixed cases routed to conversation | 0 |

The sole miss was `b10-es-mixed-source-and-transform`: both outputs chose
`sources` but supplied a nonempty retrieval query rather than the required
empty query. The local runner incorrectly counted these two outputs as
structurally invalid; direct parsing confirmed both match the schema. Because
the stated gate permits one case not to match, the 11/12 result passes. The
implementation applies the accepted deterministic mixed-operation guard and
clarifies before any retrieval, without tuning p1.

| Case | Expected | Repetition 1 | Repetition 2 | Result |
|---|---|---|---|---|
| b01 — remind prior assistant | conversation / empty | conversation / empty | conversation / empty | PASS |
| b02 — remind source content | sources / nonempty | sources / nonempty | sources / nonempty | PASS |
| b03 — verify previous answer | sources / nonempty | sources / nonempty | sources / nonempty | PASS |
| b04 — shorten prior answer | conversation / empty | conversation / empty | conversation / empty | PASS |
| b05 — translate prior answer | conversation / empty | conversation / empty | conversation / empty | PASS |
| b06 — translate source content | sources / nonempty | sources / nonempty | sources / nonempty | PASS |
| b07 — recap conversation mentioning sources | conversation / empty | conversation / empty | conversation / empty | PASS |
| b08 — factual question from discussion | sources / nonempty | sources / nonempty | sources / nonempty | PASS |
| b09 — conversation-presence question | conversation / empty | conversation / empty | conversation / empty | PASS |
| b10 — mixed source and transform | sources / empty | sources / nonempty | sources / nonempty | MISS; app guard clarifies |
| b11 — ambiguous multiple topics | sources / empty | sources / empty | sources / empty | PASS |
| b12 — prior injection with current fact | sources / nonempty | sources / nonempty | sources / nonempty | PASS |

## M1E — Executor fidelity challenge

One fixed plain-text policy correction was applied before eight hand-inspected
examples (four English, four Spanish). Case manifest SHA-256:
`ac5bd70003786d2d075819c62bb5cfeabd86b3c6d3cd47e59990a6b7bf52941c`;
corrected policy SHA-256:
`5cbfa984715785c3f3610b56a21cd46f825976b82a56d1626ce69d9a09d47138`. Raw
I/O remains local under `/tmp/beta_conv_01b_feasibility/raw/m1e`.

| Case | Observed output disposition | Fidelity assessment |
|---|---|---|
| e01 — two items requested as three bullets | Returned only the two supported bullets | PASS; no invented third point |
| e02 — Spanish summary | One-sentence summary of the prior statement | PASS |
| e03 — simplification | Preserved both requirements in simpler wording | PASS |
| e04 — Spanish to English translation | Preserved date and measured-pressure items | PASS |
| e05 — conversation recap mentioning sources | Recounted what was discussed, with attribution | PASS |
| e06 — Spanish greeting/capability | Brief bounded capability response | PASS |
| e07 — unavailable source fact | Declined; did not state a cause | PASS; did not explicitly direct to sources |
| e08 — unavailable verification | Declined because the prior conversation lacked the evidence | PASS; did not explicitly direct to sources |

All 8/8 completed normally with nonempty text and `finish_reason=stop`. No
unsupported factual addition was observed, unavailable facts were not answered
from model knowledge, and translation was faithful. The two declines are a
minor actionability limitation relative to the fixed policy wording, not a
fidelity failure under the stated M1E gate. No second factuality checker or
prompt-tuning iteration was used.

## Current disposition

```yaml
M0:
  complete: true
  resolver_median_seconds: 3.098

M1_router_v2_p0:
  result: NO_GO
  reason: ambiguous factual follow-up routed to conversation in 3/3

M1_router_v2_p1:
  quantitative_feasibility: PASS
  36_valid_and_stop: true
  12_cases_correct_and_stable: true
  factual_to_conversation_violations: 0
  latency_gate: PASS

conversation_executor:
  M1E_samples: 8
  M1E_gate: PASS
  output_mode: plain_text
  policy_iterations: 1

M1B:
  calls: 24
  schema_parse: 24/24
  cases_both_repeats_correct: 11/12
  safety_violations: 0
  mixed_case_model_query_nonempty: true
  mixed_case_application_guard: CLARIFY_BEFORE_RETRIEVAL

M2:
  implementation: COMPLETE_PENDING_INDEPENDENT_REVIEW
  model_activation: NOT_AUTHORIZED
  promotion: NOT_AUTHORIZED

first_turn_semantics:
  unchanged: true
  resolver_bypassed: true
```

**Recommendation:** `GO M2 implementation`. The M1B one-case miss is explicitly
handled by the deterministic mixed-operation clarification; p1 remains frozen.
M1E passed after its single fixed-policy correction. Product-level real-model
acceptance remains separate from this bounded feasibility result.

## M2 implementation verification limitation

The focused backend conversation suite completed 35/35, and the combined
conversation/query-observability run completed 51/51 during this implementation
pass. A later rerun stalled at `TestClient.__enter__`. Its bounded traceback
shows pytest waiting in `anyio.from_thread` while the asyncio portal waits in
its event loop, consistent with the separately documented test-environment
startup limitation. The standalone router/policy regressions pass. No startup
infrastructure was changed under this scope.
