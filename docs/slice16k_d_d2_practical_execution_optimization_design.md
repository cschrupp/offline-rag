# 16K-D D2 — Practical Execution Optimization (Design)

**Design authority:** `S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-AUTH-001` — AUTHORIZED  
**Exact parent:** `7be6a2b5c7ca7b521f0c642d6a024a1e421d6636`  
**Branch:** `implementation/16k-d-dense-cuda-profiling`  
**Status:** DESIGN ONLY / EXECUTION NOT AUTHORIZED  

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

No separate D1 acceptance-record commit is required; this design successor
records IR-002 ACCEPT.

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

## 5. Existing reference lane

Accepted reference lane:

**CUDA / native BF16 / batch 32 / SDPA**

No new BF16/batch-32 baseline run is required merely to create another control.

D2 may reuse sealed D0/D1 BF16 evidence as its reference distribution:

- D0 historical;
- D0 clean;
- D1-A1;
- D1-A2.

A new BF16/batch-32 run is permitted only if implementation review finds a
material software/runtime identity drift that makes the sealed comparison
inadmissible.

---

## 6. D2 experimental structure

D2 is staged and stop-conditional, not an exhaustive matrix.

Maximum intended campaign: **six** new full cold runs.  
Likely success path: **four**.

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

### 6.2 D2-C0 — CPU production baseline

After the initial two G1 runs, execute one complete CPU-only cold production-path
run:

**C0** — CPU / current model / current production batch policy

Requirements: CUDA unavailable/disabled to this process · same model/revision ·
same 1296-child workload · fresh process · fresh embeddings · fresh Qdrant ·
generated=1296 · reused=0.

**C0 SHALL NOT** be graded against the CUDA 10/12-minute proxy threshold.

Purpose: establish no-VRAM deployment behavior, total cold ingestion time, dense
encode share, throughput, peak process/system memory where measurable,
correctness, and which controllable CPU-path component deserves optimization.

Forbidden conclusion form: “Seneca is too slow on CPU.”

### 6.3 D2-G2 — CUDA FP16 / batch 16 — CONDITIONAL

Opened automatically only if G1 does not provide a satisfactory GPU deployment
candidate.

Change relative to G1: **batch 32 → batch 16**.  
Keep: CUDA / FP16 / SDPA / same model.

Runs: **G2-1**, **G2-2** (cold).

Justified only by practical memory-pressure / robustness — **not** a general
batch-size sweep. No batch 8/24/48/64/etc.

**G2 trigger** (any of):

- G1 clearly misses the existing GPU proxy target;
- one of the two G1 runs exceeds the 12-minute variance guard;
- G1 fails due to CUDA memory/resource behavior;
- FP16/b32 remains sufficiently close to GPU memory capacity that batch-16 is
  justified as a directly shippable robustness treatment.

A merely academically interesting difference does not justify G2.

### 6.4 GPU candidate confirmation

Screening uses two runs. Once either G1 or G2 appears to be the deployment
candidate, execute exactly one additional cold run of that lane: **Gx-3**.

The resulting three runs constitute the existing §9.4 confirmation set.

Final GPU candidate requirements:

- 3 valid cold runs;
- median wall ≤10 minutes;
- no run >12 minutes;
- generated=1296 / reused=0;
- correctness/parity gate satisfied.

If G1 succeeds, G2 is skipped.

**Normal success path:** `G1-1 → G1-2 → C0 → G1-3` (4 runs).  
**If G1 fails and G2 succeeds:** `G1-1 → G1-2 → C0 → G2-1 → G2-2 → G2-3` (6 runs).

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
runtime/software identity.

**GPU (safe):** peak CUDA allocated · peak CUDA reserved · total VRAM ·
terminal CUDA/OOM/resource error if any.

**CPU (safe):** peak process RSS · logical/physical CPU facts · effective
PyTorch thread configuration · process CPU time · system RAM facts.

**Prohibition:** D2 SHALL NOT enable D1’s per-batch CUDA-event synchronization
merely for curiosity. D1 established that diagnostic sync is attribution tooling,
not a production performance measurement.

---

## 9. Memory interpretation

`nvidia-smi` VRAM occupancy alone SHALL NOT be treated as proof of CPU spillover.

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
**STOP.** Do not silently promote it as an execution-only change.

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

**GPU**

- If FP16/b32 satisfies three-run 10/12-minute gate + parity → select FP16/b32;
  STOP GPU tuning.
- Else test FP16/b16. If that satisfies gate + parity → select FP16/b16; STOP.
- If neither → STOP D2 GPU execution. Do not launch a blind parameter sweep.
  Open a new design based on the observed bottleneck.

**CPU**

C0 always produces a valid deployment benchmark if correctness and resource
safety hold. Elapsed time is reported, not converted into a binary
“Seneca CPU pass/fail.” After C0 choose one of: no immediate CPU optimization ·
narrow PyTorch/runtime tuning design · model/runtime optimization design ·
other component optimization only if materially justified.

---

## 14. Development-time budget

Expected new full-corpus-proxy executions:

- best case: **4**
- maximum under this design: **6**

No discretionary “one more run.” No full combinatorial matrix. A treatment must
be capable of changing a shipping decision.

---

## 15. Evidence / provenance

Preserve: exact design parent · implementation/harness subject · clean tracked
preflight · workload identity · model/revision · runtime identity · execution
configuration · source hashes · run order · validity status · measured results.

Invalid attempts preserved. Replace only for objective invalidity (identity
mismatch, dirty tracked tree, wrong device/dtype/batch, workload mismatch,
harness/tool failure, process failure, incomplete evidence).

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

## 17. Explicitly OUT of this design AUTH

D2 harness implementation · D2 executions · FP16 calls · CPU benchmark
execution · production/default changes · model changes · D3+ · 16K-E/F/G · main.

---

## Next gate

Independent design IR of this document. Separate implementation/execution AUTH
required before any D2 run. Retrieval-parity probe must be frozen in that
execution AUTH before treatment execution.
