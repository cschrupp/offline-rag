# KM-01 conversational recovery

Authority is the Human acceptance of the Knowledge Memory addendum at
`5ef10fc8bd284b5f7a8b61866c1963f678ba6a9d` and authorization for KM-01.

The existing workspace turn remains the source of the outcome. The recovery
panel uses its status and reason, the admitted source count and snapshot, and
observed context and generator diagnostics. Historical turns can omit the
diagnostics. For a failed request, the panel uses the existing error result
and shows its safe code and trace ID when present. Editing restores the
submitted draft and focuses the composer. Sending remains an explicit action.

## Browser demonstration

These are Chromium screenshots of the running Seneca workspace page with
deterministic API responses and synthetic workspace metadata. Each exercise
submitted one turn, opened the diagnostics, and verified that editing
restored the question without issuing another request.

- [No usable evidence](no-evidence.png)
- [Conflicting evidence](conflicting-evidence.png)
- [Ambiguous follow-up](ambiguity.png)
- [Generation timeout](technical-failure.png)

The backend HTTP regression separately exercises the real conversation route
with deterministic inference fixtures. It verifies that a conflicting
evidence result carries observed counters, preserves the admitted snapshot
and empty citations, and invokes the assembler and grounded generator once.
The clarification regression confirms no grounded query runs.

## Validation

- Conversation backend suite with local tokenizer assets and deterministic
  inference fixtures. **42 passed, 0 skipped.**
- Frontend workspace, conversation, claim citations, Training Mode and
  export regression files. **93 passed across five files.**
- ESLint, TypeScript, Ruff on production Python paths, and Git whitespace
  checks passed. Ruff flags five unused fixture bindings in the backend
  test file on both the accepted base and the candidate.
