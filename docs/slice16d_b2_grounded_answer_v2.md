# Slice 16D-B2 — Grounded Answer V2 & Claim-Level Citations

```text
STATUS: IMPLEMENTATION EVIDENCE CANDIDATE
HUMAN ACCEPTANCE: PENDING

Implementation baseline:
0874ba6d2273393e392ce92bab8d6956eb287490

Accepted A2 design:
dce3456e519cb6c96570e20f5af800d00cafb5a7

A2 closeout:
f0bdf78d0ae6a79737055d324b22fc35e1e501f5

B1 foundation remediation:
ACCEPTED / SEALED
implementation: c68cc3f8f16a2588ba093886f3e48e1c7037f83f
closeout: b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90

Branch:
implementation/16d-b2-grounded-answer-v2

16D-B2: IMPLEMENTATION CANDIDATE / HUMAN ACCEPTANCE PENDING
16D-B3 / 16D-C: NOT AUTHORIZED
Slice 16: IN PROGRESS / NOT COMPLETE
```

## Scope delivered

Product `/query` now executes **Grounded Answer V2** through the same
retrieval/rerank/context/generation pipeline (no second RAG pipeline).

- Model-facing contract id: `grounded_answer_v2`
- Response-local evidence handles `E1…En`
- Strict block → evidence validation (fail closed)
- Deterministic public `answer` + additive `answer_blocks`
- Application-owned `citation_ref` (`c1…`) + bounded excerpts
- Structured `abstention_reason`
- Claim-level UI markers + hover/focus evidence card → Evidence pane
- Shared core prep: `run_grounded_query_core(retrieval_question, answer_intent, …)`

## V2 schema (model-facing)

Answered:

```json
{
  "abstain": false,
  "blocks": [
    {"text": "…", "evidence_handles": ["E1"]}
  ],
  "abstention_reason": null
}
```

Abstention (model-owned reasons only):

```json
{
  "abstain": true,
  "blocks": [],
  "abstention_reason": "insufficient_support"
}
```

Allowed model reasons: `insufficient_support` | `conflicting_evidence` |
`model_declined`. Model must not emit `no_evidence` or `ambiguous_request`.

## E-handle assignment

Accepted context order maps deterministically:

`first EvidenceUnit → E1`, `second → E2`, …

Prompt evidence uses `[EVIDENCE E1]…[/EVIDENCE E1]` with DOCUMENT/SECTION
trusted metadata. Canonical `ev_*` IDs remain internal/provenance only and are
not application-supplied citation language.

## Public projection

- `answer` = block texts joined by `\n\n`
- `answer_blocks[].citation_refs` = application `cN` refs
- `citations[]` ordered by first-reference unique evidence; one object per
  unique evidence unit
- Additive citation fields: `citation_ref`, `excerpt`, `excerpt_clipped`
- Excerpt: exact EvidenceUnit text, plain, max 400 Unicode chars, tags stripped

## Abstention matrix (standalone `/query`)

| Condition | status | abstention_reason | generator |
| --- | --- | --- | --- |
| empty evidence | insufficient_evidence | no_evidence | not invoked |
| non-empty insufficient (policy) | insufficient_evidence | insufficient_support | not invoked |
| model insufficient_support | model_abstain | insufficient_support | invoked |
| model conflicting_evidence | model_abstain | conflicting_evidence | invoked |
| model_declined | model_abstain | model_declined | invoked |
| answered | answered | null | invoked |

Standalone `/query` never emits `clarification_required` / `ambiguous_request`.

## Trace identity

Product traces use `build_product_v2_generation_config_hash`, matching the
executor V2 effective semantics (`prompt_contract` /
`output_contract` = `grounded_answer_v2`). Legacy evaluation paths keep
settings-driven v1 hashes.

## Legacy v1 preservation

Historical `grounded-answer-v1` parser/prompt/evaluation paths remain. Product
query runtime explicitly selects V2 via `product_v2=True`.

## Frontend

- Claim markers after each answer block (presentation numbers only)
- Hover **or** keyboard focus shows compact evidence card (escaped text)
- Enter / Space / click / tap opens exact citation in Evidence pane
- Detached “Evidence used” chips removed for answered V2 responses
- Session history key bumped to `seneca.ask-history.v2:` (legacy B1 entries not
  remapped)

## Tests / validation

Backend focused suite (required packet set + `test_grounded_answer_v2.py`):

- 99 passed
- 1 failed (pre-existing / unrelated to B2):
  `tests/unit/test_grounded_generation.py::test_unauthorized_endpoint_not_probed`
  — assertion expects `"not approved"`; runtime reason is
  `configured endpoint rejected by network policy: public_endpoint_forbidden`.
  Present on implementation baseline wording; B2 did not change probe logic.

Frontend:

- `npm run lint` — pass
- `npm run typecheck` — pass
- `npm test` — 69 passed (6 files), including
  `ui/src/test/slice16d_b2_claim_citations.test.tsx`
- `npm run build` — pass

Repository: `git diff --check` — clean for staged B2 changes.

## Manual product smoke

**Not performed** for this candidate (no live local provider + ingested-source
product walkthrough claimed). Automated coverage exercises schema, handles,
projection, product V2 orchestration, and claim-marker/card accessibility.

## Limitations / B3 deferrals

- No conversation orchestration / `/conversation/turn`
- No F7/F8/F9 layout/composer redesign
- Legacy B1 Ask product UX remains acceptance-withheld
- Narrow B1 shell intentionally retained for B2
