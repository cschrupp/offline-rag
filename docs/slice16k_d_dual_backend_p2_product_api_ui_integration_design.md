# 16K-D Dual-Backend P2 — Product / API / UI Integration Design

**Design authority:** `S16-K-D-DUAL-BACKEND-P2-PRODUCT-API-UI-INTEGRATION-DESIGN-AUTH-001` — AUTHORIZED
**Design-completion publication authority:** `S16-K-D-DUAL-BACKEND-P2-PRODUCT-API-UI-INTEGRATION-DESIGN-COMPLETE-PUBLISH-AUTH-001` — AUTHORIZED
**Exact design-open parent:** `7563ce0736307dd3bf303289b6d0a25bce79c4f9`
**Exact design-open tip:** `c621b3cecd17b94fa9b0767f193dca810c6283cb`
**Exact design-completion publication parent:** `c621b3cecd17b94fa9b0767f193dca810c6283cb`
**Branch:** `design/16k-d-dual-backend-p2-product-api-ui-integration`
**Status:** P2 DESIGN IR-001 REQUEST CHANGES / NARROW REWORK CANDIDATE / READY FOR INDEPENDENT DESIGN IR-002
**Implementation:** NOT AUTHORIZED
**Addresses:** Design IR-001 F001 (restore durable D15 Layer A–G matrix); F002 clarification (D16 full path forms) — no new architecture decisions

**Inherited P1 implementation authority:** `S16-K-D-DUAL-BACKEND-P1-QUALIFIED-RUNTIME-SUBSTRATE-IMPLEMENTATION-AUTH-001`
**Inherited P1 Human acceptance:** `S16-K-D-DUAL-BACKEND-P1-QUALIFIED-RUNTIME-SUBSTRATE-IMPLEMENTATION-HA-001` — ACCEPTED
**Exact accepted P1 technical subject:** `fae82b2455cfdd0d1622065904a35895372740b6`
**P1 HA-record tip (governance only):** `bdecd52891309c2c2e4ddee7d3c74174ad606290`

**Architecture authority:** dual-backend embedding architecture (Rounds 1–12) — HUMAN ACCEPTED / FROZEN
**Design posture:** architecture-conformance **integration** design over the accepted substrate — **not** a new architecture exercise.
**Decision ledger:** D01–D18 all **INHERITED / FROZEN** (no new architecture decisions in this publication).

---

## 1. Purpose

Define exact product/runtime, API, and Seneca UI integration contracts for the accepted dual-backend embedding substrate delivered by P1, without reopening frozen architecture or authorizing implementation.

P2 translates already-accepted architecture into durable integration contracts. Independent acceptance of this design is a prerequisite before any separate P2 **implementation** authority may be opened.

---

## 2. Inherited frozen architectural facts (do not reopen)

The following are accepted and binding for P2 integration design:

1. Closed production profile vocabulary: `cuda_fp16_v1`, `cpu_onnx_fp32_v1`.
2. Exactly one selected embedding execution profile per process.
3. No mid-run backend fallback / no silent profile switching.
4. Shared logical embedding / index / collection identity across accepted profiles (profile/provider/device are not durable identity).
5. Process-owned lazy runtime lifecycle (`UNLOADED` → `LOADING` → `READY`, with terminal failure semantics as frozen).
6. P1 owns artifact trust / representation readiness inspection and the `QualifiedEmbeddingRuntime` substrate (accepted at `fae82b2…`).
7. Phase ownership split remains: **P1** substrate · **P2** product/API/UI integration · **P3** provisioning/acquisition · **P4** later acceptance/promotion.
8. Architecture Round 10 already freezes structural P2 ownership sketches (`ApplicationRuntime` / `ProcessResources.embedder`, Compute Settings projection facts, candidate source surfaces, explicit non-scope). P2 design here **conforms and concretizes**; it does not redesign those facts.

---

## 3. Scope boundary

### 3.1 Allowed under this design authority

- Architecture-conformance integration decisions and contracts
- Interfaces and lifecycle/wiring into existing app runtime
- API configuration and observability contracts
- UI state / UX contracts for compute/device/profile/readiness/failure
- Error / status / readiness / fallback semantics (product-facing)
- Compatibility requirements with existing YAML, CLI, and settings
- Persistence / mutability of user compute preferences
- Acceptance criteria and deterministic test matrix structure
- Exact P2 implementation surface decomposition (files/tasks) — design only
- Explicit exclusions for P3 / P4 / campaigns / main / merge / promotion

### 3.2 Not allowed under this design authority

- Production implementation of any kind
- Provisioning / download / package acquisition logic (P3)
- New scientific execution, parity, screen, or performance campaigns
- Representation qualification changes or new profiles
- P3 / P4 work
- Merge, main promotion, or default promotion
- Reopening P1 science/architecture or rewriting accepted P1 technical subject `fae82b2…`

---

## 4. Frozen constraints for the integration design process

1. Prefer conformance to accepted Round 10 / dual-backend architecture over invention.
2. Ask and freeze remaining **integration** decisions one at a time; do not invent the full product contract in one pass.
3. Where architecture already decides a fact, record it as **INHERITED / FROZEN** rather than re-deciding it.
4. Distinguishing “eligible to open later” from “authorized now” remains mandatory: this authority opens **design only**.
5. P2 implementation remains **NOT AUTHORIZED** until this design is independently accepted and a separate implementation AUTH is explicitly issued.

---

## 5. Integration decision ledger

Status key: `OPEN` · `INHERITED/FROZEN` · `FROZEN` · `DEFERRED-TO-P3` · `DEFERRED-TO-P4`
**Ledger state:** COMPLETE — all entries dispositioned.

| ID | Decision | Status |
|---|---|---|
| D01 | Product/runtime ownership and where profile resolution occurs | INHERITED / FROZEN |
| D02 | Process lifecycle and resource ownership | INHERITED / FROZEN |
| D03 | API configuration and observability surface | INHERITED / FROZEN |
| D04 | Explicit CPU / CUDA / AUTO user semantics | INHERITED / FROZEN |
| D05 | Readiness / error / fallback semantics (product-facing) | INHERITED / FROZEN |
| D06 | Workspace / query / ingest interaction with selected embedding profile | INHERITED / FROZEN |
| D07 | UI controls and user-visible status | INHERITED / FROZEN |
| D08 | Compatibility with existing configuration files and CLI behavior | INHERITED / FROZEN |
| D09 | Persistence semantics for user compute preferences | INHERITED / FROZEN |
| D10 | Startup vs runtime mutability | INHERITED / FROZEN |
| D11 | API schema and backward compatibility | INHERITED / FROZEN |
| D12 | Security / offline boundary | INHERITED / FROZEN |
| D13 | What P2 may know about installed representations vs what remains P3 | INHERITED / FROZEN |
| D14 | Failure / recovery behavior | INHERITED / FROZEN |
| D15 | Test strategy and deterministic acceptance matrix | INHERITED / FROZEN |
| D16 | Exact P2 implementation surface | INHERITED / FROZEN |
| D17 | Explicit exclusions for P3 / P4 / campaigns / main | INHERITED / FROZEN |
| D18 | Independent-review gates for design and later implementation | INHERITED / FROZEN |

Architecture-level facts listed in §2 are **INHERITED/FROZEN** and are not ledger re-openings.

---

## 5A. Frozen decision records

### D01 — Product/runtime ownership and profile resolution — INHERITED / FROZEN

- `ApplicationRuntime` → `ProcessResources.embedder` remains the single process authority for embeddings.
- Under production Qwen settings, that object is the accepted `QualifiedEmbeddingRuntime`.
- No second `embedding_runtime` field, parallel owner, or alternate lifecycle is introduced.
- Profile resolution occurs once through the existing `make_embedder()` → `resolve_qualified_embedding_profile()` seam during process-resource construction/startup.
- Resolution uses only the already accepted effective device/precision configuration plus the frozen CUDA probe behavior.
- Backend/model materialization remains lazy: startup selects and validates the profile/representation and constructs the lightweight runtime; the heavy backend remains `UNLOADED` until first embedding use.
- UI and API handlers do not select profiles. They may express configuration intent or report resolved state later, but they do not own resolution logic.
- Ingest/query call sites do not resolve or construct embedders.
- `QueryRuntimeCache`, ingestion, and other existing consumers borrow the same `ProcessResources.embedder`.
- P2 must not introduce another resolver, another embedder instance, or request-scoped backend selection.
- No fallback or architecture reinterpretation is introduced.

Ownership invariant:

```text
effective configuration
  → process startup
  → make_embedder()
  → qualified profile resolution
  → representation validation
  → one process-owned QualifiedEmbeddingRuntime
  → shared ingest/query consumers
```

### D02 — Process lifecycle and resource ownership — INHERITED / FROZEN

- `ApplicationRuntime.start()` remains the only process-startup owner. P2 integrates embedding into the existing resource-construction step without a parallel startup path or reordering unrelated recovery/journal/publication guarantees.
- At embedding construction: `make_embedder()` performs frozen profile resolution and selected-representation validation; returns lightweight process-owned `QualifiedEmbeddingRuntime`; must **not** load Torch/ONNX or create the inference session during startup.
- Static selected-profile/representation failure → `ApplicationRuntime = NOT_READY` / `startup_failed` / `resources = none`.
- P2 must **not** duplicate this validation in `validate_global_startup_requirements()` or elsewhere; the P1 construction seam remains the single authoritative resolve → inspect → validate gate.
- After successful startup: `ApplicationRuntime = READY`, `QualifiedEmbeddingRuntime = UNLOADED`.
- First embedding use owns `UNLOADED → LOADING → READY`, or on init failure `UNLOADED → LOADING → FAILED`. Later backend execution failure likewise moves embedding runtime to terminal `FAILED`.
- Post-start dynamic embedding failure does **not** demote `ApplicationRuntime` from READY. Process stays alive; settings/diagnostics/health remain inspectable. Embedding-dependent operations fail closed until process restart. Observability may expose degraded embedding state; it must not be reinterpreted as a second application-startup failure.
- Singular ownership: `ApplicationRuntime → ProcessResources.embedder → QualifiedEmbeddingRuntime`. No request-scoped construction, no second owner, no independent runtime-cache ownership, no backend reconstruction after failure. Query/ingest only borrow.
- Invariant for later API/health design: **application readiness and embedding-runtime execution state are distinct dimensions after startup** — do not collapse embedding `FAILED` into `ApplicationRuntime NOT_READY`.

### D03 — API configuration and observability surface — INHERITED / FROZEN

- P2 extends the existing Compute Settings API **additively**; no parallel embedding-settings authority or second configuration model.
- Runtime DTO projects live process-owned `QualifiedEmbeddingRuntime` / resolution facts (as applicable): `configured_device`, `configured_precision`, `profile_id`, `representation_id`, `embedding_state`, resolved backend/device/precision/provider, `selection_reason`, model ID/revision/dimension, bounded CUDA probe facts, bounded `failure_reason`. These are observations of the active process; API must **not** recompute active profile from current/pending settings on every GET.
- Active / pending / `restart_required` remain authoritative. A settings write persists **next-start policy only** — no embedder reconstruction, representation load, selected-profile mutation, FAILED recovery, or in-process backend switch.
- Availability keeps product shape `auto` / `cpu` / `cuda`; entries may add bounded safe diagnostics (representation absent/invalid, CUDA unavailable, probe failure, incompatible precision). No filesystem paths, raw exceptions, stack traces, artifact internals, or sensitive implementation detail.
- Candidate write validation **reuses** the same qualified profile resolver as startup; translate failures to existing `SETTINGS_INVALID` + bounded reasons; do not independently reproduce CPU/CUDA/AUTO selection logic.
- When embedding runtime is `FAILED` while `ApplicationRuntime = READY`, Compute Settings GET/PUT remain available; PUT validates/persists next-start intent only and must **not** test-load the pending backend.
- `GET /v1/capabilities` may expose a compact projection of the same active process-owned embedding facts — observability only, never another resolution or readiness authority.
- Doctor remains read-only and may become representation-aware.
- Forbidden: writable profile IDs; writable ORT provider/thread controls; per-request backend selection; mid-run profile switching; API-owned fallback; test-loading as part of settings validation.
- Invariant: **configuration expresses next-start intent; the live runtime is the authority for current execution state.**

### D04 — Explicit CPU / CUDA / AUTO user semantics — INHERITED / FROZEN

- Product vocabulary: Auto → `auto`, CPU → `cpu`, GPU (CUDA) → `cuda`. No writable profile ID, backend, provider, precision, ORT threads, or representation ID.
- Live-process resolver (accepted P1) remains authoritative:

| Intent | Precision | Condition | Result |
|---|---|---|---|
| CPU | native | any hardware | `cpu_onnx_fp32_v1` / `explicit_cpu_onnx_fp32` |
| CPU | fp16 | any hardware | ERROR |
| CUDA | native or fp16 | CUDA usable | `cuda_fp16_v1` / `explicit_cuda_fp16` |
| CUDA | any | CUDA unavailable/probe failure | ERROR, no CPU fallback |
| AUTO | native | CUDA usable | `cuda_fp16_v1` / `auto_cuda_fp16` |
| AUTO | native | CUDA unavailable | `cpu_onnx_fp32_v1` / `auto_cpu_onnx_fp32_cuda_unavailable` |
| AUTO | native | CUDA probe failed | `cpu_onnx_fp32_v1` / `auto_cpu_onnx_fp32_cuda_probe_failed` |
| AUTO | fp16 | CUDA usable | `cuda_fp16_v1` |
| AUTO | fp16 | CUDA unavailable/probe failure | ERROR |

- Explicit CPU is authoritative: CUDA-capable hosts must not promote CPU → CUDA.
- AUTO resolves once for a fresh process. If AUTO would select CUDA and that representation is absent/invalid, AUTO is unavailable — no “CPU exists ⇒ AUTO fine” and no silent CPU downgrade.
- Save-time availability (next-start, static/read-only, no model load): CPU iff `onnx_fp32_v1` READY; CUDA iff CUDA usable and `torch_st_v1` READY; AUTO iff the exact profile AUTO would select for a fresh process is READY. Bounded reason codes only.
- Legacy precision remains a resolver input where already present; P2 does not expose precision as a new product control.
- `selection_reason` is observational only; users cannot write it.
- After start, AUTO is not a continuing policy engine: active CUDA `FAILED` ⇒ no runtime AUTO reinterpretation, CPU fallback, or reselection; restart under a subsequently saved policy is required.

### D05 — Readiness / error / fallback semantics — INHERITED / FROZEN

- After successful startup, app readiness and embedding-runtime state remain separate: `ApplicationRuntime=READY` while embedding may be `UNLOADED|LOADING|READY|FAILED`. Embedding `FAILED` must not demote the app to `NOT_READY`.
- Static selected-representation failure at construction → startup fail-closed (`NOT_READY` / `startup_failed` / `resources=none`). No durable post-start embedding=`FAILED` process for a representation already statically invalid at construction.
- Dynamic: construction failure → `FAILED` + `runtime_initialization_failed`; post-READY execution failure → `FAILED` + `runtime_execution_failed`. Terminal until restart; no automatic retry, reconstruction, alternate-backend fallback, or profile reselection.
- Top-level envelopes (no new P2 `EMBEDDING_UNAVAILABLE` unless later UX IR proves need): `SETTINGS_INVALID` + bounded reason; `INGEST_FAILED` + `stage=dense`; query/embed against terminal embedding runtime → `RUNTIME_NOT_READY` + bounded embedding-runtime reason.
- Closed safe product reasons (categories): representation absent/invalid; CUDA unavailable; CUDA probe failed; precision requires CUDA; AUTO-selected profile unavailable; runtime initialization/execution failed. Paths, raw exceptions, loader errors, stacks, provider internals, artifact locations → log-only.
- Forbidden: AUTO→CUDA then silent CPU fallback; CPU→CUDA promotion; CUDA→CPU fallback; mid-run switch; API/UI “try the other backend”; test-load to heal FAILED; reconstruct without restart; treating unavailable **inactive** representation as failure of an otherwise valid **active** process.
- Readiness is **selected-profile scoped**: a running CUDA process remains valid if CPU ONNX is absent, and vice versa.

### D06 — Workspace / query / ingest interaction — INHERITED / FROZEN

- All embedding-dependent flows borrow the same process-owned `ApplicationRuntime → ProcessResources.embedder → QualifiedEmbeddingRuntime`. No per-workspace/snapshot/operation, query-only, or ingest-only sessions.
- Preserve `QueryRuntimeCache` / snapshot → `DenseRetriever(..., embedder=resources.embedder)`. Snapshot/runtime teardown must not close the process embedder; lifetime stays with `ApplicationRuntime`.
- First embedding-dependent op (query or ingest) may drive `UNLOADED→LOADING→READY|FAILED`; concurrent/subsequent consumers observe shared state — no independent second load/retry.
- On shared `FAILED`: query/embed → `RUNTIME_NOT_READY` + bounded reason; managed ingest → `INGEST_FAILED` + `stage=dense` (D05). Non-embedding inspect/control surfaces remain usable while app READY.
- Logical identity invariant: `cuda_fp16_v1` and `cpu_onnx_fp32_v1` share embedding/index space. Profile, representation implementation, provider, device, precision, ORT settings, `selection_reason` must **not** enter durable identity. No corpus rekey across backend changes.
- Additive optional execution provenance only (observational, non-semantic).
- Forbidden: CPU-query/CUDA-ingest split; workspace/snapshot profile selection; session construction inside `DenseRetriever`; pending settings mutating a running op; hot-switch after save; snapshot close releasing process embedder; backend-specific reindex/rekey. Pending policy affects **next process start only**.

### D07 — UI controls and user-visible status — INHERITED / FROZEN

- Extend existing Compute Settings UI only; no second settings surface; no editable execution-profile expert panel.
- Primary controls: Auto (Recommended) / CPU / GPU (CUDA). Save = next-start intent only; active/pending/`restart_required` unchanged; no apply-now / hot-switch.
- Primary status: configured policy; active embedding device; embedding runtime state; pending policy if different; restart-required; bounded availability/failure explanations.
- User-safe state wording (underlying state exact): `UNLOADED` → available/not yet loaded; `LOADING` → loading embedding model; `READY` → ready; `FAILED` → unavailable until restart. Do not imply whole app is down when only embedding failed.
- Secondary read-only technical details: `profile_id`, `representation_id`, backend family, provider, resolved precision, model revision, `selection_reason` — never editable.
- Candidates use D04 availability (disable/reject with bounded explanation); no UI test-load or independent viability probe.
- Embedding `FAILED`: Compute Settings remains usable to inspect and save different pending policy; save does not recover/replace failed runtime in-process.
- Outside P2: 16K-E worklist/progress/ETA; provider/ORT/precision editors; writable profile/representation IDs; advanced tuning; “switch now” / “retry with CPU” / “try another backend”; any UI-owned profile resolution.
- UX invariant: **Users choose a compute policy; Seneca reports the active resolved runtime. Users do not directly configure the execution substrate.**

### D08 — Compatibility with existing configuration / CLI — INHERITED / FROZEN

- Preserve existing configuration hierarchy/schemas; no P2 migration, third authority, or backend-specific dialect.
- `seneca-compute-settings-v1` stays schema-compatible: `compute.embedding_device = auto|cpu|cuda` — no version bump solely for dual-backend.
- YAML `indexing.embedding.device = auto|cpu|cuda` continues into the same resolver; product-managed Compute Settings keep current override precedence vs YAML. No new persistent source of truth for profile/representation/backend/provider/precision.
- `implementation="sentence_transformers"` remains logical identity, not physical selector. Forbid persisted `implementation="onnx"` (or equivalent) that would perturb `embcfg_`, index/collection identity, or historical corpus compatibility. `fake` stays test/CI-only.
- Legacy `precision=native|fp16` remains a resolver input under D04; not a new product control. Observability may expose both `configured_precision` and resolved/profile precision.
- Deterministic YAML/CPU-only tests continue isolating higher-precedence product/env overrides; do not depend on ambient Compute Settings or host GPU unless explicitly testing that boundary.
- `doctor` read-only: may report representation readiness, bounded reasons, CUDA probe facts, qualification/runtime-contract status; must not download/provision/repair/rewrite/load/infer/change config.
- Unified startup: `CLI → ApplicationRuntime.start() → ProcessResources → make_embedder()`. No CLI-specific resolver, direct ST construction, or alternate embedder lifecycle.
- Invariant: **Existing configuration expresses logical policy; the accepted P1 resolver maps that policy to the physical execution profile without changing durable embedding identity or creating a new configuration authority.**

### D09 — Persistence semantics for user compute preferences — INHERITED / FROZEN

- Only durable user-managed compute preference: `seneca-compute-settings-v1` → `compute.embedding_device = auto|cpu|cuda` via existing atomic product-settings write path.
- Must not persist derived execution state: profile/representation ID; backend/provider; configured/resolved precision as new product setting; ORT threads; artifact paths; `selection_reason`; CUDA probe outcome; embedding lifecycle state. Those are re-derived at startup.
- Successful PUT: differs from active → pending + `restart_required=true`; same as active → no manufactured pending/restart.
- `OFFLINE_RAG_EMBEDDING_DEVICE` when present remains authoritative and locks the product-managed device field; P2 must not weaken that precedence.
- Persisting preference must not rewrite corpora, embedding manifests, embcfg/index/collection identities, snapshots, or historical operation/provenance.
- Validate before persist (D04): unauthorized/unavailable → `SETTINGS_INVALID` + bounded reason; no write. No coercion (`cuda→auto/cpu`, `fp16→native`); no persist of known-unsatisfiable policy.
- Invariant: **persist user intent only; derive execution state at startup.**

### D10 — Startup vs runtime mutability — INHERITED / FROZEN

| Concern | At startup | During live process |
|---|---|---|
| Profile resolution | Once via `make_embedder()` / accepted resolver | Immutable for process lifetime |
| Selected representation validation | Full static validation; failure aborts startup | No hot revalidation |
| Availability snapshot | Once from read-only representation/CUDA checks; no model load | Cached for Compute Settings/capabilities; no per-request digest rehash |
| Heavy backend/session | Not created | Lazy first-use construction only |
| Embedding lifecycle | Begins `UNLOADED` | Only toward `READY` or terminal `FAILED` |
| Product device preference | Effective policy frozen into active process | Persist next-start intent only |
| Active profile/embedder | Constructed once | No reconstruction, hot-switch, fallback, or FAILED recovery |
| Application readiness | Established by successful startup | Embedding `FAILED` does not demote app from READY |

- Preserve distinction: next-restart availability vs current runtime health (e.g. CPU available READY + active CUDA `FAILED` does not authorize in-process failover).
- Availability snapshot stable for process lifetime; new process → new snapshot.
- Shutdown: drain workers per existing contract before releasing process embedding resources; snapshot teardown must not close embedder; final teardown via `ProcessResources.close()` at correct stage.
- Invariant: **pending configuration is mutable; active execution topology is not.**

### D11 — API schema and backward compatibility — INHERITED / FROZEN

- All P2 API/DTO changes additive only; existing paths, request shapes, and required fields remain valid.
- Preserve existing Compute Settings meaning for: `runtime.active_device`, `cuda_available`, `torch_cuda_build`, `selection_reason`, `availability.{auto,cpu,cuda}.available`. May add embedding state/profile/representation/backend/provider/precision/bounded reasons as **extensions**, not replacements.
- PUT remains `embedding_device: "auto"|"cpu"|"cuda"` only — no writable profile/representation/provider/precision/backend/runtime-state fields.
- Managed-operation dense provenance grows additively (optional `profile_id`, `representation_id`, backend family, provider, resolved precision); historical records without new fields remain valid; no forced provenance rewrite/migration.
- TypeScript: keep `"auto"|"cpu"|"cuda"`; may add bounded unions; preserve open-string forward-compat where already intentional.
- Do not hardcode scientific artifact SHA-256s, qualification-tree hashes, filesystem paths, or provisioning authority into frontend/API contracts.
- Errors: existing top-level codes unchanged (D05); bounded safe sub-reasons may expand; clients understanding only top-level codes remain correct. No new required request field to retain current behavior.
- Invariant: **old clients remain valid; new clients gain richer observability.**

### D12 — Security / offline boundary — INHERITED / FROZEN

- P2 product/runtime paths are consumption-only: startup/query/ingest/Compute Settings/capabilities/health/doctor must not download, export, quantize, repair, provision, rewrite, or mutate model artifacts.
- `/models` and configured embedding roots are read-only runtime inputs; acquisition/staging/install/mutation is P3/install-time, not P2.
- Product surfaces may expose bounded safe facts only (device policy, profile/representation IDs, runtime state, bounded reasons, authorized CUDA/provider/runtime facts). Must not disclose paths, stacks, raw ST/ORT/PyTorch/provider exceptions, loader traces, arbitrary manifest contents, or non-public provenance.
- Artifact digests are governance/qualification evidence, not general product telemetry — do not expose merely because qualification layer has them.
- No HF/network model-source calls from P2 profile resolution, readiness, startup, settings validation, doctor, query, or ingest; no phone-home of model-tree/artifact state.
- Preserve env-lock, authz, and atomic settings-write; observability is not a bypass.
- Capabilities/health/settings/doctor: cheap + read-only + non-mutating (D10 snapshot); no viability-by-loading the heavy model/session.
- Invariant: **runtime observes trusted local artifacts; it does not acquire, modify, disclose, or remotely validate them.**

### D13 — Installed-representation knowledge vs P3 — INHERITED / FROZEN

- P2 consumes P1 inspection/qualification **read-only**: at startup classify `torch_st_v1` / `onnx_fp32_v1` as `ABSENT|INVALID|READY`, cache in D10 snapshot, use for selected-profile startup validation, expose bounded readiness via Compute Settings/capabilities/doctor.
- P2 must not download/copy/stage/publish/export/quantize/repair/rewrite manifests or bundles, invent digests, regenerate invalid representations, provide provisioning CLI, package model repos/OCI, or mutate `/models`.
- Selected representation mandatory: not READY → startup fail-closed (D02/D05).
- Inactive ABSENT/INVALID must not invalidate an otherwise usable process; only disables that next-start choice (e.g. valid CUDA process + `onnx_fp32_v1=ABSENT` continues; CPU unavailable until P3 provisions).
- Selected missing/invalid = configuration/provisioning deficiency; product may explain with bounded reasons; remediation is install/P3 — no runtime self-heal.
- P2 inherits P1’s definition of READY; must not reimplement/weaken/extend/reinterpret qualification or scientific evidence.
- Phase boundary: **P1 defines/verifies trust → P2 observes/consumes → P3 acquires/installs/mutates.**

### D14 — Failure / recovery behavior — INHERITED / FROZEN

- Static startup failure: app never READY; operator fixes config/provisioning and starts a new process; selected-representation issues → P3/install-time, not P2 self-heal.
- Dynamic embedding `FAILED`: terminal for process lifetime; subsequent embed ops fail immediately (D05); app stays READY so settings/health/capabilities/diagnostics remain usable.
- Only recovery: **process restart**, optionally applying previously saved pending device policy.
- Forbidden: auto-retry; reconstruct; alternate-backend fallback; profile reselection; unload/reload APIs; UI “retry with CPU” / “switch now”; test-load recovery; reviving a terminal FAILED runtime object.
- In-flight managed ops use existing failure semantics (e.g. `INGEST_FAILED`); no special dual-backend recovery coordinator.
- Crash/journal/publication/shutdown ordering unchanged; embedding fits inside those guarantees.
- After restart: fresh lifecycle `new process → resolve → validate → QualifiedEmbeddingRuntime(UNLOADED)` — not resumption of prior FAILED object.

### D15 — Test strategy and deterministic acceptance matrix — INHERITED / FROZEN

P2 implementation acceptance is driven primarily by deterministic unit/integration tests around the already accepted P1 resolver/lifecycle boundary. P2 must not reopen embedding science, parity, quantization, or performance campaigns.

#### D15 Layer A–G deterministic acceptance matrix (normative)

This matrix is the durable, self-contained acceptance contract. Future implementers and independent reviewers must be able to evaluate it from this document alone.

**Layer A — ApplicationRuntime / lifecycle**

1. Exactly one qualified runtime is constructed per successful process startup.
2. Static selected-representation failure leaves app `NOT_READY` / `startup_failed` / `resources=none`.
3. Successful startup leaves app `READY` and embedder `UNLOADED`.
4. First-use initialization/execution failure leaves app `READY` and embedder terminal `FAILED`.
5. Query/ingest consumers receive the exact same embedder object (identity/borrow proof).
6. Snapshot/query-runtime teardown does not close the process-owned embedder (non-ownership proof).
7. Process shutdown drains workers before `ProcessResources.close()` releases the embedder.

**Layer B — Compute Settings API**

1. GET reports active process truth plus cached candidate availability.
2. CPU/CUDA/AUTO availability follows D04 exactly.
3. Unavailable/unauthorized selections return `SETTINGS_INVALID` with bounded reasons and no write.
4. Valid changed policy becomes pending with `restart_required=true`; same-as-active does not create spurious pending.
5. Env lock remains enforced.
6. A `FAILED` embedding runtime does not prevent GET/PUT.
7. Settings requests never heavy-load a backend or hot-switch the active profile.

**Layer C — Capabilities**

1. Existing capabilities contract remains backward compatible.
2. New embedding facts are additive, process-owned, and compact.
3. `FAILED` may be reported truthfully.
4. Pending next-start settings do not masquerade as active state.
5. Capabilities requests perform no backend load, re-resolution, or representation rehash.

**Layer D — Doctor**

1. Correctly reports legacy Torch-only, dual-ready, ONNX absent/invalid, Torch absent/invalid, and CUDA/probe states using bounded safe reasons.
2. No downloads, mutation, network access, repair, re-export, or heavy model/session construction.

**Layer E — Managed-operation provenance / compatibility**

1. Historical records without new execution fields remain valid.
2. New optional profile/representation/backend/provider/precision fields serialize and round-trip correctly.
3. Observability fields do not alter embedding/index/collection identity.
4. Provenance collection / telemetry observation itself must not cause backend loading.

**Layer F — Security / offline regression**

1. No new product path writes `/models`, downloads artifacts, phones home, exposes filesystem paths/raw exceptions, bypasses env locks, or weakens settings atomicity.

**Layer G — API / UI compatibility**

1. Existing request bodies remain valid; no required new fields; existing response fields retain meaning.
2. TypeScript DTO changes are additive.
3. UI exposes only Auto/CPU/GPU policy controls and read-only runtime detail; no profile/provider/precision editor or switch-now action.

#### Bounded real-product confirmation (unchanged)

Required before P2 implementation can be independently accepted; not a new scientific campaign.

Minimum CPU confirmation:

```text
fresh process → startup succeeds → app READY / embedding UNLOADED
  → one real embedding-dependent product operation → embedding READY
```

Then verify that Compute Settings and capabilities report the actual active CPU/ONNX profile and lifecycle state correctly.

CUDA product confirmation is conditional on suitable host availability and should not block a CPU-capable review environment if deterministic CUDA-path tests already cover the contract. If a CUDA host is available, a bounded equivalent confirmation is desirable.

#### Explicitly not part of P2 acceptance

- ONNX↔CUDA vector parity reruns
- full 1,296-chunk performance campaign
- throughput optimization
- alternate-model experiments
- quantization studies
- cross-profile interoperability promotion

Those remain inherited science/P4 territory.

#### Final P2 acceptance checklist

Prove at minimum: one process-owned shared runtime; exact resolver semantics; selected static representation fail-closed; no inactive-representation poisoning; lazy heavy load; terminal dynamic failure; no hot switching/fallback/reconstruction; restart-only policy application; additive API/UI compatibility; read-only P2 artifact behavior; no P3 capability pulled forward; unchanged logical embedding/index identity; bounded real-product confirmation PASS; Layers A–G PASS.

### D16 — Exact P2 implementation surface — INHERITED / FROZEN

A future P2 implementation authority may touch only the following areas, and only where required to implement D01–D15:

- `src/offline_rag/app/runtime.py` — integrate the accepted P1 runtime into `ProcessResources`, construct the startup availability snapshot, preserve existing application lifecycle ordering.
- `src/offline_rag/api/compute_settings.py` — additive runtime/availability DTOs, bounded reasons, candidate validation through the shared resolver, existing pending/restart semantics.
- `src/offline_rag/app/compute_product_settings.py` — preferably unchanged; only narrowly scoped compatibility work if implementation proves necessary. No schema migration.
- `src/offline_rag/api/capabilities.py` — compact additive projection of active process-owned embedding facts.
- `src/offline_rag/app/observability_publish.py` and directly related managed-operation/workspace provenance models — only for optional additive dense execution provenance.
- Existing doctor implementation/projection, such as `src/offline_rag/doctor.py` and its current CLI exposure — read-only representation/CUDA observability only. Any exact doctor/CLI projection path to be modified must be enumerated in the future implementation AUTH before modification.
- `src/offline_rag/app/query_runtime.py` — only if needed to preserve or prove the borrow-only/shared-object invariant; no independent resolver or embedder lifecycle.
- `ui/src/api/types.ts` plus the existing Compute Settings UI surface only — additive DTO support and D07 UX.

P1 substrate is consumed, not redesigned (out of scope by default):

- `src/offline_rag/dense/execution_profile.py`
- `src/offline_rag/dense/embedding_runtime.py`
- `src/offline_rag/dense/embedding_artifacts.py`
- `src/offline_rag/dense/onnx_embedder.py`
- package qualification resources under `src/offline_rag/resources/embedding_representations/`

If implementation discovers a genuine P1 defect, stop and handle through a separately authorized P1 corrective path rather than silently folding it into P2.

Explicitly outside P2: provisioning/download/install/package code; model acquisition or `/models` mutation; scientific/parity/performance harnesses; P3/P4 implementation; 16K-E progress/worklist/ETA UI; new settings pages; health-contract redesign; `/health/ready` reinterpretation around embedding state; backend/profile/provider/precision editors; new recovery/fallback machinery.

D16 freezes the **maximum allowed surface**, not the expected diff. The implementation authority must still enumerate its exact intended paths, and the final candidate must provide an exact changed-file list for IR.

Review rule: **Any changed production path outside the D16 universe is presumptively scope violation unless separately authorized before implementation.**

### D17 — Explicit exclusions for P3 / P4 / campaigns / main — INHERITED / FROZEN

- P2 design acceptance and later P2 implementation acceptance must not be read as implicit downstream authority.
- **P3 closed:** provisioning CLI, download/copy/stage, atomic install/publish, `/models` mutation, bundle force/repair, remote model repos, OCI/model packaging.
- **P4 closed:** cross-profile interoperability promotion, product-default profile selection, release qualification, CUDA/CPU preferred-lane declarations.
- **Campaigns closed:** parity reruns, full 1296, screens, quantization, alternate models, throughput/latency optimization — not smuggled in as “extra P2 validation.”
- **Main/release closed** unless separately governed: merge to main, release/tag, production promotion, default-device policy change, default-profile flip, broad deployment.
- **Adjacent product closed:** 16K-E worklist/progress/ETA; transport limits; auto upload partitioning; query-priority; WebSocket/SSE progress; unload/eviction; hot switching; automatic backend failover.
- Authorization chain: `P2 design accepted → P2 implementation eligible for separate AUTH` — **not** automatically authorized. Likewise `P2 implementation accepted ≠ P3/P4/campaigns/main`. Each successor needs explicit Human Authority.

### D18 — Independent-review gates — INHERITED / FROZEN

1. **Design completion** → STOP for independent design IR. Completing this document does not authorize production implementation.
2. **Design IR** evaluates inherited architecture conformance, internal consistency, phase boundaries, and completeness of D01–D17/D18. Terminals: ACCEPT / REQUEST_CHANGES / reject as applicable. ACCEPT = design acceptability only.
3. **Human after design IR** may issue design HA and/or a **separate** P2 implementation AUTH. Implementation is never inferred from design IR ACCEPT.
4. **Implementation** only under that AUTH (own parent SHA, branch, D16-bounded path list, D17 exclusions). Complete → STOP for independent implementation IR.
5. **Implementation IR** evaluates candidate against D01–D18, D15 matrix, D16 paths, D17 exclusions, compatibility, identity, lifecycle/failure, offline/security, bounded CPU confirmation. Implementation tip ≠ design tip.
6. **Human technical acceptance** only after implementation IR ACCEPT; closes P2 implementation only — still does not open P3/P4/campaigns/main.
7. Rework: IR finding → narrow corrective authority → corrected candidate → independent re-review. No scope widen via rework.
8. Invariant: design authority, design acceptance, implementation authority, implementation acceptance, and downstream promotion are distinct subjects/decisions.

---

## 6. Acceptance criteria (frozen from D01–D18)

This section is the normative acceptance contract for a future P2 **implementation** candidate. Satisfying these criteria under a separate implementation AUTH is required for independent implementation review. **Design IR ACCEPT does not authorize that implementation.**

### 6.1 Conformance claims

A P2 implementation must conform to:

1. Accepted dual-backend architecture (Rounds 1–12) and Round 10 P2 sketches as concretized by D01–D18.
2. Accepted P1 technical subject `fae82b2455cfdd0d1622065904a35895372740b6` as the sole embedding substrate — consumed, not redesigned.
3. Phase split: P1 trust/substrate · P2 product/API/UI integration · P3 acquisition · P4 later promotion.

### 6.2 Runtime ownership and lifecycle (D01, D02, D06, D10, D14)

1. Exactly one process-owned `QualifiedEmbeddingRuntime` occupies `ApplicationRuntime → ProcessResources.embedder`.
2. Startup resolves once via `make_embedder()` → `resolve_qualified_embedding_profile()`, validates the selected representation, constructs lightweight runtime; heavy backend remains `UNLOADED`.
3. Selected-representation static failure → app `NOT_READY` / `startup_failed` / `resources=none`.
4. After success: app `READY`, embedding `UNLOADED`; first use may `UNLOADED → LOADING → READY|FAILED`.
5. Application readiness and embedding-runtime state remain distinct after startup; embedding `FAILED` does not demote the app.
6. Query and managed ingestion borrow the same embedder object; no per-workspace/snapshot/operation sessions; snapshot teardown does not close the process embedder.
7. Dynamic `FAILED` is terminal until process restart; no reconstruct, fallback, hot-switch, or auto-retry. Only recovery is restart (optionally applying pending policy).
8. Startup availability snapshot is process-lifetime, read-only, no per-request rehash or model load.
9. Pending configuration is mutable; active execution topology is not.

### 6.3 Device / AUTO / CPU / CUDA semantics (D04)

1. Product vocabulary remains Auto/CPU/GPU(CUDA) → `embedding_device` `auto|cpu|cuda`.
2. Live resolution and save-time availability match the frozen D04 tables (explicit CPU authoritative; AUTO no silent downgrade; CUDA no CPU fallback).
3. `selection_reason` observational only.

### 6.4 API / UI / persistence / compatibility (D03, D07–D09, D11)

1. Compute Settings extended additively; PUT remains device-intent only; active/pending/`restart_required` unchanged; no hot-switch.
2. Runtime DTO projects live process facts; availability uses bounded safe reasons; write validation reuses the shared resolver.
3. UI extends existing Compute Settings only; primary Auto/CPU/GPU; read-only technical detail; no profile/provider/precision editors or switch-now actions.
4. Persist only `seneca-compute-settings-v1` → `compute.embedding_device`; no derived execution state persisted.
5. API/DTO changes additive; historical managed-operation records without new provenance fields remain valid; no scientific digests hardwired into frontend/API.

### 6.5 Errors, offline, representations (D05, D12, D13)

1. Existing top-level envelopes only (`SETTINGS_INVALID`, `INGEST_FAILED`+`stage=dense`, `RUNTIME_NOT_READY` + bounded reasons); closed safe reason vocabulary; no new `EMBEDDING_UNAVAILABLE` in P2 unless later UX IR.
2. Consumption-only offline boundary; no download/mutate/`/models` writes; no HF/network acquisition; no path/raw-exception disclosure in product responses.
3. P2 observes P1 readiness (`ABSENT|INVALID|READY`); selected must be READY at startup; inactive ABSENT/INVALID does not poison active process; remediation of missing assets is P3.

### 6.6 Deterministic acceptance matrix and confirmation (D15)

Future implementation IR must satisfy the **complete normative Layer A–G matrix recorded under D15** (above) — not merely the layer names. That D15 matrix is incorporated here by reference as the self-contained acceptance gate; do not reconstruct it by inferring across unrelated design sections.

Additionally require the bounded real-product CPU confirmation as frozen under D15:

```text
fresh process → app READY / embedding UNLOADED
  → one real embedding-dependent product operation → embedding READY
  → Compute Settings / capabilities report truthful active CPU/ONNX state
```

CUDA host confirmation is conditional per D15. Science/parity/1296/throughput/alternate-model/quantization/P4 interoperability are **not** P2 acceptance.
### 6.7 Implementation surface and exclusions (D16, D17)

1. Changed production paths must lie within the D16 universe; exact AUTH path list required; out-of-universe changes are presumptive scope violations.
2. P1 substrate files out of scope by default.
3. P3, P4, campaigns, main/merge/promotion, and adjacent 16K-E/transport/hot-switch work remain NOT AUTHORIZED by P2 design or P2 implementation acceptance.

### 6.8 Review gates (D18)

1. Design IR-001 subject `38dc365c…` disposition: **REQUEST CHANGES**. This narrow rework restores the durable D15 A–G matrix and D16 path notation; candidate is **READY FOR INDEPENDENT DESIGN IR-002**.
2. Design IR ACCEPT ≠ implementation authorization.
3. Implementation requires separate explicit AUTH, then independent implementation IR, then Human acceptance — still without opening successors.

---

## 7. Explicit non-authorization

This document, its design-open tip, and this design-completion publication do **not** authorize:

- P2 implementation
- P3 provisioning
- P4 acceptance / promotion
- campaigns
- main / merge / default promotion

Design IR ACCEPT likewise does not authorize those actions.

---

## 8. Document history

| Event | Subject / tip | Note |
|---|---|---|
| DESIGN OPEN | tip `c621b3ce…` (parent `7563ce0…`) | Authority opened; ledger initially OPEN; implementation NOT AUTHORIZED |
| DESIGN COMPLETE PUBLICATION | tip `38dc365c…` (parent `c621b3ce…`) | D01–D18 INHERITED/FROZEN; READY FOR INDEPENDENT DESIGN REVIEW; implementation NOT AUTHORIZED |
| DESIGN IR-001 | subject `38dc365c…` | REQUEST CHANGES — F001 D15 matrix compression; F002 D16 path notation clarification |
| DESIGN IR-001 NARROW REWORK | parent `38dc365c…` | Restore durable D15 A–G matrix; normalize D16 full paths; READY FOR IR-002; implementation NOT AUTHORIZED |
