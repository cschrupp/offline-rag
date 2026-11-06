# BETA-CONV-01A EVAL-PREP-01 — Independent annotation instructions

**Status:** Candidate guide; no labels have been completed or accepted.

Annotators must be independent of the planner implementation and prompt
authoring. They receive the same request-only packet separately, must not see
each other's labels, and must not consult planner output, legacy routing, or
model responses while labeling. Do not revise labels after evaluation results
are viewed. Preserve each annotator's original packet and completed response;
resolve disagreements in a separate adjudication record.

For each request, label:

- `expected_operation`: `grounded_query`, `transform_text`, `clarify`, or
  `unsupported_operation`;
- `expected_reason_code` where the safe outcome is clarification or refusal;
- exact target kind and role, one-based prior-turn ordinal, or zero-based
  half-open Unicode code-point span into the exact current question;
- transform kind and every supported formatting option; mark unsupported
  requested constraints as requiring a safe clarification;
- whether evidence is required and the required source scope, constrained to
  the source IDs selected in the request;
- all permitted safe terminal outcomes and whether clarification is required;
- for grounded queries, a short intent-preservation rubric note. Do not require
  a single exact retrieval-question string when multiple phrasings preserve
  intent.

For exact targets, compute `target.sha256` over the exact UTF-8 target text and
record its Unicode code-point count. Do not normalize whitespace, repair
offsets, infer omitted history, or expand selected source scope. An unknown or
unselected named source cannot be labeled as permission to retrieve it.
For a transform, the adjudicated `target` record must include `kind`, `role`,
`ordinal` (or null for a current-message span), `sha256`, `char_count`,
`transform_kind`, and the exact `options` object. For non-transform outcomes,
`target` is null.

The two generated packets intentionally contain blank labels and omit split,
stratum, tags, and semantic-family identity. The matching case ID and request
hash bind labels to input bytes. Human reviewer assignment and annotator IDs
remain pending.
