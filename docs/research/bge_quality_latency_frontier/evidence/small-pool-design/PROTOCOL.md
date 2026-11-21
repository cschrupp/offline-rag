# Proposed small-batch CPU qualification

**Design only. Execution requires separate authorization.** Compare exactly
the same ten ordered Rich query–passage pairs from the no-history diagnostic.
Bind the same revision, snapshot, one-document scope, normalized question
SHA-256 and fused candidate order SHA-256 recorded by the diagnostic.
Require the original encoded per-candidate inputs and positions. Obtain the
pairs only from the canonical assembler inside a future approved isolated
runtime. No passage material is retained in this research branch. The
successful browser turn has a different retrieval-question digest.

## Controlled comparison

| Arm | Maximum batch size | Consecutive batch sizes |
|---|---:|---|
| A | Existing 16 | 10 |
| B | 5 | 5 + 5 |
| C | 4 | 4 + 4 + 2 |
| D | 2 | 2 + 2 + 2 + 2 + 2 |

Keep original order, all ten candidates, the approved BGE checkpoint and
tokenizer, PyTorch FP32, intra/inter 2/2 on the same four effective CPUs,
passage-only truncation and the 1,024-token ceiling. Change only grouping.
Use the canonical scorer, comparator and assembler. Score a finite raw
FP32 logit per pair. Independently verify complete, unique candidate-score
association and exact active inputs, masks and positions. Shape changes
may add/remove right padding only. Require
`abs(treatment - baseline) <= 1e-4 + 1e-5 * abs(baseline)` for every
candidate and exact full rank with the existing tie-break, selected anchors,
evidence-unit order/identity, and packed context. A parity failure prevents
qualification even if performance improves. Keep negative results.

Run in a single isolated warm process, with one warm-up per arm. Exclude
warm-ups from estimates. Use four balanced measurement blocks in this order:

1. A/B/D/C
2. B/C/A/D
3. C/D/B/A
4. D/A/C/B

This is 20 assembler calls in a future separately approved campaign,
subject to a deadline and restoration preflight sized for the full budget.
Each treatment is compared to baseline within its block. Report all trials,
batch lengths and widths, forward and scorer wall/CPU time, assembler wall
time, end RSS and shared-process high-water RSS, available RAM and swap.
Use separate fresh processes only as a follow-on if arm-specific peak memory
is needed. No transport, generator, background load, or concurrent requests.

Proposed advancement screen, frozen before measurements: median paired
warm forward and assembler wall reductions each at least 20%, at least
three of four positive pairs on each endpoint, no median paired process
CPU-seconds increase beyond 5%, and all parity gates pass. Record memory
changes and assess deployment headroom separately. The gate is an engineering
screen, not an estimate of p95 or a production SLO. A representative
multi-query and concurrent campaign would be needed before integration.

## Reused evidence and limits

The observed lengths in original order are 502, 509, 477, 435, 268, 329,
508, 454, 499 and 485. They determine arithmetic padded workload for
each consecutive grouping. The prior experiment timed only arm A on these
pairs. Recipes exact-incident sorted-eight execution and the synthetic
shape pilot support the method, but used different input populations or
batching treatments and cannot fill in B/C/D timings.
