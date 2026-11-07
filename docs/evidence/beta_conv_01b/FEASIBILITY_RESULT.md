# BETA-CONV-01B — M0/M1 Feasibility Result

**Disposition:** Router feasibility passes with `router-v2-p1`; Human review of
the transcript-only executor samples remains required before any M2 decision.

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

## Transcript-only conversation executor

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

## Overall disposition

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
  sampled: 6
  output_modes: [strict_json, plain_text]
  human_usability_judgment: PENDING

M2:
  authorized: false
  start_condition: Human reviews actual executor outputs and decides usability

first_turn_semantics:
  unchanged: true
  resolver_bypassed: true
```

**Recommendation:** `router GO to M2 consideration; executor judgment pending`.
Do not start M2 until the Human has reviewed the actual outputs. If the
three-bullet fidelity issue is unacceptable, the router result alone is not a
GO for the conversation lane; retain the existing resolver and consider
explicit conversation actions separately.
