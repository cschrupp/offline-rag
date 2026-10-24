# 16K-D Dual-Backend P3 — Provisioning & Acquisition Design (Revision 001)

**Status:** P3 DESIGN COMPLETE / INDEPENDENTLY ACCEPTED — IR-002  
**Implementation authority:** `S16-K-D-DUAL-BACKEND-P3-PROVISIONING-ACQUISITION-IMPLEMENTATION-AUTH-001`

This document durably captures the accepted Revision 001 / IR-002 contract. It is
documentation of already-accepted design, not a new design pass.

## Purpose

Implement a production-safe, durable transactional installer for the already-qualified
representations:

- `torch_st_v1`
- `onnx_fp32_v1`

P3 installs bytes already authorized by P1 qualification. P3 does **not** establish
scientific validity, regenerate ONNX, or mutate P1 trust / P2 runtime semantics.

## Trust model (unchanged)

- Package-owned qualification remains authoritative for ONNX:
  `src/offline_rag/resources/embedding_representations/onnx_fp32_v1.json`
- Accepted ONNX historical tree SHA:
  `3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345`
- Source path has no authority; only package digests grant eligibility.
- Absolute prohibition: Torch → ONNX export published as `onnx_fp32_v1`.

## Transaction shape

```
LOCK
 → inspect (P1 inspect_representation)
 → plan (preserve / install / replace / adopt_legacy)
 → acquire / copy into private target-filesystem staging
 → validate staged content
 → publish immutable instances
 → ONE forward bundle-selection publication
 → post-publish P1 inspect of requested representations
 → success OR rollback
 → UNLOCK
```

## CLI

`offline-rag provision embedding` with:

- `--representation torch_st_v1|onnx_fp32_v1|all` (omit → `torch_st_v1`)
- `--onnx-source <PATH>`
- existing `--force` / `--json`

One bundle-aware writer serves CLI and `scripts/provision_embedding.py`.

## Durability (supported local FS)

Under same-filesystem + POSIX rename + working file/directory fsync assumptions:

1. write/fsync files  
2. write/fsync installed manifest  
3. rename staged instance → immutable final; fsync parent dir  
4. write/fsync temporary bundle; atomic replace; fsync model-root dir  

Equivalent power-loss behavior is **not** claimed for arbitrary network/cloud/FUSE FS.

## Reader observation limitation

Post-publication rollback cannot undo observations made between forward bundle
publication and restoration. Bounded by P2 process-start frozen availability.

## Report compatibility

`EmbeddingProvisionReport` / `ProvisioningStatus` unchanged.
P3 detail lives under `metadata` (`p3_schema`, `outcome_code`, `bundle_changed`, …).

## Out of scope

P4, campaigns, parity/1296, quantization, alternate models/representations, main/merge/promotion.
