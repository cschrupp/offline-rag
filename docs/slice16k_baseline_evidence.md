# Slice 16K — Baseline Evidence Freeze Narrative

**Freeze subject:** `S16-K-BASELINE-EVIDENCE-FREEZE-001`  
**Campaign authority:** `S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001`  
**AUTH-open / execution pin:** `eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e`  
**Technical implementation measured:** `40c6eb3824ac9f9c1cbc35c889e3e4110b229469`  
**Prior independent review:** `S16-K-BASELINE-EVIDENCE-FREEZE-IR-001` — REWORK REQUIRED (R1–R4)  
**Rework authority:** `S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework parent:** `0d169ae62d620709b220e8ebc97b2932d64a843b`  
**Independent review:** `S16-K-BASELINE-EVIDENCE-FREEZE-IR-002` — ACCEPT  
**Exact independently accepted freeze subject:** `3abc3a6c0ef31cc255ea6de8796203d26700ec23`  
**Disposition:** BASELINE EVIDENCE FROZEN / INDEPENDENTLY ACCEPTED  
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
**Design document:** `docs/slice16k_gpu_residency_allocator_diagnostic_design.md`  
**Design scope:** state/history-dependent residency + allocator hypotheses beyond static free-VRAM; execution NOT AUTHORIZED; M0–M2 / 16K-C/D / device-CUDA policy / fireground / main NOT AUTHORIZED  
**Exact constrained-VRAM execution tip:** c921c954da25a2f61415707d2f5b54579bc48571  
**Evidence path:** `docs/evidence/16k_constrained_vram/`  
**Campaign outcome:** no CUDA-class failure at B1 (free≈1912 MiB) or B2 (free≈494 MiB); B1-repeat skipped; all primary turns HTTP 200 / durable `model_abstain` / `internal_failure` null; historical 500 not reproduced  
**Diagnostic scope:** controlled free-VRAM reproduction on instrumented build; external occupant only; M0–M2 NOT AUTHORIZED  
**Rework scope:** close IR-001 R1–R4 only; no VRAM/device/CUDA behavioral fix  
**Remediation scope:** durable `internal_failure` classification + server traceback log for grounded-query `internal_error`; public D08 / GET `/v1/trace/{id}` remain sanitized; no VRAM/device/CUDA behavioral fix  
**Public projection:** GET `/v1/trace/{id}` explicit allowlist excludes `internal_failure`  
**Device/VRAM/CUDA behavior:** unchanged under this authority  
**Note:** Accepted B0–B3 evidence remains valid and is not rewritten. Downstream
16K-C/D and Human acceptance of baseline evidence remain blocked while the live
query regression is under diagnosis. IR-002 ACCEPT closes the observability
defect only; it does not identify the historical 500 root cause, does not
establish dual-CUDA/VRAM pressure, and does not authorize constrained-VRAM
reproduction.  

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

**Runtime config fingerprint:** `status: not_captured` (no contemporaneous
effective-config hash recovered from campaign evidence/logs). Exact
effective-runtime reproducibility is correspondingly limited. Static repository
defaults are not a substitute.

---

## Nine acceptance questions

### 1. What is the current workload cost?

**Measured fact (B1, fresh empty workspace, as-found artifact caches):**

- searchable children: **585**
- uploaded raw bytes: **6,796,067**
- pipeline_total_ms (`metrics.stage_durations.total_ms`): **8,795**
- durable_operation_wall_ms (`updated_at − created_at`): **≈ 10,227**
- stage durations (ms): parse 93, chunk 44, dense_generation 106,
  dense_materialization 3,538, lexical 398, publication 64, finalization 20

**Measured fact (B2, byte-identical replace):**

- searchable children: **585** (unchanged membership)
- pipeline_total_ms: **483**
- durable_operation_wall_ms: **≈ 599**
- embeddings_generated **0** / embeddings_reused **585**

Collector `timestamps.*` / `timing.collector_observed_*` values are evidence-
harness observation times when terminal state was polled; they are **not**
authoritative durable terminal timestamps (`timing.durable_terminal_updated_at`).

**Derived:** In this campaign workspace, Fireground alone is a **585-child**
workload (~6.8 MiB PDF). Historical Fireground attempts in the occupied
`ws_fdd77b…` workspace reported workspace-wide `child_chunk_count` 3113/3208
because other sources were already present (**historical evidence**, not B1).

### 2. Where is time spent?

**Measured fact (B1):** Dense materialization dominated (3,538 ms of 8,795 ms
pipeline_total_ms). Dense generation was negligible (106 ms) because embeddings
were reused.
**Measured fact (B2):** pipeline_total_ms 483; dense_generation/materialization
fields absent/null in metrics (full reuse path; no new dense generation stage
cost recorded).

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
**Measured fact:** `api_pid_listed_in_nvidia_smi_compute_apps_after_idle` =
**false** (and compute_apps never listed the API PID during the sequence).  
**Measured fact:** side-process `torch.cuda.mem_get_info` free stayed
~7.45 GiB; API-process `memory_allocated`/`memory_reserved` were
**unavailable** without in-process instrumentation (not authorized).

**Derived:** Host GPU memory remained elevated and roughly stable across the
15-minute idle window. That is **not** equivalent to proving embedding-model
residency inside the API process.

### 5. Does the accepted model remain resident after ingestion?

**Status: not_established.**

**Measured fact:** `embedding_model_resident_in_api_process` is **null** /
`embedding_model_resident_status: not_established`. Absence from nvidia-smi
compute_apps (especially under this WSL observation path) does **not** prove
non-residency.

**Derived:** Because B1/B2 reused all embeddings, the campaign did not force a
full model-load / generate-heavy CUDA path. Persistent GPU residency previously
seen on generate-heavy Fireground attempts remains an open observation for
16K-D.

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
  stress or establish API-process model residency
- host GPU memory stayed elevated during idle, without API PID attribution in
  nvidia-smi compute_apps
- accepted static pins remain: Qwen3-Embedding-0.6B @ `97b0c614…`, plain-v1,
  dim 1024, batch 32, device auto→cuda observed in B1 `dense_execution` (dtype /
  attention not resolved on reuse-only B1)

**Evidence constraint (R4) — do not rewrite Q12:**

Historical generate-heavy successful runs (`wop_11cdee8f…`, `wop_861fc8…`)
reported:

- device: `cuda`
- dtype: `bfloat16`
- attention_backend: `sdpa`
- batch_size: `32`

while the frozen 16K-D design text (§9.2) describes the current baseline as
CUDA **FP32** / batch 32 before FP16 testing.

**Disposition:** the FP32 premise is **not established** by this baseline and
must be verified/reconciled before 16K-D chooses its controlled optimization
sequence. This freeze does **not** select BF16/SDPA as the new baseline and
does **not** rewrite Q12.

**Constraint:** 16K-D must still address generate-heavy CUDA reliability and
any residency/eviction policy using dedicated optimization authority.

### 9. What remains unknown?

- generate-heavy cold embedding throughput (chunks/sec, tokens/sec, first-batch
  vs steady-state) for Fireground bytes when caches do not satisfy reuse
- API-process torch allocator series (allocated/reserved)
- whether embedding model weights remain mapped in the API process after
  reuse-only operations (`not_established`)
- contemporaneous effective **runtime_config_fingerprint** for the B1→B3
  sequence (`not_captured`)
- verified current default dtype/attention vs historical BF16/SDPA reports
- reproduction probability of `cublasGemmEx` / `embedding_generation_failed`
  under controlled allocator pressure
- beta usability threshold numbers (Q13) — intentionally not invented here

---

## Current governance state

- **16K-B:** COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED / HA RECORD
  INDEPENDENTLY ACCEPTED
- **16K baseline evidence:** FROZEN / INDEPENDENTLY ACCEPTED
  (`S16-K-BASELINE-EVIDENCE-FREEZE-IR-002` — ACCEPT at `3abc3a6c…`)
- **Historical IR:** `S16-K-BASELINE-EVIDENCE-FREEZE-IR-001` — REWORK REQUIRED
  (R1–R4) — preserved as provenance against prior tip `0d169ae6…`
- **Human disposition:** HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS
- **Observability remediation:** IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
  (`S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002`
  — ACCEPT at technical subject `1630787…`; handoff tip `17fc511…`;
  acceptance-record under
  `…-IR-002-ACCEPTANCE-RECORD-AUTH-001` from parent `17fc511…`)
- **Human acceptance of observability remediation:** NOT RECORDED
- **Constrained-VRAM diagnostic:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-AUTH-001` — EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED (historical handoff STOP preserved in header; parent `98a5d1f…`; AUTH-open `ddc7250…`; evidence `docs/evidence/16k_constrained_vram/`)
- **Scientific diagnostic execution:** EXECUTION COMPLETE / NO RERUN REQUIRED
- **Constrained-VRAM diagnostic IR-001:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-001` — REWORK REQUIRED (R1–R2) — preserved as provenance
- **Constrained-VRAM rework authority:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-REWORK-AUTH-001` — AUTHORIZED (parent `a71f4fe…`; AUTH-open `c6466cf…`); **Constrained-VRAM rework status:** COMPLETE / INDEPENDENTLY ACCEPTED
- **Constrained-VRAM independent review:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002` — ACCEPT at subject `7ad48b7…`
- **Constrained-VRAM acceptance-record authority:** `S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED from parent `7ad48b7…`
- **Historical HTTP 500:** NOT REPRODUCED / ROOT CAUSE UNRESOLVED
- **CUDA-class failure:** NOT OBSERVED
- **M0–M2 eligibility gate:** NOT SATISFIED
- **GPU residency/allocator diagnostic design:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-AUTH-001` — DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW (parent `bd450fd…`; branch `design/16k-gpu-residency-allocator-diagnostic`; doc `docs/slice16k_gpu_residency_allocator_diagnostic_design.md`); execution NOT AUTHORIZED
- **16K-C / 16K-D / 16K-E→G:** NOT AUTHORIZED
- **Further constrained-VRAM reproduction:** NOT AUTHORIZED
- **M0–M2:** NOT AUTHORIZED
- **Fireground CUDA/cublasGemmEx:** OPEN / SEPARATE / NOT FIXED
- **Main promotion:** NOT AUTHORIZED

Accepted B0–B3 evidence remains valid. Human acceptance / downstream progression
remains held. The historical 500 root cause remains unresolved.
