# BETA-CONV-01A — Implementation result and verification handoff

**Implementation status:** COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
**Verification/evaluation:** PREPARATION HANDOFF; EXECUTION NOT AUTHORIZED
**Planner activation and implementation promotion:** NOT AUTHORIZED

## Accepted implementation subject

| Field | Value |
| --- | --- |
| Accepted implementation | `e243c4d34d8d784ea6b1b67ebfc8088fb129f988` |
| Prior candidate | `756348050136c108c8438437f4c42ea75b6e717b` |
| Independent review | BETA-CONV-01A Implementation IR-002 — ACCEPT |
| Human acceptance | ACCEPTED for `e243c4d34d8d784ea6b1b67ebfc8088fb129f988` |
| Branch | `implementation/beta-conv-01a-llm-task-planning` |
| Implementation base | `51fc93a8867f85417b6522632879e7c4c62c8e55` |
| Preserved implementation parent | `64b5883311338689f291f181e47686fc1a9e3906` |
| Main | Unchanged at `51fc93a8867f85417b6522632879e7c4c62c8e55` |

The implementation adds the accepted structured planner behind the default
`legacy` router mode, strict wire-plan and reference validation, sealed
grounded and transform execution paths, planner trace v3, bounded application
guidance, and UI history/export support. It preserves the selected workspace
source scope and admitted snapshot for grounded execution. It does not change
the accepted design, generation provider, or existing query executor.

IR-001 findings F001–F003 were corrected in `e243c4d`. In particular,
planner-output character counts saturate at the trace bound; exact current
message substrings are preserved after nonblank validation; and failed
source-reference validation is recorded as rejected and prevents retrieval.

## Implementation verification

The implementation agent reported these checks:

| Check | Result |
| --- | --- |
| Focused planner and existing conversation tests on corrected candidate | 99 passed |
| Targeted Ruff checks | PASS |
| `git diff --check` | PASS |
| Focused UI test file | 5 passed; unchanged by IR-001 corrective |
| Targeted ESLint on changed UI files | PASS; unchanged by IR-001 corrective |
| UI TypeScript project check | INCOMPLETE: five errors remain in `ui/src/test/slice16k_r04_cuda_oom.test.tsx` |
| Broader existing conversation regression selection | INCOMPLETE: prior run stalled and was interrupted |
| Independent reviewer test execution | NOT PERFORMED |
| Local-model smoke or model evaluation | NOT RUN |

These implementation-agent test results are reported results, not independent
test execution by the reviewer. The known conversation API/lifespan stall is
not counted as a pass and has not been repaired or waived. No evaluation
threshold or model result is claimed.

## Verification and evaluation handoff — prepared, not authorized

The next work is a separate bounded verification/evaluation tranche. This
section records its scope and gates; it grants no model-call or test-execution
authority.

### Required work before evaluation execution

1. Close or explicitly disposition the conversation API regression-coverage
   gap. The accepted design requires real handler/admission coverage for cited
   factual work, prior/current text transforms, selected-source re-grounding,
   safe clarification, history/export, and request validation before readiness.
   Preserve the prior `TestClient.__enter__` stall as incomplete evidence. Any
   fixture/startup repair beyond an isolated verification harness requires its
   own bounded authority.
2. Resolve the UI typecheck diagnostics in the unrelated CUDA OOM test fixture
   or document their exact impact on the verification gate. Do not change those
   fixtures silently as part of model evaluation.
3. Freeze the synthetic request set, split, independent labels, scorer, and
   hashes before any held-out run: 300 requests, grouped 180 development / 120
   held-out, plus the separately authored safety challenge families required
   by the accepted design. No private conversation, title, excerpt, or
   credential enters the committed evaluation set.
4. Record the exact host, approved local endpoint/model identity and available
   revision/checksum, serving configuration, environment and lockfile. An
   inaccessible model build identity remains an explicit reproducibility
   limitation.
5. Freeze latency accounting before holdout: request-to-complete-response
   boundary, percentile estimator, and treatment of errors, timeouts, invalid
   plans, cancelled and incomplete requests. Failed or slow attempts remain
   in denominators. Run the paired harness in an isolated process without
   production inference contention.
6. Exercise strict-offline adapter compatibility, structured-output
   incompatibility, timeout/cancellation and injected invalid-plan cases
   deterministically. Invalid plans must not invoke an executor or fall back
   to legacy. The API router must not acquire a shadow branch or second
   planner call.

### Proposed bounded evaluation matrix

Use the accepted design's sequential offline comparison only: legacy and
planner on the same frozen case, with no API shadowing. Development runs may
check instrumentation stability. Freeze all scorer, host, model, prompt and
threshold inputs before opening the held-out split. Run the held-out cases
three times per arm as specified by the accepted design; report case-level
rates and every per-repeat failure. The two-arm projection is 720 routing
observations for 120 held-out cases × 3 repeats × 2 arms, before development
and challenge sets. This is a workload estimate, not execution authority.

Carry forward the accepted gates without tuning against held-out results,
including zero observed critical grounding/scope violations, operation and
target accuracy, structured-plan validity, clarification precision, end-to-end
completion, repeatability, inference counts, paired P50/P95 latency bounds,
and resource telemetry. Report raw numerators and denominators and uncertainty
intervals. A finite zero-failure result is not a population-risk guarantee.

### Gate separation

```yaml
implementation:
  independent_review: IR-002_ACCEPT
  human_acceptance: ACCEPTED

api_verification_gap:
  status: OPEN

offline_model_evaluation:
  handoff: PREPARED
  execution_authority: NOT_GRANTED

planner_activation: NOT_AUTHORIZED
implementation_promotion: NOT_AUTHORIZED
```

The next Human decision is a separate bounded authorization for verification
and, if its prerequisites are satisfied, offline model evaluation. That
authorization must state whether the API test-gap work is included or must be
closed first. Planner activation and promotion remain separate decisions.
