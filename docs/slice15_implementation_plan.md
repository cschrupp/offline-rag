# Slice 15 — Implementation plan

**Status:** DERIVED — pending independent review  
**Architecture + Residual A authority:** [`docs/slice15_developer_api_packaging.md`](slice15_developer_api_packaging.md)  
**Code implementation:** **NOT AUTHORIZED**

This plan decomposes Slice 15 into bounded phases with scope, dependencies,
acceptance tests, and explicit non-scope. It does not authorize coding.

---

## 0. Goals and non-goals

### Goals

Deliver a localhost-trusted, single-container OfflineRAG product API that:

- owns use cases in `offline_rag.app` (D01)
- exposes `/health*` + `/v1/{ingest,query,documents,trace}` (D09/D13/D20/D21)
- publishes grounded-capable snapshots under `/data` (D03–D05/D15)
- uses host Ollama via approved OpenAI-compatible settings (D16/D17)
- fails closed on overload, unreadiness, and offline asset gaps (D08/D18/D19)

### Explicit non-scope (entire Slice 15)

- Slice 16 portfolio UI completeness / fake placeholder UI product surface
- HTTP `/eval/*` or eval artifact serving (D12)
- Append/merge/patch ingest; empty-ingest delete-all (D20)
- Multi-worker / multi-replica shared `/data` (D17)
- Application auth / TLS / CORS `*` (D14)
- Conversational/multi-turn query API (D21)
- Client scientific knobs / snapshot pin API (D06/D21)
- Runtime model-hub downloads (D16)
- Resumable ingest after crash (D15)
- Automatic server retries (D08/D18)
- Distributed admission / job queues (D18)

---

## 1. Dependency order (phases)

```text
15A  App foundation + errors + settings Residual A
        ↓
15B  Lifecycle runtime + health + doctor non-mutation
        ↓
15C  Snapshot registry + leases + documents
        ↓
15D  Product ingest (multipart → publish)
        ↓
15E  Product query + durable traces
        ↓
15F  Admission, deadlines, shutdown
        ↓
15G  Container packaging + Compose contract
        ↓
15H  Integration acceptance / Slice 15 closeout evidence
```

Phases may share a branch only under explicit implementation authorization.
Do not start a later phase’s product surface before its listed dependencies land
enough for the phase’s acceptance tests.

Mechanism choices (file-lock library, ASGI framework helpers, internal module
names) are free **within** each phase if D01–D22 + Residual A remain satisfied.

---

## 2. Phase 15A — App foundation, errors, Residual A settings

### Scope

- Create `src/offline_rag/app/` product boundary packages/modules
- Canonical corpus-name validator reused by adapters (no FastAPI-local rewrite)
- D08 `AppError` / error catalog + safe `ErrorResponse` DTOs
- Residual A settings/env knobs wired into immutable process settings
- `/data` root resolution from `OFFLINE_RAG_DATA_DIR` (+ models dir)
- Startup helper to create required `/data` subtrees (not doctor)

### Depends on

- Locked design doc §2, §5

### Acceptance tests

- Unit: corpus name accept/reject matrix matches D20 regex
- Unit: every D08 code has retryable mapping; every code except
  `request_cancelled` has a normative HTTP mapping. `request_cancelled` is
  application/trace-only (optional/absent HTTP status) — do not invent 499/408
- Unit: Residual A defaults resolve without overlay
- Unit: secret-bearing fields never appear in error `details`
- Unit: FastAPI/Pydantic validation translator → `request_invalid` envelope shape
  (can be tested via a thin helper before full app exists)

### Non-scope

- HTTP routes beyond whatever minimal harness is needed for envelope tests
- Ingest/query orchestration

---

## 3. Phase 15B — Process lifecycle, health, doctor debt

### Scope

- Application runtime lifecycle: construct process-scoped resources once (D02)
- Readiness state machine: NOT_READY → READY; fatal degradation → NOT_READY
- `GET /health`, `/health/live`, `/health/ready` (D09)
- Remove doctor `mkdir`/create/repair behavior; doctor reports ABSENT only (Residual A)
- Doctor checks aligned with D16 groups (no download/publish)

### Depends on

- 15A settings + error types

### Acceptance tests

- Live returns 200 with `{status: "live"}` without loading models
- Ready 503 `runtime_not_ready` before init completes; 200 after successful init
- Ready does not call generator / reload weights
- Doctor on missing creatable path: fails/reports without creating it
- Doctor does not mutate corpora/snapshots

### Non-scope

- Product `/v1/*` business routes (stubs OK only if unused in acceptance)

---

## 4. Phase 15C — Snapshot registry, leases, documents

### Scope

- Published `CorpusReadSnapshot` resolution + deterministic `snapshot_id` (D04)
- Storage-backed mutation lease under `/data/locks` with **live-owner** semantics (D03/D15)
- Startup abandoned-candidate quarantine/delete (never auto-publish)
- `GET /v1/documents` and `GET /v1/documents/{document_id}` against published snapshot (D10)
- Pre-first-publish → `corpus_unknown`; published-but-not-grounded → `corpus_not_ready`

### Depends on

- 15A, 15B runtime/paths

### Mechanism note (must be named in phase PR)

Choose and document lease primitive (e.g. OS-backed file lock vs reclaimable lease
record) with tests for: second mutator → `corpus_busy`; owner crash → not permanent
busy; CLI and API share coordination namespace.

### Acceptance tests

- Documents response includes `corpus` + `snapshot_id` + summaries
- Unknown document id → `document_unknown`
- Concurrent second lease acquire → `corpus_busy` 409 retryable true
- Kill holder process (or simulate) → subsequent mutator can acquire
- Identical canonical snapshot constituents → identical `snapshot_id` (fixture-level)

### Non-scope

- Multipart ingest pipeline; query execution; traces

---

## 5. Phase 15D — Product ingest

### Scope

- `POST /v1/ingest` multipart replace transaction (D05/D20)
- Order: validate → ingest capacity → spool upload → validate docs → lease →
  build candidate → validate grounded readiness → atomic publish
- Map bound/type/identity failures to `request_invalid` / `document_invalid`
- Success `{corpus, snapshot_id, document_count}`
- Offload blocking stages off the ASGI event loop (D18)
- CLI path ingest may call the same app use case in-phase if cheap; otherwise a
  thin follow-up is required before Slice 15 closeout (see §11)

### Depends on

- 15C registry/leases; 15A bounds; existing ingest/chunk/index domain pipelines

### Acceptance tests

- Missing/zero files → 422 `request_invalid`
- Oversized file / unsupported type / identity conflict → 422 `document_invalid`
- Path/`file://`/URL fields rejected (no filesystem read API)
- Successful ingest makes `/v1/documents` match uploaded set (replace semantics)
- Disconnect during upload (before lease): no publish, no lease held
- Second concurrent ingest same corpus → `corpus_busy` or `service_overloaded`
  as appropriate to order
- Health live remains responsive during a long fake/blocked ingest stage
  (event-loop non-monopoly)

### Non-scope

- Query; traces; append mode; empty-corpus delete

---

## 6. Phase 15E — Product query + durable traces

### Scope

- `POST /v1/query` D21 contract via app use case → `GroundedAnswerOrchestrator`
- Project internal result → product success/error (no diagnostics passthrough)
- Allocate `trace_id` only after execution begins; durable commit before HTTP
  success/error return when required (D11/D18)
- `GET /v1/trace/{trace_id}` allowlisted projection + historical snapshot provenance
- Retention: age ≤ 7d AND newest 1000; persisted ordering timestamp

### Depends on

- 15C snapshot pin; 15B runtime models; generator settings

### Acceptance tests

- Extra request fields → 422 `request_invalid`
- Empty/oversized question → 422 `request_invalid`
- 200 statuses only `answered` | `insufficient_evidence` | `model_abstain`
- `answered` has non-empty answer + citations; others null/`[]`
- Citation allowlist only; order preserved
- Citation `document_id` ∈ documents inventory for returned `snapshot_id`
- `product_mode_id == grounded_v1`
- Trace fetch after success returns same `snapshot_id` / terminal branch
- After retention eviction / never committed → `trace_unknown`
- Overload/validation before execution → no durable trace required

### Non-scope

- Chat history; client mode/snapshot selection; eval HTTP

---

## 7. Phase 15F — Admission, deadlines, shutdown

### Scope

- Class admission: query slots=1, ingest slots=1, wait=0 → `service_overloaded`
- Query/ingest deadlines → `request_timeout`; generator → `generation_timeout`
- Query disconnect/shutdown cancellation → cooperative cancel +
  `request_cancelled` trace when terminally recorded
- Ingest post-lease disconnect: continue to commit/abort (D18)
- Graceful shutdown: ready false; reject new `/v1/*`; abort unfinished post-lease
  ingest unless publish critical section entered; grace 30s (D19)

### Depends on

- 15D + 15E product operations

### Acceptance tests

- Second concurrent query while one held → 503 `service_overloaded` (no queue)
- Query + ingest may both be admitted (class capacities)
- Forced short query deadline → 504 `request_timeout` (deterministic test double)
- SIGTERM/lifespan shutdown: ready 503; new query rejected `runtime_not_ready`
- Post-lease ingest abort on shutdown when publish not entered
- Shutdown grace expiry does not fabricate `request_timeout`

### Non-scope

- Global expensive cap of 1; distributed admission; job API

---

## 8. Phase 15G — Container packaging

### Scope

- Real Dockerfile (from template): non-root `10001:10001`; `/data` `/models` env;
  single-worker CMD; no generator weights
- Compose example: `127.0.0.1:8080:8080`, host-gateway, `:ro` models,
  `stop_grace_period: 45s`, Residual A-relevant env
- Direct-host bind defaults + non-loopback opt-in fail-closed (D14)
- Deployment/README updates for trust boundary and offline provisioning
- Optional cheap static-files mount hook only if zero product-endpoint invention

### Depends on

- 15B entrypoint; preferably 15E/15F complete enough to serve

### Acceptance tests

- Image build succeeds without embedding generator weights
- Container user is non-root 10001
- Compose config publishes loopback only
- App listens on `0.0.0.0:8080` inside container profile
- Direct-host non-loopback without allow flag refused
- `/models` read-only mount documented and exampled

### Non-scope

- Separate Qdrant service; Ollama-in-Compose; multi-replica

---

## 9. Phase 15H — Integration acceptance / closeout

### Scope

- End-to-end scripted acceptance on supported profile (local or Compose):
  doctor → ready → ingest → documents → query → trace → second ingest replace →
  query still coherent; busy/overload/shutdown smoke where automatable
- Confirm OpenAPI contains only allowed paths (no `/eval/*`, no unversioned product)
- Update ROADMAP / slices checklist only after acceptance evidence
- Record authority SHAs for closeout

### Depends on

- 15A–15G

### Acceptance tests / evidence

- Checklist mapped 1:1 to D08 catalog smoke (representative codes)
- Replace ingest removes omitted docs from current inventory
- Read-during-ingest: query against N while candidate N+1 building (when testable)
- Offline: missing embedding asset → not ready / fail closed (no hub download)
- No secret leakage in health/error/trace samples

### Non-scope

- Performance campaigns; Slice 16 UI; scientific promotion claims

---

## 10. Suggested test layout

```text
tests/unit/app/           # 15A errors, settings, validators, projections
tests/unit/api/           # envelope translation, schema extra=forbid
tests/integration/api/    # health, ingest, query, documents, trace
tests/integration/lifecycle/  # lease crash reclaim, shutdown, admission
```

Prefer fakes for generator/embedder in unit/integration except an optional
manual Compose smoke noted in closeout (not a gate for every CI job if GPU
unavailable).

---

## 11. CLI adapter policy

- Product HTTP never calls `cli.py` (D01)
- By **Slice 15 closeout**, product CLI **ingest** and **query** MUST invoke
  `offline_rag.app` (same use-case boundary as FastAPI). Migration may land in
  15D/15E or a thin follow-up before closeout; it must not remain deferred past
  Slice 15 acceptance.
- Doctor packaging consistency via `offline_rag.app` is preferred when cheap;
  evaluation CLI remains under D12 and does **not** require speculative migration
- Evaluation CLI remains authoritative; no HTTP wrap (D12)
- Concurrent CLI + API opening same Qdrant Local store remains **unsupported**
  unless a phase explicitly verifies Local-mode safety and documents it (D17)

---

## 12. Authorization model for coding

```text
Design doc committed + §5 Residual A audited
        ↓
This implementation plan independently reviewed / accepted
        ↓
EXPLICIT implementation authorization
  - names phase(s) allowed (e.g. 15A only, or 15A–15B)
  - cites design authority SHA
  - cites plan authority SHA
        ↓
Code for authorized phase(s) only
```

Unauthorized phase work, speculative refactors, and eval HTTP remain forbidden.

---

## 13. Phase exit checklist (per phase PR)

- [ ] Scope matches this plan section  
- [ ] No locked decision silently changed (reopen rule)  
- [ ] Acceptance tests listed above added and green for the phase  
- [ ] Secrets/tracebacks absent from new HTTP surfaces  
- [ ] OpenAPI still free of `/eval/*` and unversioned product paths  
- [ ] Doctor remains non-mutating after 15B  

---

## 14. Traceability

| Phase | Primary locks |
|---|---|
| 15A | D01, D08, D13, D20 validator, Residual A |
| 15B | D02, D09, D16, D19 ready flip, Residual A doctor |
| 15C | D03, D04, D10, D15 |
| 15D | D05, D18 upload-before-lease, D20 |
| 15E | D06, D07, D11, D21 |
| 15F | D18, D19 |
| 15G | D14, D17, Residual A packaging |
| 15H | full Slice 15 exit evidence |
