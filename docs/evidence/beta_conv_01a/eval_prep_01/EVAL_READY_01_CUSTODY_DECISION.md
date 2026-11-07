# EVAL-READY-01 — Held-Out Custody Decision

**Decision:** Human accepts the existing source-visible 120-case held-out split
as a process-frozen evaluation set for this beta evaluation.

This is not a confidential or genuinely blind benchmark. The split is
reconstructible from the committed deterministic builder. The permitted
conclusion is limited to within-domain, source-visible beta qualification; it
must not be described as blind generalization.

Before any held-out model execution, the exact held-out case identities and
request hashes, independent labels and adjudications, scorer, thresholds,
planner configuration, schedule, and environment identities must be frozen.
The planner/prompt must not be tuned against held-out outcomes, and cases must
not be regenerated after observing failures. Independent annotation and the
independently authored safety challenge set remain mandatory. The zero-critical
safety-violation gate is unchanged. This decision does not authorize held-out
scoring, real-model execution, planner activation, or promotion.

If stronger external-validity evidence is needed later, prepare a genuinely
independent test set under a separate authority.
