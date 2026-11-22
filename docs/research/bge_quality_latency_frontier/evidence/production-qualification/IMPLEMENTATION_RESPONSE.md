# Implementation response

The research revision is ready for independent review. The canonical report
preserves the four-arm Recipes results, the Rich small-pool negative result,
the timing outliers, and the two query-level BGE-15 regressions.

**BGE-30 sorted-eight is the lowest-scientific-risk candidate.** The plan
requires multi-query ranking and evidence parity, paired latency and CPU
measurements, and concurrent-load, failure, and cancellation checks before
a production decision.

**BGE-15 sorted-eight delivered the largest measured speedup.** It assembled
the Recipes context in a median 20.491 seconds versus 60.361 seconds for
consecutive BGE-30, and changed selected evidence. The held-out plan preserves
the preregistered margins and requires independent relevance and sufficiency
judgments and explicit query-level harm analysis. The population specification
is ready for review. Its roster, corpus permissions, and adjudicators remain
open.

The decision memorandum links separate deployment and rollback designs and
bounded authorizations for the next campaigns. Validation consists of
`git diff --check`, relative-link checks, and byte-for-byte verification
of the existing report prefix. This revision is documentation only.
Both qualification campaigns and production promotion remain pending.
