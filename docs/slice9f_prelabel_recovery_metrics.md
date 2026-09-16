# Slice 9F — Prelabel recovery metrics (outside Silver run)

**Purpose:** Operational record of prelabel attempt 1 and the authorized
`--force` recovery attempt 2 for the authoritative 9F lineage. Kept outside
the Silver artifact. Not the final 9F pilot report; does not declare 9F complete.

**Authoritative run:** `authorrun_b28d88f64054491a837cb4a144cbe056`  
**chunk_set_id:** `chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2`

## Prelabel attempt 1 (pre-recovery)

| Field | Value |
|---|---|
| Targeted | 34 |
| Successful | 13 |
| Failed | 21 |
| Failure reason | `model_response_invalid`: 21 |
| Successful-case candidates | 1249 |
| Accounted successful-case requests | 2498 |
| Agreement (successful cases) | exact 1248; adjacent 1; polar 0 |
| Review priority (successful cases) | low 5; medium 8 |
| Failed cases | rolled back cleanly; no durable judgments/summaries |
| Diagnosed failure shape | bare JSON with `grade`+`rationale`; rationale length >500 |
| Corrective commit | `950eb7ae7d354c71d6b2d10f6774682b91f39401` |
| Post-fix diagnostic | 6/6 parse valid; rationale lengths 211–308 |

### Provenance notes

- Proposal-era `authorcfg_id`: `authorcfg_9396160feb17154a6cfdc8493788ba6175bd1694a981b72a9e77d30d616fbd8c`
- Prelabel `authorcfg_id`: `authorcfg_07c540e81c287d209ee54fc780fc6dbe62f58d6210a2c4272a6d4752aaa163b5`
- Prompt-body changes (commit `950eb7a`) do **not** change `authorcfg_id` under the current semantic hash (model/config/contracts only). Record as observability/provenance finding for the pilot report.
- Reported request count 2498 undercounted total model traffic: calls made before a case hit `model_response_invalid` were not included in `model_request_count`.

## Prelabel forced recovery attempt 2

| Field | Value |
|---|---|
| Exit | 0 |
| Duration | ~35145 s (~9.8 h) |
| Targeted / successful / failed | 34 / 34 / 0 |
| `model_response_invalid` | 0 |
| Model requests | 6318 (full 3159×2) |
| Complete durable prelabels | 34 |
| Cases with no durable prelabel | 0 |
| Candidates | 3159 (unchanged) |
| Agreement | exact 3147; adjacent 11; polar 1 |
| Review priority | low 13; medium 20; high 1 |
| Two passes on all complete cases | yes |
| `human_review` | unset for all 34 |
| Pool | 34/34 unchanged |
| `authoring_run_id` / `chunk_set_id` | unchanged |
| Prelabel `authorcfg_id` | `authorcfg_07c540e81c287d209ee54fc780fc6dbe62f58d6210a2c4272a6d4752aaa163b5` (unchanged) |
| Recovery commits | prompt fix `950eb7a`; progress/metrics `d746a66` |

Do not collapse attempt 1 and attempt 2 into one apparent run in the pilot report.
