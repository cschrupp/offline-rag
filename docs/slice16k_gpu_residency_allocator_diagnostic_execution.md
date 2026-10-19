# Slice 16K — GPU Residency / Allocator Diagnostic Execution

**Authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001` — AUTHORIZED  
**Exact parent:** `a04d8f6131553beed0585a3c877cfbc2641c1863`  
**Branch:** `diagnostic/16k-gpu-residency-allocator`  
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
**Historical HTTP 500:** ROOT CAUSE UNRESOLVED  
**Further GPU residency/allocator diagnostic tranche:** NOT IMPLIED / NOT AUTHORIZED  
**Controlling design:** `docs/slice16k_gpu_residency_allocator_diagnostic_design.md` (accepted)  
**Accepted tooling subject:** `a26ea53f6ce32c6454d21a6d6af988d50299ae49`  
**Tooling acceptance-record parent:** `a04d8f6131553beed0585a3c877cfbc2641c1863`  

**Human disposition:** HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS  

Historical execution under explicit go-ahead completed at scientific checkout
`c9daa88…`. IR-001 withheld acceptance solely for F001 (evidence not
repository-visible); evidence publication closed that defect at `579d1fa…`.
IR-002 ACCEPT independently accepts the published NEGATIVE scientific result and
M0–M2 eligibility = NOT SATISFIED. This acceptance-record commit is docs-only;
**no scientific rerun**, further GPU diagnostic tranche, M0–M2, 16K-C/D,
device/CUDA policy, Fireground, or main promotion is authorized under it.

---

## 1. Controlling inheritance (unchanged)

From the accepted design + tooling:

- historical binding and pre-request mechanical assert;
- product behavioral baseline `163078753eeda33959c9957cfad4e82876a7a5f5` plus
  the three accepted diagnostic instrumentation deltas (manifest digests at
  `a26ea53…`);
- campaign-positive = HTTP 500 + durable CUDA-related `internal_failure`;
- order family: C0 → H3 → H1 → H2 → H4;
- repeat + matched recovery before declaring a controlled causal candidate;
- M0–M2 eligibility ≠ authorization;
- static free-VRAM alone remains NOT SUFFICIENTLY CAUSAL / NOT REPRODUCED;
- historical HTTP 500 ROOT CAUSE UNRESOLVED.

---

## 2. Frozen execution matrix

| Cell | Fresh-process conditioning before bound request | Purpose |
|------|--------------------------------------------------|---------|
| **C0** | No induced model/history/allocator conditioning | Cold reference |
| **H3-A** | `load_embedder` → `load_reranker` | Dual-resident E→R ordering |
| **H3-B** | `load_reranker` → `load_embedder` | Dual-resident R→E ordering |
| **H3-C** | `touch_embedder` → `touch_reranker` | E→R prior-use / process-history |
| **H3-D** | `touch_reranker` → `touch_embedder` | R→E prior-use / process-history |
| **H1-A** | `load_embedder` only | Embedder-resident; reranker not yet resident |
| **H1-B** | `load_reranker` only | Reranker-resident; embedder not yet resident |
| **H2-C** | `load_embedder`; no allocator manipulation | H2 matched allocator control |
| **H2-A** | `load_embedder` → `h2_reserve_gap` | Same-process reserve-gap history |
| **H2-B** | `load_embedder` → `h2_fragment` | Same-process fragmentation proxy |
| **H4-A** | `load_embedder` → `load_reranker`, then external memory-only occupant targeting **400–800 MiB** free | External contention after Seneca residency |

No arbitrary additional cells during execution. No redundant “both models”
H1 cell (H3 covers dual residency + order/history).

---

## 3. H2 executability rule

Do **not** condition the allocator before loading both models and assume the
manipulation survived. Tooling evidence showed dual-model load can consume most
of a created reserve gap.

H2 common pre-request residency anchor:

1. fresh API process;
2. `load_embedder`;
3. verify embedder CUDA-resident and reranker **not** yet loaded/resident;
4. require probe-reported CUDA free memory ≥ **1024 MiB**;
5. execute H2 manipulation (`h2_reserve_gap` or `h2_fragment`);
6. capture allocator state immediately before the primary request;
7. issue frozen `conversation/turn` (request may naturally load the reranker).

If ≥1024 MiB free is not met after embedder-only residency → **H2 NOT EXECUTABLE**
under this tooling. Do not weaken the precondition or modify the probe under
this execution authority.

**H2-A established only if** post-action allocator shows increased
reserved-vs-allocated gap with live allocated memory returned to pre-action
level.  
**H2-B established only if** retained 64 MiB pattern and increased fragmentation
proxy / `inactive_split_bytes` are observable.  
Otherwise: **MANIPULATION NOT ESTABLISHED / INCONCLUSIVE** (not negative).

---

## 4. H4 rationale

Memory-only CUDA occupant (no compute stress); free band **400–800 MiB**.

Prior constrained-VRAM campaign showed static pressure in this band alone was
insufficient. H4 changes history: both Seneca models resident first, then
external contention — an interaction test, not a rerun of the old free-VRAM
campaign.

---

## 5. Per-cell protocol

Every ordinary matrix cell: **one** fresh-process primary run initially. No
routine repetition of successful cells.

Before each primary request, mechanically verify:

| Check | Value |
|-------|--------|
| workspace_id | `ws_fdd77b77611448eb93cdc239d2610281` |
| revision | `13` |
| snapshot_id | `snap_3c4048d380b1f5db12a20f820082c1942ccaacc96e368dfb04c22aba5090a9c9` |
| question | `what is common valor?` |
| prior_turns | `[]` |
| surface | `POST /v1/workspaces/{id}/conversation/turn` |
| product code | baseline `163078753…` + exactly the three accepted diagnostic deltas; SHA-256 must equal tooling manifest at `a26ea53…`; no other `src/offline_rag/**` deltas |

Any mismatch → **run STOP** (do not substitute current state).

---

## 6. Positive / repeat / recovery

**Campaign-positive** = HTTP 500 + durable CUDA-related `internal_failure`
(existing classifier). Console CUDA text alone is not campaign-positive.

On first campaign-positive cell:

1. preserve evidence;
2. same exact cell in a **new** API process;
3. if reproduces → fresh-process **matched recovery** (manipulated factor removed;
   other conditioning preserved as closely as possible).

| Family | Matched recovery |
|--------|------------------|
| H3 | fresh C0/reference (no induced load/history) |
| H1 | fresh C0/reference |
| H2-A/B | fresh **H2-C** (embedder-only, no allocator manipulation) |
| H4-A | fresh dual-resident E→R, **no** occupant |

Only **failure → fresh-process reproduction → matched-control recovery**
establishes a controlled causal candidate. Then **STOP** the entire campaign.

Conditioning-time failure (model load / allocator primitive before the bound
request) is **not** campaign-positive: record
`CONDITIONING_FAILURE` / `CELL_NOT_EXECUTABLE`.

---

## 7. Stage progression

```
C0 → H3-A…D → H1-A/B → H2-C/A/B → H4-A
```

Qualifications:

- reproduced + recovery-controlled positive → stop immediately;
- H4 runs only if H1–H3 and executable H2 cells are negative or inconclusive.

---

## 8. Evidence

Path: `docs/evidence/16k_gpu_residency_allocator/`

Each run JSON includes design §10 fields plus at least:

- execution authority and execution checkout SHA;
- accepted tooling subject `a26ea53…`;
- tooling acceptance-record parent `a04d8f6…`;
- cell and fresh-process run identity;
- exact conditioning action sequence;
- probe `api_pid`;
- loaded-model / CUDA-resident inventories;
- allocator allocated / reserved / stats;
- host GPU used/free; per-process GPU when available;
- H2 manipulation checks;
- occupant PID/allocation for H4;
- binding assertion;
- primary HTTP status and timing;
- trace ID and durable classification;
- whether candidate-positive criteria were satisfied;
- repeat/recovery relationship when applicable.

Diagnostic token must never enter evidence or logs.

At campaign termination: `campaign_summary.json` (matrix executed, skips/reasons,
stopping condition, scientific disposition, M0–M2 eligibility state).

---

## 9. Terminal scientific dispositions

| Disposition | Meaning |
|-------------|---------|
| **POSITIVE** | Reproduced CUDA-class failure + matched recovery; controlled causal candidate |
| **NEGATIVE** | All authorized executable cells completed without reproduced positive |
| **INCONCLUSIVE** | Material cells could not establish manipulation / execute / binding integrity; or results cannot support a causal disposition |

A positive identifies a controlled causal candidate for the historical failure
**class**. It does **not** establish production root cause by itself.

---

## 10. Authority boundary

**Authorized under this AUTH (when execution go-ahead is given):** frozen campaign
above; evidence generation; process startup/termination; accepted diagnostic
probe/actions; existing memory-only H4 occupant.

**Not authorized:** production-code changes; probe/tooling modifications;
`torch.cuda.empty_cache()`; model eviction/unload policy; device-policy changes;
compute-stress occupants; `/query` as a matrix dimension; M0–M2 implementation;
16K-C/D; fireground corrective work; main promotion.

`/query` remains post-hoc surface-isolation only after informative primary
failure or ambiguity.

---

## 11. Publication gate

**AUTH-open commit (historical):** documented on five 16K ledgers + this
execution contract; STOP before C0 until explicit go-ahead.

**Evidence-publication commit (this corrective authority):** preserve
byte-for-byte campaign artifacts under
`docs/evidence/16k_gpu_residency_allocator/`, publish
`scripts/diag_gpu_residency/run_campaign.py`, and record IR-001 F001 rework /
publication status. No scientific cell may be rerun under
`…-EVIDENCE-PUBLICATION-AUTH-001`.
