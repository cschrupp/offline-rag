# Rich small-pool experiment provenance

- Accepted study parent: `71bff228c4e98098c61782e5a3bab6c6c1e7e2e3`.
- Executed valid-schedule harness: `ee1e2905a0603db99a40c90d9e636e18af884575`.
- Deployment: `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`, image
  `sha256:3bc83208a7526a49abed1b9bd9586b5ae4fd041771732e03030c3ac20419e692`.
- Original container: `e006597fd6e4e40939e49c1dd73da7c6d85f33d87d44929c15dc5f0f38bb7cac`.
- Snapshot: `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`,
  Rich revision 2, one active document. No-history normalized question and
  ordered candidate/tensor identities match the previous Rich diagnostic.
  The historical browser's resolver produced a different retrieval hash.
- Original BAAI/bge-reranker-v2-m3, revision
  `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`. Preflight compared six
  model/config/tokenizer hashes. The measured process used Torch FP32 2/2
  and unchanged Qwen3 CPU ONNX 8/1. The diagnostic cgroup had no tighter
  CPU quota and four effective CPUs.
- Retry VM start was 23:28:36 UTC with its 7,200-second STOP policy intact.
  The runner required more than 3,000 seconds remaining, budgeted 1,800
  seconds for diagnostics and retained time for bounded restore. Preflight
  checked the original signature, both health endpoints, idle connections
  and CPU, model/snapshot identity, data size and available disk/RAM.
- The original container was stopped gracefully before copying data.
  Only the isolated container opened copied Qdrant storage. The models mount
  was read-only, networking disabled. The instrumented BGE scorer retained
  canonical behavior and measured FP32 forwards. The only treatment was
  changing the scorer's consecutive batch size for each arm. Candidate
  order, full-shape historical A encodings and positions, per-pair active
  encodings across arms, logits, canonical ranking and selected context
  were verified.
- The first attempt's retained measurement stream ended at the first call
  of block 4, with 17 observations and no logged restoration confirmation.
  No conclusion is drawn from that incomplete set. It is preserved
  separately, not pooled with the restart. The original image/container
  were confirmed healthy after the operator's restart before a fresh
  four-warm-up and 16-measurement schedule was launched. The retry used
  durable temporary VM-side logs so the client connection was not the
  sole copy.
- Python compilation and shell syntax checks passed. The focused research,
  matching and canonical retrieval suites passed 44 tests, including a
  synthetic regression that retains a fast arm whose parity gate fails.

## Completion and restoration

The retry completed exactly 20 assembler calls and returned zero. All 15
arm-to-baseline comparisons passed scientific parity. No treatment cleared
the unchanged 20% median forward and assembler wall-time screen.
The original deployment returned HTTP 200 for both health endpoints after
restart. The original image, mounts, restart policy, revision, snapshot,
and source inventory matched preflight. The retained before-manifest of
the interrupted attempt matched the retry preflight exactly. After
verification, the isolated data and temporary VM launch/measurement files
were removed, including the leftover interrupted attempt directory.
Only the interrupted sample log's trailing whitespace was normalized
during import. Its samples and values are retained separately.
