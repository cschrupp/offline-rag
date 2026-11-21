# Independent re-review handoff

Review this revision against `f2a1e145fb60a82581da559c36a939a8fdb6ca9f`.
The study is based on deployed source `9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`.
The original replay and local pilot execution commits are recorded in
[replay-commit.txt](evidence/study/replay-commit.txt) and
[pilot-commit.txt](evidence/study/pilot-commit.txt). Historical input SHA-256
values are pinned in [the digest manifest](data/historical-input-sha256.json).
The recorded observations identify the exact Gold cohort, corpus, chunk set,
9H-P retrieval runs, and corrected 14C run.

The [preregistered plan](RESEARCH_PLAN.md) asks whether batching reduces
forward time, smaller RRF input prefixes retain relevance, the value of a
cross-encoder varies by query, adaptive depth improves the tradeoff, and
ranking gains carry through to grounded answers. The completed evidence
supports the exploratory local batching and depth-replay comparisons and
a historical same-population 14C frontier. Adaptive policy and paired
answer evaluation remain open.

Use the commands in [reproducibility instructions](REPRODUCIBILITY.md)
to regenerate the seven figures, test failure paths without inference, and
replay the original artifacts to a scratch file for a byte-for-byte comparison.
Access to the hash-pinned historical judgments and rankings is needed for
full replay. No model access is needed to render the figures or run the tests.

Review the 3 improvements, 2 regressions and 11 ties shown in Figure 7 against
the 16 human-reviewed rows. The full-pool judged-positive count drops from
79 to 64 even as mean Recall@10 rises slightly. Check whether the report
keeps these endpoints distinct and communicates the exploratory nature of
the macro-average. Check whether the pilot rejects tolerated numerical
changes that flip rank and whether its synthetic workload is sufficiently
qualified in the caption and conclusion.

The exact incident passages and evidence-unit parity were outside the local
pilot. Reduced-depth timing on the same adjudicated population, a qualified
adaptive policy, and controlled grounded-answer comparisons remain pending.
This revision authorizes no production integration, configuration change,
deployment, VM experiment, merge or promotion.
