# Stage 2 local development failures and resolutions

These are failed implementation rehearsals, not qualification passes. Their
raw synthetic request/server journals and terminal records are retained under
[`local-rehearsal/development-failures/`](local-rehearsal/development-failures/)
with per-file SHA-256 manifests. The final passing 36-send rehearsal is
separate at [`local-rehearsal/51c14191c20a4084`](local-rehearsal/51c14191c20a4084).

| Attempt | Sends / settled | Observed first failure | Correction or disposition |
| --- | ---: | --- | --- |
| `0acf7bdc0f41493e` | 7 / 6 | Ambiguous overload classification | Required exact rejection reason and terminal/no-trace state. |
| `14598a7323ba43af` | 18 / 17 | Drain cancellation reason mismatch | Correlated cancellation signal with worker terminal reason. |
| `15b93bd43c8b4ac4` | 16 / 15 | Held-forward disconnect validation mismatch | Separated transport disconnect from worker return and persisted trace outcome. |
| `178df77018644d9b` | 17 / 16 | Cooperative deadline was not observed | Waited for the actual lifecycle checkpoint after releasing the held forward. |
| `199bb33cd2f142fa` | 16 / 15 | Held-forward disconnect validation mismatch | Same correction as above; kept incomplete run failed. |
| `1a88089f5bd44521` | 18 / 17 | Event-list variable initialization error | Reordered per-request event collection before its assertions. |
| `2d3c7dd18004414a` | 18 / 18 | Second-arm copy differed for mode-0600 files | Copied the synthetic seed as image UID/GID 10001 in a short-lived network-disabled container. |
| `333bd3fd9e44446c` | 14 / 13 | Global query capacity was confused with per-operation release | Required operation release after worker return while preserving a separately occupied global slot. |
| `4f2ba51eefee4bde` | 19 / 18 | Cold arm preparation hit a global two-second diagnostic deadline before query admission | Changed to the accepted 180-second global setting and a two-second override only for the explicit deadline lifecycle case. |
| `6a2855d95c9a47ca` | 18 / 17 | Event-list variable initialization error | Same correction as above; incomplete run remained failed. |
| `7b89a039b18446f7` | 36 / 35 | A prior-arm `resources_closed` event contaminated drain validation | Scoped resource-close evidence to the current session/monotonic interval; full schedule did not qualify. |
| `c3be721b8e1c41f0` | 3 / 2 | Query-slot release was not independently observed | Added explicit operation release and global-capacity evidence. |
| `c4cfc6ccf3af43e8` | 17 / 16 | Cooperative deadline was not observed | Same lifecycle checkpoint correction; incomplete run remained failed. |
| `d54ceb138d4f4369` | 18 / 17 | Stale drain-grace event matched across arms | Added monotonic lower bound to lifecycle-event correlation. |
| `f9ea74d771554665` | 36 / 35 | A prior-arm `resources_closed` event contaminated drain validation | Same arm-scoping correction; full schedule did not qualify. |

Every listed run failed closed and the watchdog reported restoration of the
disposable baseline with no session container remaining. Where the driver
stopped before the full schedule, no success classification was written.
The detailed records are synthetic diagnostics only and contain no private
workspace corpus content.
