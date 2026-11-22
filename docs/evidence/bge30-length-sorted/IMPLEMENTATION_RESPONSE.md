# Implementation response

Implemented opt-in length-sorted eight-pair batching for the shared PyTorch
reranker, with consecutive batching as the default. The strategy preserves
the original RRF pool, passage-only truncation, raw scoring, and canonical
tie-break. Configuration validates YAML and the Docker/service environment
override. The scientific fingerprint is unchanged. Execution diagnostics
record the strategy and device without changing the durable trace schema.

The candidate uses the 18D-R reranker-initialization line at
`f2dd2bda1890fb86ddb055ef101c2e5e098eba43` to retain initialization safety.
Technical candidate `6f1ea0941065c014983882ecc16fc03f260346cc` covers settings,
scoring, retrieval, assembly and diagnostic propagation. The new tests
exercise synthetic pairs, malformed inputs and logits, context/evidence
parity, and the loader override. The benchmark is separate from application
code. The complete request is preserved in [AUTHORIZATION.md](AUTHORIZATION.md).

## Validation

```bash
PYTHONPATH=src python -m pytest -q --tb=short \
  tests/unit/test_cross_encoder_batching.py \
  tests/unit/test_cross_encoder_initialization.py \
  tests/unit/test_hybrid_rerank.py tests/unit/test_context_expansion.py \
  tests/unit/test_slice10a_generation_semantic.py \
  tests/unit/test_slice10d_generation_hard_negative.py \
  tests/unit/test_provenance_prompt.py \
  tests/unit/app/test_slice15c_snapshots_leases_documents.py \
  tests/unit/app/test_query_failure_observability.py
```

154 passed with one existing FastAPI TestClient deprecation warning. The final
run included locally provisioned tokenizer artifacts, so all 17 snapshot
cases executed. Targeted Ruff lint and format, Python compilation, and
`git diff --check` passed.

## CPU development results

The [raw measurements](cpu-development.jsonl) are scorer timings on the local
Intel Core i9-10885H, CPU-only PyTorch 2.14.0, with 2/2 PyTorch threads and
the installed pinned FP32 BGE checkpoint. Both strategies warmed up before
the two measurements per arm. This exploratory run started before the
tokenizer-only lock was added, so the timings do not include that lock. The
shared-model forward path and batching/pair order match the candidate.

| Synthetic workload | Consecutive median wall | Sorted-eight median wall | Consecutive median CPU | Sorted-eight median CPU |
| --- | ---: | ---: | ---: | ---: |
| 10 short homogeneous pairs | 3.435 s | 3.686 s | 6.802 CPU-s | 7.328 CPU-s |
| 30 heterogeneous pairs | 38.521 s | 13.945 s | 76.515 CPU-s | 27.744 CPU-s |

Sorted-eight retained exact rankings and passed the preregistered FP32
tolerance, with maximum absolute logit difference of 0 for the homogeneous
case and about 1.91e-6 for the mixed case. The mixed batches changed from
16×333 and 14×333 to 8×48, 8×68, 8×103, and 6×333. Sorted prepasses took
about 1.2–2.5 ms. The cumulative process peak was roughly 2.40 GiB.
These two synthetic cases do not establish an activation threshold, a
production latency estimate or per-strategy peak memory.

CUDA device tests and benchmarks remain pending because the current host
environment has CPU-only PyTorch. Before opting into a CPU pilot, run
representative fixed-depth parity plus concurrent-load and cancellation
qualification. Keep the existing consecutive fallback for all deployments.
