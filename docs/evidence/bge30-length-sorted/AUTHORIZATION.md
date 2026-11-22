# Seneca — Implement BGE-30 Length-Sorted Batching Across CPU and CUDA

## Decision and authority

Authorize immediate implementation of Option C as a supported, configurable execution strategy throughout Seneca's BGE PyTorch reranker.

**Do not defer coding until the remaining large-scale qualification studies are complete.**

This authorization covers implementation, local tests, development benchmarks, documentation, and a reviewable GitHub pull request.

It does not authorize enabling the strategy by default in production, deploying a new image, or modifying existing workspaces.

Repository: `cschrupp/offline-rag`

Research qualification reference:
`27b1389654f7c89e72e98447bd81d34cc38b03fe`

Measured four-arm experiment:
`05a38aaf4820f598defe8d4c9c13d87f3bddb641`

## 1. Repository and authority preflight

Read `AGENTS.md`, the current scientific contracts, the production qualification decision, and the actual current implementation.

Inspect:

- `src/offline_rag/rerank/cross_encoder.py`
- `src/offline_rag/config/models.py`
- `src/offline_rag/rerank/config_hash.py`
- Retrieval and context-assembly orchestration
- Existing CPU and CUDA scorer tests
- Runtime configuration loading and deployment overlays
- Exact-incident batching research implementation

Create a dedicated implementation branch from the appropriate current application baseline.

Keep research evidence and production implementation commits distinct.

## 2. Implement a shared batching strategy

Add a validated execution configuration with two choices:

- `consecutive` — existing behavior, retained as the default.
- `length_sorted_8` — new Option C strategy.

The new strategy must:

1. Preserve the original RRF candidate pool and its ordering.
2. Preserve all candidates and `reranker.input_k=30`.
3. Use the approved tokenizer with passage-only truncation and the original 1,024-token ceiling.
4. Determine actual post-truncation sequence lengths before padding.
5. Stable-sort pairs by sequence length, using original ordinal to resolve ties.
6. Execute groups of up to eight pairs.
7. Restore each raw logit to its original candidate ordinal.
8. Preserve the existing canonical ranking and tie-breaking.
9. Preserve selected anchors, evidence units, and packed context when numerical parity permits.
10. Fail explicitly on malformed inputs, duplicate or missing ordinals, score-count mismatches, or nonfinite logits.

Avoid duplicating the scorer for CPU and GPU.

Do not introduce ONNX, quantization, a different checkpoint, or other inference changes.

## 3. CPU and CUDA support

The same strategy must support PyTorch CPU and CUDA inference.

Preserve the existing device-selection mechanism and device-specific tensor transfer.

For CUDA, account for asynchronous execution when measuring latency. Use synchronization at appropriate benchmark boundaries so GPU timings represent completed computation.

Do not assume sorted-eight is faster on GPU. Smaller batches may reduce accelerator utilization.

Avoid unnecessary host/device synchronization in the production scoring loop.

No CUDA device is required to build or unit-test the shared implementation, but actual CUDA performance qualification must remain pending until measured on suitable hardware.

## 4. Scientific identity and configuration

Keep the original scoring model, tokenizer, input construction, truncation, precision contract, score transformation, candidate depth, and tie-breaking unchanged.

Assess whether the new strategy can be classified as execution-only under the existing scientific identity contract.

Do not add the strategy to `reranker_config_hash` merely because it is configurable, but do not silently exclude it without documenting the scientific compatibility argument and parity tests.

Existing snapshots must continue resolving under the default execution strategy without re-publication.

Record strategy and resolved device in non-secret execution provenance where compatible with existing trace schemas.

## 5. Comprehensive regression testing

Test both strategies on representative pair counts:

0, 1, 2, 5, 8, 10, 15, 16, 30, and more than 30 where supported.

Cover:

- Short and long sequences.
- Homogeneous and heterogeneous lengths.
- Identical-length pairs.
- Passage truncation at 1,024 tokens.
- Exact original-ordinal score association.
- Identical active input IDs, masks and applicable position IDs.
- Numerical-logit tolerance.
- Near ties and canonical tie-breaking.
- Exact ranked IDs, anchors, evidence units and packed context.
- Invalid inputs and explicit failure behavior.
- Default configuration and snapshot compatibility.

Use the preregistered FP32 tolerance from the accepted experiment.

Do not relax a failed gate to produce a passing test.

For CUDA, run device-backed parity tests when an authorized compatible GPU environment is available. Otherwise mark those tests pending, not passed.

## 6. Performance and deployment assessment

Reuse the existing research benchmarks and timing infrastructure.

Compare consecutive versus sorted-eight across representative CPU workloads.

Record total scoring latency, forward latency, CPU time, prepass cost, memory and batch shapes.

If CUDA hardware is available in an approved development environment, compare both strategies using equivalent CUDA measurements.

Do not claim a general performance improvement from the Recipes case alone.

Investigate whether a conditional strategy is warranted for small or homogeneous pools, but do not invent or enable an unqualified runtime-selection threshold.

## 7. Documentation

Update developer documentation to describe:

- The new execution strategy.
- Default and opt-in configuration.
- CPU and CUDA behavior.
- Scientific compatibility.
- Expected workload-dependent benefits.
- Known Rich workspace limitations.
- Performance and parity test procedures.
- Rollback to consecutive batching.
- Docker configuration and observability.

Link the implementation to *The 59-Second Retrieval* without rewriting historical experimental observations.

## 8. GitHub delivery

Commit the implementation, focused tests and documentation.

Push a dedicated feature branch and prepare a draft pull request.

Provide:

- Branch and commit SHA.
- PR URL.
- Complete changed-file summary.
- CPU test results.
- CUDA test results or explicit hardware limitation.
- Scientific compatibility assessment.
- Benchmark results.
- Known regressions and limitations.
- Recommended path to an opt-in CPU pilot.

Retain the full authorization prompt and Codex implementation response.

## Restrictions

Do not:

- Change `reranker.input_k`.
- Modify frozen scientific evaluation artifacts.
- Reindex or reingest workspaces.
- Change immutable snapshot identities.
- Change production defaults.
- Deploy to the Seneca VM.
- Run new production queries.
- Merge the implementation into main.
- Enable the new strategy globally before qualification.

**Deliver functioning implementation code now, with consecutive batching remaining the production fallback. Stop at the reviewable draft PR.**