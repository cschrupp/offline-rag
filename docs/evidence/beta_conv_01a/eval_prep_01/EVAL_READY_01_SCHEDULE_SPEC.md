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

The serialized design has a known temporal-drift limitation: all legacy
observations precede all planner observations. The schedule fixes the arm
order, randomizes case order deterministically within each arm, and retains
the predeclared matched warm population. The final methodology review must
assess this limitation and freeze the order before held-out execution; results
must be reported as a sequential comparison, not as drift-controlled
interleaved evidence.

The candidate watchdogs/resource stop rules are listed in
`EVAL_READY_01_STATUS.md`; they are proposals, not frozen execution authority.
Every timeout, cancellation, API failure, or watchdog termination remains in
the schedule denominator. Expiry before complete durable coverage makes the
campaign incomplete and not evaluable.
