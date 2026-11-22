# Production decision memorandum

**Decision today: retain consecutive BGE-30.** The workstream accepts
the completed experiments as isolated research evidence. The report
retains the original measurements, individual outliers, prior PyTorch
and ONNX negative results and scope limits. The new plans define the next
decisions and contain no production authorization.

| Candidate | Current evidence | Decision |
|---|---|---|
| BGE-30 sorted-eight | Exact rank and packed-evidence parity on the Recipes query, with 43.9% paired median assembler reduction in the four-arm run | Lowest scientific risk because it preserves depth. Qualify across length and pool-size strata and under load. A frozen conditional policy may be preferable if overhead erases gains on some shapes |
| BGE-15 sorted-eight | Fastest observed Recipes treatment, 20.491 s median assembly and 66.7% paired reduction. One of five anchors and evidence units changed vs BGE-30 | Strongest measured speedup. Independent held-out judgments, per-query harm and evidence-sufficiency gates, then compatible publication design are necessary |
| Smaller consecutive batches on Rich | Scientific parity, no candidate passed 20% wall screen | Keep existing grouping for this workload. The Rich treatment and shape differ from Recipes sorting |

The two depth-15 losses in the development cohort remain explicit:
Fire Safety −0.0676 and Construction Materials −0.0636 nDCG@10. The
Recipes timing has no labels and cannot supply a quality gate or a
production p95. A successful fixed-depth parity decision does not qualify
a depth change.

- [Fixed-depth coverage, parity, and load plan](EXECUTION_QUALIFICATION.md)
- [Held-out population, judging, and acceptance framework](HELD_OUT_QUALITY.md)
- [Separate deployment and rollback designs](DEPLOYMENT_DESIGNS.md)
- [Proposed exact execution authorizations](NEXT_AUTHORIZATIONS.md)

The immediate dependencies are a rights-cleared and family-split query
roster, a pinned CPU/Docker environment and capacity budget, and assigned
independent reviewers. No roster has been populated or scored in this
design tranche. Independent review should assess sampling coverage,
harm-bound power, cancellation behavior, and the separate deployment
authority before approving execution.
