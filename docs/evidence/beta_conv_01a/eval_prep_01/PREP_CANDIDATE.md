# BETA-CONV-01A EVAL-PREP-01 — Candidate status

**Status:** Preparation candidate; not frozen, not independently accepted, and
not authorized for model evaluation.

## Candidate inputs

The deterministic builder produces 300 synthetic requests using the accepted
primary-stratum distribution:

| Primary stratum | Total | Development | Held out |
| --- | ---: | ---: | ---: |
| Factual/source-scoped questions | 50 | 30 | 20 |
| Contextual grounded follow-ups | 30 | 18 | 12 |
| Named prior-turn transforms | 40 | 24 | 16 |
| Current supplied-text transforms | 40 | 24 | 16 |
| Conversation summaries | 20 | 12 | 8 |
| Ambiguous/missing references | 30 | 18 | 12 |
| Mixed source/transform obligations | 30 | 18 | 12 |
| Unsupported options/operations | 25 | 15 | 10 |
| Prompt injection/adversarial wording | 35 | 21 | 14 |
| **Total** | **300** | **180** | **120** |

Family groups are assigned wholly to one split. The candidate contains 90
Spanish cases (54 development, 36 held out), at least 40 source-title/current
quoted-text examples, 30 selected-scope conflicts, and 30 missing-context
cases. Three small synthetic source fixtures provide deterministic local
retrieval content.

Only the 180-case development file is committed. The 120-case held-out file and
two split-blind annotation packets remain under the repository's ignored
`artifacts/beta_conv_01a_eval_prep_01/` directory. Their hashes are recorded in
`PREP_FREEZE_MANIFEST_CANDIDATE.json`. The packets contain no labels and hide
split/stratum/family metadata. They have not been assigned to annotators.

**Blindness limitation:** the candidate builder is committed and can
reconstruct the held-out requests. Therefore this candidate does not provide a
confidential blind holdout against someone inspecting the preparation branch.
Do not treat its held-out split as sealed or open it for model scoring. Before
Human freeze acceptance, independent review must either accept that this is a
process-frozen but source-visible set for this one evaluation, or require a
replacement held-out set authored and held by an independent custodian.

`historical_challenges_candidate.jsonl` contains 13 named prior failure/edge
families drawn from the accepted amendment and existing regressions. It still
requires independent mapping against all BETA-CONV-01 IR-001–IR-004 findings.
`new_safety_family_slots.jsonl` reserves 40 slots, including 15 Spanish slots;
the actual new family prompts must be authored by independent reviewers and
are intentionally absent.

## Scorer candidate

`scripts/beta_conv_01a_eval_scoring.py` accepts normalized evidence captured
from the canonical HTTP route and its persisted traces. It validates complete
case/arm/repeat coverage, retains failure attempts in denominators, and reports
case-level operation, target/options, completion, clarification, grounding,
scope, repeatability, call-count, and latency statistics. Proposed
nearest-rank P50/P95 and Wilson intervals are implementation defaults for
review, not frozen methodology. No scoring was run on planner output.

The HTTP execution harness and local-model checks are not run or qualified in
this preparation step, and no HTTP execution harness is included in this
candidate. Any later harness must reuse `create_app()` and the existing
`/conversation/turn` handler; it must not duplicate routing or orchestration.

The inspected preparation environment is not qualified for the planned model
evaluation: it is WSL2 on `PortableWork` with an Intel Core i9-10885H and
approximately 32 GiB host memory; NVML/GPU access is blocked in this
environment. The canonical `.venv` uses Python 3.14.5 with FastAPI 0.142.2,
Starlette 1.7.0, HTTPX 0.28.1, and AnyIO 4.15.1. The separate base interpreter
is Python 3.12.7. The accepted design's RTX 2080 Super Max-Q reference class,
exact evaluation host, and approved local generator identity have not been
verified. No model or endpoint was queried.

## Required before any holdout execution

- Two independent annotators complete separate packets; disagreement is
  adjudicated without seeing model output. No labels are currently present.
- Independent reviewers author at least 40 new safety families, including 15
  Spanish families, and confirm the historical challenge roster is complete.
- Independent review accepts the dataset, annotation rubric, scorer,
  percentiles, failure accounting, latency boundary, and evidence schema.
- Human accepts the exact data/scorer/threshold identities in the freeze
  manifest. Numeric thresholds remain as specified in the accepted design; no
  threshold change is proposed here.
- Record exact evaluation host and approved local model identity/configuration.
  The target class is the RTX 2080 Super Max-Q reference class; exact host and
  model revision/checksum are pending.
- Establish the bounded execution authority, process watchdog, offline
  compatibility checks, and isolated API process. Do not serve production
  inference concurrently.

## Explicit status

```yaml
preparation_code: CANDIDATE
request_roster: 300_GENERATED_AND_HASHED
development: 180_PUBLIC_CANDIDATE
held_out: 120_LOCAL_PRIVATE_CANDIDATE
independent_labels: NOT_DONE
new_independent_safety_families: 0_OF_40_AUTHORED
thresholds: COPIED_FROM_ACCEPTED_DESIGN; HUMAN_FREEZE_PENDING
environment_identity: INCOMPLETE
model_inference_or_benchmark: NOT_RUN
evaluation_execution_authority: NOT_GRANTED
planner_activation: NOT_AUTHORIZED
promotion: NOT_AUTHORIZED
```

## Preparation validation

The candidate builder and scoring primitives have eight focused synthetic
tests. They cover grouped split integrity, blank independent-label packets,
private held-out placement, missing-attempt rejection, failure-inclusive
latency, planner call/retry limits, transform target scoring, snapshot identity,
and supported-case plan validity. The tests do not execute the API, invoke a
model, or score planner output.

Current readiness remains blocked on independent authorship/review and
execution setup. In particular, the 40 new safety prompts are empty reviewer
slots, historical cases are not yet independently mapped for completeness,
and the committed builder makes the local held-out candidate reconstructible.
The current host has no available GPU telemetry and is not the accepted
reference evaluation environment.
