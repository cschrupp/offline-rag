# EVAL-READY-01 — Held-Out Schedule Candidate

The schedule builder reads case IDs only from the private 120-case held-out
candidate. It does not copy request text, prior turns, labels, or scores into
the schedule. Its generated JSON is in the ignored `artifacts/` directory and
must remain private until the custody/freeze decision is resolved.

The builder emits three unexecuted alternatives: full-arm serialization,
counterbalanced serialized repetition blocks, and request-level interleaving
for diagnostics. The fixed router mode is selected at canonical app startup, so
the request-level interleaved alternative would require per-request overrides
or substantially more application restarts. Neither is proposed for execution.

The **preferred methodology-review candidate** is counterbalanced serialized
repetition blocks. Each block runs one 120-case repetition in one arm, then the
canonical app is stopped and restarted in the other arm. The proposed sequence
is:

| Repetition | First session | Second session |
| --- | --- | --- |
| R1 | Legacy | Planner |
| R2 | Planner | Legacy |
| R3 | Legacy | Planner |

This is six sequential single-arm application sessions and five controlled
restarts, with no more than one canonical app or model instance active. Each
matched repetition uses the same deterministic case order in both arms. The
first request of every session is `cold_start`; the remaining 119 are
`warm_interactive`. The proposal therefore contains six cold observations and
357 matched warm case/repetitions. The exact seeded order is recorded.

Full-arm serialization remains in the output as the original baseline: all
three legacy repetitions followed by all three planner repetitions, with one
cold request per arm and 359 matched warm pairs. It is **not selected for the
latency gate** unless a methodology reviewer explicitly accepts the
stationarity assumption. Its fixed arm order perfectly associates arm with
elapsed time, so host load, temperature, power, or runtime drift can appear as
an arm latency difference.

Counterbalancing reduces but does not eliminate temporal confounding. Drift
within 120-request blocks and the unequal 2:1 arm-first order remain, and the
six session startups add overhead. The candidate is not drift-controlled. Its
cold/warm accounting differs from full-arm serialization and requires
independent methodology review before any freeze decision.

All 720 attempts remain sequential. The router configuration is verified
from the live runtime before each app session; the adapter rejects a case
assigned to the wrong arm. No second app, per-request router override, or
production router change is introduced. Schedule selection and scoring
population remain pending independent methodology review, exact input freeze,
and separate execution authority.

The candidate watchdogs/resource stop rules are listed in
`EVAL_READY_01_STATUS.md`; they are proposals, not frozen execution authority.
Every timeout, cancellation, API failure, or watchdog termination remains in
the schedule denominator. Expiry before complete durable coverage makes the
campaign incomplete and not evaluable.
