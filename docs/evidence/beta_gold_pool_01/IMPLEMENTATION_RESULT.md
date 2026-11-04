# BETA-GOLD-POOL-01 implementation result

**Authority:** bounded BETA-GOLD-POOL-01 implementation authorization

**Base:** `2bca470bdcec35c6733fe54150f11363ba888bcf`

**Branch:** `implementation/beta-gold-pool-01-query-prompt`
**Candidate:** see the containing Git commit; this document intentionally does
not self-reference a commit SHA.

## Implementation

- The qualified factory now admits the explicit `model-query-prompt-v1`
  contract for the existing CUDA FP16 and CPU ONNX FP32 profiles. The default
  remains `raw-query-v1`; FakeEmbedder and unknown query contracts still fail
  closed.
- Both production adapters require a non-empty registered `query` prompt and
  invoke SentenceTransformers with `prompt_name="query"`. Missing, empty, or
  malformed prompt metadata raises a bounded adapter error. There is no raw
  query fallback.
- CPU ONNX continues through the shared ST/ONNX constructor and encoder.
- Gold pooling keeps its six-arm execution order and all-or-fail reviewability
  semantics. Failed outcomes now persist a failed retriever, bounded stage, and
  bounded exception category; no exception message or query text is copied into
  these diagnostic fields.
- The P1 amendment is recorded in
  [`beta_gold_pool_01_p1_query_prompt_amendment.md`](../../beta_gold_pool_01_p1_query_prompt_amendment.md).
  Query-contract selection still changes dense retrieval identity only; the
  existing index-identity invariance test passes.

Changed paths:

- `ROADMAP.md`
- `docs/BACKLOG.md`
- `docs/beta_gold_pool_01_p1_query_prompt_amendment.md`
- `docs/evidence/beta_gold_pool_01/IMPLEMENTATION_RESULT.md`
- `docs/milestone4_offline_gold_authoring.md`
- `docs/slice9c_candidate_pooling.md`
- `src/offline_rag/dense/embedder.py`
- `src/offline_rag/dense/onnx_embedder.py`
- `src/offline_rag/dense/query_text.py`
- `src/offline_rag/gold_authoring/pool.py`
- `src/offline_rag/gold_authoring/pool_arms.py`
- `src/offline_rag/gold_authoring/pooling_models.py`
- `tests/unit/app/test_slice16m_gold_pool_aux_index.py`
- `tests/unit/dense/test_dense_onnx_embedder.py`
- `tests/unit/test_dense_query_text.py`
- `tests/unit/test_slice9c_gold_pool.py`

## Numerical qualification

The installed, pinned model revision was evaluated locally without downloads.
The reference was the standard PyTorch CPU FP32 SentenceTransformers adapter;
the candidate was the product `make_embedder()` → qualified
`cpu_onnx_fp32_v1` runtime. Both used the same registered `query` prompt and
normalization.

Workload: the existing frozen D2 query population selected from the
1,296-child manifest (64-document parity population, 16 deterministic query
IDs). The query-ID set SHA-256 was
`9d1bf665faa970a3c4ff0de13473bc313334a1808a0d01d190eb429953db71a5`.

| Metric | Result | Existing D2 requirement | Result |
|---|---:|---:|---|
| Median query-vector cosine | `0.9999999999989395` | `>= 0.999` | PASS |
| Minimum query-vector cosine | `0.9999999999977348` | `>= 0.995` | PASS |

This establishes CPU ONNX registered-prompt vector agreement for that frozen
query population. It does not rerun full D2 document/retrieval parity or the
16K-F corpus campaign. The model load emitted the existing tokenizer regex
warning from Transformers; both same-revision reference and candidate used the
installed tokenizer artifacts. The warning is retained as a qualification
limitation, not suppressed or modified here.

CUDA execution was not possible in this sandbox: `nvidia-smi -L` reported that
GPU access is blocked by the operating system. CUDA factory routing and the
CUDA adapter's registered-prompt call, validation, raw-query behavior, and
no-fallback behavior are covered by tests, but no physical CUDA query run is
claimed.

## Validation

- `tests/unit/test_dense_query_text.py`
- `tests/unit/dense/test_dense_onnx_embedder.py`
- `tests/unit/test_slice9c_gold_pool.py`
- `tests/unit/app/test_slice16m_gold_pool_aux_index.py`
- `tests/unit/dense/test_dense_embedding_runtime.py`

Combined focused result: **95 passed**, one existing Starlette/httpx
deprecation warning.

The following broader P1/P2/P4 test attempts stalled after partial progress and
did not produce a test summary; they are **inconclusive**, not passes:

- `tests/unit/app/test_slice16k_d_p2_dual_backend_product_integration.py`
- `tests/unit/app/test_slice16k_d_p4_dual_backend_acceptance.py` (bounded
  60-second run exited `124` after nine progress dots).

Ruff lint passes for the changed production modules and the focused adapter /
factory / local-pooling tests, excluding pre-existing lint debt in
`tests/unit/test_slice9c_gold_pool.py`. Formatting checks also report existing
formatting drift in touched legacy files; no repository-wide formatting was
applied. `git diff --check` passes.

## Preserved historical evidence and execution boundary

The failed live Quick Play record was not edited or retried. Its current
SHA-256 is:

`056d60fee372d189886172e64ecc5ed1c3bb3e6541b73e43c32a64f0f49ee1f4`

No live Quick Play/bootstrap operation, real-corpus campaign, production
promotion, or Slice 17 work was performed. No model was downloaded and no
historical P1/D2 evidence was rewritten.
