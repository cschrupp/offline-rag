# Codex — Execute BGE-15 Four-Arm Qualification

The completed Rich small-pool experiment at `e56d8eefc28bab0e85bbc2c8802d53acef7e05a2` is accepted as exploratory research evidence.

Proceed to the next separately authorized research campaign, using the previously reviewed BGE-15 protocol:

`docs/research/bge_quality_latency_frontier/evidence/bge15-cpu/PROTOCOL.md`

Preserve its four arms:

- A: BGE-30, consecutive batching.
- B: BGE-15, consecutive batching.
- C: BGE-30, sorted-eight batching.
- D: BGE-15, sorted-eight batching.

Use the exact Recipes snapshot, original query and scope, unchanged model, fixed CPU execution profile, and the predeclared comparison and parity gates.

Before execution:

1. Start from a fresh VM window with sufficient time for all 20 calls and restoration.
2. Confirm the original container is running and both health endpoints return 200.
3. Validate the real Qdrant and lexical backing of both immutable snapshot publications in the isolated copy.
4. Verify that both reranker configurations reject the other's snapshot and that production publications remain untouched.
5. Confirm isolated Qdrant ownership and absence of concurrent experiments.

Execute only if all prerequisites pass. Do not shorten the study to fit the VM deadline.

Afterward:

- Report all four arms, paired latency, CPU cost, resource usage and candidate/evidence changes.
- Distinguish batching parity within each depth from the quality impact of changing candidate depth.
- Preserve the two known BGE-15 quality regressions.
- Restore the original container, then confirm that it remains running and both health endpoints return 200.
- Retain the full authorization, implementation response, measurements and restoration evidence.
- Update *The 59-Second Retrieval* and push a separate experimental branch.

No deployment, workspace migration, reranker-default change, or production promotion is authorized.

Stop after submitting the experiment for independent review.
