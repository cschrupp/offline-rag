# Slice 16 closure — authoring-server failure UX design

**Authority:** `S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-AUTH-001` — AUTHORIZED  
**Status:** DESIGN IN PROGRESS / PARTIALLY FROZEN  
**Implementation:** NOT AUTHORIZED  
**Parent product surface:** Gold Lab baseline bootstrap (GAP-16G-02 / 9B propose)

### Freeze ledger

| ID | Topic | Disposition |
|---|---|---|
| Q1 | Mixed-attempt classification | ACCEPTED / FROZEN |
| Q2 | Model-unavailable class | OPEN |
| Q3 | Safe-reason identifiers | OPEN |
| Q4 | Surfacing `failure_reason_counts` | OPEN |
| Q5 | ErrorCode choice | OPEN |
| Q6 | Operator UI copy | OPEN |

This design does **not** close Slice 16, authorize 16J/16K, or change authoring
science (prompts, sampling, quality gates, pooling).

---

## 1. Observed defect (authoritative)

Bootstrap path today (`src/offline_rag/app/gold_lab/bootstrap.py`):

1. Adapter outcomes during 9B propose are recorded per attempt with
   `ProposalFailureReason` and aggregated as `failure_reason_counts`
   (`src/offline_rag/gold_authoring/propose.py`).
2. When `run.successful_count < 1`, bootstrap always terminalizes with safe
   reason `zero_usable_proposals`.
3. Pre-run `ProposePreRunError` (except the eligible-population case) is also
   mapped to `zero_usable_proposals`.

Operator UI (`ui/src/features/goldLab/errors/goldLabErrors.ts`) maps
`zero_usable_proposals` to copy that implies authoring completed without usable
candidates — even when every attempt was a transport/auth/timeout/HTTP failure.

**Invariant violated:** transport/server failure collapses into
`zero_usable_proposals`.

---

## 2. Design mission

Freeze a deterministic classification and propagation contract:

```text
authoring adapter outcome
  → proposal attempt evidence
  → bootstrap failure classification
  → API/operator-safe reason
  → truthful Seneca UI copy
```

`zero_usable_proposals` MUST mean: authoring calls were sufficiently successful
to evaluate outputs, but none yielded usable candidates.

---

## 3. Existing attempt evidence (must be preserved)

Adapter (`OpenAICompatibleAuthoringAdapter`) already emits:

| Adapter `failure_reason` | Propose mapping |
|---|---|
| `timeout` | `ProposalFailureReason.TIMEOUT` / `failed_transport` |
| `transport_error` | `TRANSPORT_ERROR` / `failed_transport` |
| `http_error` | `HTTP_ERROR` / `failed_transport` |
| `authentication_error` | `AUTHENTICATION_ERROR` / `failed_transport` |
| `redirect_not_allowed` | `REDIRECT_NOT_ALLOWED` / `failed_transport` |
| `empty_response` | `EMPTY_RESPONSE` / `failed_response` |

Propose also records non-transport evaluation failures:
`invalid_json`, `schema_invalid`, quality rejects, `proposal_context_unavailable`.

`ProposeJobResult.failure_reason_counts` already aggregates these. Design
preference: **promote this evidence** into bootstrap classification; do not invent
a parallel diagnostic subsystem unless classification cannot be derived from
counts + attempt statuses.

---

## 4. Required operator-facing distinctions (minimum)

The frozen taxonomy MUST distinguish at least:

1. Server / endpoint unreachable (transport)
2. Request timeout
3. Authentication / authorization failure
4. HTTP / server error
5. Configured model unavailable or rejected, **if independently knowable**
6. Genuine successful authoring calls producing zero usable proposals

### 4.1 Current knowability note (pre-freeze)

- Timeout, transport, auth (HTTP 401/403), and generic HTTP ≥400 are already
  independently labeled by the adapter.
- “Model unavailable/rejected” is **not** currently a separate adapter reason;
  many local stacks return HTTP 404/400/500 with body text. Design freeze must
  decide whether to:
  - keep these under `http_error` / a new HTTP-class safe reason, or
  - add a narrowly parsed model-unavailable class when response evidence is
    unambiguous.

---

## 5. Proposed operator-safe reason codes (DRAFT — not frozen)

Recommended additive safe reasons (names draft):

| Safe reason | Meaning |
|---|---|
| `authoring_endpoint_unreachable` | Transport failure reaching the configured endpoint |
| `authoring_request_timeout` | Authoring request timed out |
| `authoring_authentication_failed` | HTTP 401/403 or equivalent auth failure during invoke |
| `authoring_http_error` | Other HTTP ≥400 from authoring server |
| `authoring_model_unavailable` | *(optional)* Model rejected/unavailable when independently knowable |
| `zero_usable_proposals` | Calls succeeded enough to evaluate; zero usable candidates |

Pre-existing sync/admission reasons remain unchanged:
`authoring_not_ready`, `authoring_endpoint_unauthorized`, etc.

UI copy MUST be truthful and must not instruct the operator that proposals were
evaluated when only transport failed.

---

## 6. Mixed-attempt classification — Q1 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q1 MIXED-ATTEMPT CLASSIFICATION`  
**Disposition:** ACCEPTED / FROZEN

**Applicability:** `successful_count < 1` and proposal attempts contain one or
more classified failure reasons.

**Classification rule:** Choose the highest-priority observed failure class
across the complete set of attempt evidence. Never use last-attempt-wins /
last-error-wins.

**Priority (highest → lowest):**

1. `authentication_error`
2. `timeout`
3. `transport_error`
   - connection refused / unreachable
   - DNS / socket / transport failure
   - redirect-not-allowed or equivalent endpoint transport-policy rejection
4. `http_error`
   - generic HTTP failure
   - any later-frozen model-unavailable subtype is classified within/refined
     from this class, without changing Q1 priority
5. evaluation/content-only failure → `zero_usable_proposals`

**Invariant:** `zero_usable_proposals` is legal **ONLY** when no authentication,
timeout, transport, or HTTP failure evidence exists.

Therefore any operational/infrastructure failure evidence **MUST NOT** emit
`zero_usable_proposals`.

**Aggregation source:** Use the complete observed failure evidence /
`failure_reason_counts` for the proposal run. Do not infer the terminal reason
from iteration order.

**No-success examples:**

| Observed evidence | Terminal class |
|---|---|
| auth + timeout | authentication_error |
| timeout + transport | timeout |
| transport + HTTP error | transport_error |
| HTTP error + evaluation rejection | http_error |
| evaluation rejection + unusable/empty model output only | zero_usable_proposals |

**Q1 boundary:** Does **not** decide whether a specific HTTP status/body can
safely become `model_unavailable`. Until that later freeze, those cases remain
`http_error`; no heuristic string matching may promote them.

Pre-run failures (`ProposePreRunError`) must map to the correct safe reason
(population oversize stays; unauthorized/not-ready stay; must **not** default to
`zero_usable_proposals`).

---

## 7. Propagation contract (DRAFT — not frozen)

```text
9B propose completes with successful_count == 0
  → classify(failure_reason_counts, attempts)
  → operation FAILED
  → ErrorCode: GOLD_CONFLICT (unless a stronger existing code is frozen)
  → details.reason: <classified safe reason>
  → optional details.failure_reason_counts: existing counts (if already exposed
     or trivially promotable without a new subsystem)

Seneca operation / error UI
  → messageForGoldSafeReason(reason)
  → operator-safe copy for that reason only
```

No connectivity probing, background health monitors, provider-specific SDKs,
model downloads, authoring config redesign, or retry policy expansion beyond
existing semantics.

---

## 8. Explicit non-goals

- 16J branding
- 16K capacity work
- Slice 16 closeout
- Changing proposal prompts, sampling, quality gates, pooling science
- Changing Gold ledger / QC / RF / ES / CD policy
- Parallel telemetry platform

---

## 9. Remaining freeze questions

1. ~~Mixed-attempt priority~~ — Q1 FROZEN
2. Whether `model_unavailable` is a separate class in this slice (Q2)
3. Exact safe-reason string identifiers (Q3)
4. Whether `failure_reason_counts` is surfaced in operation error details (Q4)
5. ErrorCode: keep `GOLD_CONFLICT` for all operational classes vs split codes (Q5)
6. UI copy strings for each safe reason (Q6)

**Implementation remains NOT AUTHORIZED until design freeze ACCEPT and a
separate implementation authority.**
