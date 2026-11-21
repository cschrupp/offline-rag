# Exact-incident batching protocol

Parent: `9452907113a857cee8c3de3328fad810ec366ab7`.

Same production image, Recipes revision 4, frozen incident snapshot, selected
document, question and settings. Use a graceful stop, copied writable data,
read-only original models, network disabled, and one diagnostic process.
Restore the original container on exit and require matching publication state,
container signature and both health endpoints before deleting temporary data.
Keep the prior 30-minute minimum preflight deadline margin, and bound the
diagnostic process to 20 minutes plus a 15-second termination grace.

One warm-up per arm in A/B order, followed by measured blocks A/B, B/A, A/B.
A uses 16+14. B performs a timed unpadded tokenization prepass, stable sorts by
post-truncation length and original ordinal, and scores batches 8+8+8+6.
Scatter B scores back to original ordinals. Both arms use Torch FP32 2/2 and
identical checkpoint, tokenizer, passage-only truncation, maximum length
1024, canonical ranking, and context assembly. Qwen3 configuration is frozen.

Numerical gate for every pair including warm-up:
`abs(B-A) <= 1e-4 + 1e-5 * abs(A)`. Require finite FP32 outputs,
exact candidate identity and score association, matching active token and
position IDs with right padding, exact full rank including tie break,
chosen anchors, evidence-unit identity, packed context and token count.
No performance qualification on parity failure.

Practical improvement gate: median of three paired fractional reductions
must be at least 20% for forward wall and at least 20% for assembler wall.
Report all trials and CPU/memory costs independently. Warm isolated single
query measurements do not establish deployment percentiles or concurrency.
