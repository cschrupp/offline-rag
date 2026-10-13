# Slice 16 closure — authoring-server failure UX design

**Design authority:** `S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-AUTH-001` — AUTHORIZED  
**Design freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-FREEZE-001` — ACCEPTED / FROZEN  
**Independent design review:** `S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-IR-001` — REWORK REQUIRED  
**Reviewed subject (IR-001):** `ea95a2fe5261a42c8d841a4789f6aed1b9028cc7`  
**Design rework:** R1 / R2 / R3 — ACCEPTED / FROZEN (amends FREEZE-001; no new Human Authority)  
**Status:** DESIGN FROZEN / READY FOR INDEPENDENT DESIGN RE-REVIEW  
**Implementation:** NOT AUTHORIZED  
**Parent product surface:** Gold Lab baseline bootstrap (GAP-16G-02 / 9B propose)

### Freeze ledger

| ID | Topic | Disposition |
|---|---|---|
| Q1 | Mixed-attempt classification | ACCEPTED / FROZEN (amended by R2 / R3) |
| Q2 | Model-unavailable class | ACCEPTED / FROZEN (deferred) |
| Q3 | Safe-reason identifiers | ACCEPTED / FROZEN |
| Q4 | Surfacing `failure_reason_counts` | ACCEPTED / FROZEN |
| Q5 | ErrorCode choice | ACCEPTED / FROZEN |
| Q6 | Operator UI copy | ACCEPTED / FROZEN (amended by R3) |
| Q7 | Design freeze completeness | ACCEPTED / FROZEN (reaffirmed after R1–R3) |
| R1 | Typed ProposePreRunError classification | ACCEPTED / FROZEN |
| R2 | Authentication provenance | ACCEPTED / FROZEN |
| R3 | Auth/authz copy + redirect classification | ACCEPTED / FROZEN |

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
   mapped to `zero_usable_proposals`, and the eligible-population case is
   currently selected by brittle `str(exc)` substring matching.

Operator UI (`ui/src/features/goldLab/errors/goldLabErrors.ts`) maps
`zero_usable_proposals` to copy that implies authoring completed without usable
candidates — even when every attempt was a transport/auth/timeout/HTTP failure.

**Invariant violated:** transport/server failure collapses into
`zero_usable_proposals`.

**IR-001 additional defects (design-level, at reviewed SHA):**

- F001: `ProposePreRunError` has no stable machine-readable reason; classification
  via message text is non-deterministic.
- F002: adapter `authentication_error` can be emitted for local readiness/privacy
  failures, which must not become `authoring_authentication_failed`.
- F003: Q6 auth copy says only “authentication” while 403 is authorization; and
  `REDIRECT_NOT_ALLOWED` was classified under unreachable transport copy.

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

**R2 / R3 note:** adapter emission of `authentication_error` for local
readiness/privacy failures is an implementation defect relative to this freeze.
Those local paths must retain truthful local safe reasons and must not enter the
Q1 authentication class. `REDIRECT_NOT_ALLOWED` remains a distinct
`ProposalFailureReason` but classifies under the Q1 HTTP tier (R3).

---

## 4. Required operator-facing distinctions (minimum)

The frozen taxonomy MUST distinguish at least:

1. Server / endpoint unreachable (transport)
2. Request timeout
3. Authentication / authorization failure
4. HTTP / server response Seneca could not accept
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
- authentication remains `authentication_error` only under R2 provenance
- all other HTTP ≥400 failures remain `http_error`
- disallowed redirect (`REDIRECT_NOT_ALLOWED`) remains in the HTTP tier (R3)

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
- Identifier `authoring_authentication_failed` is preserved (Q3); operator copy
  truthfully covers authentication or authorization (R3).

**Canonical transformation:**

```text
failure_reason_counts
  → Q1 deterministic terminal class
  → Q3 stable operator-safe details.reason
```

---

## 6. Mixed-attempt classification — Q1 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q1 MIXED-ATTEMPT CLASSIFICATION`  
**Disposition:** ACCEPTED / FROZEN (amended by R2 / R3)

**Applicability:** `successful_count < 1` and proposal attempts contain one or
more classified failure reasons.

**Classification rule:** Choose the highest-priority observed failure class
across the complete set of attempt evidence. Never use last-attempt-wins /
last-error-wins.

**Priority (highest → lowest):**

1. `authentication_error`
   - **only** upstream HTTP 401 or HTTP 403 under R2 provenance
2. `timeout`
3. `transport_error`
   - connection refused / unreachable
   - DNS / socket / transport failure
   - **not** redirect-not-allowed (R3)
4. `http_error`
   - generic non-auth HTTP failure (`HTTP_ERROR`)
   - `REDIRECT_NOT_ALLOWED` (disallowed HTTP redirect; R3)
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
| redirect-not-allowed + evaluation rejection | http_error |
| evaluation rejection + unusable/empty model output only | zero_usable_proposals |

**Q1 boundary:** Does **not** decide whether a specific HTTP status/body can
safely become `model_unavailable`. Until that later freeze, those cases remain
`http_error`; no heuristic string matching may promote them.

### 6.1 ProposePreRunError — DESIGN REWORK R1 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — DESIGN REWORK R1 TYPED PROPOSE PRE-RUN CLASSIFICATION`  
**Disposition:** ACCEPTED / FROZEN  
**Closes IR-001 finding:** F001

`ProposePreRunError` handling is within this design.

Use a closed internal discriminator, conceptually `ProposePreRunReason`:

| Member | Meaning |
|---|---|
| `AUTHORING_NOT_READY` | readiness gate failed |
| `AUTHORING_ENDPOINT_UNAUTHORIZED` | privacy / allowlist / network-policy rejection |
| `NO_ELIGIBLE_POPULATION` | captured ChunkSet has no eligible source children |
| `PROPOSAL_COUNT_INVALID` | SamplingError for invalid count (e.g. `count <= 0`) |
| `PROPOSAL_COUNT_EXCEEDS_ELIGIBLE_POPULATION` | requested count exceeds eligible population |
| `OUTPUT_EXISTS` | output path exists without force |
| `SOURCE_SNAPSHOT_UNAVAILABLE` | CLI wrapper ChunkAccessError / snapshot unavailable |

`ProposePreRunError` **MUST** carry that discriminator structurally (e.g. required
`reason: ProposePreRunReason`). The human-readable exception message may remain
for logs/CLI diagnostics but **MUST NOT** participate in bootstrap classification.

**Gold bootstrap mapping (`details.reason`):**

| Internal reason | Bootstrap `details.reason` |
|---|---|
| `AUTHORING_NOT_READY` | `authoring_not_ready` |
| `AUTHORING_ENDPOINT_UNAUTHORIZED` | `authoring_endpoint_unauthorized` |
| `PROPOSAL_COUNT_EXCEEDS_ELIGIBLE_POPULATION` | `proposal_count_exceeds_eligible_population` |
| `NO_ELIGIBLE_POPULATION` | `bootstrap_internal_failure` |
| `PROPOSAL_COUNT_INVALID` | `bootstrap_internal_failure` |
| `OUTPUT_EXISTS` | `bootstrap_internal_failure` |
| `SOURCE_SNAPSHOT_UNAVAILABLE` | `bootstrap_internal_failure` if it somehow reaches this bootstrap catch; normally unreachable because bootstrap already owns captured-snapshot resolution |

The last group is intentionally fail-closed. In the authorized bootstrap path,
`proposal_count` has already been validated, `force=True` is used, and snapshot
capture/resolution has its own handling. Reaching those pre-run reasons means an
invariant/path mismatch, not “zero usable proposals.”

**Frozen constraints:**

- NO `str(exc)` classification.
- NO substring matching such as `"exceeds eligible"`.
- Every `ProposePreRunError` raise site MUST assign a `ProposePreRunReason`.
- Bootstrap switches on `exc.reason` only.
- An unknown, missing, or future unhandled `ProposePreRunReason` MUST fail closed
  as `GOLD_CONFLICT` (or the existing appropriate coarse envelope) +
  `bootstrap_internal_failure`, and MUST NEVER become `zero_usable_proposals`.
- `zero_usable_proposals` is not a `ProposePreRunError` fallback.
- Existing user/operator-safe admission reasons remain unchanged where an exact
  typed mapping exists.
- This typed discriminator is internal; it does not add a client API field.
- Do **not** define an enum member literally named `UNKNOWN`. A closed enum plus a
  defensive unhandled-value fallback in bootstrap gives the desired behavior
  without legitimizing producers emitting an unspecified classification.

### 6.2 Authentication provenance — DESIGN REWORK R2 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — DESIGN REWORK R2 AUTHENTICATION PROVENANCE`  
**Disposition:** ACCEPTED / FROZEN  
**Closes IR-001 finding:** F002

| | |
|---|---|
| Q1 class | `authentication` |
| Q3 safe reason | `authoring_authentication_failed` |

**MAY be produced ONLY from:** an actual upstream HTTP 401 or HTTP 403 response
returned by the configured authoring request.

**Everything local remains outside that class:**

| Local evidence | Safe reason / mapping |
|---|---|
| readiness failure | `authoring_not_ready` |
| privacy / allowlist / network-policy rejection | `authoring_endpoint_unauthorized` or its already-existing truthful admission/pre-run mapping |
| model not configured / not approved | `authoring_not_ready` |
| endpoint not approved | `authoring_endpoint_unauthorized` |
| local hostname/network-policy authorization failure | `authoring_endpoint_unauthorized` or existing local failure mapping |

**Critical invariant:**

```text
authoring_authentication_failed
  ⇒ Seneca actually received an upstream 401 or 403

No upstream 401/403
  ⇒ authoring_authentication_failed is FORBIDDEN
```

**Frozen constraints:**

- No inference from `readiness.reason_codes`.
- No inference from `AuthoringPrivacyError`.
- No parsing of exception text.
- No provider-specific heuristics.
- No `SafeErrorDetails` expansion.
- No new diagnostic API.
- Existing local admission/pre-run safe reasons remain authoritative.

### 6.3 Redirect + auth/authz truthfulness — DESIGN REWORK R3 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — DESIGN REWORK R3 TRUTHFUL AUTH/AUTHZ + REDIRECT CLASSIFICATION`  
**Disposition:** ACCEPTED / FROZEN  
**Closes IR-001 finding:** F003

**A — authentication/authorization copy** (identifier preserved):

`authoring_authentication_failed` operator copy covers authentication **or**
authorization rejection for the R2-frozen provenance (upstream 401 or 403).

**B — redirect classification:**

```text
ProposalFailureReason.REDIRECT_NOT_ALLOWED
  → Q1 http_error tier
  → authoring_http_error
```

It MUST NOT map to `transport_error` or `authoring_endpoint_unreachable`, because
receipt of a redirect proves an HTTP response was received.

**HTTP bucket explicitly includes:**

- `HTTP_ERROR`
- `REDIRECT_NOT_ALLOWED`

**Frozen constraints:**

- no separate redirect safe reason
- no redirect body/location exposed
- no redirect-follow behavior change
- no provider-specific parsing
- no status code shown to the operator
- `authoring_endpoint_unreachable` only means actual transport reachability failure
- `authoring_authentication_failed` only means upstream 401/403
- `authoring_http_error` covers generic non-auth HTTP failure + disallowed redirect

---

## 7. Propagation contract (frozen)

```text
9B propose completes with successful_count == 0
  → classify(failure_reason_counts, attempts)   # Q1 (+ R2/R3)
  → operation FAILED
  → ErrorCode: GOLD_CONFLICT                     # Q5
  → details.reason: <Q3 safe reason>
  → failure_reason_counts: NOT serialized to client  # Q4

Seneca operation / error UI
  → messageForGoldSafeReason(reason)            # Q6 FROZEN (+ R3)
  → operator-safe copy for that reason only
```

### 7.3 Operator UI copy — Q6 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q6 OPERATOR UI COPY`  
**Disposition:** ACCEPTED / FROZEN (amended by R3)

Exact normative `messageForGoldSafeReason` strings:

| `details.reason` | Exact operator copy |
|---|---|
| `authoring_authentication_failed` | The configured Gold Lab authoring server rejected authentication or authorization. Check the authoring API key and Settings, then try again. |
| `authoring_request_timeout` | The Gold Lab authoring server did not respond in time. Confirm the server is running and reachable, then try again. |
| `authoring_endpoint_unreachable` | Seneca could not reach the configured Gold Lab authoring server. Confirm the endpoint in Settings and that the server is running, then try again. |
| `authoring_http_error` | The configured Gold Lab authoring endpoint returned a response Seneca could not accept. Check authoring Settings and server logs, then try again. |
| `zero_usable_proposals` | Gold Lab authoring completed its calls but did not produce usable candidate questions from this workspace publication. |

**Semantic distinctions (must be tested):**

| Class | Meaning |
|---|---|
| authentication | upstream responded with HTTP 401 or 403; authentication or authorization rejected |
| timeout | request did not complete within the allowed time |
| transport | endpoint could not be reached |
| HTTP | endpoint responded with a non-auth result Seneca could not accept (including disallowed redirect) |
| zero_usable_proposals | authoring calls completed sufficiently to evaluate output, but no usable candidate questions resulted |

**Frozen constraints:**

- Exact copy above is normative for this slice.
- No provider names, endpoint URL values, credentials, HTTP status codes, raw
  response bodies, or raw exception strings.
- No model-unavailable inference.
- Operational failures must not imply that proposal outputs were evaluated.
- `zero_usable_proposals` must not be shown for Q1 operational failure classes.
- Existing admission-failure copy remains unchanged.

**Required regression (original defect):**

```text
authoring server stopped / connection refused
  → authoring_endpoint_unreachable
  → "Seneca could not reach the configured Gold Lab authoring server..."
  → MUST NOT show zero_usable_proposals copy
```

### 7.2 ErrorCode — Q5 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q5 ERRORCODE FOR CLASSIFIED POST-ADMISSION TERMINAL FAILURES`  
**Disposition:** ACCEPTED / FROZEN

All Q1→Q3 terminal classes use:

| Terminal class | ErrorCode | `details.reason` |
|---|---|---|
| authentication | `GOLD_CONFLICT` | `authoring_authentication_failed` |
| timeout | `GOLD_CONFLICT` | `authoring_request_timeout` |
| transport/unreachable | `GOLD_CONFLICT` | `authoring_endpoint_unreachable` |
| HTTP failure | `GOLD_CONFLICT` | `authoring_http_error` |
| evaluation/content-only | `GOLD_CONFLICT` | `zero_usable_proposals` |

**Semantic split:**

- `ErrorCode` → coarse failed-operation category
- `details.reason` → precise operator-safe authoring failure classification

**Frozen constraints:**

- Applies only after authoring admission has succeeded.
- Existing admission/pre-run ErrorCode behavior is unchanged.
- Do not introduce new ErrorCode values for this closure slice.
- Do not translate upstream authoring authentication failure into Seneca
  client/user authentication or authorization semantics.
- Do not use HTTP status/error-code differences as a second competing
  classification channel.
- UI copy for these failures branches on frozen Q3 `details.reason`.
- `zero_usable_proposals` keeps `GOLD_CONFLICT` exactly as before, with
  corrected Q1 meaning.
- Retryability must not be inferred from `GOLD_CONFLICT` alone; the safe
  reason remains the discriminant if retry guidance is later frozen.

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

## 8. Scope boundary (frozen)

### IN SCOPE

- deterministic classification of existing authoring failure evidence
- corrected bootstrap terminal reason
- existing `GOLD_CONFLICT` envelope
- exact operator-safe UI copy
- tests proving classification and non-leakage of `failure_reason_counts`
- typed `ProposePreRunError` / `ProposePreRunReason` contract (R1)
- authentication provenance limited to upstream 401/403 (R2)
- redirect classified under HTTP tier with truthful copy (R3)

### OUT OF SCOPE

- new provider diagnostics
- `model_unavailable`
- body/status heuristics
- new `SafeErrorDetails` fields
- new diagnostic API
- connectivity probes / health monitoring
- retry redesign
- authoring configuration changes
- 16J branding
- 16K capacity work
- Slice 16 final closeout
- Changing proposal prompts, sampling, quality gates, pooling science
- Changing Gold ledger / QC / RF / ES / CD policy

---

## 9. Design freeze completeness — Q7 ACCEPTED / FROZEN

**Authority freeze:** `S16-CLOSURE-AUTHORING-FAILURE-UX — Q7 DESIGN FREEZE COMPLETENESS`  
**Disposition:** ACCEPTED / FROZEN (reaffirmed after R1–R3)

Q1–Q6, as amended by DESIGN REWORK R1–R3, constitute the complete design freeze
for this closure gate under:

`S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-FREEZE-001` — ACCEPTED / FROZEN

| Freeze | Summary |
|---|---|
| Q1 | Highest-priority observed class wins; any operational evidence forbids `zero_usable_proposals`; HTTP includes `REDIRECT_NOT_ALLOWED` |
| Q2 | No separate `model_unavailable`; non-auth HTTP remains `http_error` |
| Q3 | Exact Q3 `details.reason` identifiers |
| Q4 | `failure_reason_counts` server-side only; not client-serialized |
| Q5 | All five post-admission terminals: `GOLD_CONFLICT` + Q3 reason |
| Q6 | Exact five Seneca operator strings (auth/authz + response-not-accepted wording) |
| R1 | Closed `ProposePreRunReason`; bootstrap switches on `exc.reason` only; unhandled → `bootstrap_internal_failure` |
| R2 | `authoring_authentication_failed` only from upstream HTTP 401/403 |
| R3 | Auth copy covers authz; redirect → HTTP tier |
| Q7 | Design decision surface closed; ready for independent design re-review |

**Next gate:** independent design re-review of this successor tip.  
**Implementation:** NOT AUTHORIZED until separate implementation authority after design IR ACCEPT.
