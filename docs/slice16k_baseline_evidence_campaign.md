# Slice 16K — Baseline Evidence Campaign Manifest

**Authority:** `S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001` — AUTHORIZED  
**AUTH-open:** `S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-OPEN-001`  
**Governance parent:** `4f2c045717e2f8fe5b583173847a3bfa97046061`  
**Technical subject under measurement:** `40c6eb3824ac9f9c1cbc35c889e3e4110b229469`  
**Branch:** `evidence/16k-baseline`  
**Campaign status:** EXECUTION COMPLETE / FROZEN / INDEPENDENTLY ACCEPTED  
**Exact AUTH-open execution pin:** `eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e`  
**Freeze subject:** `S16-K-BASELINE-EVIDENCE-FREEZE-001`  
**Prior freeze tip (IR-001 subject):** `0d169ae62d620709b220e8ebc97b2932d64a843b`  
**Independent review:** `S16-K-BASELINE-EVIDENCE-FREEZE-IR-001` — REWORK REQUIRED (R1–R4)  
**Rework authority:** `S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework parent:** `0d169ae62d620709b220e8ebc97b2932d64a843b`  
**Independent review:** `S16-K-BASELINE-EVIDENCE-FREEZE-IR-002` — ACCEPT  
**Exact independently accepted freeze subject:** `3abc3a6c0ef31cc255ea6de8796203d26700ec23`  
**Human disposition:** HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS  
**Regression:** workspace query/conversation HTTP 500 after retrieval-model initialization  
**Diagnostic authority:** `S16-K-POST-BASELINE-LIVE-QUERY-REGRESSION-DIAGNOSTIC-AUTH-001` — AUTHORIZED  
**Exact diagnostic parent:** `3abc3a6c0ef31cc255ea6de8796203d26700ec23`  
**Observability remediation authority:** `S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001` — AUTHORIZED  
**Exact remediation parent:** `b65d1beda2ef8e19e59acebe498043b4188712c5`  
**Exact AUTH-open pin:** `0894a54bf5c8c8a06c0ec4821ebf3d804a92fc15`  
**Remediation branch:** `implementation/16k-query-failure-observability`  
**Remediation IR-001:** `S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-001` — REWORK REQUIRED (R1–R4)  
**Exact IR-001 subject:** `9a8d30333bdc9fad800411b861bb05d2a038ea35`  
**Exact IR-001 handoff tip:** `0ac6cd298e02f69133559aa682ac796ba90abfc8`  
**Rework authority:** `S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework parent:** `0ac6cd298e02f69133559aa682ac796ba90abfc8`  
**Exact rework AUTH-open pin:** `ea763e5da7eb55dc08a58bb783c360c43e75f3cb`  
**Exact rework review subject / technical subject:** `163078753eeda33959c9957cfad4e82876a7a5f5`  
**Exact rework handoff tip:** `17fc511b3ac12a1a7822ca012b7a6d2309f859bf`  
**Observability remediation:** IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent review:** `S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002` — ACCEPT  
**Exact independently accepted technical subject:** `163078753eeda33959c9957cfad4e82876a7a5f5`  
**IR-002 acceptance-record authority:** `S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `17fc511b3ac12a1a7822ca012b7a6d2309f859bf`  
**Exact IR-002 acceptance-record tip:** 6d1902c10ead7ee5a3b0ccfe640112c78ae0b9fd  
**Human acceptance of observability remediation:** NOT RECORDED under this authority  
**Constrained-VRAM diagnostic authority:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-AUTH-001` — AUTHORIZED  
**Exact constrained-VRAM diagnostic parent:** `98a5d1f6dceb6c51943c6888b39adb28926eb27f`  
**Diagnostic branch:** `diagnostic/16k-constrained-free-vram-reproduction`  
**Diagnostic status:** EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW  
**Constrained-VRAM diagnostic status:** EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED  
**Scientific diagnostic execution:** EXECUTION COMPLETE / NO RERUN REQUIRED  
**Constrained-VRAM diagnostic IR-001:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-001` — REWORK REQUIRED (R1–R2)  
**Constrained-VRAM rework authority:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-REWORK-AUTH-001` — AUTHORIZED  
**Exact constrained-VRAM rework parent:** `a71f4fe2202be0fd1f7a4460d0287e407eec953a`  
**Constrained-VRAM rework status:** COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent review:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002` — ACCEPT  
**Exact independently accepted subject:** `7ad48b71dcdc096669399a4ea9b165cffa2d226b`  
**Acceptance-record authority:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `7ad48b71dcdc096669399a4ea9b165cffa2d226b`  
**Historical HTTP 500:** NOT REPRODUCED / ROOT CAUSE UNRESOLVED  
**CUDA-class failure:** NOT OBSERVED  
**M0–M2 eligibility gate:** NOT SATISFIED  
**GPU residency/allocator diagnostic design authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-AUTH-001` — AUTHORIZED  
**Exact GPU residency design parent:** `bd450fd601e655fc03e9c7c929075aa9c3673e9c`  
**Design branch:** `design/16k-gpu-residency-allocator-diagnostic`  
**Design status:** DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW  
**GPU residency/allocator diagnostic design status:** DESIGN COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent design review:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001` — ACCEPT  
**Exact independently accepted design subject:** `2417e47fc2aef1d59c31f0307a0cdb222c56e618`  
**Acceptance-record authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `2417e47fc2aef1d59c31f0307a0cdb222c56e618`  
**GPU residency/allocator diagnostic tooling authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-AUTH-001` — AUTHORIZED  
**Exact GPU residency tooling parent:** `d501370aef96c953f4780d2048d11b91306ee856`  
**Tooling branch:** `implementation/16k-gpu-residency-allocator-diagnostic-tooling`  
**Tooling status:** TOOLING IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT TOOLING REVIEW  
**GPU residency/allocator diagnostic tooling status:** TOOLING IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent tooling review:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001` — ACCEPT  
**Exact independently accepted tooling subject:** `a26ea53f6ce32c6454d21a6d6af988d50299ae49`  
**Tooling acceptance-record authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact tooling acceptance-record parent:** `a26ea53f6ce32c6454d21a6d6af988d50299ae49`  
**GPU residency/allocator diagnostic execution authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001` — AUTHORIZED  
**Exact GPU residency execution parent:** `a04d8f6131553beed0585a3c877cfbc2641c1863`  
**Execution branch:** `diagnostic/16k-gpu-residency-allocator`  
**Historical execution handoff:** EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW  
**Execution subject:** `c9daa88fb80c63c7ce6106e8d73df1976aae09d4`  
**Independent diagnostic review (IR-001):** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-001` — REWORK REQUIRED (F001: evidence not repository-visible) — preserved as provenance  
**Evidence publication authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EVIDENCE-PUBLICATION-AUTH-001` — AUTHORIZED  
**Exact evidence publication parent:** `c9daa88fb80c63c7ce6106e8d73df1976aae09d4`  
**Evidence path:** `docs/evidence/16k_gpu_residency_allocator/`  
**Exact independently accepted review/evidence subject:** `579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2`  
**Independent diagnostic review (IR-002):** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002` — ACCEPT  
**GPU residency/allocator diagnostic status:** EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED  
**Scientific disposition:** NEGATIVE / INDEPENDENTLY ACCEPTED  
**M0–M2 eligibility gate:** NOT SATISFIED / INDEPENDENTLY ACCEPTED  
**Acceptance-record authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2`  
**Historical HTTP 500 (GPU residency campaign):** ROOT CAUSE UNRESOLVED  
**Further GPU residency/allocator diagnostic tranche:** NOT IMPLIED / NOT AUTHORIZED  
**16K-C authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact 16K-C parent:** `f2741c105db48aea081b5282dc48e4b7f11fd6b6`  
**16K-C branch:** `implementation/16k-c-first-user-capacity-model`  
**16K-C status:** IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED  
**16K-C independent review (IR-001):** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-001` — REWORK REQUIRED (F001) — preserved as provenance  
**16K-C rework authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-REWORK-AUTH-001` — AUTHORIZED  
**Exact 16K-C rework parent:** `40e5b096041805fb149516b6eb89c793f6519213`  
**16K-C independent review (IR-002):** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002` — ACCEPT  
**Exact independently accepted 16K-C subject:** `219c8551d208530ec93c5697ca5591ad52bfb228`  
**16K-C acceptance-record authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact 16K-C acceptance-record parent:** `219c8551d208530ec93c5697ca5591ad52bfb228`  
**F001:** CLOSED  
**16K-C document:** `docs/slice16k_c_first_user_capacity_model.md`  
**Execution document:** `docs/slice16k_gpu_residency_allocator_diagnostic_execution.md`  
**Execution scope:** frozen C0/H3/H1/H2/H4 matrix under accepted design+tooling; scientific rerun / further GPU diagnostic tranche NOT AUTHORIZED under acceptance-record AUTH; M0–M2 / device-CUDA / fireground / main NOT AUTHORIZED  
**Tooling document:** `docs/slice16k_gpu_residency_allocator_diagnostic_tooling.md`  
**Tooling scope:** env-gated in-process probe + runner; campaign execution NOT AUTHORIZED  
**Design document:** `docs/slice16k_gpu_residency_allocator_diagnostic_design.md`  
**Design scope:** state/history-dependent residency + allocator hypotheses beyond static free-VRAM; execution NOT AUTHORIZED; M0–M2 / 16K-C/D / device-CUDA policy / fireground / main NOT AUTHORIZED  
**Exact constrained-VRAM execution tip:** c921c954da25a2f61415707d2f5b54579bc48571  
**Evidence path:** `docs/evidence/16k_constrained_vram/`  
**Campaign outcome:** no CUDA-class failure at B1 (free≈1912 MiB) or B2 (free≈494 MiB); B1-repeat skipped; all primary turns HTTP 200 / durable `model_abstain` / `internal_failure` null; historical 500 not reproduced  
**Diagnostic scope:** controlled free-VRAM reproduction on instrumented build; external occupant only; M0–M2 NOT AUTHORIZED  
**Rework scope:** close IR-001 R1–R4 only; no VRAM/device/CUDA behavioral fix  
**Remediation scope:** durable `internal_failure` + server traceback for grounded-query `internal_error`; no VRAM/device/CUDA behavioral fix  
**Public projection:** GET `/v1/trace/{id}` allowlist excludes `internal_failure`  
**Device/VRAM/CUDA behavior:** unchanged  
**Accepted B0–B3 evidence:** retained / not rewritten  
**Evidence paths:** `docs/evidence/16k_baseline/*.json`  
**Freeze narrative:** `docs/slice16k_baseline_evidence.md`  

This document remains the pre-execution measurement contract. It is **not** the
results narrative. Design charter remains
[`docs/slice16k_beta_ingestion_readiness_design.md`](slice16k_beta_ingestion_readiness_design.md)
(Q3 / Q11 / Q12 / Q13 / §9.1). Those questions are **not** reopened here.

### Execution-closed record

- B0–B3 execution complete under execution pin `eb0ebd86…`
- Campaign workspace (live): `ws_5cba280e8c3649e7babe980cc87b2566`
- B1 operation: `wop_6ec49226e3034c5ebc5af2d2c63f5fe8` — succeeded
- B2 operation: `wop_735d1d59a0994032a78cb4258494adb8` — succeeded
- API PID continuity: `1926194` through B1 → idle → B2
- IR-001 REWORK REQUIRED (R1–R4) against `0d169ae6…`; evidence/docs-only rework
  successor is the candidate for re-review (no campaign rerun)

### Rework preservation note

Scientific measurements, operation IDs, hashes, identities, historical
operations, and raw memory samples remain immutable. Rework corrects residency
semantics, runtime_config_fingerprint provenance (`not_captured`), timing
labels, and the BF16/SDPA vs FP32 evidence constraint only.

## 1. Purpose

Produce a durable, independently reviewable 16K baseline evidence subject that
establishes present-system workload, performance, GPU-memory, reuse, and
reliability characteristics **before** 16K-C changes capacity policy or 16K-D
changes CUDA/dense execution.

## 2. Frozen execution rule

**Measure first. Do not improve while measuring.**

The campaign may measure the accepted system and publish reproducible evidence.
It may **not** change the system to improve the result.

Canonical baseline must preserve the accepted runtime configuration, including:

- embedding model + revision
- embedding text contract = plain / plain-v1
- embedding dimension
- device policy
- resolved CUDA path (when CUDA is selected)
- dtype
- batch size
- attention path
- chunking semantics
- dense/lexical identities
- Qdrant behavior
- model-residency behavior (observe; do not correct)

If the accepted system keeps the embedding model resident after use, the
baseline observes that behavior rather than correcting it.

**Forbidden in the canonical baseline run:** CUDA→CPU fallback, cache clearing,
model unloading, reduced batch size, FP16, alternate attention, allocator
tuning, `torch.cuda.empty_cache()`, or similar intervention.

## 3. Static configuration pins (repository defaults under measurement)

These are inherent repository/config defaults for the technical subject. Live
resolved values are recorded in B0 / run JSON (not in this opening commit as
runtime measurements).

| Pin | Value |
|---|---|
| Embedding model_id | `Qwen/Qwen3-Embedding-0.6B` |
| Embedding revision | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| Embedding dimension | `1024` |
| Indexing embedding text contract | `plain` / `plain-v1` |
| Embedding batch_size (default) | `32` |
| Embedding device policy (default) | `auto` |
| Adapter contract | `sentence-transformers-v1` |

## 4. B1 workload identity — B1-FIREGROUND-INCIDENT-CLASS-V1

Exact Fireground incident-class workload previously exercised in the
failed/successful source-add sequence. Source bytes remain **external/private**
and are **not** committed to Git. Identity is by content hashes, not folder path.

### 4.1 Member table (immutable)

Member count: **1**

Canonical member rows (already ordered by
`(content_sha256, display_name, byte_size)`):

```json
[{"byte_size":6796067,"content_sha256":"01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2","display_name":"Fireground_Operational_Guides.pdf"}]
```

**Aggregate manifest hash** (SHA-256 of the UTF-8 canonical JSON array above,
`sort_keys=true`, `separators=(",", ":")`, no whitespace):

`9864d642c45b485f175555dff229252fceea1b81437869189179766508526070`

### 4.2 Historical durable references

| Field | Value |
|---|---|
| Historical workspace_id | `ws_fdd77b77611448eb93cdc239d2610281` |
| Historical published source_id (post-success) | `src_b56617ebdc90460fbf0c46536d278275` |
| Historical active_from_snapshot_id | `snap_3c4048d380b1f5db12a20f820082c1942ccaacc96e368dfb04c22aba5090a9c9` |
| Historical failed op (observability-era CUDA dense failure) | `wop_e6fa35c221a94189a71df317edd28ca6` |
| Historical prior failed op (same bytes; earlier dense failure) | `wop_b6133d6d172c43058f9d81edd566a4f3` |
| Historical successful Fireground SOURCE_ADD | `wop_861fc8bfcfc34dd1a20f3badcccd630b` |
| Adjacent successful SOURCE_ADD (different bytes; same session) | `wop_11cdee8f125a45c394bd5ae1accdcd2b` |
| Expected incident-class searchable-child scale (historical) | Workspace `child_chunk_count` **3113** on failed Fireground attempts; **3208** on successful Fireground publish (workspace desired-set including this member). Fresh empty-workspace B1 child count is measured, not predetermined. |
| Document identity | `doc_01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2` |

Pre-open readonly inventory reconciled external bytes to the vault
`content_hash` / historical ops above. Local folder paths are intentionally
omitted from this document.

### 4.3 B0 verification rule

Before B1 starts, B0 recomputes count + member SHA-256 table + aggregate hash
from the available external set and compares to this frozen definition.

- **Exact match** → B1 may proceed.
- **Any mismatch** (missing/extra member, size/hash change, aggregate mismatch)
  → B1 MUST NOT START. Do not silently substitute. Stop for a bounded campaign
  amendment selecting an explicitly non-identical equivalent labeled e.g.
  `B1-INCIDENT-CLASS-EQUIVALENT-V1 — NOT BYTE-IDENTICAL TO HISTORICAL INCIDENT`.

## 5. Run matrix

### B0 — Environment / pin capture

Record repository SHA (execution pin), technical subject, configuration hashes,
model/revision, device, dtype, batch size, attention backend when observable,
GPU identity/VRAM, software/runtime versions relevant to CUDA/PyTorch, starting
workspace/snapshot state for the **new** campaign workspace (not yet created at
AUTH-open), and as-found scientific artifact-cache reuse inventory where
observable.

B0 may inspect an as-found running process for pins but **must not** make
residency claims from that process. B0 records B1 manifest verification result.

### Pre-B1 cold restart

One intentional API/server restart immediately before B1 to establish a known
cold process state. Confirm embedding model not yet loaded; record pre-B1
GPU/PyTorch memory. This is measurement preparation, not remediation.

### B1 — Cold-process / fresh-workspace replay

- Label: cold-process / fresh-workspace replay of B1-FIREGROUND-INCIDENT-CLASS-V1
- Workspace: newly created under this campaign AUTH; EMPTY; active sources = 0;
  current snapshot = null; no prior scientific mutation history except creation
- Operation: `SOURCE_ADD` of the exact Fireground member set
- Process/model: cold by controlled restart
- Scientific artifact cache: **as-found, not cleared**
- Generated/reused work: measured, not predetermined

### Idle residency window (15 minutes)

Same uninterrupted API PID. Samples:

- **T0:** immediately after B1 terminal state
- **T+5m:** short-term idle sample
- **T+15m:** end-of-idle sample

At each sample record: external GPU used/free; `torch.cuda.memory_allocated()`;
`torch.cuda.memory_reserved()`; `torch.cuda.mem_get_info()`; embedding model
loaded/resident state if safely observable; API PID; wall-clock timestamp;
whether intervening query/background work occurred if practical.

Claim boundary: “Model/allocator residency persisted for at least 15 minutes of
observed application idleness.” Not an eviction-policy recommendation.

### B2 — B2-WARM-REUSE-REPLACE-V1

- Same workspace as B1
- Target: Fireground logical source created/published by B1
- Operation: `SOURCE_REPLACE` with byte-identical replacement (same content
  SHA-256 / document identity)
- Expected scientific membership: unchanged
- Expected lineage change: same `source_id`; source version increments;
  workspace revision advances; new operation ID / idempotency key
- Verify active desired set equals expected membership before and after B2
- If B2 unexpectedly generates scientific work instead of reusing it, record
  that as evidence; do not modify the run to force reuse

### B3 — Residency / continuity analysis (not a third ingest)

Analysis over B1 → idle → B2 only. Answers whether model/allocator state
persisted through 15 minutes of idleness, what changed when the second
operation began, and whether the second operation remained stable.

### Process continuity contract

- One intentional cold restart immediately before B1
- Thereafter one uninterrupted API process through B1, idle, B2, and B3
- No server restart, no `torch.cuda.empty_cache()`, no explicit unload, no
  device migration, no batch/config changes
- Record at minimum: API/server PID, process start timestamp, repository SHA /
  execution pin, runtime config hash, GPU identity, CUDA/PyTorch versions
- If the process dies, restarts, reloads under a new PID, or CUDA state is
  otherwise reset between B1 and B3: residency sequence is **invalidated**.
  Do not splice measurements across processes. Rerun from a fresh cold start
  or stop for review if the interruption is material evidence.

## 6. Required measurements

Authoritative list: design §9.1 / Q11. Capture where obtainable without
modifying product behavior:

- searchable children and document counts
- generated/reused embeddings
- input-token p50/p95/p99/max
- oversized-unsplittable count
- per-batch max sequence length
- encode duration
- embedding-artifact persistence duration
- dense point construction duration
- Qdrant materialization/upsert duration
- parse / chunk / dense / lexical / publication / finalization / total durations
- device, dtype, batch size, attention backend
- chunks/sec and reliable model-input tokens/sec
- first-batch versus steady-state timing
- CUDA memory observations (see §5 idle + before/during/after B1 and B2)

Distinguish `torch` allocated / reserved / `mem_get_info` free from external
GPU used/free. Do not falsely equate WSL/Windows GPU reporting with PyTorch
allocator state.

## 7. Reliability evidence (historical)

The freeze artifact must include already-observed Fireground history as
**historical** evidence (not campaign-generated):

- prior `cublasGemmEx` / dense failure with truthful partial counters
  (`wop_e6fa35…`: embeddings_generated=384, embeddings_reused=2528,
  embeddings_failed=32, classification=`embedding_generation_failed`)
- prior related failure `wop_b6133…` (same bytes; earlier observability gap)
- subsequent successful source addition `wop_11cdee8f…` (adjacent)
- subsequent successful Fireground source addition `wop_861fc8…`
- persistent GPU residency remains an observation target for the live campaign

The baseline may conclude the failure appears intermittent/runtime-state
dependent if evidence supports that formulation. It must **not** claim the CUDA
root cause is solved.

## 8. Permitted repository changes

Production source is forbidden.

Permitted under this campaign:

- `docs/slice16k_beta_ingestion_readiness_design.md`
- `docs/slice16_implementation_plan.md`
- `ROADMAP.md`
- this campaign manifest
- `docs/slice16k_baseline_evidence.md` (freeze narrative; later)
- `docs/evidence/16k_baseline/*.json` (later)

A small benchmark-only / non-product helper may be added only if required to
reproducibly collect measurements that cannot reasonably be captured otherwise.
If used, it must live outside production `src/`; not be imported by product
code; not alter runtime configuration; not unload models or clear CUDA caches;
not mutate scientific results; and be obviously measurement-only.

If meaningful measurement requires modifying `src/offline_rag/**`, **STOP** and
request scope expansion.

## 9. Evidence artifact paths (post-run)

```
docs/evidence/16k_baseline/b0_pins.json
docs/evidence/16k_baseline/b1_fireground_incident_class.json
docs/evidence/16k_baseline/b2_warm_reuse_replace.json
docs/evidence/16k_baseline/b3_residency.json
docs/evidence/16k_baseline/historical_reliability.json
docs/slice16k_baseline_evidence.md
```

JSON files are machine-readable factual records, not prose conclusions.

## 10. Explicitly forbidden

This authority does **not** authorize:

- 16K-C implementation / expanded production capacity
- 16K-D optimization (FP16, batch-size changes, attention changes, GPU model
  eviction/unloading policy, `empty_cache` policy, CUDA fallback/retry changes)
- Fireground corrective implementation
- 16K-E UI changes
- 16K-F full beta-corpus acceptance
- 16K-G
- production code changes
- main promotion

## 11. Acceptance boundary / STOP

Campaign ends with frozen evidence candidate
`S16-K-BASELINE-EVIDENCE-FREEZE-001` answering, without prescribing fixes:

1. What is the current workload cost?
2. Where is time spent?
3. How much embedding work is generated versus reused?
4. What does CUDA memory do before, during, and after sequential operations?
5. Does the accepted model remain resident after ingestion?
6. Is the current runtime stable across the bounded baseline sequence?
7. What evidence constrains 16K-C capacity design?
8. What evidence constrains 16K-D optimization/reliability design?
9. What remains unknown?

Then: **STOP FOR INDEPENDENT S16-K-BASELINE-EVIDENCE-FREEZE-001 REVIEW.**

No 16K-C or 16K-D authority is implied by completing the runs.
