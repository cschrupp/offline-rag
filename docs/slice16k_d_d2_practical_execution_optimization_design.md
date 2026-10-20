# 16K-D D2 — Practical Execution Optimization (Design)

**Design authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-AUTH-001` — AUTHORIZED  
**Exact original design parent:** `7be6a2b5c7ca7b521f0c642d6a024a1e421d6636`  

**Design IR-001:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-001` — REWORK REQUIRED (F001–F004) — preserved  
**Design rework authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework parent:** `80f4b09e0c85400d13c1f505a073cee6eab6f50b`  
**F001–F004:** CLOSED  

**Design IR-002:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-002` — REWORK REQUIRED (F005–F006) — preserved  
**Design rework-2 authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-REWORK2-AUTH-001` — AUTHORIZED  
**Exact rework-2 parent:** `5da766959fa3557f9300fa3a3147f0bb4f3bd853`  
**F005–F006:** CLOSED  

**Design IR-003:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-IR-003` — ACCEPT  
**Exact independently accepted design subject:** `8f96657d73b2213fb9b43557b001bc4c5a42188b`  

**Implementation authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact implementation parent:** `8f96657d73b2213fb9b43557b001bc4c5a42188b`  

**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Status:** D2 PRACTICAL EXECUTION OPTIMIZATION DESIGN COMPLETE / INDEPENDENTLY ACCEPTED  
**D2 execution:** NOT AUTHORIZED (implementation tranche only)

**Pivot:** 16K-D moves from a scientific optimization program to a bounded
product-engineering optimization program.

---

## 1. Accepted predecessor state (D1)

**D1 scientific IR-002:** `S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-002` — ACCEPT  

Accepted subjects:

| Subject | SHA |
|---------|-----|
| Execution harness | `177620a3440c310759775dbf303420b80df7a05c` |
| Sealed cell evidence | `4326586fe0ce3b7ca4c40ded743272d72ba53036` |
| Accepted analysis publication | `7be6a2b5c7ca7b521f0c642d6a024a1e421d6636` |

**D1 F001:** CLOSED  

**Historical IR-001:** `S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-001` — REWORK REQUIRED (F001 analysis) — preserved  

D1 established enough attribution for engineering decisions:

- full-run latency structure is reproducible;
- intrinsic batch content / simple shape is materially disfavored;
- host-only delay is materially disfavored as the primary cause;
- latency expansion is represented in GPU/device execution;
- no simple allocator / clock / thermal culprit was established;
- state/history-dependent GPU/model execution remains unresolved.

**D2 SHALL NOT** continue root-cause investigation unless a later product
decision specifically requires it.

No separate D1 acceptance-record commit is required; this design records IR-002 ACCEPT.

---

## 2. Product objective

D2 answers:

> Which controllable execution configuration gives Seneca the best practical
> ingestion performance on GPU-equipped machines while also establishing a
> truthful CPU-only deployment baseline, with the least additional engineering
> effort and without changing retrieval semantics unnecessarily?

The objective is **not** to scientifically explain every performance phenomenon.

Optimization hierarchy:

1. reduce cold ingestion wall time;
2. preserve correctness and retrieval behavior;
3. support machines without discrete GPU;
4. reduce memory pressure where useful;
5. minimize implementation and experimental effort;
6. avoid semantic/model changes unless execution-level controls are insufficient.

---

## 3. Governing principle

D2 SHALL experiment primarily with variables Seneca can actually control and ship:

- execution device;
- model execution precision;
- embedding batch size;
- supported PyTorch/runtime settings;
- later, if necessary, embedding model/runtime choice.

D2 SHALL NOT spend additional experimental budget explaining uncontrollable or
low-value environmental effects unless they block a shipping configuration.

A result such as “CPU is slow” is **not** an admissible D2 conclusion.

CPU measurements establish a deployment baseline and identify which controllable
part of the CPU path deserves optimization.

---

## 4. Frozen workload and semantic identity

All full cold D2 runs use:

| Field | Value |
|-------|-------|
| Workload | `D0-INCIDENT-1296-CHILD-V1` |
| Searchable children | 1296 |
| Generated / reused | 1296 / 0 |
| Chunk set | `chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d` |
| Corpus | `corpus_3c74b057074e928cccf7da048c06db0cf6df63bbe546ec14c071604949f160e3` |
| Chunk manifest SHA256 | `de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3` |
| Corpus manifest SHA256 | `69cefa61214e0e5e0a5eb71df01e323ede6f1807226181ef4134faeceb91b353` |
| Model | `Qwen/Qwen3-Embedding-0.6B` |
| Revision | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |

Unchanged: searchable-unit semantics · chunking semantics · strict offline behavior.

**Model replacement is NOT part of the initial D2 execution matrix.**

---

## 5. Reference evidence boundary (F003)

Accepted reference lane identity:

**CUDA / native BF16 / batch 32 / SDPA**

No new BF16/batch-32 baseline run is required merely to create another control.

### 5.1 Admissible uses of sealed evidence

| Evidence | Admissible for performance comparison (§9.4 / FP16 speedup / D2 pass-fail) | Admissible for context only |
|----------|-----------------------------------------------------------------------------|-----------------------------|
| Accepted **clean D0** BF16/b32 production-path baseline | **Yes — authoritative performance reference** | Yes |
| D0 historical | **No** | Yes — historical variability/context only |
| D1-A1 / D1-A2 | **No** | Yes — attribution/context only |

D1-A1/A2 synchronized diagnostic wall times **must not**:

- calculate FP16 speedup;
- act as production-performance controls;
- pass/fail D2;
- enter the §9.4 confirmation set.

A new BF16/batch-32 run is permitted only if implementation review finds a
material software/runtime identity drift that makes the sealed **clean D0**
performance comparison inadmissible.

---

## 6. D2 experimental structure

D2 is staged and stop-conditional, not an exhaustive matrix.

Campaign size (F005) — deterministic budgets, no discretionary eighth run:

| Path | Full cold runs |
|------|----------------|
| Normal success (G1 screen + confirmation + parity) | **4** |
| G1 early screen failure → G2 success | **6** |
| G1 confirmation timing/variance failure → G2 success | **7** absolute maximum |

Operator judgment phrases such as “clearly misses,” “appears to be the
deployment candidate,” or VRAM being “sufficiently close to capacity” are
**forbidden** as decision inputs. Decisions use §6.5 / §6.7 only.

### 6.1 D2-G1 — CUDA FP16 / batch 32

First treatment. Change only: **BF16 → explicit FP16**.

Keep: CUDA · batch 32 · SDPA · same Qwen model/revision · same embedding text ·
same workload · same indexing/materialization path.

Runs: **G1-1** (cold), **G1-2** (cold).

Each: fresh process · fresh isolated embeddings · fresh isolated Qdrant ·
generated=1296 · reused=0.

Purpose: engineering screen whether a controllable precision change substantially
improves the production ingestion path on the reference Turing GPU — not a
precision-mechanism study.

### 6.2 D2-C0 — CPU production baseline (F004)

After the initial two G1 runs (or after G1 terminates as a valid negative
resource failure — see §6.6), execute one complete CPU-only cold production-path
run:

**C0** — frozen baseline:

| Fact | Frozen value |
|------|----------------|
| Device | CPU · CUDA unavailable/disabled to this process |
| Model / revision | same Qwen as §4 |
| Batch size | **32** |
| Path | production embedding / indexing / materialization path |
| Tuning | **none** — no thread-count, precision, quantization, runtime, or batch-size optimization in C0 |

Also: same 1296-child workload · fresh process · fresh embeddings · fresh Qdrant ·
generated=1296 · reused=0.

**C0 SHALL NOT** be graded against the CUDA 10/12-minute proxy threshold.

If CPU dtype/backend are selected dynamically by current production code, C0
**observes rather than alters** them and **must record**:

- effective dtype;
- effective attention/backend where meaningful;
- batch size (must be 32);
- PyTorch intra-op threads;
- PyTorch inter-op threads;
- CPU identity / logical / physical count;
- process RSS / system RAM facts.

If implementation discovers an existing CPU-specific production default that
differs from this assumed baseline, it must **pin that fact before execution**,
not silently tune it.

Purpose: establish no-VRAM deployment behavior, total cold ingestion time, dense
encode share, throughput, peak process/system memory where measurable,
correctness, and which controllable CPU-path component deserves optimization.

Forbidden conclusion form: “Seneca is too slow on CPU.”

### 6.3 D2-G2 — CUDA FP16 / batch 16 — CONDITIONAL

Opened only under §6.5 / §6.6 / §6.7 when G2 is eligible. **Not** opened for
G1 parity/correctness failure attributable to FP16 (§6.7 / §10).

Change relative to G1: **batch 32 → batch 16**.  
Keep: CUDA / FP16 / SDPA / same model.

Runs: **G2-1**, **G2-2** (cold).

**Not** a general batch-size sweep. No batch 8/24/48/64/etc.

**High VRAM occupancy alone is not an automatic G2 trigger.** If FP16/b32 is
fast, stable, correct, and passes timing + parity, stop. Actual CUDA
OOM/resource failure under correct identity remains a legitimate G2 trigger
(§6.6). Batch-16 is **not** a retry for an FP16 semantic/parity failure.

### 6.4 GPU candidate confirmation (Gx-3)

When §6.5 says a lane remains mathematically eligible for confirmation, execute
exactly one additional cold run of that lane: **Gx-3**.

The resulting three runs constitute the existing §9.4 confirmation set.

**Timing/variance confirmation gate** (G1 or G2 after Gx-3):

- 3 valid cold runs (valid negative resource classification per §6.6 does not
  enter this gate as a success);
- median wall ≤10 minutes;
- no run >12 minutes;
- generated=1296 / reused=0.

**Correctness/parity gate** is separate (§10 / §6.7). Both must succeed to
select a GPU lane. Timing/variance failure and parity failure have different
G2 consequences (§6.7).

### 6.5 Deterministic two-run screening rule (F001)

Let wall times of the two screening runs be \(w_1, w_2\) in minutes.
Apply only after both runs are **valid** under §6.6 / §15 (not invalid harness
failures).

#### After G1-1 + G1-2

| Condition | Decision |
|-----------|----------|
| Either run \(> 12\) min | G1 cannot satisfy timing gate → do **C0**, then **G2** |
| Both runs \(> 10\) min | A third run cannot produce a 3-run median ≤10 → do **C0**, then **G2** |
| Both \(\le 12\) min **and** at least one \(\le 10\) min | G1 remains mathematically eligible → do **C0**, then **G1-3** |

Then evaluate G1 under §6.7 (timing/variance vs parity).

#### After G2-1 + G2-2

| Condition | Decision |
|-----------|----------|
| Either run \(> 12\) min | Do **not** run G2-3 → **STOP** GPU optimization under D2 |
| Both runs \(> 10\) min | Do **not** run G2-3 → **STOP** GPU optimization under D2 |
| Both \(\le 12\) min **and** at least one \(\le 10\) min | Run **G2-3**, then apply timing/variance gate + parity |

If G1 succeeds timing/variance **and** parity, G2 is skipped.

**Campaign paths (F005):**

| Outcome path | Sequence | Runs |
|--------------|----------|------|
| Normal success | `G1-1 → G1-2 → C0 → G1-3` | **4** |
| G1 early screen failure → G2 success | `G1-1 → G1-2 → C0 → G2-1 → G2-2 → G2-3` | **6** |
| G1 confirmation timing/variance failure → G2 success | `G1-1 → G1-2 → C0 → G1-3 → G2-1 → G2-2 → G2-3` | **7** absolute max |

No discretionary eighth run.

### 6.6 Resource failure vs invalidity (F002)

A CUDA OOM / resource exhaustion occurring under the **correct frozen**
workload, device, precision, batch size, and software identity is a
**VALID NEGATIVE TREATMENT RESULT**, not an invalid run.

Therefore:

- **G1** valid resource failure → **G2 eligible** (after C0 in campaign order);
- **G2** valid resource failure → **GPU optimization stops** under D2.

Only failures attributable to harness defect, wrong identity, dirty tracked tree,
external interruption, incomplete evidence, or other infrastructure/process
faults may be classified **invalid** and replaced under §15.

An undesirable configuration **must not** be rerun until it happens to survive.

### 6.7 Post-confirmation / G2 eligibility (F006)

After G1-3 (or earlier when G1 never reaches confirmation), classify the G1
outcome and apply exactly one transition:

| G1 outcome | G2 |
|------------|-----|
| Timing/variance failure (two-run screen fail, or three-run median/variance fail) | **May open** |
| Valid resource failure (§6.6) | **May open** |
| Parity/correctness failure attributable to FP16 | **NOT opened** — **STOP** GPU optimization under D2 |

Batch size 16 SHALL NOT be used as a retry for an FP16 semantic/parity failure
unless a later design explicitly establishes a reason to test that hypothesis.

After G2:

| G2 outcome | Disposition |
|------------|-------------|
| Timing/variance success + parity success | Select FP16/b16; STOP GPU tuning |
| Timing/variance failure (screen or confirmation) | **STOP** GPU optimization under D2 |
| Valid resource failure | **STOP** GPU optimization under D2 |
| Parity/correctness failure | **STOP** GPU optimization under D2 (terminal for D2) |

A GPU lane is selected only when both timing/variance confirmation (§6.4) and
parity/correctness (§10) succeed for that lane.

---

## 7. Explicitly NOT authorized under this design

- another D1 root-cause investigation;
- BF16 batch-size sweep;
- arbitrary batch-size sweep;
- attention-backend experimentation;
- CUDA cache eviction policy;
- production `empty_cache()` behavior;
- persistence optimization;
- Qdrant optimization;
- chunking / searchable-unit changes;
- embedding-model replacement (initial matrix);
- quantization / model conversion;
- ONNX / OpenVINO migration;
- HTTP-500 investigation;
- 16K-E/F/G;
- main promotion;
- D2 harness implementation / D2 executions (separate AUTH required).

If FP16 execution controls are insufficient, the next design SHALL choose
deliberately among: CPU/PyTorch optimization · model/runtime optimization ·
another narrowly justified GPU parameter. **No automatic D3 sweep.**

---

## 8. Measurement contract

D2 uses lighter instrumentation than D1. Timing must resemble the production
ingestion path closely enough to be operationally meaningful.

**Mandatory per full run:** wall-clock ingestion · dense generation/encode ·
persistence · point/materialization · Qdrant · generated/reused/failed ·
vectors materialized · chunks/sec · model-input tokens/sec where available
without expensive synchronization · device · dtype · batch size · attention
backend · model ID/revision · execution HEAD · workload hashes ·
runtime/software identity · validity classification
(`valid` / `valid_negative_resource` / `invalid`).

**GPU (safe):** peak CUDA allocated · peak CUDA reserved · total VRAM ·
terminal CUDA/OOM/resource error if any.

**CPU (safe) — required for C0:** peak process RSS · logical/physical CPU facts ·
effective PyTorch intra-op / inter-op threads · process CPU time · system RAM
facts · observed effective dtype / attention-backend where meaningful.

**Prohibition:** D2 SHALL NOT enable D1’s per-batch CUDA-event synchronization
merely for curiosity. D1 established that diagnostic sync is attribution tooling,
not a production performance measurement.

---

## 9. Memory interpretation

`nvidia-smi` VRAM occupancy alone SHALL NOT be treated as proof of CPU spillover
and SHALL NOT by itself open G2.

Record controllable memory facts (PyTorch peak allocated/reserved, device total,
process/system RAM where feasible). The engineering question is whether a
different shippable configuration reduces memory pressure and improves elapsed
ingestion — not establishing underlying CUDA/PyTorch memory mechanisms if the
configuration decision is clear.

---

## 10. Correctness and parity

Performance alone cannot promote an execution lane.

Before FP16 becomes a production/default candidate, D2 must establish:

1. indexing completes successfully;
2. child/vector counts remain correct;
3. embedding dimensionality remains correct;
4. no artifact/index corruption;
5. existing deterministic indexing/retrieval regressions remain green;
6. a frozen retrieval-parity probe is executed against BF16 reference and FP16
   candidate.

The exact retrieval-parity probe and acceptance criteria **MUST be frozen before
treatment execution** in the implementation/execution authority — not invented
after seeing FP16 results.

If FP16 materially changes retrieval behavior beyond the frozen parity boundary:
**STOP** GPU optimization under D2. Do not silently promote it as an
execution-only change. Do **not** open G2 as a retry (§6.7). Any G2
parity/correctness failure is likewise terminal for D2.

---

## 11. CPU optimization boundary

C0 is mandatory in D2. CPU tuning beyond C0 is **not** automatically authorized.

After C0, inspect component shares. If dense encoding dominates, next CPU
optimization design should prioritize controllable encode-path variables
(threading, CPU batch size, supported CPU precision/runtime; only later
alternative embedding runtime/model). If a non-encode component reaches
**≥10%** of total dense-phase wall time, it may justify optimization.

A slower CPU result is an input to **where** to optimize, not a rejection of CPU
support.

---

## 12. Model-change boundary

Model replacement is a **conditional escalation**, not part of the initial D2
matrix. Eligible only if execution-level CUDA controls fail to provide an
adequate GPU lane, or CPU measurements show the current model/runtime is the
dominant obstacle to practical CPU support.

Any model change requires its own design (identity, dimensionality/identity
treatment, retrieval-quality comparison, offline availability, memory/runtime,
migration/cache). Do not casually substitute a smaller model solely because it
benchmarks faster.

---

## 13. Decision rules

**GPU** — apply §6.5 / §6.6 / §6.7 only (no discretionary language).

- If G1 timing/variance confirmation + parity succeed → select FP16/b32;
  STOP GPU tuning.
- Else if G1 failed on timing/variance or valid resource only, and G2 opened
  and G2 timing/variance + parity succeed → select FP16/b16; STOP GPU tuning.
- Else if G1 (or G2) parity/correctness failure attributable to FP16 → STOP
  GPU optimization under D2 (G2 not opened from a G1 parity failure).
- Else → STOP D2 GPU execution. Do not launch a blind parameter sweep.
  Open a new design based on the observed bottleneck.

**CPU**

C0 always produces a valid deployment benchmark if correctness and resource
safety hold (and is not a GPU resource-failure case). Elapsed time is reported,
not converted into a binary “Seneca CPU pass/fail.” After C0 choose one of:
no immediate CPU optimization · narrow PyTorch/runtime tuning design ·
model/runtime optimization design · other component optimization only if
materially justified.

---

## 14. Development-time budget

Expected new full-corpus-proxy executions (F005):

- normal success: **4**
- G1 early screen failure → G2 success: **6**
- G1 confirmation timing/variance failure → G2 success: **7** absolute maximum

No discretionary eighth run. No full combinatorial matrix. A treatment must
be capable of changing a shipping decision.

---

## 15. Evidence / provenance / validity

Preserve: exact design parent · implementation/harness subject · clean tracked
preflight · workload identity · model/revision · runtime identity · execution
configuration · source hashes · run order · validity status · measured results.

### 15.1 Invalid (replaceable)

Classify **invalid** and preserve, then replace, only for objective
infrastructure/identity faults:

- identity mismatch;
- dirty tracked tree;
- wrong device / dtype / batch relative to the frozen cell;
- workload mismatch;
- harness/tool failure;
- external interruption / incomplete evidence;
- process failure **not** attributable to a correct-identity CUDA
  OOM/resource exhaustion under the frozen treatment.

### 15.2 Valid negative treatment (not replaceable as retry)

Correct-identity CUDA OOM/resource exhaustion → **valid negative treatment
result** (§6.6). Preserve; do not discretionary-rerun.

### 15.3 Valid scientific/engineering outcomes

Slow and fast results are both valid. No discretionary rerun.

---

## 16. Revised 16K-D sequence

Previous mechanical sequence
`D2 precision → D3 batch sweep → D4 attention → D5 persistence/Qdrant`
is **SUPERSEDED**.

Practical sequence:

```
D0 baseline → D1 attribution → D2 practical execution optimization → decision
```

Later work is evidence-triggered, not mechanically scheduled:

- CPU/PyTorch tuning;
- model/runtime optimization;
- another narrowly justified CUDA control;
- persistence/Qdrant only if materially significant.

Once a deployable candidate satisfies frozen GPU usability/correctness gates and
CPU fallback is characterized, **16K-D should close** rather than continue
optimizing for its own sake.

---

## 17. Explicitly OUT of this design AUTH / execution boundary

Historical design AUTH excluded harness implementation. That exclusion is
superseded by `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-IMPLEMENTATION-AUTH-001`
for implementation-only work.

Still OUT until a later execution AUTH: D2 scientific/benchmark cell execution ·
FP16 treatment calls · CPU benchmark execution · parity execution ·
production/default changes · model changes · D3+ · 16K-E/F/G · main.

---

## Next gate

Design IR-003 ACCEPT recorded. Implementation AUTH is open with execution still
closed. After implementation IR ACCEPT, freeze the retrieval-parity contract and
open execution AUTH before the first FP16 treatment call.
