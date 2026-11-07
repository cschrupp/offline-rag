# EVAL-READY-01 — Held-Out Schedule Candidate

The schedule builder reads case IDs only from the private 120-case held-out
candidate. It does not copy request text, prior turns, labels, or scores into
the schedule. Its generated JSON is in the ignored `artifacts/` directory and
must remain private until the custody/freeze decision is resolved.

The builder prepares two alternative 720-attempt orders:

1. `serialized`: legacy arm's complete matrix followed by planner arm's
   complete matrix.
2. `interleaved`: one matched case/repetition pair at a time, alternating
   which arm goes first.

Both orders have three repetitions for every held-out case in each arm and
predeclare 359 pairs as warm in both arms. The first request of each arm is
marked cold. The remaining first-pair boundary is excluded from paired warm
latency; it remains in cold-start reporting. An exact seeded hash order is
recorded. The alternatives are not cumulative: a later authority must choose
exactly one.

Calls remain sequential. Switching arm configuration in the current
application requires a separately controlled canonical app process for that
arm; there is no per-request router override. Execution planning must preserve
the accepted interleaved order without running inference concurrently or
creating a second conversation implementation. Whether this can be achieved
under the one-active-app restriction without repeated app startup is an open
technical qualification item. No shortcut or production router change is
authorized here.

The candidate watchdogs/resource stop rules are listed in
`EVAL_READY_01_STATUS.md`; they are proposals, not frozen execution authority.
Every timeout, cancellation, API failure, or watchdog termination remains in
the schedule denominator. Expiry before complete durable coverage makes the
campaign incomplete and not evaluable.
