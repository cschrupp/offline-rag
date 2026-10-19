# Slice 16K — GPU Residency / Allocator Diagnostic Tooling

**Authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-AUTH-001` — AUTHORIZED  
**Exact parent:** `d501370aef96c953f4780d2048d11b91306ee856`  
**Branch:** `implementation/16k-gpu-residency-allocator-diagnostic-tooling`  
**Tooling status:** TOOLING IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT TOOLING REVIEW  
**GPU residency/allocator diagnostic tooling status:** TOOLING IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED  
**Independent tooling review:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001` — ACCEPT  
**Exact independently accepted tooling subject:** `a26ea53f6ce32c6454d21a6d6af988d50299ae49`  
**Tooling acceptance-record authority:** `S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001-ACCEPTANCE-RECORD-AUTH-001` — AUTHORIZED  
**Exact tooling acceptance-record parent:** `a26ea53f6ce32c6454d21a6d6af988d50299ae49`  
**Design parent (accepted):** `docs/slice16k_gpu_residency_allocator_diagnostic_design.md`  
**Mode:** diagnostic tooling / instrumentation only — **campaign execution NOT AUTHORIZED**

**Behavioral product baseline:** `163078753eeda33959c9957cfad4e82876a7a5f5`  
**Flag-off behavior:** product-equivalent to baseline (probe absent)

---

## 1. Purpose

Establish an env-gated **in-process** diagnostic probe and external runner so that
later execution can condition and observe:

- model load / residency / load-order history;
- same-process PyTorch CUDA allocator allocated / reserved / stats;
- H2-A reserve-gap and H2-B fragmentation-proxy primitives;

without scientific campaign runs, workspace mutation, or production CUDA policy
changes.

---

## 2. Probe interface (frozen)

| Item | Value |
|------|--------|
| Enable flag | `OFFLINE_RAG_DIAG_GPU_PROBE=1` |
| Secret | `OFFLINE_RAG_DIAG_GPU_PROBE_TOKEN` |
| Auth header | `X-Seneca-Diag-Token` |
| GET | `/v1/_diag/gpu/state` (`include_in_schema=False`) |
| POST | `/v1/_diag/gpu/action` (`include_in_schema=False`) |
| Mount | only when flag enabled |
| Disabled | routes absent / 404 |
| Fail closed | enabled + missing token **or** non-loopback HTTP bind → startup failure |

### Actions (`POST` body `{"op": "..."}`)

`load_embedder` · `load_reranker` · `touch_embedder` · `touch_reranker` ·
`h2_reserve_gap` · `h2_fragment` · `release_h2`

### Forbidden in probe

`torch.cuda.empty_cache()` · model unload/eviction · device migration ·
workspace / snapshot / query / conversation mutation.

Secret must never appear in evidence or logs.

---

## 3. Capability parameters (tooling only)

Precondition: CUDA free memory ≥ 1024 MiB before an allocator capability
primitive; else STOP capability as BLOCKED.

**H2-A-CAP:** allocate exactly 256 MiB `torch.uint8` CUDA → record → drop refs →
synchronize → record; no `empty_cache`.

**H2-B-CAP:** prime 256 MiB uint8 → drop prime (no empty_cache) → 16×8 MiB →
retain alternating 8 (64 MiB live) → record pattern + stats; no escalation.

---

## 4. Acceptance gates (G1–G8)

See authority freeze: gating/security, same-process allocator observation,
H2-A/H2-B primitives, model conditioning with ordered event record, no workspace
mutation, instrumentation provenance vs baseline.

---

## 5. Evidence

`docs/evidence/16k_gpu_residency_allocator_tooling/`

- `instrumentation_manifest.json` — baseline, allowlisted deltas, digests
- capability run JSON (non-scientific)

---

## 6. Unauthorized under this authority

Campaign execution · execution AUTH · product CUDA/device/eviction policy ·
M0–M2 · 16K-C/D · fireground corrective · main promotion.
