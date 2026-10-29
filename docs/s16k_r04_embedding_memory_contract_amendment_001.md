# S16K-R04 Embedding-Memory Contract Amendment 001

## Authority and status

```yaml
authority: S16K-R04-EMBEDDING-MEMORY-M3-M4-TRIGGERS-DESIGN-AUTH-001
parent_design_subject: beecfd56fb5c085fabcca0131f0af7e67923836f
parent_human_acceptance_tip: e078c56c94eef63e00d4b347f057f89b71da7f0b
branch: design/16k-r04-embedding-memory-m3-m4-triggers-amendment
scope:
  M3_applicability: DEFINED
  M4_applicability: DEFINED
  M5_admission: DEFINED
implementation: NOT_AUTHORIZED
scientific_execution: NOT_AUTHORIZED
```

This amendment defines only the applicability and progression rules for M3,
M4, and M5. It does not change treatments, parity thresholds, candidate
qualification rules, workload identity, campaign budget, production behavior,
or CUDA execution authority. It is a design proposal pending independent
review and Human acceptance.

## A01 — Active precursor state

M3 and M4 applicability use the currently accepted experimental state, not
automatically the most recently executed treatment.

Define `ACTIVE_CONTROLS` cumulatively:

1. Start with M0 controls.
2. Apply M1 controls only when M1 is mechanism `SUPPORTED` and its candidate
   disposition is `QUALIFIED`.
3. Apply M2 controls only when M2 is mechanism `SUPPORTED` and its candidate
   disposition is `QUALIFIED`.
4. Apply an M3 or M4 treatment only when that treatment independently meets
   the same two conditions.

A rejected or inconclusive treatment does not become the baseline for a later
treatment. The evidence reducer/controller identifies the three-replicate
condition whose controls exactly equal `ACTIVE_CONTROLS`; applicability
metrics must come from that condition.

## A02 — M3 applicability

Open M3 when forward memory remains materially relevant after the preceding
accepted decisions, or valid OOM evidence shows that the forward phase remains
memory-constrained. This is an applicability decision only; it does not make
H-ATTN `SUPPORTED`.

For each successful replicate in the active three-replicate condition, define:

```text
P = peak PyTorch allocated bytes during the fixed-32 encode
B = PyTorch allocated bytes immediately before that encode
I = max(0, P - B)

P_med = median(P1, P2, P3)
M = max(256 MiB, 0.05 × P_med)
```

The encode-stage peak counters must be reset at the registered stage boundary;
`P` and `B` are measured in the same process and allocator domain.

### Successful-forward trigger

`M3_PROFILE` is applicable when all three active-state replicates complete the
fixed-32 forward and:

```text
median(I1, I2, I3) >= M
```

At least two of the three replicates must also individually satisfy `I >= M`.
This uses the existing 256 MiB / 5% materiality boundary as an applicability
proxy for the maximum forward working set available to an attention-only
reduction. It does not assert that an attention treatment will achieve that
reduction.

### Forward-OOM trigger

M3 is also applicable when at least two valid active-state replicates:

```text
complete model loading
reach the fixed-32 encode phase
terminate with a qualified CUDA OOM during that forward
```

The forward peak is right-censored in this case. The OOM establishes resource
applicability only; H-ATTN remains quantitatively `INCONCLUSIVE` unless its
existing complete target-phase comparison is satisfied.

### M3 treatment admission

M3_PROFILE remains one diagnostic cell. After profiling:

- If no supported non-baseline native SDPA backend is observed for the exact
  shapes, close M3 as `NOT_APPLICABLE / NO_ELIGIBLE_ALTERNATE`.
- Otherwise, test at most two eligible native backends in isolated conditions
  under the existing three-replicate rules.
- Profiler-run memory is not used for mechanism qualification.
- Do not install FlashAttention-2 or use an unsupported backend.

## A03 — M4 applicability

M4 is applicable only after cache, dtype, and any selected attention state are
correct, and when token-shape heterogeneity meets the following predeclared
applicability proxy. The proxy justifies testing token-budget batching; it is
not evidence that GPU memory will fall by the same fraction.

Using the exact frozen Qwen-token counts `t1 ... t32`, calculate:

```text
FIXED_PADDED = 32 × max(t)

PARTITIONED_PADDED =
    Σ(items_in_partition × max_tokens_in_partition)

SAVINGS_FRACTION =
    (FIXED_PADDED - PARTITIONED_PADDED) / FIXED_PADDED
```

Use the already frozen deterministic greedy M4 partitioner. M4 is applicable
only when all of the following hold:

```text
all three active-state runs have identical frozen token counts
the deterministic partitioner produces more than one partition
PARTITIONED_PADDED < FIXED_PADDED
SAVINGS_FRACTION >= 0.05
```

The 5% opening threshold is an experiment-applicability proxy aligned with the
existing fractional materiality boundary. It is not evidence of a GPU-memory
reduction. H-TOKEN is `SUPPORTED` only if actual M4 execution meets the existing
D12 memory-effect threshold, correctness, parity, and performance requirements.

If any individual sequence exceeds the frozen token budget, or the applicability
proxy is not met, M4 is `NOT_APPLICABLE`; no CUDA cell is consumed.

## A04 — M5 admission

M5 may open only after every applicable prior stage is resolved. Its selected
controls must equal cumulative `ACTIVE_CONTROLS` produced exclusively by
treatments whose dispositions are both:

```text
mechanism = SUPPORTED
candidate = QUALIFIED
```

M3 or M4 stages closed as `NOT_APPLICABLE` do not block M5. An applicable stage
that remains incomplete, invalid, or inconclusive blocks M5.

If no treatment changed `ACTIVE_CONTROLS` from M0, there is no production
candidate to confirm: M5 is `NOT_APPLICABLE / NO_QUALIFIED_TREATMENT`. M5 does
not run merely to repeat the baseline.

## A05 — Existing design remains frozen

This amendment does not change:

```text
M0/M1/M2 definitions
KV-cache hypothesis
direct-FP16 hypothesis
M3 treatment mechanics
M4 partition algorithm
D2 parity thresholds
256 MiB / 5% material-effect rule
10% performance bound
three-replicate requirements
right-censored OOM semantics
22 CUDA-cell cap
one optional CPU ONNX reference
four-hour campaign cap
no internal retry
no CPU fallback
no production implementation
```

## A06 — Implementation boundary

After this amendment is independently reviewed and Human-accepted, a separate
implementation corrective may:

- derive `ACTIVE_CONTROLS` from raw accepted evidence;
- identify the active three-replicate baseline condition;
- compute M3 incremental forward working set and applicability;
- compute M4 deterministic padded-token savings and applicability;
- enforce the M5 admission rule;
- incorporate the separate F008 safe CUDA-OOM classification correction.

No other harness redesign is authorized by this amendment. Implementation,
workload freeze, model loading, CUDA execution, CPU ONNX reference execution,
Well Logging retry, and promotion remain unauthorized.

## Review terminal

```yaml
S16K_R04_AMENDMENT_001:
  parent_design_subject: beecfd56fb5c085fabcca0131f0af7e67923836f
  human_acceptance_tip: e078c56c94eef63e00d4b347f057f89b71da7f0b
  M3_applicability: DEFINED
  M4_applicability: DEFINED
  M5_admission: DEFINED
  independent_review: PENDING
  human_acceptance: PENDING
  implementation: NOT_AUTHORIZED
  scientific_execution: NOT_AUTHORIZED
  promotion: NOT_AUTHORIZED

terminal: READY_FOR_INDEPENDENT_DESIGN_REVIEW
```
