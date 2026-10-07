# Slice 16D-B2 — Grounded Answer V2 & Claim-Level Citations

```text
STATUS: COMPLETE / ACCEPTED / SEALED
HUMAN ACCEPTANCE: ACCEPTED
INDEPENDENT REVIEW: PASSED

Authorized implementation baseline:
0874ba6d2273393e392ce92bab8d6956eb287490

Initial implementation candidate:
7b6da5d31b3815cce8c5bae57c3165e510f5e1ca

Rework 1 accepted implementation:
baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149

REWORK:
16D-B2 REWORK 1 COMPLETE

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

16D-B2: COMPLETE / ACCEPTED / SEALED
16D-B3: AUTHORIZED BY HUMAN
        IMPLEMENTATION NOT YET STARTED
        ACTIVATION PENDING VERIFIED B2 CLOSEOUT
16D-C: NOT AUTHORIZED
16E–16H: NOT AUTHORIZED
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

### Rework 1 closures

**R1 — fail-closed V2 history referential integrity**
(`ui/src/features/ask/askHistory.ts`):

- Answered entries require non-empty `answer`, blocks, citations;
  `abstention_reason === null`; unique `citation_ref`s; every block ref
  resolves; plain `answer` equals block projection; public citation set equals
  first-reference unique order.
- Non-answered entries require B2 reason matrix only; reject
  `ambiguous_request`, arbitrary reasons, and answered/non-answered shape
  mismatches. Malformed rows dropped (no synthetic bindings).

**R2 — interactive claim evidence card**
(`ui/src/features/ask/ClaimAnswer.tsx`):

- Marker+card share one interaction root; leaving the root closes the card.
- Pointer can move from marker into the card / Open evidence without
  unmounting.
- Focus leave uses `queueMicrotask` + `document.activeElement` containment
  (jsdom/`relatedTarget` null-safe) so keyboard users can reach Open evidence.
- Removed no-op document `pointerdown` listener.

## Tests / validation

Backend focused suite (required packet set + `test_grounded_answer_v2.py`):

- Not re-run for Rework 1 (frontend-only code changes).
- Pre-existing / unrelated failure remains documented from prior candidate:
  `tests/unit/test_grounded_generation.py::test_unauthorized_endpoint_not_probed`
  (`"not approved"` vs `public_endpoint_forbidden`).

Frontend (Rework 1):

- `npm run lint` — pass
- `npm run typecheck` — pass
- `npm test` — 79 passed (6 files), including R1/R2 cases in
  `ui/src/test/slice16d_b2_claim_citations.test.tsx`
- `npm run build` — pass

Repository: `git diff --check` — clean for staged Rework 1 changes.

## Manual product smoke

Performed against restarted local API on B2 code + Vite UI + local generator
(`qwen3.6-35b-a3b` at configured openai-compatible endpoint) and workspace
`ws_1f0faad69b9041e7aa6c60190538ba7d` with ingested Week02/Week13 PDFs.

1. **Answered query (UI + API)**
   - V2 fields present: `answer_blocks`, `abstention_reason`, `citation_ref`,
     `excerpt`, `excerpt_clipped`.
   - Natural answer + claim marker `Citation 1: Week02 (1).pdf` after block.
   - No raw `ev_*` in Answer/card UI; no “Evidence used” chip row.
   - Evidence card showed source display name, page 3, section path, bounded
     excerpt; Open evidence → Evidence pane `Version 1 · page 3`.

2. **Multi-evidence (API)**
   - Status `answered`; 2 blocks; citations `c1,c2,c3` unique; block1
     `["c1","c2"]`, block2 `["c3"]`; excerpts from EvidenceUnits (400-char
     bound observed).

3. **No-evidence / empty retrieval**
   - Live tiny-text scopes always returned non-empty retrieval; observed
     `model_abstain` / `insufficient_support` with empty answer/blocks/citations
     (generator invoked). True application `insufficient_evidence` /
     `no_evidence` (generator not invoked) remains covered by automated
     backend tests; not manually induced on this corpus.

4. **Historical exact-version (UI)**
   - After removing unrelated `a.txt` (workspace rev 5→6, new snapshot), prior
     answered entries showed **Historical snapshot**.
   - Claim marker reopen showed Evidence `Week02 (1).pdf` **Version 1 · page 3**
     with Historical snapshot (not rebound to a newer source version).
   - Note: Week02 PDF replace attempt via PUT failed validation / interrupted;
     historical gate used snapshot bump via source remove instead.

5. **Structured model abstention**
   - Live: `model_abstain` / `insufficient_support` on nonce questions against
     tiny text sources (API). UI canned copy path covered by automated
     `abstentionCopy` tests; conflicting_evidence / model_declined not
     manually induced (fixture/automated coverage retained).

## Acceptance closeout

- Independent Rework-1 review: **PASS — RECOMMEND HUMAN ACCEPTANCE**
- Human acceptance: **ACCEPTED**
- Final status: **COMPLETE / ACCEPTED / SEALED**
- Accepted implementation SHA: `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`
- Frontend validation (Rework 1): lint / typecheck / 79 tests / build **PASS**
- Manual real-provider smoke: recorded above (not newly fabricated)
- Backend suite: not re-run for frontend-only Rework 1
- Previously documented unrelated backend failure
  (`test_unauthorized_endpoint_not_probed`) remains unrelated
- B2 did **not** implement B3 conversational orchestration or 16D-C

## Limitations / B3 deferrals

- No conversation orchestration / `/conversation/turn` in B2
- No F7/F8/F9 layout/composer redesign in B2
- Legacy B1 Ask product UX remains acceptance-withheld
- Narrow B1 shell intentionally retained through B2
- **16D-B3** is human-authorized but **not started**; activation awaits
  verified B2 closeout
