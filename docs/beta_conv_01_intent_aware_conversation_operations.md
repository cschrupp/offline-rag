# BETA-CONV-01 — Intent-aware conversation operations

**Status:** DESIGN COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED / PROMOTED
**Accepted design subject:** `b61570f0815aaaa44d632d82c1fc50f63c673884`
**Design promotion tip:** canonical `main` at `dfc045f4178db41f723feb0483e8f163a801bc40`
**Accepted A2 baseline:** `dce3456e519cb6c96570e20f5af800d00cafb5a7`
**Implementation:** AUTHORIZED / IN PROGRESS
**Implementation branch:** `implementation/beta-conv-01-intent-aware-operations`
**Slice 17:** NOT OPENED

## 1. Objective and boundary

Distinguish factual research requests from explicit text transformations in the
existing workspace conversation. Preserve the accepted grounded-answer and
provenance contracts while allowing users to summarize, rewrite, simplify, or
translate text that is explicitly supplied or unambiguously present in the
visible conversation.

This is the accepted narrow amendment to Slice 16 Amendment A2. All existing
A2 clauses remain authoritative except the specifically scoped changes in §3.

Included:

- deterministic intent routing for clear, supported transformation requests;
- bounded selection of the text to transform from the current message or
  validated visible conversation turns;
- a separate, no-retrieval transformation call through the configured local
  generation adapter;
- explicit response, trace, and UI provenance distinguishing transformed
  conversation text from source-grounded answers;
- fail-closed clarification for missing or ambiguous transform targets.

Excluded:

- BETA-CONV-02 analytical synthesis, comprehensive cross-document comparison,
  or document-wide coverage claims;
- unrestricted autonomous reasoning, tools, web access, external providers,
  or a second RAG pipeline;
- conversation persistence or lifecycle changes, new storage, source-selection
  changes, model-provider changes, and broad Ask UI redesign;
- any weakening of retrieval, snapshot, citation, strict-offline, or evidence
  validation contracts;
- scientific benchmark execution, promotion, or Slice 17 work.

## 2. Accepted architecture inspected

The current product surface is
`POST /v1/workspaces/{workspace_id}/conversation/turn`, implemented through
`run_conversation_turn()`. It validates bounded client-supplied `prior_turns`,
admits the turn against one workspace revision and immutable snapshot, resolves
linguistic context, and invokes the shared `run_bound_snapshot_query()` path.
That path is the sole authority for retrieval, source scope, answer generation,
citations, and query traces. The canonical single-turn `/query` API is separate
and remains unchanged.

`resolve_conversation_context()` currently resolves only a standalone retrieval
question. Its prompt and parser treat transcript text as untrusted data and
fail closed to `clarification_required`. The UI builds prior turns from visible
plain text and persists the active conversation only under the existing A2
session-local policy. The API receives those turns from the client and can
validate only their shape, order, and bounds; it cannot verify that the text
originated in the active browser conversation or belongs to the requested
workspace. The configured `Generator` adapter already provides the offline/
local generation boundary and common error handling.

The implementation must extend this orchestration rather than introduce a
second retrieval path. For transforms it may call the existing generator
adapter directly with a new versioned transform prompt contract; it must not
call retrieval, context assembly, the grounded answer generator, or citation
projection.

## 3. Accepted scoped amendment to A2

### A2-D03 — Accepted non-grounded text-operation exception

Retain the freeze:

> CONVERSATION PROVIDES LINGUISTIC CONTEXT. RETRIEVED SOURCES PROVIDE FACTUAL
> AUTHORITY.

Add this narrow rule:

- An explicit text transformation may use exact text supplied in the current
  user message or client-supplied text selected from the visible active
  workspace conversation as its **transformation input**. The browser-managed
  conversation/workspace relationship is a UI invariant, not server-verified
  provenance.
- `prior_turns` remain client-supplied, untrusted input. The server validates
  structure, role sequence, and bounds, but cannot independently prove turn
  origin, active-conversation membership, or workspace membership. The system
  must not claim that it cryptographically or independently verified these
  properties.
- The UI must construct `prior_turns` only from its active workspace
  conversation. No server-side conversation storage, new authentication, or
  expanded history is introduced by this slice.
- That input is not promoted to factual evidence. A transformed result is not
  independently verified and must be labeled as conversation-text output.
- Previous assistant answers remain forbidden as evidence for factual answers.
  A request to transform one may operate on its text only and must not imply
  that its factual claims were checked.
- Every request that asks what is true, what a source says, or asks for factual
  analysis of documents remains on the grounded path and requires fresh
  retrieval from the currently selected source scope.

No other source of conversation memory is introduced. The UI must not include
cross-workspace, cross-conversation, hidden-session, account-level, or unrelated
browser-history context. Because `prior_turns` are client supplied, the backend
does not claim it can independently verify that exclusion; it treats all
received text as untrusted.

### A2-D05 / D05a — Accepted intent branch above the existing grounded core

After existing request validation, workspace readiness, snapshot admission,
and source-scope binding, apply deterministic intent routing:

1. `conversation_transform`: a high-precision supported transformation
   operator and a valid, uniquely identified text target are both present.
   Invoke only the new transformation contract; do not invoke the resolver,
   retrieval, grounded-answer generation, or citation validation.
2. `clarification_required`: a transformation is clearly requested but its
   target is missing or ambiguous. Return the existing safe clarification
   outcome. Do not invoke any generator or retrieval stage.
3. `grounded_query`: all other requests, including factual requests, source
   summaries, document comparisons, and contextual follow-ups. Preserve the
   current resolver → fresh retrieval → `grounded_answer_v2` flow without
   alteration.

The router is deterministic and versioned. It recognizes only an explicitly
supported operator grammar (summarize/summary, rewrite/rephrase, simplify or
explain for a specified audience, and translate to a named language). It does
not use a model to classify intent. An uncertain request never enters the
transform path. If it explicitly appears to request transformation but cannot
be resolved safely, it asks for clarification; otherwise the existing grounded
route remains the default.

The routing result is a validated discriminated union. `target_text` is an
ephemeral in-memory value and is never placed in a trace:

```text
grounded_query {
  kind: "grounded_query"
}

conversation_transform {
  kind: "conversation_transform"
  operation: "summarize" | "rewrite" | "simplify" | "translate"
  target_kind: "current_message" | "prior_user_turn" | "prior_assistant_turn"
  target_text: non-empty bounded string
  options: allowlisted operation options (e.g. bullet count, audience, target language)
}

clarification_required {
  kind: "clarification_required"
  reason: "transform_target_missing" | "transform_target_ambiguous" |
          "transform_request_unsupported"
}
```

Routing decision table (first matching row wins):

| Request evidence | Route |
| --- | --- |
| Asks what a document/source says, requests factual analysis, or asks for source-based comparison | `grounded_query` |
| Explicit supported transform operator + exact delimited text in the current message | `conversation_transform` |
| Explicit supported operator + one unambiguous named prior user/assistant turn | `conversation_transform` |
| Explicit transform intent but target missing, ambiguous, unsupported, or beyond the bounds | `clarification_required` |
| No high-precision transform match | `grounded_query` and existing resolver behavior |

Transform options are allowlisted by operation. Translation requires a
non-empty target language; rewrite/simplify may accept an explicit audience;
summary may accept a bounded format request such as a bullet count. Unsupported
options clarify rather than silently being ignored. The current user request
remains the authoritative instruction for operation/options, while the target
text is always untrusted data.

Source-oriented wording takes precedence over a superficial transform verb:
“summarize what document X says,” “explain that finding using my selected
sources,” and “compare documents A and B” remain grounded requests. Analytical
comparison remains within current grounded behavior; comprehensive synthesis
is deferred to BETA-CONV-02.

Routing examples:

| User request | Route and reason |
| --- | --- |
| “Summarize your previous answer in three bullets.” | Transform the uniquely named prior assistant turn; no retrieval. |
| “Rewrite your last explanation for a beginner.” | Transform the uniquely named prior assistant turn; no retrieval. |
| “Summarize what document X says about the pump.” | Grounded query; source facts require fresh retrieval and citations. |
| “Explain that finding in more detail.” | Grounded contextual follow-up; resolve context and retrieve fresh evidence. |
| “Translate this paragraph into Spanish: [delimited text].” | Transform the explicitly supplied text; no retrieval and no verification claim. |
| “Translate the paragraph on page 4 of document X.” | Grounded path; the target must be obtained from a source and remains subject to citations. |
| “Translate this.” with no uniquely identified text. | Clarification; target is missing. |
| “Summarize that.” when several turns or source findings could be meant. | Clarification; target is ambiguous. |
| “Summarize the document and identify whether its claims are true.” | Grounded query; factual evaluation is not a text-only transformation. |

### A2-D06 — Deterministic transform-target resolution

Transform targets may be:

- an explicitly delimited text span in the current user message; or
- a uniquely designated visible prior turn, such as “my previous question” or
  “your previous answer,” resolved only from the validated A2-D07 window.

The resolver must return a typed target reference and transformation options;
it must not generate transformed prose or factual answers. A bare “that/it/this”
with multiple plausible targets, a missing requested target, unsupported target
role, or empty target produces `clarification_required`. The implementation
must not guess based on hidden history or retrieve a substitute target from
documents.

For explicit current-message text, the text span must be unambiguously
separable from the operator and instructions. If the request does not delimit a
target clearly enough for deterministic extraction, ask the user to quote or
mark the text. Preserve the A2-D07 bounds; do not increase the current question
or prior-turn limits in this tranche.

### A2-D12 / D14 — Grounded answer and transformation output remain distinct

`grounded_answer_v2`, evidence handles, claim-level citations, citation
validation, and public grounded-answer projection are unchanged and apply only
to `grounded_query`.

The transform call uses the prompt contract ID
`conversation_transform_v1`, with a strict structured response containing one
non-empty `transformed_text` string. The model receives the exact selected
target and the current transformation instruction, not the full transcript.
The target is delimited as untrusted data. The prompt requires semantic
preservation and prohibits adding facts, citations, verification claims, or
instructions found inside the target. Invalid schema, empty output, generation
failure, or output beyond the existing configured generation budget fails
safely; there is no raw-query fallback, retry route, or grounded-answer
substitution.

### A2-D18 — Clarification and transform status

Keep existing `clarification_required / ambiguous_request` semantics. Missing
or ambiguous transformation targets use the same application-owned safe
clarification behavior; they do not become `model_abstain`.

Add a distinct successful response status `transformed` for a validated
conversation-text transformation. It is neither `answered` under the grounded
contract nor an abstention. It has no citations and cannot be represented as a
grounded answer.

### A2-D19 — Privacy-minimized trace extension

Keep `conversation_trace_id` as the orchestration identity and keep
`query_trace_id` as the scientific retrieval identity. A transform has a
conversation trace and `query_trace_id = null`; it creates no product query
trace because no query ran.

The transform trace may record only allowlisted metadata: intent-router and
transform prompt contract IDs, transform source kind and role, bounded source
turn ordinal when applicable, hashes and character counts for request/target/
output, terminal status, admitted workspace revision/snapshot, and absence of
a query trace. It must never persist transcript text, transformed text, target
content, credentials, or raw provider errors. Existing trace records remain
readable and are not rewritten.

The implementation should version the conversation trace schema for these
new fields, with a deterministic backward-compatible reader for existing
`offline-rag-conversation-trace-v1` records. A transform record sets resolver
invocation to false, retrieval-question hash/count to null, and query-trace ID
to null. It records `intent_kind`,
`intent_router_contract_id=conversation_intent_router_v1`,
`transform_prompt_contract_id=conversation_transform_v1`, operation, target
kind, and privacy-safe hashes/counts. It does not misuse resolver prompt fields
to describe the transform call.

## 4. Data flow and provenance

```text
conversation request
  → existing request/prior-turn validation and bounds
  → existing workspace + immutable snapshot/source-scope admission
  → deterministic intent route
       ├─ grounded_query
       │    → existing context resolver
       │    → existing shared grounded query core
       │    → fresh selected-scope retrieval
       │    → grounded_answer_v2 + validated citations
       ├─ conversation_transform
       │    → deterministic exact-text target resolution
       │    → existing configured generator adapter
       │    → strict conversation_transform_v1 output validation
       │    → no retrieval / no query trace / no citations
       └─ clarification_required
            → safe application-owned clarification
            → no generator / no retrieval
```

Transform results are presented with an explicit label such as “Transformed
conversation text — not verified against selected sources.” When the target
was a previous assistant response, the UI should say it transformed that prior
response, not that Seneca re-answered the underlying facts. For transform turns,
the UI must suppress the source-scope label and Current/Historical snapshot
badge because neither describes the basis of the transformed answer. It must
not open the Evidence pane or render citation markers. Instead show the
transformation-source label from the response. A grounded answer retains the
existing source-scope and Current/Historical indicators with exact citations.

The transform response may carry the admitted workspace/snapshot metadata for
continuity of the existing conversation lifecycle, but that metadata must not
be described as evidence supporting the transformed text. Source selection
continues to be bound by the existing admission contract; the transform path
does not read or widen it.

For a transform, `context_used` is true only when the resolved target came from
a prior visible conversation turn; it is false for text supplied in the current
message. This flag describes text selection only and never asserts factual
authority.

## 5. API and frontend impact

Reuse the existing conversation-turn endpoint and request DTO. Preserve
`/query`, `prior_turns`, workspace identity, source selection, existing
conversation session-storage bounds, and new-conversation behavior.

Extend the response with the discriminating `response_kind` values
`grounded_answer`, `conversation_transform`, `clarification`) and add the
`transformed` status. For `conversation_transform`:

```json
{
  "response_kind": "conversation_transform",
  "status": "transformed",
  "query_trace_id": null,
  "retrieval_question": null,
  "answer": "...",
  "answer_blocks": [],
  "citations": [],
  "transformation_source": "current_message | prior_user_turn | prior_assistant_turn"
}
```

For existing grounded responses, `response_kind` is `grounded_answer`; all
existing fields and validations remain unchanged. Clarifications retain their
current response contract and receive `response_kind: clarification`. The
frontend history reader must continue to load existing session entries that
predate `response_kind`, treating them as the existing grounded/clarification
shapes only; it must never infer a transformed response from absent citations.

History validation must accept a citation-free response only when it has the
explicit `response_kind: conversation_transform` and the complete transform
shape: `status: transformed`, non-empty `answer`, empty `answer_blocks` and
`citations`, null `query_trace_id` and `retrieval_question`, and an allowlisted
`transformation_source`. Missing or unknown `response_kind` must not weaken the
existing grounded-answer citation requirements. Existing stored response
shapes remain readable without retroactively labeling them as transforms.

Update Ask rendering and export so the transform label and text are preserved,
the empty citation set is accepted only for the explicit transform kind, and
the Evidence pane is not offered for transform output. Future grounded turns
may still include the visible transformed assistant text in `prior_turns` for
linguistic context; the server continues to treat it as untrusted and
non-authoritative.

`assistantPresentationText()` must return the actual non-empty `answer` for an
explicitly identified transformed response so the visible text can continue as
linguistic context. This does not make it factual evidence. Markdown export
must remove the blanket assertion that all assistant responses were generated
from cited sources. Its global notice must accurately describe mixed grounded
and transformed conversations, and each transform turn must be individually
labeled as not source-verified, with no Sources section or fabricated citation.
JSON export must retain `response_kind` and `transformation_source` so the
distinction survives export.

No new endpoint, database, persistent conversation storage, model provider,
frontend state framework, or retrieval abstraction is introduced.

## 6. Failure and clarification behavior

| Condition | Required outcome |
| --- | --- |
| Clear transform with inline target | Transform exact supplied text; no retrieval |
| Clear transform with uniquely named prior turn | Transform exact visible turn text; no retrieval |
| Transform target absent | `clarification_required`; no model or retrieval call |
| Deictic target has multiple candidates | `clarification_required`; no model or retrieval call |
| Unsupported/uncertain transform phrasing | Do not classify as transform; remain on grounded path or clarify under existing resolver semantics |
| Request asks for source facts or source-based analysis | Existing grounded route and selected-scope retrieval |
| Transform generator unavailable / timeout | Existing safe generation failure contract; no retrieval fallback |
| Malformed, empty, or oversized transform output | Safe generation failure; no citations or partial answer |
| Injection-like instructions inside selected text | Remain untrusted text; no policy, routing, source, or tool change |
| Grounded retrieval lacks evidence | Existing A2 abstention / citation-validation behavior |

## 7. Acceptance plan for later implementation authority

### Deterministic routing and references

- Clear inline summarize, rewrite, simplify, and translate requests select
  `conversation_transform`.
- “Summarize your previous answer in three bullets” selects the latest uniquely
  designated assistant turn and does not call retrieval.
- “Rewrite my previous question for a beginner” selects the preceding user
  turn.
- Missing target, ambiguous “that” with multiple possible targets, malformed
  target delimiters, and unsupported operator/target combinations clarify
  without model or retrieval execution.
- Source-scoped factual questions, contextual follow-ups, “what does document X
  say,” and document comparisons remain grounded; verify source selection and
  immutable admitted snapshot are unchanged.
- Single-turn `/query` regression suite remains unchanged and passing.

### Grounding, injection, privacy, and response validation

- Prior assistant factual claims transformed as text receive a visible
  not-source-verified label and no citations.
- Unsupported factual requests cannot enter the transform route merely by
  mentioning “rewrite,” “explain,” or “summarize.”
- Injection text in current or prior-turn input cannot add instructions,
  source scope, tools, citations, or external access to the transform call.
- Strict response schema, output bounds, trace allowlist, response-kind
  validation, local-history migration, export formatting, and empty-citation
  constraints fail closed.
- Transform traces contain hashes/counts and no private text; transforms have
  no query trace. Grounded turns preserve current query-trace and citation
  provenance.
- Strict-offline execution uses the configured local generator endpoint only;
  no external network/model/provider is introduced.

### Test levels and gate

- Deterministic router/target-resolution unit tests and API orchestration tests
  assert exact stage call counts (transform: generator once, retrieval zero;
  clarification: both zero; grounded: current pipeline unchanged).
- Frontend tests cover transform provenance text, no citation/Evidence UI,
  history refresh/export, and compatibility with existing response records.
- At least one real local-model test exercises representative summary,
  rewrite, and translation prompts against the configured local generator;
  deterministic fakes alone do not satisfy implementation acceptance.
- Mixed-history UI/export tests verify that transforms suppress source/snapshot
  indicators, `assistantPresentationText()` returns transformed text, and
  citation-free history passes validation only for the explicit valid transform
  shape. Markdown and JSON export tests verify the transform source label, no
  Sources section for transforms, and accurate notices for mixed histories. A
  recommended Markdown notice is:

  > This conversation may contain source-grounded answers and transformations
  > of conversation text. Only turns explicitly labeled as grounded and
  > accompanied by citations were answered from selected sources. Transformed
  > text was not independently verified.
- No real-corpus benchmark or scientific qualification campaign is required.
  Any local-model result is functional acceptance evidence, not a new quality
  or latency SLO.
- All existing grounded-conversation, source-scope, snapshot, citation,
  strict-offline, and `/query` regressions remain in the required test set.

## 8. Implementation and review gates

```yaml
BETA-GAME-02B:
  status: COMPLETE / HUMAN ACCEPTED / PROMOTED
  technical_subject: 76b168c7ffc1258cd744bc3b095759d7b059d175

BETA-CONV-01:
  phase: IMPLEMENTATION
  design_review: IR-002 ACCEPT
  human_design_acceptance: ACCEPTED
  design_promotion: COMPLETE
  implementation: AUTHORIZED / IN PROGRESS
  promotion: NOT AUTHORIZED

BETA-CONV-02:
  status: DEFERRED
  implementation: NOT AUTHORIZED

Slice_17:
  status: NOT OPENED / NOT AUTHORIZED
```

Implementation proceeds under the accepted design and its separate Human
authorization. Stop for independent implementation review before any promotion.
