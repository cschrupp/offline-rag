The exact-incident comparison completed all eight authorized calls and
passed both preregistered 20% wall-time thresholds. Median paired warm
reductions were 48.6% for BGE forward wall time, 46.8% for assembler wall
time, and 48.5% for BGE forward CPU-seconds. The maximum absolute logit
delta was 3.81e-6. All comparisons retained all 30 candidates, their
association and ordering, selected anchors, five evidence units and the
645-token packed context. End RSS was similar across arms. Shared-process
peak RSS cannot be attributed to either arm alone.

The report adds a chapter with all trials and compares them to the earlier
34.3% synthetic forward reduction. Those observations are kept separate
by host and workload. The interim chapter history and original evidence
remain intact. Python compilation, Bash syntax, exact summary reproduction,
Git diff checks and 42 focused tests passed.

The original service, health endpoints and publication state were
verified after restoration. There was no generation, production integration
or promotion. The result supports independent review for broader
qualification and does not establish concurrency, p95, or multi-query parity.
