Completed **The 59-Second Retrieval**, an interim research report with six figures, reproducibility instructions, and the underlying measurements. The clean local branch is `research/bge-quality-latency-frontier` at `68b3708ccdf27b7644ae45819b01174a2413eadf`, based on deployed revision `9c92e706`.

[Full report](/tmp/seneca-research-59/docs/research/bge_quality_latency_frontier/REPORT.md) · [Figures](/tmp/seneca-research-59/docs/research/bge_quality_latency_frontier/figures) · [Reproducibility instructions](/tmp/seneca-research-59/docs/research/bge_quality_latency_frontier/REPRODUCE.md)

- **Candidate depth.** All 22 Slice 9H-P cases supported deterministic prefix replay. On the 16 human-reviewed cases, BGE-15 scored **0.8293 nDCG@10** and **0.7978 Recall@10**, versus **0.8283** and **0.7905** at depth 30. Depths 15 and 20 cleared the exploratory quality screen. Depths 5 and 10 missed it. Replay measured relevance only.
- **Length-aware batching.** Sorted batches of eight reduced local BGE forward wall time by a median **34.3%** across two paired blocks. Both passed the predefined logit tolerance and preserved all 30 ranks. The pilot used synthetic pairs matched to the incident’s token lengths. Actual incident evidence parity remains unverified.
- **Quality–latency frontier.** Accepted Slice 14C supports two same-population points: hybrid at **5.617 s / 0.791 nDCG@10** and hybrid plus BGE at **7.413 s / 0.842**. The new depth replay cannot add measured latency points to that frontier. The Recipes evidence also leaves ingredient coverage and the cause of `model_abstain` open.

**Next controlled experiment:** With separate authorization, compare consecutive `16+14` against sorted-eight batching on the exact incident inputs at fixed Torch `2/2`, using one warm-up per arm and three counterordered measured pairs. Require logit, rank, and packed-evidence parity before considering a production change.

All **24 focused tests** passed. The replay reproduced byte for byte, and lint, formatting, compilation, figure generation, and diff checks passed. Production and frozen evidence remained unchanged.
