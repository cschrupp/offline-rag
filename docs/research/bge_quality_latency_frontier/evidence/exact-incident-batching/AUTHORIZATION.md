# Seneca — Exact-Incident Batching Qualification

**Prior research revision:** `9452907113a857cee8c3de3328fad810ec366ab7`

**Independent review disposition:** Accepted as interim research evidence. No production promotion.

## Objective

Validate whether length-aware BGE batching improves warm CPU inference latency on the actual four-vCPU Seneca VM, preserving all 30 candidates and the scientific retrieval output.

Compare:

- A: Existing consecutive batches of 16 + 14.
- B: Stable length-sorted batches of 8, restoring original candidate-score order.

Use the approved BGE PyTorch FP32 backend with intra/inter-op threads `2/2`.

## Experimental safeguards

Before execution, verify:

- Original deployed image and container identity.
- Recipes workspace revision 4 and exact frozen snapshot.
- Original selected-document scope and incident retrieval question.
- Model, tokenizer, retrieval configuration and scientific fingerprints.
- Available memory, disk, CPU allocation and VM shutdown deadline.
- Isolation, Qdrant ownership and reliable restoration.

Use the previously validated maintenance and isolated-data procedure.

No model substitution, backend change, candidate-depth change, new ingestion or generation is authorized.

## Measurements

Execute one warm-up per arm followed by three counterordered paired blocks.

Compare A/B, B/A and A/B, retaining the original candidate identities.

Record:

- Assembler wall time.
- BGE forward wall time per batch and total.
- Forward process CPU-seconds.
- Actual token lengths and padded positions.
- Memory/RSS.
- Effective CPU allocation and thread settings.
- Per-pair raw-logit differences.
- Exact candidate-score association.
- Full ranked candidate IDs and tie-breaking.
- Selected anchors, evidence units and packed context identity.

Predeclare the numerical parity tolerance and the minimum practically meaningful performance improvement before execution.

A speed improvement cannot be accepted if ranking or evidence parity fails.

Compare paired measurements and report the complete observations, not only the best result.

Do not infer production p95 latency or concurrency performance from this isolated experiment.

## Reporting

Extend *The 59-Second Retrieval* with a new chapter describing:

1. Why length-aware batching was selected.
2. How the experiment preserved model and retrieval semantics.
3. Actual four-vCPU performance compared with the synthetic pilot.
4. Numerical and scientific parity outcomes.
5. CPU and memory tradeoffs.
6. Limitations and the resulting engineering decision.

Retain the complete authorization prompt, implementation response, measurement records and restoration evidence.

Use a separately reviewable experiment branch based on the accepted research revision.

Do not modify the published interim findings retrospectively.

Restore the original service and verify both health endpoints, mounts, image, restart policy and publication state.

Stop after recording and reporting. Do not deploy or promote the batching treatment.
