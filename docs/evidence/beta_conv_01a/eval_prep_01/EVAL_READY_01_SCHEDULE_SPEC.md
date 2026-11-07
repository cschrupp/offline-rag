# EVAL-READY-01 — Held-Out Schedule Candidate

The schedule builder reads case IDs only from the private 120-case held-out
candidate. It does not copy request text, prior turns, labels, or scores into
the schedule. Its generated JSON is in the ignored `artifacts/` directory and
must remain private until the custody/freeze decision is resolved.

The builder produces two diagnostic orderings, but only the serialized order is
eligible for this evaluation candidate. The application router mode is fixed
when the canonical application starts, so request-by-request interleaving
would require repeated application restarts or a forbidden runtime override.
Neither is part of this package.

The selected schedule candidate is one serialized 720-attempt order:

1. `serialized`: legacy arm's complete matrix followed by planner arm's
   complete matrix.

The serialized run uses one canonical app process at a time: execute the full
legacy arm, stop that app, then start the same canonical app configured for
planner and execute the full planner arm. This requires one controlled restart
between arms, not one restart per request. Both arms use the same frozen
request order and each arm's first request is marked `cold_start`; subsequent
requests are `warm_interactive`.

The interleaved schedule remains available only as a diagnostic comparison in
the private builder output. It is not an executable alternative and must not
be selected under the current router-mode contract.

The selected order has three repetitions for every held-out case in each arm
and predeclares 359 pairs as warm in both arms. The first request of each arm
is marked cold. The remaining first-pair boundary is excluded from paired warm
latency; it remains in cold-start reporting. An exact seeded hash order is
recorded.

All 720 attempts remain sequential. The router configuration is verified from
the live runtime before each arm begins; the adapter rejects a case assigned
to the wrong arm. Only one canonical app/runtime and one model instance may be
active at a time. No second app, per-request router override, or production
router change is introduced.

### Temporal-drift assessment

The selected full-arm serialized order has a material limitation: all legacy
observations precede all planner observations. Because elapsed time and arm
are perfectly associated, changes in host load, temperature, power state, or
runtime state can appear as an arm latency difference. This weakens the
intended paired P50/P95 latency comparison. It does not by itself invalidate
operation-accuracy or safety counts, but those results still require the other
frozen-input and annotation gates.

Therefore the current `legacy`-then-`planner` schedule is not sufficient by
itself to support a planner latency-gate conclusion unless an independent
methodology reviewer explicitly accepts the stationarity assumption and its
limitations.

A practical candidate for review is **counterbalanced serialized
repetition-block order**: run one complete 120-case repetition in one arm, stop
that canonical app, start the other arm, then continue with the next repetition
in the opposite arm order. Across three repetitions this uses six sequential
single-arm app sessions and five controlled restarts, with never more than one
app or model instance active. The same deterministic case order is used within
each matched repetition. The first request of each session is tagged
`cold_start`; remaining requests are `warm_interactive`. With the current
120-case population and matching order, this yields six cold requests and 357
paired warm case/repetitions. This is a counterbalanced block proposal, not
request-level interleaving and not drift-controlled evidence; drift within a
120-request block and the unequal 2:1 order balance remain.

The alternative changes cold/warm accounting and is only a candidate for
independent methodology review. Do not execute either schedule until that
review, exact input freeze, and separate execution authorization. Whichever
schedule is selected, report the actual arm order and temporal limitation; do
not describe serialized evidence as interleaved or drift-controlled.

The candidate watchdogs/resource stop rules are listed in
`EVAL_READY_01_STATUS.md`; they are proposals, not frozen execution authority.
Every timeout, cancellation, API failure, or watchdog termination remains in
the schedule denominator. Expiry before complete durable coverage makes the
campaign incomplete and not evaluable.
