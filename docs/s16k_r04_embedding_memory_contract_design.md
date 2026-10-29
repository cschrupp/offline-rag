# S16K-R04 — Qwen3 Embedding Memory Contract / CUDA OOM Characterization Design

## Authority and status

```yaml
authority: S16K-R04-EMBEDDING-MEMORY-CONTRACT-DESIGN-AUTH-001
repository: cschrupp/offline-rag
exact_design_parent: 0442dce84c155e2160a09d8f5a8132f34a1d0762
branch: design/16k-r04-embedding-memory-contract
status: DESIGN AUTHORIZED

implementation: NOT AUTHORIZED
scientific_or_live_cuda_execution: NOT AUTHORIZED
another_well_logging_attempt: NOT AUTHORIZED
16K-F/G: NOT AUTHORIZED
promotion: NOT AUTHORIZED
```

This document freezes a bounded measurement and hypothesis program. It selects no production fix and changes no implementation, dependency, runtime setting, capacity policy, or scientific evidence.

## 1. Purpose

Determine the CUDA inference memory contract Seneca should use for its provisioned Qwen3-Embedding-0.6B model on constrained hardware while preserving embedding and retrieval semantics. Separate these possible causes before choosing a production change:

- unnecessary inference-time KV cache;
- model loading/materialization peak;
- actual attention kernel and its intermediate memory;
- Qwen-token sequence and padding workload;
- PyTorch allocator state and fragmentation;
- allocations outside the PyTorch allocator, including external GPU occupancy.

The method is `observe → isolate one variable → measure → verify parity → decide`. The observed OOM does not by itself justify `use_cache=False` or any other treatment.

## 2. Accepted predecessor evidence

The following is inherited and frozen:

- Incident source: `Well Logging for Earth Scientists.pdf`, 22,656,044 bytes, SHA-256 `f50a3df2e1d22c8c925a60981a79b4e70a675cb70504ce725e7d0d2e03195afd`.
- Original incident: CUDA out-of-memory error occurred during embedding generation. R03 remains closed as bounded `NOT_REPRODUCED`; this design does not rewrite it.
- Accepted adaptive implementation: `469bb8a3b137c279b1dcfa8bcef8cb8c7fbeaf40`; ladder `32 → 16 → 8 → 4`, no CPU fallback, no profile switch, and no identity change.
- Live Run 001 result: `0442dce84c155e2160a09d8f5a8132f34a1d0762`; one run ended `cuda_memory_exhausted` at effective batch 4, with 893 reused, 0 generated, 32 failed embeddings over 1,498 desired child chunks. Workspace publication rolled back to revision 2 / source count 1, while API readiness remained 200. No retry occurred and no capacity qualification was established.
- Preflight observed approximately 7,161 MiB of 8,192 MiB GPU memory occupied. Process-level attribution was not observable. High occupancy was observed; owner/root cause was not established.

The committed live result is [LIVE_EXECUTION_RESULT.md](evidence/16k_r04_cuda_oom/LIVE_EXECUTION_RESULT.md). Its local raw snapshots remain outside Git.

## 3. Current Seneca execution path

Static inspection of the authorized checkout establishes this path:

```text
chunk artifacts → embedding text → cache lookup → pending texts
 → SentenceTransformersEmbedder
 → SentenceTransformer(local bundle, device=cuda, offline)
 → apply_fp16_after_load(model)
 → model.encode(batch_size=effective batch, normalize_embeddings=True)
 → returned vectors → artifact persistence → Qdrant materialization
```

Relevant implementation surfaces are `src/offline_rag/dense/embedder.py`, `precision.py`, `profiling.py`, and `execution_profile.py`. Current production configuration is profile `cuda_fp16_v1`, SentenceTransformers backend, batch 32, model revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, dimension 1024, and normalized output. Current precision application occurs after `SentenceTransformer(...)` construction via `.half()`.

The local provisioned bundle is pinned by `models/embeddings/qwen3-embedding-0.6b/offline-rag-embedding.json`; local `config.json` SHA-256 is `b5bf1f51fc45be473a54718cef92448d90a1be001bf9b9a44b8c7f10a19feaa9`. It declares Qwen3, hidden size 1024, 28 layers, 16 query heads, 8 KV heads, 32,768 maximum positions, `torch_dtype=bfloat16`, and `use_cache=true`. The local SentenceTransformers module graph is Transformer → last-token Pooling → Normalize.

Installed canonical environment versions, read from package metadata without importing/initializing CUDA, are SentenceTransformers 5.7.0, Transformers 4.57.6, and PyTorch 2.14.0.

### Static cache finding and limit

The installed SentenceTransformers 5.7.0 source forwards `model_kwargs` to the Transformers loader and does not explicitly override `use_cache` in the installed transformer-module source. The installed Qwen3 `Qwen3Model.forward` signature defaults `use_cache=None` and passes that value through; the provisioned Qwen config declares `use_cache=true`. This statically predicts cache-enabled behavior. Newer, unversioned SentenceTransformers module documentation says cache is disabled unless overridden, so it must not be used as evidence for pinned 5.7.0 behavior. M0 must inspect the actually loaded model and the output of its actual forward before deciding whether H-KV applies.

## 4. External research findings

1. The pinned [Qwen model configuration](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/config.json) declares the architecture and source defaults above. These are source configuration facts, not proof of Seneca's loaded parameters or forward behavior. The model card identifies the [Qwen3-Embedding paper](https://arxiv.org/abs/2506.05176).
2. The [SentenceTransformers constructor reference](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html) documents `model_kwargs` forwarded to `AutoModel.from_pretrained`, including `torch_dtype` and attention selection. The installed [5.7.0 release](https://github.com/huggingface/sentence-transformers/releases/tag/v5.7.0) and local source are authoritative for this environment; current documentation is not substituted for pinned implementation inspection.
3. PyTorch distinguishes tensor `allocated` bytes from caching-allocator `reserved` bytes. Its [CUDA memory guide](https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html) documents allocator-history snapshots, OOM events, and the blind spot for direct CUDA/C++ or third-party allocations. `empty_cache()` releases unused cache, not live tensors; it is not the primary memory strategy.
4. PyTorch [SDPA documentation](https://docs.pytorch.org/docs/2.14/generated/torch.nn.functional.scaled_dot_product_attention.html) says CUDA may dispatch among fused and C++ math implementations based on input constraints. The configured `sdpa` API alone does not identify the kernel that ran. The [SDPA backend context API](https://docs.pytorch.org/docs/2.14/generated/torch.nn.attention.sdpa_kernel.html) is beta and will be used only for isolated diagnostic characterization, never assumed to be a production setting.
5. The official [FlashAttention repository requirements](https://github.com/Dao-AILab/flash-attention#nvidia-cuda-support) target standard FlashAttention-2 at Ampere/Ada/Hopper and direct Turing users to a separate project. Standard FlashAttention-2 installation is therefore excluded from this Turing/RTX 2080 characterization. Native PyTorch SDPA candidates are considered only if the pinned runtime reports them supported for the actual tensors.

These sources motivate measurements; none establishes a result on Seneca's workload or host.

## 5. Current-runtime facts and unknowns

| Area | Static fact | M0 must observe at runtime |
|---|---|---|
| Library stack | ST 5.7.0 / Transformers 4.57.6 / PyTorch 2.14.0 installed | Exact runtime versions and CUDA build/device capability in the diagnostic process |
| Module/model | Bundle says ST Transformer → Pooling → Normalize; feature-extraction mapping is expected to load Qwen3 base model | Actual first-module and underlying HF model classes |
| KV cache | Bundle config `use_cache=true`; pinned source has no explicit ST override | Loaded config and nested config values; `use_cache` passed to forward; whether non-null cache/past object is returned |
| Precision | Seneca applies `.half()` after ST construction; bundle config declares BF16 | Parameter dtype counts before/after precision stage; initialization and transfer peaks |
| Attention | Qwen3 supports SDPA; no Seneca attention kwarg is set | Configured `_attn_implementation` and profiler-visible implementation/kernel names |
| Sequence length | Tokenizer config says 131,072; ST 5.7 caps it to model `max_position_embeddings` (32,768) unless overridden | Actual `model.max_seq_length`, tokenizer model max, padding side, truncation and padded batch shapes |
| Inference | ST 5.7 `encode` is under `torch.inference_mode()` and calls `eval()`; the local path requests sentence embeddings and normalized output | Grad mode, `training`, hidden-state/attention flags, logits/cache output facts at the forward boundary |
| Work | Seneca chunks target about 350 tokens / max 512 using its own tokenizer | Exact Qwen tokenizer lengths, batch padding and workload maxima; Seneca token counts are not substitutes |
| Memory | Run 001 host preflight showed high unattributed occupancy | Allocator allocated/reserved peaks, device free/total, external device usage and process attribution per cell |

No value in the runtime column is inferred from model `config.json` alone.

## 6. Hypothesis table

| Hypothesis | Falsifiable prediction | Test |
|---|---|---|
| H-KV | A cache object is actually produced and disabling cache alone reduces forward peak memory materially with parity | M0 then conditional M1 |
| H-DTYPE | Direct FP16 materialization lowers initialization peak versus load-then-`.half()` without materially worsening steady/forward memory or parity | M2 |
| H-ATTN | Actual dispatch is a memory-costly path and a supported native SDPA backend lowers forward peak with parity | M0 profiler, then conditional M3 |
| H-TOKEN | Qwen-token padding/workload explains material peak variation at fixed passage count; token-budget batching lowers peak with parity | M4, only after runtime configuration is correct |
| H-ALLOCATOR | OOM coincides with allocator fragmentation/large inactive splits or insufficient PyTorch-managed headroom | Per-cell allocator counters and diagnostic OOM snapshot |
| H-EXTERNAL | Device-wide usage materially exceeds PyTorch allocator accounting or varies with unattributed external consumers | Per-cell NVML/driver/device observation paired with PyTorch counters |

An observed configuration value alone does not establish material memory contribution. A hypothesis is `SUPPORTED` only if its predeclared treatment meets the decision rule in D12; otherwise it is `FALSIFIED`, `NOT_APPLICABLE`, or `INCONCLUSIVE` as specified below.

## 7. Decision ledger D01–D15

| ID | Frozen decision |
|---|---|
| D01 | M0 emits the runtime contract below; loaded values and actual forward evidence take precedence over source defaults. |
| D02 | KV cache is first. M1 runs only when M0 sees loaded cache enabled and a cache object produced. If cache is disabled or no object is produced, M1 is `NOT_APPLICABLE`; no artificial A/B is run. |
| D03 | M2 compares existing load-then-`.half()` with direct `torch_dtype=torch.float16`; it changes materialization only. Cache/attention/tokenization/pooling/normalization/model revision remain as frozen by preceding accepted state. |
| D04 | Inference mode, eval mode, disabled autograd, no hidden-state/attention collection, and no logits are inherited expectations to verify, not production changes. Cache output is separately observed. |
| D05 | Actual Qwen tokenization and batch shapes are measured on exact embedding strings; Seneca tokenizer counts do not stand in for them. |
| D06 | Report configured attention API separately from profiler-observed execution. Native PyTorch SDPA candidates only; standard FA2 and third-party Turing forks are excluded. |
| D07 | Every cell records allocator stats at each stage; on OOM it captures bounded allocator history/snapshot diagnostic-only, and verifies the OOM event is present when supported. |
| D08 | Every cell records device total/used/free and visible process data. If process ownership is unavailable, record `NOT_OBSERVABLE`; do not infer a process owner. |
| D09 | Freeze one exact 32-item first-pending batch from Run 001 if reconstructable from local provisioned/cached artifacts. Freeze ordered IDs and digest before CUDA; never store private text. If exact order/cache state cannot be reproduced, use the explicitly labeled deterministic incident-adjacent substitute described in §8; do not call it exact incident reproduction. |
| D10 | Staged, conditional M0–M5 sequence; at most three valid fresh-process replicates per condition, at most two eligible M3 treatments, at most 21 measured cells, one cell at a time, 15-minute per-cell cap and 4-hour total cap. No within-cell retry. |
| D11 | Reuse `d2-retrieval-parity-v1` thresholds from accepted D2 evidence; no weaker threshold. OOM before vector output requires the CPU ONNX profile as offline parity reference for this exact batch under separate execution authority; this is not runtime fallback. |
| D12 | A candidate must pass all correctness/parity requirements, meet a predeclared memory improvement threshold, and stay within the latency bound. Metrics and rules are in §9 and §12. |
| D13 | Select the smallest semantically neutral candidate in hierarchy: cache state, direct FP16 load, supported native attention, then token-budget batching. Choose no candidate if none passes. |
| D14 | Preserve the accepted `32→16→8→4` production ladder unchanged as exceptional final safety recovery; do not redesign/remove it in this program. |
| D15 | Harness implementation, experimental execution, any production implementation, and any later full Well Logging ingestion each require their own authority. No broader product or slice work follows from this design. |

## 8. Frozen diagnostic workload and identity

Preferred workload: the first pending outer encode batch in Live Run 001, with the same model bundle/revision, embedding-text contract, profile, prompt behavior, normalization, and 32-item configured batch. Run 001 reports 1,498 desired chunks, 893 reused embeddings, and 32 failed items, but its committed operation projection does not itself contain the ordered pending chunk IDs. Therefore the exact batch identity is **not yet established**.

Before M0 starts, an authorized, CPU-only workload-freeze step must:

1. Verify the source SHA, workspace/source state, model revision, chunk/config identity, and cache/artifact inventory corresponding to Run 001.
2. Reconstruct pipeline pending selection/order from the immutable artifacts and accepted code at `0442dce…` without loading the model or creating a CUDA context.
3. Require exactly 32 ordered text identities for the first failed outer batch; serialize only ordered chunk IDs, each embedding-text SHA-256, an aggregate digest, and the source/config/chunk-set identities.
4. Validate that reconstructing the candidate selection reproduces the reported 893 reused / first 32 failed boundary. If not, stop exact reconstruction.

If exact reconstruction is impossible, use the same 32 source chunks selected by a deterministic rule from the preserved parsed/chunk artifacts: order by the production pipeline's actual traversal order, choose the first 32 currently missing embedding-artifact identities, and freeze that selection before any model call. Mark it `INCIDENT_ADJACENT_SUBSTITUTE`; it may characterize hypotheses but cannot be described as reproducing the exact Run 001 batch. If these chunks cannot be recovered without re-running PDF parsing, the design requires a new design review before choosing another workload.

All text stays local and untracked. The manifest includes ordered IDs, per-item text digests, aggregate workload digest, exact tokenizer/model revision, token counts, and batch partition; it contains no source text or raw token IDs.

## 9. Measurement contract

Each cell is one fresh diagnostic process, one model materialization, one frozen workload execution, and no adaptive batch retries. It invokes the same pinned SentenceTransformer bundle and encoding options as Seneca, but bypasses the R04 retry loop so an OOM is observed at the registered batch rather than being hidden by fallback attempts. The production ladder is unchanged.

Capture versions, GPU/device/driver, process attribution, configuration, and runtime facts listed under D01. At each stage—before load; immediately after ST construction; after `.half()` for the current path or direct materialization for M2; immediately before encode; after successful encode; and after cleanup—record:

- `memory_allocated`, `memory_reserved`, `max_memory_allocated`, `max_memory_reserved`;
- `mem_get_info()` free and total bytes;
- `torch.cuda.device_memory_used()` where supported;
- device-wide total/used/free and visible process list from best-effort NVML/`nvidia-smi` sampling at 10 Hz;
- stage wall time, with CUDA synchronization around the measured encode interval;
- input count, actual Qwen-token lengths and summary, sum of tokens, maximum sequence length, padded-token count (`batch_count × batch_max`), and padding fraction.

Reset allocator peak counters at each measured stage boundary. Keep allocator measurements distinct from device-wide measurements. The latter can include allocations invisible to PyTorch. If the host driver cannot expose process owners, record `NOT_OBSERVABLE`.

For each OOM cell, enable PyTorch allocator history only for that diagnostic process and cell, with `max_entries=20,000` and Python stack traces. Dump the snapshot immediately on OOM before teardown, disable history in `finally`, and record whether a snapshot was written and whether the OOM event appears. A missing snapshot/OOM event makes the allocator diagnosis incomplete, not the OOM invalid. Snapshot files and traces remain local; they are not always-on production instrumentation.

## 10. Experimental sequence M0–M5

Each valid trial uses a fresh process and the exact same 32 text items. Run up to three matched repetitions per condition. A trial is valid only if exact workload digest, installed versions, device/profile, and model revision match. Pair baseline/treatment runs whose initial device free memory differs by no more than 256 MiB; if this cannot be met, mark the comparison `INCONCLUSIVE` and stop rather than adjusting allocator or device settings.

### M0 — current-runtime characterization

No treatment. Load and execute current path as frozen. Observe loaded `use_cache`, cache outputs, actual parameter dtype, precision conversion stages, max sequence length/padding, inference/eval/grad state, configured attention and profiler-observed kernels, allocator/device memory, and output vectors. M0 is mandatory and must precede any treatment. If M0 succeeds, its vectors are the exact-workload baseline. If M0 OOMs, capture the OOM evidence and use D11's offline CPU ONNX reference for parity in later treatment cells.

### M1 — KV-cache treatment

Run only if M0 shows both loaded cache enabled and a non-null cache object produced. Change only `use_cache: true → false`, passed via the pinned ST `config_kwargs` before underlying model construction. Verify top-level and nested config state is false, the model call receives the intended state, and no cache object is returned. If M0 cache is false or no cache is produced, mark `NOT_APPLICABLE` and proceed to M2. Do not change dtype, batch, attention, text, tokenizer, pooling, normalization, or revision.

### M2 — direct FP16 materialization

Use the accepted cache state from M0/M1. Compare current `SentenceTransformer(...) → model.half()` with `SentenceTransformer(..., model_kwargs={"torch_dtype": torch.float16})`; remove only the post-load conversion in the treatment. Measure construction/loading peak separately from post-load steady state and first-forward peak. A lower steady-state reading alone does not prove an initialization improvement.

### M3 — attention characterization

Open only if forward memory remains material after preceding accepted decisions, or M0 directly demonstrates a costly path. First profile one separate diagnostic forward and retain actual operator/kernel names; profiler-run memory is not used as the numerical acceptance measure because profiling can perturb peaks. Query native PyTorch SDPA backend eligibility for the exact shapes. Test at most two eligible non-baseline native SDPA backends in isolated cells, one at a time. Do not install standard FlashAttention-2 or a third-party Turing fork. If the reference Turing device only supports the math backend, record that as the result and skip treatments.

### M4 — model-token-budget batching

Open only after cache, dtype, and any selected attention state are correct, and if peak memory still varies materially with workload shape. Compare fixed passage-count batch 32 with deterministic greedy ordered grouping under `padded_tokens ≤ 32 × p95(Qwen-token-lengths)` and `item_count ≤ 32`. Record both total real tokens and padded tokens; never change text, tokenizer, truncation, prompt, pooling, normalization, model or vector identity. If any individual sequence exceeds the budget, mark M4 `NOT_APPLICABLE` rather than silently truncating.

### M5 — selected-candidate confirmation

Combine only the selected passing settings from M1–M4 and run the frozen 32-item workload, still without a PDF or workspace lifecycle. M5 is three fresh-process repetitions at batch 32 unless M4's batching treatment is the selected candidate, in which case use its frozen deterministic partitions. Require success and parity in all three runs plus the thresholded memory/performance result. M5 confirms only the small frozen batch; it does not authorize or qualify a full Well Logging `SOURCE_ADD`.

## 11. Parity and correctness gates

Use accepted `d2-retrieval-parity-v1` thresholds from `docs/evidence/16k_d_dense_cuda/d2/d2_retrieval_parity_v1_1792555359.json`:

- 1,024-dimensional vectors; all values finite; normalized vector norm within `1e-4` of 1.0.
- Per-vector cosine: median at least `0.999`, minimum at least `0.995`.
- Retrieval: mean top-10 set overlap at least `0.95`, minimum at least `0.80`, and top-1 agreement at least 15 of 16 fixed queries.
- Exact-workload retrieval uses all 32 passages as documents and the first 16 in frozen workload order as queries; both paths use the accepted query/text contract. For an M0 OOM, the exact batch's offline CPU ONNX output is the diagnostic reference, not a production fallback.
- Output count, document identity/order, dimension, normalization, and artifact identity must be correct; a partial vector list is a failed cell.

Any candidate that violates parity is rejected, even if it saves memory. OOM is not a parity pass. Do not weaken these thresholds for this design.

## 12. Metrics and mechanical acceptance rules

For each condition, compare three valid paired repetitions using the median; require the direction of the stated memory effect in at least two of three pairs. Mark comparisons inconclusive if pair headroom differs by more than 256 MiB or external device usage changes by more than 256 MiB between paired stage windows.

A treatment is a **material memory improvement** only when its registered target peak falls by at least `max(256 MiB, 5% of the paired baseline peak)` and the median reduction meets that same threshold. No other primary peak measure may worsen by more than 256 MiB. Median encode wall time may not regress by more than 10%. Every successful run must pass §11. These thresholds apply to the specific mechanism:

- H-KV: first-forward `max_memory_allocated`; also report reserved and device-wide peaks.
- H-DTYPE: device-wide load-stage peak and allocator load-stage peak, separately; a lower post-load steady state alone is insufficient.
- H-ATTN: first-forward allocated peak; report reserved/device-wide peaks and actual kernel.
- H-TOKEN: first-forward allocated peak and max padded-token workload.

Candidate decision:

1. A configured-state predicate may be `NOT_APPLICABLE` (for example, cache already disabled).
2. A measured treatment is `SUPPORTED` only if all three runs succeed, parity passes in all runs, memory reduction meets the threshold, no other peak regresses beyond the bound, and latency regression is ≤10%.
3. It is `FALSIFIED` if the intended state was applied and matched trials fail the material-improvement threshold or parity. It is `INCONCLUSIVE` if environment matching, evidence capture, or repeatability gates fail.
4. An OOM cell is a valid negative resource outcome when workload/config/device identity is exact; it never triggers retry below the registered batch. On OOM, snapshot immediately. Non-OOM errors, process crashes, identity mismatch, or parity failure terminate the sequence as invalid for the causal question.
5. Stop after M5. No result from M0–M5 becomes production behavior without later implementation authority and independent review.

## 13. Stop conditions

- Workload cannot be frozen exactly or explicitly classified as the allowed substitute before CUDA/model execution.
- Model/config/revision/library mismatch, missing artifacts, unexpected extra process or concurrent embedding workload, GPU identity change, or failed preflight.
- Device-memory pairing tolerance is exceeded; attribution uncertainty must remain explicit.
- Any non-OOM execution error, process crash, artifact-identity error, invalid snapshot, privacy leak, or failed parity gate.
- A cell reaches 15 minutes or the campaign reaches four hours.
- Three valid replicates cannot be obtained without exceeding the cap; report inconclusive, do not relax criteria.
- Never retry a cell internally, increase memory policy, alter allocator configuration, change production batch/recovery, kill processes, or repeat the real PDF operation.

Two qualified OOM cells may be followed only by the next pre-registered single-variable treatment if its targeted phase can plausibly address the observed stage and all preflight conditions still hold. Otherwise stop. This keeps the sequence conditional while preventing an unbounded retry campaign.

## 14. Candidate-selection logic

Select at most one candidate per mechanism and cumulatively preserve only earlier candidates that passed. Prefer, in order:

1. disable a cache only if M0 proves it is actually produced and M1 materially improves forward memory;
2. direct FP16 materialization only if M2 lowers initialization peak materially and does not regress forward/steady memory;
3. an eligible native attention path only if M3 shows actual execution and material memory improvement;
4. token-budget batching only if M4 meets the same memory/parity/performance rules.

Keep the R04 adaptive ladder as the final safety net. If no candidate clears all gates, select none and preserve current production behavior. No CPU fallback, offload, quantization, allocator tuning, or model replacement is a candidate in this decision tree.

## 15. Expected implementation surfaces

This design authorizes no edits to these surfaces. A later diagnostic-harness authority may consider:

- `src/offline_rag/dense/embedder.py`
- `src/offline_rag/dense/precision.py`
- `src/offline_rag/dense/profiling.py`
- `src/offline_rag/dense/execution_profile.py`
- `scripts/diag_16k_r04_*/`
- `tests/unit/dense/`

Diagnostic harness implementation must be separately reviewed from any production runtime change. Test code must prove that the harness does not silently apply treatments or emit private text.

## 16. Explicit exclusions and later authority boundaries

Excluded: production code; another Well Logging upload; full-corpus 16K-F; 16K-G; Slice 17; CPU automatic fallback or CPU spill/offload; disk offload; `device_map`; quantization; model replacement; new allocator policies or `PYTORCH_ALLOC_CONF`; per-process memory fractions; permanent duplicate-server lock; standard FlashAttention-2 installation on Turing; third-party Turing attention replacements; main promotion; and any R03 modification.

Required subsequent gates, each separate:

1. Independent design review and Human acceptance of this exact design.
2. Bounded diagnostic-harness implementation authority; code review and validation.
3. Separate experimental execution authority for M0–M5, with host preflight, resource caps, and evidence custody. The offline CPU ONNX parity reference is permitted only if expressly included in that execution authority; it is not a product fallback.
4. If M5 selects a candidate, separate production implementation authority and independent review.
5. Any further full Well Logging ingestion requires a new bounded live-execution authority. It is not implied by M0–M5.

## Required design terminal

```yaml
S16K-R04:
  tranche: QWEN3_EMBEDDING_MEMORY_CONTRACT_DESIGN
  authority: S16K-R04-EMBEDDING-MEMORY-CONTRACT-DESIGN-AUTH-001
  exact_base: 0442dce84c155e2160a09d8f5a8132f34a1d0762
  branch: design/16k-r04-embedding-memory-contract
  design_artifact: docs/s16k_r04_embedding_memory_contract_design.md

  static_facts:
    local_qwen_config_use_cache: true
    pinned_sentence_transformers_explicit_cache_override: NOT_FOUND
    qwen3_forward_default: null_uses_config
    current_loaded_cache_or_cache_output: TO_BE_OBSERVED_M0
    direct_fp16_constructor_supported_by_pinned_api: STATICALLY_SUPPORTED
    model_parameter_dtype_and_load_peak: TO_BE_OBSERVED_M0
    inference_mode_and_eval: INHERITED_BY_PINNED_ST_ENCODE
    actual_attention_kernel: TO_BE_OBSERVED_M0
    qwen_token_distribution: TO_BE_MEASURED_AFTER_WORKLOAD_FREEZE

  hypotheses:
    H_KV: FIRST_CONDITIONAL_TEST
    H_DTYPE: SECOND_ISOLATED_TREATMENT
    H_ATTN: CONDITIONAL_NATIVE_SDPA_CHARACTERIZATION
    H_TOKEN: CONDITIONAL_PADDED_TOKEN_BUDGET
    H_ALLOCATOR: SNAPSHOT_AND_STAGE_COUNTERS
    H_EXTERNAL: DEVICE_WIDE_AND_PROCESS_OBSERVATION

  sequence: M0_M1_M2_M3_M4_M5_CONDITIONAL
  parity: D2_RETRIEVAL_PARITY_V1_THRESHOLDS
  max_measured_cells: 21
  implementation: NOT_AUTHORIZED
  cuda_or_model_execution: NOT_AUTHORIZED
  well_logging_retry: NOT_AUTHORIZED
  16K_F_G: NOT_AUTHORIZED
  promotion: NOT_AUTHORIZED

  terminal: STOP_FOR_INDEPENDENT_DESIGN_REVIEW
```

## References

- Qwen model card and pinned source config: [Qwen3-Embedding-0.6B, revision `97b0c614…`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B/blob/97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3/config.json); [Qwen3-Embedding paper](https://arxiv.org/abs/2506.05176).
- SentenceTransformers: [version 5.7.0 release](https://github.com/huggingface/sentence-transformers/releases/tag/v5.7.0); [SentenceTransformer constructor and `model_kwargs`](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html); [inference efficiency guide](https://sbert.net/docs/sentence_transformer/usage/efficiency.html).
- PyTorch 2.14: [CUDA memory snapshots and allocator visibility](https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html); [SDPA dispatch and backend behavior](https://docs.pytorch.org/docs/2.14/generated/torch.nn.functional.scaled_dot_product_attention.html); [backend selection API](https://docs.pytorch.org/docs/2.14/generated/torch.nn.attention.sdpa_kernel.html).
- FlashAttention: [official CUDA support requirements](https://github.com/Dao-AILab/flash-attention#nvidia-cuda-support); [FlashAttention paper](https://arxiv.org/abs/2205.14135); [FlashAttention-2 paper](https://arxiv.org/abs/2307.08691).
- Pinned local implementation inspected read-only: `.venv/lib/python3.14/site-packages/sentence_transformers/sentence_transformer/model.py`, `.venv/lib/python3.14/site-packages/sentence_transformers/base/modules/transformer.py`, and `.venv/lib/python3.14/site-packages/transformers/models/qwen3/modeling_qwen3.py`. Installed versions are recorded above; no package was imported for model initialization and no CUDA context was created.
