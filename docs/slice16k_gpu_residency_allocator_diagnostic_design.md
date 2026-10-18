# Slice 16K — GPU Residency / Allocator Diagnostic Design

**Authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-AUTH-001` — AUTHORIZED  
**Exact parent:** `bd450fd601e655fc03e9c7c929075aa9c3673e9c`  
**Branch:** `design/16k-gpu-residency-allocator-diagnostic`  
**Design status:** DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW  
**GPU residency/allocator diagnostic design status:** DESIGN COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent design review:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001` — ACCEPT  
**Exact independently accepted design subject:** `2417e47fc2aef1d59c31f0307a0cdb222c56e618`  
**Acceptance-record authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact acceptance-record parent:** `2417e47fc2aef1d59c31f0307a0cdb222c56e618`  
**Mode:** design / disposition only — **experiment execution NOT AUTHORIZED** under this authority  

**Human disposition:** HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS  

---

## 1. Purpose

Define and freeze the next diagnostic campaign for the unresolved historical
grounded-query HTTP 500, testing **state/history-dependent GPU residency and
allocator hypotheses** beyond static free-VRAM.

This document is the measurement contract. It does **not** authorize runtime
campaigns, product/device/CUDA policy changes, or M0–M2 work.

---

## 2. Prior conclusion (preserved)

| Finding | Status |
|---------|--------|
| Static pre-request free VRAM alone | **NOT SUFFICIENTLY CAUSAL / NOT REPRODUCED** |
| Historical HTTP 500 | **ROOT CAUSE UNRESOLVED** |
| Constrained free-VRAM campaign | EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED |
| M0–M2 eligibility (after constrained-VRAM) | **NOT SATISFIED** |

Evidence: `docs/evidence/16k_constrained_vram/` under
`S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-AUTH-001`.

The next campaign must **not** reframe H1–H4 as “VRAM hypotheses.” They test
materially different mechanisms.

---

## 3. Primary scientific question

Under the historical grounded-conversation binding, can the historical
CUDA-class grounded-query failure be reproduced by controlled state/history
conditions involving process history, model residency/coexistence, and CUDA
allocator state, given that static pre-request free VRAM alone was insufficient
to reproduce it?

The campaign may **isolate** process history, residency/coexistence, and
allocator state. It must not require varying all three together.

---

## 4. Mechanism distinctions (mandatory)

Do not collapse these into a single “GPU residency” or “VRAM” label:

| Concept | Meaning |
|---------|---------|
| **Memory pressure** | Reduced device free memory / competition for device pages |
| **Allocator state** | Same-process PyTorch CUDA allocator reserved vs allocated, fragmentation, large-block availability |
| **Model residency** | Which model tensors are CUDA-resident (distinct from “object loaded”) |
| **Load ordering** | Sequence by which embedder / reranker become resident |
| **Process history** | Prior in-process ops (ingest/query/warm) before the bound request |
| **External GPU contention** | Another process consuming device memory concurrent with Seneca |

Four states that must be recorded separately when claimed:

1. **model object loaded in process** ≠  
2. **model tensors resident on CUDA** ≠  
3. **PyTorch allocator reserved memory** ≠  
4. **driver-level GPU memory consumed**

---

## 5. Hypotheses

### H1 — Residency / coexistence

A particular resident-model combination or residency history is sufficient to
expose the failure.

### H2 — Allocator state

Holding relevant model residency fixed, allocator reserved-vs-allocated state /
fragmentation / large-block availability is sufficient to expose the failure.

**H2 methodological bound:** An external GPU occupant can reduce driver-level
free memory; it does **not** reproduce fragmentation/reservation inside Seneca’s
own PyTorch CUDA allocator. H2 therefore requires same-process allocator
telemetry (and any manipulation) from the Seneca CUDA process. External
`nvidia-smi` free-memory data is **not** a substitute for allocator state and
is **not** H2 evidence. If same-process allocator observability cannot be
obtained without new diagnostic instrumentation, **H2 is not executable** until
a separate instrumentation/tooling authority exists.

### H3 — Load ordering / process history

Holding comparable resource pressure, the order/history by which the embedder
and reranker become resident is sufficient to expose the failure.

### H4 — External contention

A competing CUDA consumer interacting with Seneca’s existing resident models can
expose the failure even when static free VRAM by itself does not.

**H4 bound:** Standalone CUDA occupant (no Seneca imports), memory pressure only
by default. Tests **external contention**, not Seneca allocator fragmentation.
Do **not** use H4 occupant evidence as H2 evidence. Compute stress requires an
additional frozen decision / authority.

### Excluded (already addressed)

- Static pre-request free-VRAM band alone as a sufficient cause (constrained-VRAM
  campaign; not reproduced).

---

## 6. Scientific binding (exact)

| Field | Value |
|-------|-------|
| workspace_id | `ws_fdd77b77611448eb93cdc239d2610281` |
| workspace revision | `13` |
| snapshot_id | `snap_3c4048d380b1f5db12a20f820082c1942ccaacc96e368dfb04c22aba5090a9c9` |
| surface (primary) | `POST /v1/workspaces/{id}/conversation/turn` |
| question | `what is common valor?` |
| prior_turns | `[]` |

**Binding assertion:** Immediately before every primary request, mechanically
assert that workspace / revision / snapshot still resolve exactly as frozen.
If not, **STOP that run** — do not silently substitute current workspace state.

**Secondary surface:** `POST .../query` only as bounded post-hoc
surface-isolation after an informative primary failure or ambiguity. Not a
matrix dimension.

---

## 7. Product-code baseline (subject)

| Field | Value |
|-------|-------|
| Product-code baseline | Equivalent to technical observability subject `163078753eeda33959c9957cfad4e82876a7a5f5` |
| Runtime Git SHA | May be a later **docs-only** descendant used as execution checkout |

Before campaign execution (under a future execution AUTH):

1. Mechanically verify that relevant product/runtime code is unchanged from
   `1630787…` (or an explicitly documented equivalent tree).
2. Any **new product instrumentation** requires separate authority.
3. Diagnostic-only tooling may be separately authorized without redefining the
   production subject.

---

## 8. Campaign skeleton (execution unauthorized here)

Order:

```
C0  cold baseline (no induced residency/history conditioning)
 ↓
H3  load order / process-history conditioning
 ↓ negative/inconclusive
H1  model residency / coexistence conditioning
 ↓ negative/inconclusive
H2  same-process allocator-state conditioning
 ↓ negative/inconclusive
H4  external GPU contention (conditional)
```

Rationale: successful cold runs under the prior campaign already demonstrated
dual-model coexistence under some conditions, so simple coexistence alone is a
weak sole explanation; load-order/history is examined before coexistence
refinement; H2 requires same-process allocator capability; H4 last and only if
H1–H3 are negative/inconclusive.

Recovery control is required after any candidate-positive cell (see §11).

---

## 9. Controlled variables and transitions

### Per hypothesis (design intent)

| Cell family | Manipulated factor | Held roughly constant |
|-------------|--------------------|------------------------|
| C0 | none (cold process, no induced history) | binding; product baseline |
| H3 | load order / prior in-process ops that establish residency sequence | comparable driver free memory; no H2 allocator manipulation; no H4 occupant |
| H1 | which models are CUDA-resident / coexistence pattern | load-order history documented; no H2 allocator manipulation; no H4 occupant |
| H2 | same-process allocator reserved/allocated / fragmentation proxy | residency inventory fixed; no external occupant as causal factor |
| H4 | external CUDA occupant (memory pressure) | Seneca residency as established; not used as H2 evidence |

Exact cell tables (named ops, warm protocols) are finalized under a future
**execution AUTH**; this design freezes the factor structure and bounds.

### Forbidden under this design and any future campaign unless separately authorized

- production `torch.cuda.empty_cache()` behavior changes;
- model eviction / unload product policy;
- device / CUDA product policy changes;
- compute-stress occupants (beyond memory allocation for H4);
- M0–M2, 16K-C, 16K-D, fireground corrective work, main promotion.

---

## 10. Required measurements (evidence schema)

### Every run (minimum)

| Field | Notes |
|-------|--------|
| `condition` / `hypothesis` / `cell_id` | C0 / H1–H4 cell identity |
| `api_pid` | Seneca API process |
| `execution_git_sha` | checkout SHA used for the run |
| `product_code_baseline_ok` | boolean result of §7 verification |
| `cold_warm_class` | cold vs warm classification |
| `prior_in_process_ops` | none / listed ops |
| `loaded_model_inventory` | process-level loaded objects |
| `cuda_resident_model_inventory` | **separate** from loaded inventory |
| `gpu_used_mib` / `gpu_free_mib` | host / nvidia-smi |
| `per_process_gpu_mib` | where available |
| `load_order` | ordered residency establishment |
| `occupant_pid` | null unless H4 |
| `http_status` | primary surface |
| `trace_id` | |
| `durable_internal_failure` | full classifier fields if present |
| `wall_s` / timing | request wall time at minimum |
| `binding_assert_ok` | workspace/rev/snapshot assertion |

### H2 additional (mandatory for H2 executability)

Observable from the **Seneca CUDA process** (not only host nvidia-smi):

- allocator allocated;
- allocator reserved;
- relevant memory stats / snapshot or equivalent.

If these cannot be obtained without new diagnostic instrumentation, mark H2
**NOT EXECUTABLE** pending separate tooling AUTH. Do not substitute H4 or
nvidia-smi free for H2.

### Evidence location (future execution)

Planned path: `docs/evidence/16k_gpu_residency_allocator/`  
No run evidence is created under this design AUTH.

---

## 11. CUDA-class failure definition (campaign-positive)

Reuse the existing observability taxonomy (`internal_failure` / CUDA markers /
mapped stage). **No parallel classifier.**

A **campaign-positive** failure requires **all** of:

1. Primary request fails with **HTTP 500**; and  
2. Durable ProductQueryTrace records a **CUDA-related** `internal_failure`
   under the existing classifier, including mapped failure stage/classification.

A CUDA-looking console message without durable classification is
**investigative evidence**, not campaign-positive by itself.

---

## 12. Stopping and reproducibility rules

Do **not** stop on a single failure.

For any cell:

```
first CUDA-class candidate failure (campaign-positive definition)
        ↓
same-cell fresh-process repeat
        ↓
matched recovery control restoring the manipulated factor
        ↓
reproduces + recovers?
        ├─ YES → STOP; causal candidate established
        └─ NO  → continue frozen matrix
```

**Reproduced** means: failure recurs under the same cell in a fresh process,
**and** the matched recovery control succeeds.

Then STOP; do not press into more invasive cells.

If the complete matrix finishes without a reproduced positive, STOP
**negative** or **inconclusive** as appropriate (document which hypotheses were
executable; H2 may be NOT EXECUTABLE).

### Scope distinction (mandatory)

A reproduced condition identifies a **controlled causal candidate** for the
historical failure **class**. It does **not** by itself establish the
production root cause of the historical incident.

---

## 13. M0–M2 eligibility

| State | Meaning |
|-------|---------|
| Eligibility | Satisfied **only** after a reproduced, recovery-controlled CUDA-class failure under this campaign |
| Authorization | **NOT** implied by eligibility |

M0–M2 remains **NOT AUTHORIZED** until a separate authority exists.

---

## 14. Unauthorized under this authority (explicit)

- experiment execution;
- production code changes;
- device-policy changes;
- model eviction / unload policy;
- product `torch.cuda.empty_cache()` behavior;
- M0–M2;
- 16K-C / 16K-D;
- fireground corrective work;
- main promotion;
- compute-stress occupants (beyond H4 memory allocation default).

---

## 15. Publication and next gates

Under this design AUTH:

1. AUTH-open on the five 16K ledgers + this design document.  
2. Design status (historical handoff): **DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW**.
3. Live disposition: **DESIGN COMPLETE / INDEPENDENTLY ACCEPTED** (`S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001` — ACCEPT at `2417e47fc2aef1d59c31f0307a0cdb222c56e618`).  
4. **STOP** — no runtime campaign.

Future gates (separate authorities, not opened here):

- independent design review ACCEPT (or REWORK);  
- execution AUTH (and any H2/H3 tooling AUTH if required);  
- campaign execution → STOP for diagnostic IR.

---

## 16. Frozen decision index

| ID | Decision |
|----|----------|
| Q1 | Design AUTH first; parent `bd450fd…`; branch `design/16k-gpu-residency-allocator-diagnostic` |
| Q2 | Umbrella residency/history question; H1–H4 nested |
| B1 | Exact historical binding + pre-request mechanical assert |
| B2 | `conversation/turn` primary; `/query` post-hoc only |
| B3 | Product baseline ≡ `1630787…`; docs-only checkout allowed; verify before execute |
| B4 | C0 → H3 → H1 → H2 → H4 (H4 conditional) |
| B5 | Strengthened measurements; H2 needs same-process allocator telemetry |
| B6 | Existing classifier; HTTP 500 + durable CUDA internal_failure |
| B7 | Fresh-process repeat + recovery; no single-failure STOP |
| B8 | Eligibility ≠ authorization for M0–M2 |
| B9 | This design doc + five ledger pins |
| B10 | H4 occupant optional; not H2 evidence |
| B11 | Docs-only under this AUTH |
