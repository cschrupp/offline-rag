# BGE-15 four-arm execution

- Parent and accepted prior Rich evidence: `e56d8eefc28bab0e85bbc2c8802d53acef7e05a2`.
- Executed harness: `d7a648f50f94b0c92ffb2786f6f01dbc76786f97`.
- Frozen protocol: [BGE-15 CPU qualification](../bge15-cpu/PROTOCOL.md).
- Deployment revision `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`, image
  `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`,
  original container `e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac`.
- Recipes revision 4, baseline snapshot
  `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`,
  603 indexed passages, original single-document scope and original question.
- BGE model `BAAI/bge-reranker-v2-m3` at
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`, Torch CPU FP32 2/2.
  Frozen Qwen3 CPU ONNX 8/1, four effective logical CPUs in affinity,
  no tighter diagnostic CPU quota. Before/after probes checked the same
  six model, config and tokenizer hashes and production retrieval
  settings hash. Unchanged mount and container policy were required.
- The fresh operator-started VM window served the previous Rich matrix
  and was healthy, restored and idle before this experiment. Over 90
  minutes remained before the unchanged 7,200-second automatic STOP.
  The runner requires more than 3,600 seconds and caps diagnostic
  execution at 2,400 seconds plus 15-second termination grace.
- Safe maintenance stopped the original container gracefully before
  copying its data. The original Qdrant store was never opened by the
  diagnostic. One network-disabled container opened copied Qdrant and
  mounted the original model store read-only. Preflight had 15,468,020
  KiB available RAM and 21,128,492 KiB free disk.
- Ordinary registry operations validated actual dense and lexical backing
  at both depths. The canonical publisher wrote the additional immutable
  snapshot only in the isolated copy, then both settings objects rejected
  the opposite snapshot as reranker_config_stale. The copied workspace
  and immutable BGE-30 manifest stayed unchanged. Both bindings used the
  same model resources and exclusive Qdrant owner.
- The only batching treatment is stable length prepass and grouping;
  reshuffled scores are scattered back to original pool order. Per-pair
  token IDs, masks and positions use hashes and do not expose text.
  At depth 15 the canonical reranker takes the top 15 from RRF before
  scoring. The log includes candidate/rank IDs, opaque evidence hashes,
  stage and per-batch timings, and signed deltas for same-depth contrasts.

## Outcome and restoration

The diagnostic exited zero after exactly 20 calls. All 10 within-depth
batching comparisons passed. B, C and D cleared the preregistered
performance screen against A. Depth reduction changed top-five
membership and packed context in every paired comparison. No quality
judgment or production migration was made.

After restarting the original container, the runner verified both health
endpoints and compared the full preflight projection again. The original
container signature, image, mounts, restart policy, workspace revision,
snapshot, corpus pointer, snapshot manifest hash and source inventory
matched. The original container was checked again after startup and remained
running with both health endpoints returning HTTP 200. Temporary VM
experiment files were removed. The automatic STOP policy was unchanged.
