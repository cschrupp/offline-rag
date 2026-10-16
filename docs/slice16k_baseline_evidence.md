# Slice 16K — Baseline Evidence Freeze Narrative

**Freeze subject:** `S16-K-BASELINE-EVIDENCE-FREEZE-001`  
**Campaign authority:** `S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001`  
**AUTH-open / execution pin:** `eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e`  
**Technical implementation measured:** `40c6eb3824ac9f9c1cbc35c889e3e4110b229469`  
**Disposition:** BASELINE EVIDENCE FROZEN / PENDING INDEPENDENT REVIEW  

Campaign contract:
[`docs/slice16k_baseline_evidence_campaign.md`](slice16k_baseline_evidence_campaign.md)

Machine-readable evidence:

- [`docs/evidence/16k_baseline/b0_pins.json`](evidence/16k_baseline/b0_pins.json)
- [`docs/evidence/16k_baseline/b1_fireground_incident_class.json`](evidence/16k_baseline/b1_fireground_incident_class.json)
- [`docs/evidence/16k_baseline/b2_warm_reuse_replace.json`](evidence/16k_baseline/b2_warm_reuse_replace.json)
- [`docs/evidence/16k_baseline/b3_residency.json`](evidence/16k_baseline/b3_residency.json)
- [`docs/evidence/16k_baseline/historical_reliability.json`](evidence/16k_baseline/historical_reliability.json)

Evidence classes used below:

- **Measured fact** — directly observed
- **Derived metric** — calculated from measured values
- **Historical evidence** — prior Fireground operations
- **Interpretation / hypothesis** — not a finding

This freeze does **not** authorize 16K-C or 16K-D.

---

## Run identities

| Run | Identity |
|---|---|
| B0 | Pin/config capture + B1 manifest verification (`match=true`) |
| Cold start | WSL restart cleared prior API; intentional cold API PID `1926194` before B1 |
| B1 | `wop_6ec49226e3034c5ebc5af2d2c63f5fe8` SOURCE_ADD in fresh `ws_5cba280e8c3649e7babe980cc87b2566` |
| Idle | Same PID; samples T0 / T+5m / T+15m |
| B2 | `wop_735d1d59a0994032a78cb4258494adb8` byte-identical SOURCE_REPLACE |
| B3 | Analysis only (not a third ingest) |

Workload: **B1-FIREGROUND-INCIDENT-CLASS-V1**  
Aggregate manifest hash: `9864d642c45b485f175555dff229252fceea1b81437869189179766508526070`  
Member: `Fireground_Operational_Guides.pdf` / 6796067 bytes /
`01bea4d628ffea01aab164535c81392a8b42b9a587f9b6295f302a9938f2f0c2`

---

## Nine acceptance questions

### 1. What is the current workload cost?

**Measured fact (B1, fresh empty workspace, as-found artifact caches):**

- searchable children: **585**
- uploaded raw bytes: **6,796,067**
- total wall: **8,795 ms**
- stage durations (ms): parse 93, chunk 44, dense_generation 106,
  dense_materialization 3,538, lexical 398, publication 64, finalization 20

**Measured fact (B2, byte-identical replace):**

- searchable children: **585** (unchanged membership)
- total wall: **483 ms**
- embeddings_generated **0** / embeddings_reused **585**

**Derived:** In this campaign workspace, Fireground alone is a **585-child**
workload (~6.8 MiB PDF). Historical Fireground attempts in the occupied
`ws_fdd77b…` workspace reported workspace-wide `child_chunk_count` 3113/3208
because other sources were already present (**historical evidence**, not B1).

### 2. Where is time spent?

**Measured fact (B1):** Dense materialization dominated (3,538 ms of 8,795 ms).
Dense generation was negligible (106 ms) because embeddings were reused.
**Measured fact (B2):** Total 483 ms; dense_generation/materialization fields
absent/null in metrics (full reuse path; no new dense generation stage cost
recorded).

**Unknown under this campaign:** input-token p50/p95/p99/max, per-batch max
sequence length, first-batch vs steady-state encode timing for a
generate-heavy cold embedding path — B1/B2 did not generate embeddings.

### 3. How much embedding work is generated versus reused?

**Measured fact:**

| Run | generated | reused | failed |
|---|---:|---:|---:|
| B1 | 0 | 585 | 0 |
| B2 | 0 | 585 | 0 |

**Measured fact:** parse/chunk artifacts also reused (generated 0 / reused 1
document-level artifacts each).

**Interpretation (not a finding):** B1 was cold-process / fresh-workspace but
**not** artifact-cold. Historical caches made B1 a reuse-dominated replay.

### 4. What does CUDA memory do before, during, and after sequential operations?

**Measured fact (external nvidia-smi host GPU used MiB):**

| Sample | used MiB |
|---|---:|
| pre-B1 cold API | 5181 |
| after B1 terminal | 5149 |
| idle T0 | 5157 |
| idle T+5m | 5280 |
| idle T+15m | 5258 |
| after B2 terminal | 5202 |

**Measured fact:** API PID `1926194` continuous through B1→idle→B2.  
**Measured fact:** `nvidia-smi` compute_apps never listed the API PID.  
**Measured fact:** side-process `torch.cuda.mem_get_info` free stayed
~7.45 GiB; API-process `memory_allocated`/`memory_reserved` were
**unavailable** without in-process instrumentation (not authorized).

**Derived:** Host GPU memory remained elevated and roughly stable across the
15-minute idle window. This is **not** the same as proving the embedding model
remained resident inside the API process.

### 5. Does the accepted model remain resident after ingestion?

**Measured fact:** Not observed as an API-attributed GPU resident process during
this campaign sequence.

**Derived:** Because B1/B2 reused all embeddings, the campaign did not force a
full model-load / generate-heavy CUDA path. Persistent GPU residency previously
seen on generate-heavy Fireground attempts remains an open observation for
16K-D, not established by B1/B2 here.

### 6. Is the current runtime stable across the bounded baseline sequence?

**Measured fact:** B1 succeeded; B2 succeeded; PID continuity held; no CUDA
failure in campaign runs; scientific membership unchanged across B2 replace.

**Historical evidence:** same Fireground bytes previously failed
(`wop_e6fa35…`, 384 generated / 2528 reused / 32 failed,
`embedding_generation_failed`) and later succeeded (`wop_861fc8…`).

**Interpretation / hypothesis (not a finding):** Historical failure appears
intermittent / runtime-state dependent rather than a deterministic
document-content failure. **CUDA root cause is not solved.**

### 7. What evidence constrains 16K-C capacity design?

**Measured fact:**

- transport size of the Fireground member: ~6.8 MiB raw PDF
- scientific searchable children for that member alone: **585**
- historical occupied-workspace Fireground attempts co-measured ~3.1k–3.2k
  workspace children (**historical**)

**Constraint input for 16K-C:** raw PDF bytes and searchable-child workload are
not interchangeable; a single ~7 MiB PDF produced 585 children here. Capacity
policy must separate transport/resource safety from workspace/search workload
(design Q4 / §8). No numeric production limits are selected by this freeze.

### 8. What evidence constrains 16K-D optimization/reliability design?

**Measured fact / historical evidence inputs for 16K-D:**

- historical partial-failure counters on CUDA-era dense failure (`wop_e6fa35…`)
- later success on same bytes (`wop_861fc8…`)
- campaign B1/B2 were reuse-dominated and did not reproduce generate-heavy CUDA
  stress or API-attributed VRAM residency
- host GPU memory stayed elevated during idle, but without API process
  attribution
- accepted config pins remain: Qwen3-Embedding-0.6B @
  `97b0c614…`, plain-v1, dim 1024, batch 32, device auto→cuda observed in B1
  `dense_execution`

**Constraint:** 16K-D must still address generate-heavy CUDA reliability and
any residency/eviction policy using dedicated optimization authority; this
baseline does not select FP16, batch changes, attention changes, or eviction.

### 9. What remains unknown?

- generate-heavy cold embedding throughput (chunks/sec, tokens/sec, first-batch
  vs steady-state) for Fireground bytes when caches do not satisfy reuse
- API-process torch allocator series (allocated/reserved) — requires authorized
  in-process instrumentation or an approved measurement helper path that can
  observe the server process
- whether embedding model weights remain mapped in the API process after
  reuse-only operations
- reproduction probability of `cublasGemmEx` / `embedding_generation_failed`
  under controlled allocator pressure
- beta usability threshold numbers (Q13) — intentionally not invented here

---

## Current governance state after freeze

- **16K-B:** COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED / HA RECORD
  INDEPENDENTLY ACCEPTED
- **16K baseline evidence:** FROZEN / PENDING INDEPENDENT REVIEW
- **16K-C / 16K-D / 16K-E→G:** NOT YET AUTHORIZED
- **Fireground CUDA/cublasGemmEx:** OPEN / SEPARATE / CHARACTERIZED BY BASELINE
  WHERE EVIDENCE SUPPORTS IT / NOT FIXED
- **Main promotion:** NOT AUTHORIZED

---

**STOP FOR INDEPENDENT S16-K-BASELINE-EVIDENCE-FREEZE-001 REVIEW.**
