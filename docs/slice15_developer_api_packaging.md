# Slice 15 — Developer API and single-container packaging

**Status:** Architecture **COMPLETE / LOCKED** (S15-D01 … S15-D22)  
**Pre-implementation contract (Residual A):** **LOCKED / ACCEPTED**  
**Implementation plan:** [`docs/slice15_implementation_plan.md`](slice15_implementation_plan.md) — **ACCEPTED**  
**Code implementation:** phased — **15A/15B/15C COMPLETE / ACCEPTED**; **15D–15H NOT AUTHORIZED**

**Architecture + Residual A authority:** this document.  
**Authority SHA (design + Residual A):** `6583fb3be64f2c66e8655b8b99166c358f8f0844`  
**Drafting baseline HEAD (pre-artifact):** `3ed9212c777798338d5b2229eff7d7aabe3d5adb`  
**Milestone:** Milestone 7 **IN PROGRESS**; Slice 14 **COMPLETE / ACCEPTED**.  
**Landed implementation head (15C):** `5d70be09a3534a093bad9754f4051840ed1fde92`  
**15C merge commit:** `47a11f1968be75cf772fc7a9e4447ee26e283c52`

This document remains the reviewable architecture authority. Conversation history
is not an authority once this artifact is accepted at a committed SHA. Later
phases still require explicit per-phase implementation authorization.

---

## 0. Gate status

```text
MILESTONE 7:                          IN PROGRESS
SLICE 14:                             COMPLETE / ACCEPTED
SLICE 15 ARCHITECTURE (D01–D21):      COMPLETE / LOCKED
S15-D22 CONSOLIDATION BOUNDARY:       LOCKED / ACCEPTED
SLICE 15 RESIDUAL A:                  LOCKED / ACCEPTED
SLICE 15 IMPLEMENTATION PLAN:         ACCEPTED
PHASE 15A:                            COMPLETE / ACCEPTED
PHASE 15B:                            COMPLETE / ACCEPTED
PHASE 15C:                            COMPLETE / ACCEPTED
PHASE 15D:                            NOT AUTHORIZED
PHASES 15E–15H:                       NOT AUTHORIZED
S15-D20 TRANSPORT-ORDER CLARIFICATION: LOCKED / ACCEPTED
```

Architecture may reopen only for a concrete contradiction, missing required
semantic contract, or demonstrated implementation impossibility under D01–D22.
Silent amendment of locked decisions is forbidden. Narrow D22 reopen amendments
must be committed as explicit locked clarifications (see S15-D20 transport order).

---

## 1. Objective

Expose the accepted OfflineRAG grounded path through a stable local HTTP API and
package it as one application container with external host generation (Ollama /
OpenAI-compatible), without inventing a second RAG pipeline.

---

## 2. Locked architecture decisions (S15-D01 … S15-D22)

Later decisions refine earlier public shapes where noted (especially D21 vs early
D04/D07 request/response wording).

### S15-D01 — Canonical application boundary

**LOCKED / ACCEPTED**

- Product use-case boundary: `src/offline_rag/app/`
- Adapters (CLI, FastAPI, future UI) → app → existing domain/infrastructure
- App coordinates accepted components; does not reimplement domain algorithms
- Forbidden: FastAPI → `cli.py`; CLI → HTTP for normal local use; route-owned
  pipeline orchestration; domain → app upward dependency
- Form: boundary + lifecycle + typed contracts; not mandatory `*Service` classes

### S15-D02 — Process lifecycle scoping

**LOCKED / ACCEPTED**

Three scopes:

| Scope | Examples |
|---|---|
| Process lifespan | `AppSettings` snapshot; embedder; reranker; generator HTTP client; Qdrant Local infrastructure; app runtime/dependency registry |
| Corpus-scoped cached runtime | Lexical handle; corpus/index state; retriever wiring; corpus-bound query graph / orchestrator — only via app-owned cache keyed by corpus/index identity + explicit invalidation |
| Request / invocation | Validated input; `trace_id`; deadline/cancellation; result/error DTOs; ephemeral diagnostics |

- Settings are an immutable process snapshot; hot reload **OUT OF SCOPE**
- Adapters call lifecycle; they do not load models or open Qdrant themselves

### S15-D03 — Corpus concurrency and mutation semantics

**LOCKED / ACCEPTED**

- Reads: snapshot-consistent; bind published identity at request start
- Writes: serialized per corpus; fail-closed `corpus_busy`; no default queue
- Exclusion: storage-backed corpus lease (cross-process); not memory-only
- Publication: build candidate → validate → atomic publish; failed mutation leaves prior published snapshot
- Live in-place destructive rebuild of the published backing while readers use it: **FORBIDDEN**
- Global lock across corpora: **FORBIDDEN**

### S15-D04 — CorpusReadSnapshot and query resolution

**LOCKED / ACCEPTED**

- Client supplies logical corpus name (not scientific IDs)
- App resolves exactly one published immutable `CorpusReadSnapshot`
- `snapshot_id` = deterministic identity of the canonical snapshot manifest
  (not publication counter, timestamp, or random UUID)
- Request remains pinned to that snapshot for the full invocation
- Product pin-by-identity query API: **OUT OF SCOPE**
- Silent mode/capability downgrade: **FORBIDDEN**

Public request options were further constrained by **D06/D21** (no client mode
or scientific knobs).

### S15-D05 — Product `/ingest` transaction

**LOCKED / ACCEPTED**

- High-level mutation: source → accepted ingest → chunk → required indexes →
  compatibility validation → candidate snapshot → atomic publication
- No public stage endpoints (`/chunk`, `/index`, …) in Slice 15
- Synchronous to terminal outcome; no job queue / `202` / poll API
- Cancel/abort before publication ⇒ no publish
- Target: full readiness for the single grounded product mode (D06)

### S15-D06 — Product query mode

**LOCKED / ACCEPTED**

- Exactly one canonical grounded product path (`GroundedAnswerOrchestrator` stack)
- Not a Slice 14 “production winner” claim
- No client algorithm/mode selection
- `product_mode_id` is server-owned response provenance
- Retrieve-ladder remains CLI/eval/research only
- Ingest must publish full grounded readiness; silent downgrade forbidden

### S15-D07 — Query outcomes and HTTP semantics

**LOCKED / ACCEPTED**

| Layer | HTTP | Discriminant |
|---|---|---|
| Normal grounded terminal | **200** | `status`: `answered` \| `insufficient_evidence` \| `model_abstain` |
| Execution/API failure | non-2xx | D08 error envelope |

- `generation_failed` / parse / citation failures are **not** 200 statuses
- Public success field naming finalized in **D21** as `status` (not a parallel name)

### S15-D08 — Application error taxonomy

**LOCKED / ACCEPTED** (with additive codes from later decisions)

Envelope:

```text
ErrorResponse
├── error.code
├── error.message
├── retryable          # mandatory top-level
├── trace_id?
└── details?           # allowlisted only
```

Owner: `offline_rag.app`. FastAPI/CLI translate only.

| code | HTTP | retryable | Notes |
|---|---|---|---|
| `request_invalid` | 422 | false | Incl. normalized FastAPI/Pydantic validation |
| `document_invalid` | 422 | false | Bad ingest document/payload |
| `document_unknown` | 404 | false | Not in resolved published snapshot |
| `corpus_unknown` | 404 | false | Logical corpus not product-visible |
| `corpus_not_ready` | 409 | false | Exists but no grounded-capable published snapshot |
| `corpus_busy` | 409 | true | Mutation lease held |
| `snapshot_unavailable` | 409 | false* | Published snapshot cannot be bound/read safely |
| `ingest_failed` | 500 | false | Internal ingest/index candidate failure |
| `generation_unavailable` | 502 | true | Provider connectivity/auth/protocol |
| `generation_timeout` | 504 | true | Generator timed out |
| `generation_failed` | 502 | false | Unusable provider-level result (default) |
| `response_parse_error` | 502 | false | Structured output contract failure |
| `citation_invalid` | 502 | false | Post-generation citation validation failed |
| `runtime_not_ready` | 503 | true | App runtime not ready / draining |
| `service_overloaded` | 503 | true | Healthy but no expensive capacity |
| `request_timeout` | 504 | true | App operation deadline |
| `request_cancelled` | n/a† | true | Durable trace classification for cancelled query |
| `trace_unknown` | 404 | false | Missing/expired/uncommitted trace |
| `internal_error` | 500 | false | Unexpected orchestration failure |

\* Retrying immediately is not something clients should assume helps.  
† `request_cancelled` is application/trace-terminal only under D18: it has **no
normative HTTP status**. Implementations must not invent `499`, `408`, or another
HTTP mapping for the already-disconnected-peer case.

- `mode_not_ready`: **not** in Slice 15 catalog
- Framework-native validation bodies: **forbidden**; normalize to envelope
- Clients branch on `error.code`, never `error.message`
- Automatic server retries: **not authorized** by taxonomy alone

### S15-D09 — Health / liveness / readiness

**LOCKED / ACCEPTED**

| Endpoint | Meaning | Success | Failure |
|---|---|---|---|
| `GET /health/live` | Process/HTTP alive | 200 `{status: live}` | process down |
| `GET /health/ready` | App runtime ready | 200 allowlisted ready fields | 503 `runtime_not_ready` |
| `GET /health` | Liveness alias | same as live | — |

- Corpus queryability is **not** process readiness
- No model load, generation call, or `/v1/models` on probes
- Ready inspects cheap app-owned state from startup (D02); may flip READY→NOT_READY on known fatal degradation
- No background health daemon required

### S15-D10 — `/documents` product boundary

**LOCKED / ACCEPTED**

- `GET /v1/documents?corpus=…` → published snapshot inventory only
- Response includes `corpus`, `snapshot_id`, `documents[]`
- `GET /v1/documents/{document_id}?corpus=…` metadata/provenance only
- No full-text/raw download; no chunk browser; no historical/candidate browser
- Document = stable source ingest unit used in citation provenance
- Optional summary fields only if already available cheaply
- Unknown id in current published snapshot → `document_unknown`
- Pre-first-publish reads → `corpus_unknown` (D20)

### S15-D11 — `/trace/{id}` contract

**LOCKED / ACCEPTED**

- Durable allowlisted audit record for one product `/query` execution
- Owned by `offline_rag.app`; opaque per-query `trace_id` (UUID-style)
- Not verbatim internal `QueryTrace` / diagnostics dump
- Terminal semantics: D07 `status` **or** D08 `error_code` (no parallel ok/failed/partial taxonomy)
- Durable under `/data` with bounded retention; survives restart
- Retains immutable snapshot provenance for historical audit even after later publishes
- Wire format: explicit allowlisted projection; no metadata/prompt/provider passthrough
- New Slice-14-style instrumentation solely for traces: **not required**
- Persist query text / answer / citations: permitted; must be documented
- `GET /traces` listing, ingest traces: **OUT OF SCOPE**
- Missing → `trace_unknown`
- Trace allocated only after query execution begins (not for pre-execution validation/overload)

### S15-D12 — Evaluation surface

**LOCKED / ACCEPTED**

- CLI-first evaluation for Slice 15
- No HTTP `/eval/*`, no eval artifact serving via FastAPI
- Missing `/eval/*` is **not** a Slice 15 exit-criteria failure
- OpenAPI must not contain `/eval/*`
- No speculative evaluation refactor through a new app façade

### S15-D13 — API versioning and schema evolution

**LOCKED / ACCEPTED**

Product:

```text
POST /v1/ingest
POST /v1/query
GET  /v1/documents
GET  /v1/documents/{document_id}
GET  /v1/trace/{trace_id}
```

Ops (unversioned):

```text
GET /health
GET /health/live
GET /health/ready
```

- No unversioned product aliases; no `/v1/health/*` in Slice 15
- Within v1: additive/backward-safe changes allowed
- Breaking changes → new major version or explicit migration
- Unknown `error.code` must be tolerated generically by clients
- CLI is a direct app-layer client, not an HTTP `/v1` client
- API version ≠ scientific/snapshot/config identity

### S15-D14 — Authentication and network exposure

**LOCKED / ACCEPTED**

- Trust model: localhost-trusted single local operator; **no app auth** in Slice 15
- Direct host default: loopback bind
- Direct non-loopback: explicit opt-in (bind + allow flag conceptually)
- Official Compose: container may listen `0.0.0.0:8080`; host publish **`127.0.0.1:8080:8080`**
- Docker host-publish override cannot be reliably enforced by the app; docs must warn
- CORS `*`: forbidden by default; same-origin bundled UI preferred later
- TLS / 401/403 auth taxonomy: **OUT OF SCOPE**

### S15-D15 — `/data` persistence contract

**LOCKED / ACCEPTED**

- `/data` = sole OfflineRAG-owned durable product-state root
- Durable: published registry/manifests; Qdrant; snapshot-required non-Qdrant artifacts;
  canonical source/provenance needed for local recovery; candidate mutation state;
  lease coordination namespace; bounded traces
- Candidates may survive crash physically; **never** auto-publish; resumable ingest **not** required
- Lease coordination under `/data`, but active ownership must not survive owner death
- `/models` separate, normally `:ro`, reprovisionable; not corpus state
- Generator weights external
- Unwritable required `/data` → fail closed / `runtime_not_ready`
- Boot-time index rebuild as normal product requirement: **FORBIDDEN**

### S15-D16 — `/models` and offline model provisioning

**LOCKED / ACCEPTED**

- Pre-provisioned non-generator asset root; exact filenames implementation-owned
- Startup/runtime model-asset download and hub fallback: **FORBIDDEN**
- Approved external generator HTTP inference: **ALLOWED** under strict-offline policy
- Embedding: settings ↔ provisioned asset ↔ dense snapshot provenance must agree
- Reranker: settings ↔ asset ↔ effective query provenance when required
- Other assets only when accepted path depends on them
- Global required asset failure → `runtime_not_ready`
- Corpus-specific incompatibility → corpus/snapshot boundary (not necessarily global unreadiness)
- Doctor: read-only deep diagnostic; may probe generator; must not mutate/download/rebuild/publish

### S15-D17 — Container runtime topology

**LOCKED / ACCEPTED**

- One OfflineRAG container; external generator; Qdrant **Local mode** in-process under `/data/qdrant`
- Say “Qdrant client with Local-mode persistence,” not “embedded Qdrant server”
- Non-root process user; `/data:rw`, `/models:ro`
- Container listen `0.0.0.0:8080`; host publish `127.0.0.1:8080:8080`
- `host.docker.internal` + Linux `host-gateway`
- Supported server: **one process / one ASGI worker**; in-process async concurrency allowed
- Multi-worker and multi-replica shared `/data`: **UNSUPPORTED** for Slice 15 profile
- Concurrent independent processes opening the same Qdrant Local store: not assumed safe
- Full Slice 16 UI not required

### S15-D18 — HTTP request execution / resource control

**LOCKED / ACCEPTED**

- Expensive: `/v1/query`, `/v1/ingest`; cheap: health, documents, trace
- Bounded configurable admission; small safe defaults; fail-fast; no unbounded queue
- Ingest order (normative; see **S15-D20 transport-order clarification**):
  request-level HTTP envelope checks → **ingest-class capacity** →
  streaming multipart parse/spool (corpus validated when encountered; part order
  unconstrained) → validate complete document set → **corpus lease** → mutate →
  publish. Upload-before-lease remains mandatory.
- Overload → `service_overloaded` 503
- App deadline → `request_timeout` 504; generator → `generation_timeout` 504
- Expensive blocking work must not monopolize the sole ASGI event loop
- Query disconnect: best-effort cooperative cancel; trace may record `request_cancelled`
- Ingest disconnect before lease: cleanup, no mutation
- Ingest disconnect after lease: **not** a cancel signal; managed continuation to commit or abort
- Deadline before publish: abort; after publish: no rollback
- Automatic retries: not authorized
- Phase ownership of admission: **15D** owns ingest-class fail-fast capacity only
  (`max_concurrent_ingest = 1`, wait=`0`); **15F** owns query admission, deadlines,
  disconnect behavior, and shutdown/drain semantics (shared admission abstraction
  refactor allowed in 15F)

### S15-D19 — Graceful shutdown and crash recovery

**LOCKED / ACCEPTED**

- Graceful ≠ crash
- Shutdown first: `/health/ready` → 503 `runtime_not_ready`
- New `/v1/*` during drain: rejected with `runtime_not_ready`
- `/health/live` may remain 200 until exit
- In-flight query: cooperative cancel → `request_cancelled` when terminally recorded
- Shutdown-grace expiry is **not** itself `request_timeout`
- Post-lease ingest on shutdown: **abort** unfinished mutation unless atomic publication
  critical section already entered (then finish commit)
- Crash: durable-state recovery only; candidates never auto-publish; leases not permanent;
  uncommitted traces → `trace_unknown`
- Startup recovery is app lifecycle (not doctor mutation)
- Compose stop grace must accommodate app grace

### S15-D20 — `/v1/ingest` request boundary

**LOCKED / ACCEPTED** (including transport-order clarification below)

- `multipart/form-data` only: `corpus` + one-or-more `files`
- No HTTP filesystem paths, `file://`, or remote URL fetch
- CLI local-path ingest retained as non-HTTP operator capability
- Corpus name: `[A-Za-z0-9][A-Za-z0-9._-]{0,63}` via **one** app-layer validator
- Create-on-successful-publication only; pre-first-publish product reads → `corpus_unknown`
- Mutation lock namespace may still serialize first concurrent ingests (`corpus_busy`)
- Sole semantic: **full replace** of published document set; **no** `mode` field
- Empty/missing files → `request_invalid` (not delete-all)
- Document identity from canonical ingestion layer; duplicate filename alone not invalid
- Ambiguous canonical identity → `document_invalid`; whole request fails
- Identical canonical snapshot ⇒ **same** `snapshot_id` (D04)
- Success 200: `{corpus, snapshot_id, document_count}`
- No ingest `trace_id`

#### S15-D20 transport-order clarification (D22 reopen — LOCKED / ACCEPTED)

A literal reading that required validating the multipart `corpus` field before
acquiring ingest capacity and before any body consumption is **not implementable**:
multipart part order is not guaranteed, so corpus may arrive after file parts.
Requiring “corpus first” would invent an unauthorized public ordering constraint.
This narrow clarification replaces that impossible prefix only.

Normative ingest transport sequence:

```text
validate request-level HTTP envelope
(Content-Type/boundary + cheap Content-Length rejection when available)
        ↓
acquire ingest-class capacity
(max_concurrent_ingest = 1, wait = 0 → service_overloaded)
        ↓
streaming-parse multipart in arbitrary legal part order
  - extract + validate corpus as soon as encountered
  - bounded-spool file parts
  - enforce actual streamed bytes (not Content-Length alone)
  - enforce file count
  - no whole-request RAM buffering
        ↓
require exactly one valid corpus + one-or-more files
        ↓
validate complete uploaded document set
        ↓
acquire per-corpus mutation lease
        ↓
move/establish correctness-critical candidate under /data/corpora
        ↓
parse / chunk / index candidate
        ↓
validate grounded readiness
        ↓
atomic publish
```

Frozen transport invariants:

```text
MULTIPART PART ORDER:     UNCONSTRAINED
                          (no "corpus must come first" requirement)

UPLOAD BEFORE CORPUS LEASE: STILL MANDATORY
```

Consequence (accepted): a saturated service may return `service_overloaded`
before parsing a body-level invalid corpus, because capacity is acquired before
consuming an expensive request body. That is conventional fail-fast behavior and
does not authorize unbounded body buffering before capacity.

### S15-D21 — `/v1/query` request/response contract

**LOCKED / ACCEPTED**

Request (`application/json`, `extra=forbid`):

```json
{ "corpus": "manuals", "question": "..." }
```

- Trim outer whitespace on `question`; non-empty; finite max; no adapter rewriting
- Forbidden client fields include mode, snapshot, history, generation/retrieval knobs
- Single-turn only; no conversation memory

Success 200 normative fields:

```text
corpus, snapshot_id, product_mode_id, trace_id, status, answer, citations
```

| status | answer | citations |
|---|---|---|
| `answered` | non-empty string | validated set |
| `insufficient_evidence` | `null` | `[]` |
| `model_abstain` | `null` | `[]` |

Citation allowlist:

```text
evidence_unit_id, document_id, source_chunk_id, kind,
section_path, page_start?, page_end?, line_start?, line_end?, clipped
```

- Project from `ResolvedCitation` / `GroundedAnswerResult`; do not serialize diagnostics/metadata/hashes wholesale
- Preserve validated citation order; bind to execution `snapshot_id`
- Failures → D08 non-2xx

### S15-D22 — Design residual / consolidation boundary

**LOCKED / ACCEPTED**

- Architecture interview complete at D21
- Residual A (contract values) must be frozen **before implementation authorization**
- Residual B: no further architecture Qs
  - Static UI hook: optional cheap packaging detail; no fake UI required
  - Doctor: acceptance-contract detail under D16
  - **This consolidated design document: required before implementation authorization**
- Next: reconcile repo, freeze Residual A, derive implementation plan, review, then authorize

---

## 3. Normative public HTTP surface (Slice 15)

```text
GET  /health
GET  /health/live
GET  /health/ready

POST /v1/ingest
POST /v1/query
GET  /v1/documents?corpus=...
GET  /v1/documents/{document_id}?corpus=...
GET  /v1/trace/{trace_id}
```

OpenAPI must match this set (plus schemas/error model). No `/eval/*`, no unversioned
product aliases, no `/v1/health/*`.

---

## 4. Repository reconciliation (drafting HEAD `3ed9212…`)

Findings relative to D01–D22. Gaps are expected; implementation is not authorized.

### Aligns / partially present

| Area | Observation |
|---|---|
| Deploy templates | `deploy/docker-compose.example.yml` already uses `127.0.0.1:8080:8080`, `host.docker.internal:host-gateway`, `/data` + `/models:ro`, host Ollama env, `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` |
| Dockerfile template | Excludes generative runtime; sets `OFFLINE_RAG_DATA_DIR=/data`, `OFFLINE_RAG_MODELS_DIR=/models`; placeholder CMD |
| Domain generation | `ResolvedCitation` / `GroundedAnswerResult` exist for app projection (D21) |
| Corpus name grammar | `validate_corpus_name` matches D20 pattern |
| CLI query/ingest/doctor | Operator surfaces exist; doctor is diagnostic-oriented today |
| Paths config | `config/base.yaml` already separates data paths vs `models/*` artifact roots |
| Strict-offline generation | Approved endpoints/models patterns already exist in settings |

### Missing or divergent (must be closed in implementation after Residual A)

| Gap | Notes |
|---|---|
| `src/offline_rag/app/` | **Absent** — D01 boundary not created |
| FastAPI product routes | `src/offline_rag/api/routes/` empty (`.gitkeep` only) |
| Versioned `/v1` API | Not implemented |
| D08 error envelope / FastAPI 422 normalization | Not implemented |
| Health live/ready split | Not implemented |
| Product `/documents`, `/trace` | Not implemented |
| Storage-backed mutation lease | Not implemented as D03/D15 live-owner lease |
| Published `CorpusReadSnapshot` registry + deterministic `snapshot_id` product binding | Needs app-layer publication model on top of existing corpus/index identities |
| Sync product ingest (parse→chunk→index→publish) | CLI stages remain separate commands today |
| Durable product query trace store | Domain `QueryTrace` exists; D11 product store/projection does not |
| Admission control / deadlines / shutdown drain | Not implemented |
| Single-worker enforced server entrypoint | Template CMD is a placeholder |
| Non-root UID/GID contract | Not defined in Dockerfile template |
| Compose `stop_grace_period` | Not set in example Compose |
| Eval HTTP | Correctly absent (D12) |
| `paths.eval_results: eval/results` | Outside `/data` today — acceptable as optional CLI path; must not be required for product readiness |
| Doctor vs D16 | Exists but predates packaging acceptance checklist; needs Residual A acceptance mapping; must remain non-mutating (today may create some missing dirs — reconcile carefully) |

### Roadmap / slices docs

- `detailed_implementation_slices.md` Slice 15 still lists `/eval/run` or CLI-first and unversioned path names — superseded by D12/D13; this document is authoritative for architecture.
- `DEPLOYMENT.md` describes intended post-Slice-15 interface; still accurate at high level.
- `ROADMAP.md` M7 later checklist still unchecked for FastAPI/container — correct until implementation.

---

## 5. Residual A — pre-implementation contract

**STATUS: LOCKED / ACCEPTED**

Numeric/default rows below are frozen. Mechanism choices (libraries, class names,
internal module splits, exact lease primitive) remain implementation-owned if
acceptance criteria and D01–D22 constraints are met.

### 5.1 Identifiers

| Key | Frozen value |
|---|---|
| `product_mode_id` | `grounded_v1` |

### 5.2 Bounds and timeouts

| Key | Frozen value |
|---|---|
| `max_files_per_ingest` | `32` |
| `max_bytes_per_document` | `26214400` (25 MiB) |
| `max_total_upload_bytes` | `104857600` (100 MiB) |
| `max_question_chars` | `8000` |
| `query_deadline_seconds` | `180` |
| `ingest_deadline_seconds` | `1800` |
| `generation_timeout_seconds` | settings `generation.timeout_seconds` (base default 120) |
| `max_concurrent_query` | `1` |
| `max_concurrent_ingest` | `1` |
| `admission_wait_seconds` | `0` (fail-fast; no backlog) |
| `shutdown_grace_seconds` | `30` |
| Compose `stop_grace_period` | `45s` |
| Trace retention max age | `7 days` |
| Trace retention max count | `1000` |

#### Normative clarification — admission capacities

`max_concurrent_query = 1` and `max_concurrent_ingest = 1` are **class
capacities**, not a global expensive-work cap of 1.

```text
one admitted query
+
one admitted ingest
    = may coexist under the public admission contract
```

There is still **no waiting backlog** behind either slot. Failure to acquire the
relevant class slot promptly → `service_overloaded` / 503 / `retryable=true`.

A global expensive-work cap of 1 is **not** introduced: a long ingest must not
block all product queries merely by admission policy, because D03/D04 require
snapshot-consistent reads during mutation. If a specific model/runtime component
cannot safely run concurrently, implementation may serialize that component
narrowly without redefining this public admission contract.

#### Normative clarification — trace retention

Both bounds apply (logical AND). Retain a trace only if:

```text
age <= 7 days
AND
trace is among the newest 1000 retained records
```

Cleanup removes a trace when **either** bound fails. Retention ordering requires a
**persisted ordering timestamp** (or equivalent durable total order). Ordering must
**not** be inferred from opaque `trace_id`.

### 5.3 `/data` layout (container) mapped to existing path roles

Normative container root: `/data`. Frozen mapping (host/dev may use repo-relative
`data/` via settings):

```text
/data/
  raw/                    # paths.raw_data
  qdrant/                 # paths.qdrant_storage
  corpora/                # paths.corpora (+ corpus state, candidates)
  manifests/              # paths.manifests (as applicable)
  processed/              # paths.processed
  chunks/                 # paths.chunks
  chunk-manifests/        # paths.chunk_manifests
  embeddings/             # paths.embeddings
  index-manifests/        # paths.index_manifests
  lexical-indexes/        # paths.lexical_indexes
  lexical-index-manifests/
  traces/                 # NEW product trace store (D11)
  staging/                # NEW bounded upload spool (pre-lease; D20)
  locks/                  # NEW lease coordination namespace (D03/D15)
  eval/                   # OPTIONAL operator convenience; not product-required
  logs/                   # OPTIONAL
```

Active mutation-lease coordination lives only under `locks/` (not under `corpora/`).

`/models/` remains the provisioned non-generator root (`paths.retrieval_models` and
related artifact roots under `models/…` in current config).

Publication registry representation and exact lease primitive (e.g. OS file lock vs
lease record + reclaim) are **mechanism choices** constrained by D03/D15 live-owner
semantics; the implementation plan must name the chosen mechanism with acceptance
tests for crash reclaim and `corpus_busy`.

Abandoned-candidate policy: on startup, non-published candidate trees are
quarantined under a corpus-local `abandoned/` prefix or deleted; never published.

### 5.4 HTTP contract details

| Item | Frozen value |
|---|---|
| Ingest success | `corpus: string`, `snapshot_id: string`, `document_count: int` |
| Query success | seven D21 fields; `answer: string \| null`; `citations: array` |
| Error envelope | D08; FastAPI 422 → `request_invalid` |
| Validation `details` allowlist | `fields: [{loc, msg, type}]` bounded/truncated; no input values that may contain secrets |
| OpenAPI title | `OfflineRAG API` |
| OpenAPI version field | `1.0.0` (API product version, not git SHA) |

### 5.5 Configuration / env names

Primary env knobs (immutable at process start):

| Env | Role |
|---|---|
| `OFFLINE_RAG_DATA_DIR` | Durable root (default `/data` in container) |
| `OFFLINE_RAG_MODELS_DIR` | Models root (default `/models`) |
| `OFFLINE_RAG_STRICT_OFFLINE` | Strict-offline mode |
| `OFFLINE_RAG_LLM_BASE_URL` | Generator base URL |
| `OFFLINE_RAG_LLM_MODEL` | Generator model id |
| `OFFLINE_RAG_APPROVED_LLM_MODELS` | Approved model allowlist |
| `OFFLINE_RAG_APPROVED_LLM_ENDPOINTS` | Approved endpoint allowlist (if not only YAML) |
| `OFFLINE_RAG_LLM_API_KEY` | Optional bearer (never logged) |
| `OFFLINE_RAG_HTTP_HOST` | Bind host (`127.0.0.1` direct-host default; container profile `0.0.0.0`) |
| `OFFLINE_RAG_HTTP_PORT` | Default `8080` |
| `OFFLINE_RAG_ALLOW_NON_LOOPBACK` | Must be true with non-loopback direct bind |
| `OFFLINE_RAG_MAX_QUESTION_CHARS` | Override bound |
| `OFFLINE_RAG_MAX_FILES_PER_INGEST` | Override bound |
| `OFFLINE_RAG_MAX_BYTES_PER_DOCUMENT` | Override bound |
| `OFFLINE_RAG_MAX_TOTAL_UPLOAD_BYTES` | Override bound |
| `OFFLINE_RAG_QUERY_DEADLINE_SECONDS` | Override |
| `OFFLINE_RAG_INGEST_DEADLINE_SECONDS` | Override |
| `OFFLINE_RAG_MAX_CONCURRENT_QUERY` | Override |
| `OFFLINE_RAG_MAX_CONCURRENT_INGEST` | Override |
| `OFFLINE_RAG_SHUTDOWN_GRACE_SECONDS` | Override |
| `OFFLINE_RAG_TRACE_RETENTION_DAYS` | Override |
| `OFFLINE_RAG_TRACE_RETENTION_MAX_COUNT` | Override |

Existing YAML settings remain authoritative where env overlays already exist; new
knobs must integrate with the accepted settings loader without hot reload.

### 5.6 Packaging

| Item | Frozen value |
|---|---|
| Container user | non-root `offlinerag` UID/GID **`10001:10001`** |
| `/data` ownership | writable by `10001` |
| `/models` | mounted `:ro` |
| HTTP CMD | single-worker ASGI module entry (exact module path impl-owned under `offline_rag.api`) |
| Workers | `1` only in supported profile |
| Compose publish | `127.0.0.1:8080:8080` |
| Compose `extra_hosts` | `host.docker.internal:host-gateway` |
| Compose `stop_grace_period` | `45s` |

### 5.7 Doctor acceptance (pre-impl contract, not new architecture)

Doctor is **diagnostic / read-only**:

- MUST inspect only
- MUST NOT `mkdir` / create / repair / provision / download / publish

Startup owns required `/data` directory creation.

Required check groups: `/data` usability; `/models` configured identities;
strict-offline coherence; approved generator config; optional generator probe;
optional corpus snapshot↔embedding compatibility when `--corpus` is supplied.

Doctor mutation debt (mkdir / write-probe / repair) was **removed in Phase 15B**
and must remain absent. Startup—not doctor—owns required `/data` creation.

---

## 6. Explicit non-goals (Slice 15)

- Slice 16 portfolio UI completeness
- HTTP evaluation job API
- Append/merge/patch ingest
- Multi-worker / multi-replica shared `/data`
- Application authentication / TLS
- Conversational/multi-turn query API
- Client-selected retrieval/generation hyperparameters
- Runtime model hub downloads
- Resumable ingest after crash
- Automatic server retries

---

## 7. Next governance steps

1. ~~Commit this consolidation artifact (+ Residual A freeze text) for remote audit~~ **DONE**  
2. ~~Independently review [`docs/slice15_implementation_plan.md`](slice15_implementation_plan.md)~~ **DONE / ACCEPTED**  
3. ~~Confirm §5 matches the accepted Residual A freeze at the authority SHA~~ **DONE**  
4. ~~Authorize and land 15A / 15B~~ **DONE** (`00282d67…` on main)  
5. ~~Authorize and land 15C~~ **DONE** (`5d70be09…` / merge `47a11f19…`)  
6. Issue explicit **15D** implementation authorization citing design authority
   `6583fb3…` and the post-15C main baseline before any product ingest work  

```text
PHASES 15D–15H: NOT AUTHORIZED BY THIS DOCUMENT ALONE
```

---

## 8. Decision index

| ID | Title | Status |
|---|---|---|
| S15-D01 | Canonical application boundary | LOCKED / ACCEPTED |
| S15-D02 | Process lifecycle scoping | LOCKED / ACCEPTED |
| S15-D03 | Corpus concurrency & mutation | LOCKED / ACCEPTED |
| S15-D04 | CorpusReadSnapshot resolution | LOCKED / ACCEPTED |
| S15-D05 | Product ingest transaction | LOCKED / ACCEPTED |
| S15-D06 | Product query mode | LOCKED / ACCEPTED |
| S15-D07 | Query outcomes & HTTP semantics | LOCKED / ACCEPTED |
| S15-D08 | Application error taxonomy | LOCKED / ACCEPTED |
| S15-D09 | Health / liveness / readiness | LOCKED / ACCEPTED |
| S15-D10 | `/documents` product boundary | LOCKED / ACCEPTED |
| S15-D11 | `/trace/{id}` contract | LOCKED / ACCEPTED |
| S15-D12 | Evaluation surface | LOCKED / ACCEPTED |
| S15-D13 | API versioning & schema evolution | LOCKED / ACCEPTED |
| S15-D14 | Auth & network exposure | LOCKED / ACCEPTED |
| S15-D15 | `/data` persistence contract | LOCKED / ACCEPTED |
| S15-D16 | `/models` & offline provisioning | LOCKED / ACCEPTED |
| S15-D17 | Container runtime topology | LOCKED / ACCEPTED |
| S15-D18 | Request execution / resource control | LOCKED / ACCEPTED |
| S15-D19 | Graceful shutdown & crash recovery | LOCKED / ACCEPTED |
| S15-D20 | `/v1/ingest` request boundary | LOCKED / ACCEPTED (+ transport-order clarification) |
| S15-D21 | `/v1/query` request/response contract | LOCKED / ACCEPTED |
| S15-D22 | Design residual / consolidation boundary | LOCKED / ACCEPTED |
| Residual A | Pre-implementation contract values | **LOCKED / ACCEPTED** |
