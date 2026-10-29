# R04 Quick M2/M3 Screen and CUDA Ingestion Corrective

## Scope and provenance

- User authorization: bounded M2/M3 engineering screen followed by production
  implementation only if the combined candidate succeeded.
- Starting subject: `4c09c924f93b54a2c2e8d9e4ba94c68b77f73fa5`.
- Branch: `implementation/16k-r04-finite-conditional-spec-authority`.
- Diagnostic harness subject: `feff974696682d287d277d7264ac1e4d46100e00`.
- Frozen 32-item workload SHA-256:
  `e4ea6d13f5c0d5dcd0c1783afc86dde8c88d7957d586fd9f2f4ddf0c96001453`.
- This is an engineering screen and one live product verification, not formal
  M0–M5 qualification. Earlier campaign claims and incomplete M0 OOM evidence
  remain unchanged.

## Screen results

The M1 reference was reused: `use_cache=false`, fixed batch 32, post-load FP16,
and automatic attention. It succeeded with vector digest
`6d94d1a8d03c88527baa0fa0b2e52fe68d70d293d221001d6ba010c65528d0dc`.

The direct-FP16 M2 screen used the same no-cache fixed-32 workload. It succeeded
with vector digest
`b7788363d9d3a2b2ca47799ba7ed36eeee59db8ec9ca048f2d58792b3a12b343`.
Against the reference, median cosine was about `0.999998`, minimum cosine about
`0.999997`, top-1 agreement was 16/16, and mean/minimum top-10 overlap were 1.0.
Direct FP16 reduced observed model-construction peak allocation from about
2.69 GB to 1.19 GB and construction time from 2.85 s to 1.55 s. Encode peak
allocation was effectively unchanged (2.410 GB reference; 2.412 GB direct
FP16). Therefore direct FP16 is useful for load-time headroom, but it does not
explain or resolve fixed-batch encode pressure by itself.

The M3 profiler screen succeeded and observed 476 efficient-SDPA calls at
`[32, 16, 1243, 128]`. Efficient attention was both the active backend and the
only eligible backend. No alternate-backend run was admitted; no dependency or
attention override was added.

The combined diagnostic candidate—direct FP16, `use_cache=false`, deterministic
token-budget partitions, default attention—returned all 32 document and 16
query vectors. Its vector digest exactly matched the direct-FP16 fixed-32 run.
Encode peak allocation was 1.768 GB, peak reserved allocation was 1.986 GB,
and encode time was 3.837 s.

## Interpretation

The incident workload is not limited by raw PDF transport size. The fixed-32
embedding batch contains highly heterogeneous token lengths and about 71.4%
padding. M1 succeeded with cache disabled, while the earlier M4 screen succeeded
with token partitions even though cache remained enabled. Those screens show
that either change can make this diagnostic workload complete; they do not
identify one exclusive root cause because the original OOM peak was
right-censored and its exact allocation event was not captured. The local model
configuration supports a large generation KV cache, which is unnecessary for
embedding inference and consumes memory alongside padded attention work.

The measured evidence supports three bounded conclusions: disable the unused
generation cache for CUDA embedding, partition highly variable token lengths
before encoding, and use direct FP16 to reduce model-load memory. The attention
profiler provides no eligible alternate kernel to pursue. The combined
candidate materially lowered encode peak on the frozen workload, but this
single screen is not a statistical or general capacity qualification.

## Production implementation

The CUDA embedding path now loads with `use_cache=false`; CUDA FP16 parameters
are materialized as FP16 during model loading and verified. Before encoding,
document payloads are tokenized with the model tokenizer and finite sequence
limit, then greedily partitioned in input order under the accepted p95
padded-token budget. The existing bounded OOM batch ladder remains in place.
Execution batch and padded-token facts flow through the qualified runtime into
the existing dense profile. CPU encoding behavior is unchanged. No CPU fallback,
attention override, dependency change, or product-limit change was made.

## Live Well Logging verification

Using the existing CUDA runtime and the frozen source bytes (22,656,044 bytes;
SHA-256 `f50a3df2e1d22c8c925a60981a79b4e70a675cb70504ce725e7d0d2e03195afd`),
one `SOURCE_ADD` was submitted against workspace
`ws_464d92440ba343bf9372216e508e81b4`, revision 2, with one active source.

- Operation: `wop_14f50ff08a72420f89a60ba677f45009` — `SUCCEEDED`.
- Published workspace revision: 3; active source count: 2.
- Rebuild: 1,498 child chunks; 605 embeddings generated, 893 reused, 0 failed.
- Dense stage: CUDA FP16; 35.079 s embedding generation; total operation
  53.114 s.
- `/health/ready`: HTTP 200 after publication and after retrieval.
- Workspace-scoped retrieval: HTTP 200, answered, with four citations resolving
  to the Well Logging source.

The operation reused 893 previously persisted embeddings, so this is a valid
end-to-end product verification of the candidate but not a clean-room
re-embedding of all 1,498 chunks.

Local raw live-run responses and SHA-256 manifest are under the ignored path
`artifacts/diag_16k_r04_embedding_memory/execution_005/live_ingestion_001/`.
No PDF bytes, vault payload, or credentials were added to Git.

## Validation and current disposition

- Focused unit suite: **61 passed** across CUDA recovery, runtime propagation,
  dense profiling, failure observability, and dense indexing.
- Ruff check on changed implementation/test files: pass; the unchanged
  `profiling.py` baseline still has its pre-existing `RUF046`, `SIM102`, and
  `PLR1730` findings.
- Ruff format check: implementation and focused test files pass. Existing
  formatting differences remain in `pipeline.py` and `profiling.py`; broad
  reformatting was avoided.
- `git diff --check`: pass.
- Scientific M0–M5 qualification: not claimed.
- CPU fallback: held, not implemented.
- Attention backend change, dependency change, and capacity-policy change: none.
- Independent review, Human acceptance of the resulting production corrective,
  and promotion: pending.

## Implementation review handoff

Changed paths in this candidate:

- `ROADMAP.md`
- `src/offline_rag/dense/embedder.py`
- `src/offline_rag/dense/embedding_runtime.py`
- `src/offline_rag/dense/pipeline.py`
- `src/offline_rag/dense/profiling.py`
- `tests/unit/dense/test_cuda_oom_recovery.py`
- `tests/unit/dense/test_dense_embedding_runtime.py`
- this result artifact

The implementation is ready for independent review. The focused validation and
the bounded real-workload check are complete. No promotion or CPU fallback is
authorized by this handoff.
