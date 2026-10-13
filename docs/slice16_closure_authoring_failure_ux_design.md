# Slice 16 closure — authoring-server failure UX design

**Authority:** `S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-AUTH-001` — AUTHORIZED  
**Status:** DESIGN IN PROGRESS / PARTIALLY FROZEN  
**Implementation:** NOT AUTHORIZED  
**Parent product surface:** Gold Lab baseline bootstrap (GAP-16G-02 / 9B propose)

### Freeze ledger

| ID | Topic | Disposition |
|---|---|---|
| Q1 | Mixed-attempt classification | ACCEPTED / FROZEN |
| Q2 | Model-unavailable class | ACCEPTED / FROZEN (deferred) |
| Q3 | Safe-reason identifiers | ACCEPTED / FROZEN |
| Q4 | Surfacing `failure_reason_counts` | ACCEPTED / FROZEN |
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

### 4.1 Model unavailable — Q2 ACCEPTED / FROZEN (deferred)

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q2 MODEL UNAVAILABLE / REJECTED CLASSIFICATION`  
**Disposition:** ACCEPTED / FROZEN

For this design, there is **no** separate `model_unavailable` operator-facing
failure class. All non-authentication HTTP failures at or above the existing
HTTP-error boundary remain `http_error`.

This includes responses that might, from provider-specific wording, appear to
mean model not found / unavailable / rejected / not loaded / unsupported /
deployment unavailable — unless a future authority establishes a strict,
machine-verifiable, non-heuristic signal.

**Frozen constraints:**

- no response-body substring matching
- no provider-message heuristics
- no inferred model state from arbitrary HTTP text
- no provider-specific special casing
- no new `model_unavailable` enum/class in this slice
- authentication remains `authentication_error`
- all other HTTP ≥400 failures remain `http_error`

A later slice may introduce `model_unavailable` only under a stable contract
(e.g. documented status/code field). That refinement may sit under Q1’s HTTP
tier without changing mixed-attempt priority.

---

## 5. Operator-safe terminal reason identifiers — Q3 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q3 OPERATOR-SAFE TERMINAL REASON IDENTIFIERS`  
**Disposition:** ACCEPTED / FROZEN

| Q1 terminal class | `details.reason` |
|---|---|
| authentication_error | `authoring_authentication_failed` |
| timeout | `authoring_request_timeout` |
| transport_error | `authoring_endpoint_unreachable` |
| http_error | `authoring_http_error` |
| evaluation/content-only failure | `zero_usable_proposals` |

**Frozen constraints:**

- These are terminal bootstrap reason identifiers, not adapter exception names.
- Existing admission/pre-run reasons remain unchanged
  (`authoring_not_ready`, `authoring_endpoint_unauthorized`,
  `proposal_count_exceeds_eligible_population`, …).
- `zero_usable_proposals` retains its corrected Q1 meaning: successful authoring
  interaction occurred sufficiently to evaluate output, but no usable proposals
  resulted, with no operational failure class present.
- No `authoring_model_unavailable` reason exists in this slice (Q2).
- No provider names, endpoint URLs, credentials, response bodies, or raw
  exception strings may be encoded into `details.reason`.
- Mixed failures first resolve through frozen Q1 priority, then map exactly once
  to the corresponding Q3 safe reason.

**Canonical transformation:**

```text
failure_reason_counts
  → Q1 deterministic terminal class
  → Q3 stable operator-safe details.reason
```

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

## 7. Propagation contract (partially frozen)

```text
9B propose completes with successful_count == 0
  → classify(failure_reason_counts, attempts)   # Q1
  → operation FAILED
  → ErrorCode: <Q5>
  → details.reason: <Q3 safe reason>
  → failure_reason_counts: NOT serialized to client  # Q4

Seneca operation / error UI
  → messageForGoldSafeReason(reason)            # Q6
  → operator-safe copy for that reason only
```

### 7.1 Failure_reason_counts surfacing — Q4 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q4 FAILURE_REASON_COUNTS SURFACING`  
**Disposition:** ACCEPTED / FROZEN

`failure_reason_counts` is **server-side classification evidence only**.

It may be used internally to determine:

```text
attempt evidence → Q1 highest-priority terminal class → Q3 details.reason
```

It must **not** be added to client-facing error details in this slice.

**Frozen constraints:**

- no new `SafeErrorDetails` field for `failure_reason_counts`
- no operator-facing counts map
- no new diagnostic API
- no provider/error histogram in the UI
- no raw adapter exception details exposed
- primary UX branches only on the frozen Q3 `details.reason`
- existing admission/progress fields remain unchanged

**Implementation invariant to test:**

```text
server may inspect failure_reason_counts
client response must not serialize failure_reason_counts
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
2. ~~Model unavailable~~ — Q2 FROZEN (deferred; remain `http_error`)
3. ~~Safe-reason identifiers~~ — Q3 FROZEN
4. ~~failure_reason_counts surfacing~~ — Q4 FROZEN (server-side only)
5. ErrorCode: keep `GOLD_CONFLICT` for all operational classes vs split codes (Q5)
6. UI copy strings for each safe reason (Q6)

**Implementation remains NOT AUTHORIZED until design freeze ACCEPT and a
separate implementation authority.**
