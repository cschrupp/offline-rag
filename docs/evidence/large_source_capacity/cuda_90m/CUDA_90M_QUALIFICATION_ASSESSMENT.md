# CUDA 90 MiB PDF qualification assessment

## Disposition

**CUDA_90M_QUALIFIED**

The bounded post-L6 campaign qualifies `cuda_fp16_v1` through the existing 90 MiB PDF product envelope on the host class represented by this execution. The preflight, Q25, Q100, and independent fresh-tree Q100 confirmation all passed with complete evidence and positive CUDA execution witnesses.

## Measured facts

- Execution Git SHA: `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`.
- Requested and resolved profile: `cuda_fp16_v1`.
- Representation/device witness: `torch_st_v1`, CUDA, FP16; dense metrics report `device: cuda` and `dtype: float16`.
- GPU witness: NVIDIA GeForce RTX 2080 Super with CUDA 13.0 runtime; allocator and external GPU samples were observed.
- Q25: 22,430,312 bytes, SHA-256 `ff360b3b…`, managed operation succeeded, identity matched.
- Q100: 96,152,520 bytes, SHA-256 `109fa209…`, managed operation succeeded, identity matched.
- Q100-CONFIRM: same exact Q100 identity, managed operation succeeded from a fresh isolated tree.
- All attempted cells completed Docling parsing, chunking, dense generation/materialization, lexical indexing, publication, and active-workspace readiness.
- Q250 and Q512 were not run under this authority.

Detailed per-cell measurements are in [`cuda_90m_campaign_summary.json`](cuda_90m_campaign_summary.json) and the raw evidence JSON files.

## Policy boundary

This is a scientific qualification result only:

```text
CUDA scientific qualification:
SUPPORTED THROUGH EXISTING 90 MiB PRODUCT ENVELOPE
```

Production large-PDF CUDA admission remains unchanged and is not authorized by this execution. The L6 production policy still names `cpu_onnx_fp32_v1` as the qualified large-PDF profile; no hot switching, fallback, AUTO behavior change, UI limit change, or production configuration change was made.

The result therefore does not by itself change `GET /v1/capabilities`, the effective runtime limit, or the shipped product policy. Any policy update is a separate design, implementation, and independent-review tranche.

## Evidence integrity

No PDF binaries were added to Git. The fixture manifest records the exact source and derived fixture identities. Historical L5 evidence was not modified. Production source and production policy were not modified. Q250 and Q512 remain `NOT RUN`.
