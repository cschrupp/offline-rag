# 16K-D P4 — Product Acceptance & Default-Policy Qualification

**Disposition:** P4 DESIGN COMPLETE / INDEPENDENTLY ACCEPTED — IR-001  
**Human acknowledgment:** ACCEPTED — single Human acknowledgment (no HA-record / status-flip)  
**Implementation authority:** `S16-K-D-DUAL-BACKEND-P4-PRODUCT-ACCEPTANCE-DEFAULT-POLICY-IMPLEMENTATION-AUTH-001`

## Purpose

Establish whether the already-built dual-backend architecture qualifies as the supported Seneca product execution architecture under the existing repository default:

```yaml
indexing:
  embedding:
    device: auto
    precision: native
```

P4 is an acceptance harness. It does not change production code, configuration, or scientific thresholds.

## Qualified policy matrix

| Configured | CUDA usable | Profile | Representation |
|---|---|---|---|
| AUTO/native | yes | `cuda_fp16_v1` | `torch_st_v1` |
| AUTO/native | no / probe fail | `cpu_onnx_fp32_v1` | `onnx_fp32_v1` |
| explicit CPU | any | `cpu_onnx_fp32_v1` | `onnx_fp32_v1` |
| explicit CUDA | usable | `cuda_fp16_v1` | `torch_st_v1` |

No cross-promotion. No runtime failover. Selection and representation readiness remain separate gates.

## Real interoperability gate

Two restart-boundary directions against persistent Qdrant:

1. CUDA index → CPU query  
2. CPU index → CUDA query  

Same logical embedding/index identity; no query-phase reindex or document re-embedding.

## Scientific evidence

Consumed, not rerun. Existing independently accepted ONNX FP32 parity and 128-screen PRODUCT-PRACTICAL evidence establish semantic compatibility. `full1296_confirmed = false`.

## Closed exclusions

Full 1296 campaign, new parity/performance campaigns, alternate models, quantization, production architectural repair, main/merge/release/promotion.
