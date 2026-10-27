# Post-L6 CUDA 90 MiB PDF qualification campaign

Authority: `S16-K-LARGE-SOURCE-CAPACITY-POST-L6-CUDA-90M-PDF-QUALIFICATION-EXECUTION-AUTH-001`

Governance base: `df14ef6924fce32c6621e6b5f0b30fbe4cc7c870`

Scientific execution pin: `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`

Evidence contract: `large-source-capacity-evidence-v1`

This bounded completion run evaluated the previously unevaluable `cuda_fp16_v1` lane through the frozen full-product PDF/Docling harness. It used the exact frozen Q25 and Q100 fixture identities. No Q250 or Q512 execution was authorized or performed.

## Matrix

| Cell | Result | Evidence |
|---|---|---|
| CUDA preflight | PASS | [`preflight/cuda_fp16_v1.json`](preflight/cuda_fp16_v1.json) |
| Q25 | VALID_PASS | [`cells/cuda_fp16_v1_Q25.json`](cells/cuda_fp16_v1_Q25.json) |
| Q100 | VALID_PASS | [`cells/cuda_fp16_v1_Q100.json`](cells/cuda_fp16_v1_Q100.json) |
| Q100-CONFIRM | VALID_PASS | [`cells/cuda_fp16_v1_Q100_CONFIRM.json`](cells/cuda_fp16_v1_Q100_CONFIRM.json) |
| Q250 | NOT RUN | Progressive matrix stops at the requested envelope |
| Q512 | NOT RUN | Progressive matrix stops at the requested envelope |

The requested and resolved profile was `cuda_fp16_v1` for every attempted cell, with `qualification_profile_verified: true`. GPU instrumentation positively observed an NVIDIA GeForce RTX 2080 Super with CUDA execution and FP16 dense execution. Each cell completed Docling parsing, chunking, dense generation/materialization, lexical indexing, publication, and durable managed-operation success with one active source and matching fixture identity.
