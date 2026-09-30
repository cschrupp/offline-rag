# Milestone 7 — Performance and UI

```text
MILESTONE 7: IN PROGRESS
M7 ENTRY AUTHORITY: dcc6b07c20f97472cf506c4665af1f88f00a886b

SLICE 14: DESIGN LOCK CANDIDATE
SLICE 14 DESIGN BASELINE: dcc6b07c20f97472cf506c4665af1f88f00a886b

Intended post-audit state (not claimed by this commit):
  SLICE 14 DESIGN: LOCKED / ACCEPTED

Gate convention until independent audit:
  SLICE 14 DESIGN: CANDIDATE PENDING AUDIT

14A IMPLEMENTATION: NOT AUTHORIZED
14B: NOT AUTHORIZED
14C: NOT AUTHORIZED
```

**Authoritative for:** Milestone 7 / Slice 14 performance & resource benchmark
**design** (contracts, phasing, provenance, quality-vs-cost first comparison).
**Not authoritative for:** 14A/14B/14C implementation or execution; benchmark
results; Milestone 6 science; 13C/13D; recovery enablement; LangGraph; NeMo;
`config/base.yaml` mutation; FastAPI/UI packaging (later M7 slices).

**Milestone 6 remains COMPLETE / ACCEPTED** at closeout
`dcc6b07c20f97472cf506c4665af1f88f00a886b`. Sealed 13B executable / Q1
`7baca2d0fd0d89b6358d04bd943c8c14ea6e742c` **UNCHANGED**. 13C remains
DEFERRED / OPEN / NOT REQUIRED FOR M6 / NOT AUTHORIZED. 13D remains
DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / NOT AUTHORIZED. This design lock
does **not** reopen M6 science.

---

## 1. Slice 14 purpose

Slice 14 is an **observational benchmark layer** over the accepted OfflineRAG
system. It measures and serializes execution cost. It must **not** optimize or
change the system being measured.

```text
Slice 14 is a non-invasive, reproducible measurement harness for the
accepted OfflineRAG pipeline.

It may observe and serialize timing/resource data and combine those
observations with already accepted quality metrics.

It may NOT change pipeline semantics or optimize the system in response
to measured results within the same slice.

Optimization decisions require a later separate gate.
```

Instrumentation must not materially alter: batching; ordering; retrieval
results; model configuration; ranking; retries; context assembly; generation
semantics. Any required semantic change is an **ARCHITECTURE / DESIGN STOP**.

---

## 2. Three benchmark levels

| Level | Purpose | Examples | Notes |
|---|---|---|---|
| **A — Micro / stage** | Isolated component cost; bottleneck diagnostics | parse, chunk, embed, dense/lexical retrieve, fusion, rerank, context assembly | No end-to-end quality claim from these alone |
| **B — Pipeline** | Compare accepted pipeline variants on the same fixed population | dense; lexical; hybrid; hybrid+reranker; hybrid+reranker+context | Quality-vs-cost comparisons |
| **C — End-to-end user path** | User-perceived latency | query start → final answer / first token / abstention | Separately labeled |

The three levels remain separately labeled and separately interpretable.

---

## 3. Timing / statistical protocol

Every benchmark run records provenance **before** measurement:

- executing commit SHA;
- configuration identity/hash;
- corpus identity;
- query/dataset identity;
- machine profile;
- model identities;
- benchmark level;
- execution mode.

Warm-up and measured observations are separate.

Minimum measured observations:

- micro / pipeline: **≥ 10**;
- expensive end-to-end generation: **≥ 5**.

Higher counts are allowed.

Timing:

- monotonic high-resolution wall clock;
- `perf_counter`-style semantics;
- never wall-clock timestamps for duration computation.

Required statistics: `n`, `min`, `p50`, `p95`, `max`, failure count, warm-up
count. Percentile calculation uses a deterministic repository-owned
implementation with explicitly defined semantics.

Do not silently drop failures. Invalid instrumentation samples may be excluded
only with an explicit machine-readable exclusion reason. Do not combine latency
observations from different machines into one distribution.

For paired comparisons, execute baseline/treatment in paired or alternating
order (e.g. Q1 baseline, Q1 treatment, Q2 baseline, Q2 treatment, …) rather
than all-baseline then all-treatment.

---

## 4. Machine and resource profile

**Required machine profile:** OS and version; architecture; CPU model;
physical/logical core count; system RAM; Python version; OfflineRAG commit SHA.

**GPU when present:** GPU model; VRAM capacity; driver version; CUDA/runtime
version where applicable.

**Models:** embedding model identity/revision/path; reranker
identity/revision/path; generator model identifier; generator
runtime/provider; quantization identity where known.

**Execution:** execution device per stage where observable; benchmark config
identity; corpus identity; query-set identity.

**Resource telemetry:**

- RAM: process RSS before stage; peak process RSS where reliably measurable;
  descriptive delta/peak.
- VRAM: used/allocated before stage; peak/max observed; device identity.

Missing telemetry = `unavailable` or `unevaluable` — never infer zero. Missing
RAM/VRAM does **not** invalidate otherwise valid timing results.

**Not required in Slice 14:** GPU utilization %, temperature, power draw,
energy consumption.

Hardware profile is identity-bearing for a benchmark **RUN**, not for the
benchmark **CASE** definition.

---

## 5. Artifact model

```text
Benchmark Suite
  └── Benchmark Run
        ├── run_manifest.json
        ├── aggregate.json
        ├── cases/
        │     └── <case_id>.json
        └── report.md
```

```text
RAW OBSERVATIONS: AUTHORITATIVE
AGGREGATES: DETERMINISTIC DERIVATIONS
REPORT.MD: HUMAN-READABLE PRESENTATION ONLY
```

**Suite identity** defines WHAT is measured (contract/version; benchmark level;
case definitions; fixed population/query-set identity; pipeline variant
definitions; measurement protocol version). It **excludes** machine identity,
executing SHA, timestamp, measurements, observed timings/resources.

### 5.1 `run_manifest.json` — minimum normative fields

Every run manifest MUST include at least:

| Field | Role |
|---|---|
| `suite_id` | Frozen suite identity (`perfsuite_…`) |
| `executing_sha` | Exact OfflineRAG commit that executed the run |
| `machine_profile` / `machine_profile_id` | Captured machine profile or its `perfhost_` identity |
| `config_id` | Effective configuration identity (`perfcfg_…`) |
| `corpus_id` | Corpus identity used for the run |
| `model_ids` | Embedding / reranker / generator identities as applicable |
| `warmup_policy` | Declared warm-up policy |
| `repetition_counts` | Declared measured-repetition counts |
| `start_timestamp` | Run start timestamp (provenance; not used as duration clock) |
| `environment` / `runtime_versions` | Environment and runtime version provenance |
| `execution_mode` | Declared execution mode (e.g. cold/warm protocol context) |

Additional provenance fields are permitted; these minima are mandatory.

### 5.2 Case artifact — minimum normative fields

Every case artifact under `cases/<case_id>.json` MUST include at least:

| Field | Role |
|---|---|
| `case_id` | Case identity (`perfcase_…` or stable case id bound to suite) |
| `variant` | Pipeline / treatment variant under test |
| query / document / fixture identity | Subject identity for the case |
| warm-up observations or count | Separated warm-up record |
| measured observations | Raw measured timing/resource observations |
| failures | Preserved failure records |
| resource observations / samples | RAM/VRAM (or unavailable/unevaluable) samples |
| derived | Deterministic statistics: `n`, `min`, `p50`, `p95`, `max` |

Raw observations remain authoritative. Derived statistics are recomputable
from raw observations under the locked statistics semantics. `report.md` is
presentation only and is not an acceptance authority.

---

## 6. Benchmark populations

Two populations remain distinct:

1. **Performance fixtures** — stable timing/load generation; parsing /
   embedding / indexing throughput; stage timing. May be synthetic/
   deterministic. Do **not** establish retrieval quality.
2. **Quality-vs-cost population** — reuses existing accepted evaluation truth
   and relevance semantics.

**Forbidden:** new Gold labels merely for Slice 14; relabeling accepted truth;
assistant-generated truth promoted to authoritative evidence.

Portfolio-facing query populations must be frozen before observing the
performance results used for the claim. Diagnostic exploration is allowed;
post-hoc cherry-picking is not.

---

## 7. Immutable suite / run model

```text
eval/results/performance_14/
  <suite_id>/
    <run_id>/
      run_manifest.json
      aggregate.json
      cases/
      report.md
```

Run statuses: `completed` | `failed_preflight` | `failed_during_execution`.

Rules:

- completed runs are immutable;
- failed runs are preserved;
- reruns receive new run IDs;
- no completed run may be overwritten;
- public claims cite an exact terminal run ID;
- “latest” is not sufficient provenance.

Slice 14 is **NOT measure-once**. Reruns are legitimate because performance
depends on execution environment. There is no consumed/terminal authorization
concept for ordinary benchmark reruns.

---

## 8. Semantic timing boundaries

Timing uses semantic project-owned boundaries, not arbitrary function
boundaries. The stage **names and start→end envelopes below are normative**.
14A implementations that time different envelopes while claiming these stage
ids are non-conforming.

### 8.1 Ingest / index path

| Stage | Start → end |
|---|---|
| `document_load` | source accepted → content available to parser |
| `parse` | parser invocation → normalized parsed content blocks returned |
| `chunk` | parsed content → final chunks ready |
| `embed` | embedding batch submitted → vectors returned |
| `dense_index_write` | vectors/payload ready → persistent dense write complete |
| `lexical_index_write` | chunks ready → lexical write complete |

### 8.2 Query path

| Stage | Start → end |
|---|---|
| `dense_retrieve` | dense request issued → dense candidate set available |
| `lexical_retrieve` | lexical request issued → lexical candidate set available |
| `fusion` | dense + lexical candidate sets available → fused ranking complete |
| `rerank` | finalized reranker input → reranked candidates returned |
| `context_assembly` | final ranked candidates → GeneratorRequest evidence/context finalized |
| `generation` | generator request submitted → complete response |
| `citation_validation` | raw generation response → validated answer/citations |

### 8.3 End-to-end

| Stage | Start → end |
|---|---|
| `end_to_end` | CLI/service query entry → accepted terminal result |

Terminal result may include: answered; insufficient_evidence; model_abstain;
generation failure; or other accepted terminal status.

### 8.4 Generation sub-boundaries

| Metric | Definition |
|---|---|
| `generation_total` | request submitted → final response complete |
| `generation_ttft` | request submitted → first generated token |
| `generation_decode` | first token → final token |
| `tokens_per_second` | generated output tokens / decode duration |

Cold and warm populations are separate. Do not silently include model
downloads, provisioning, setup, or one-time initialization inside normal
steady-state query latency. Explicit cold-start measurements may exist
separately.

---

## 9. Throughput definitions

| Domain | Primary / notes |
|---|---|
| Parsing | pages/sec primary where meaningful; documents/sec; input MB/sec |
| Chunking | source characters/sec; chunks/sec |
| Embedding | chunks/sec primary; input tokens/sec only with exact deterministic token accounting; vectors/sec; record batch size, model, device, vector dimension |
| Dense indexing | vectors/sec; total build duration |
| Lexical indexing | chunks/documents/sec; total duration |
| Retrieval / reranking | per-query latency p50/p95 primary; sequential QPS diagnostic only |
| Generation | TTFT; total latency; output token count; exact output tokens/sec where available — do not substitute words/characters labeled as tokens |

**Not Slice 14:** concurrent QPS; saturation throughput; multi-user load
testing (after API/service boundary exists).

---

## 10. Fail-closed preflight

Before measurement, preflight must prove:

**Repository:** executing SHA resolved; working-tree state recorded; suite
definition valid; suite identity recomputes.

**Inputs:** corpus exists; required indexes exist; frozen case population
resolves; no duplicate case IDs; expected case count matches.

**Models:** embedding available; reranker when needed; generator when
generation is measured; configured identities match recorded identities.

**Configuration:** effective config resolves; config identity recorded;
compared variants differ only in the declared treatment.

**Environment:** machine profile captured; output destination writable; disk
availability sufficient; telemetry capabilities detected or explicitly
unavailable.

**Protocol:** Level A/B/C declared; cold/warm declared; valid warm-up count;
repetition count meets minimum.

**Paired-comparison invariant:** baseline and treatment match on corpus;
query population; Gold/evaluation truth; machine; executing SHA; model
identities except intentional treatment; every non-treatment configuration
field.

For **hybrid** vs **hybrid + reranker**, the authorized difference is
reranker enablement plus its necessary reranker configuration. If
comparability cannot be demonstrated, fail preflight.

---

## 11. No performance PASS/FAIL SLO

Slice 14 is **descriptive, not prescriptive**.

| Kind | Values |
|---|---|
| Run status | `completed`, `failed_preflight`, `failed_during_execution` |
| Case status | `completed`, `failed` |
| Observation status | `valid`, `failed`, `excluded_instrumentation_error` |

- `valid` — may enter statistics;
- `failed` — real execution error/timeout; preserve in failure counts; not a
  latency sample;
- `excluded_instrumentation_error` — invalid instrumentation; explicit
  exclusion reason required.

Report: `attempted_count`, `valid_count`, `failure_count`,
`instrumentation_exclusion_count`.

Do **not** invent SLOs (`p95 < 500 ms = PASS`, etc.). Do **not** produce
winner / promotion candidate / optimization decision. Quality-vs-cost results
are descriptive evidence.

---

## 12. First authoritative quality-vs-cost comparison

```text
BASELINE: hybrid retrieval
TREATMENT: hybrid + reranker
GENERATION: excluded
```

Reason: both paths already exist; treatment is narrow; existing IR metrics
can be reused; reranker cost is directly attributable; generation variance
does not contaminate the first comparison.

Reuse existing accepted retrieval evaluation semantics. Preferred metrics:
Recall@1/5/10, Precision@1/5/10, HitRate@1/5/10, MRR, nDCG@1/5/10.

Performance: hybrid latency; reranker latency; total retrieval-path latency;
p50; p95; min; max; RAM/VRAM when evaluable; failure counts.

Report separately: baseline quality, treatment quality, delta quality;
baseline latency/resources, treatment latency/resources, delta
latency/resources. No automatic judgment about whether the trade-off is
“worth it.”

---

## 13. Slice 14 phasing

```text
14A — BENCHMARK CONTRACTS + INSTRUMENTATION
14B — BENCHMARK RUNNER + DRY-RUN VALIDATION
HARD STOP / INDEPENDENT HARNESS AUDIT
14C — FROZEN HYBRID VS HYBRID+RERANKER QUALITY-vs-COST SUITE
SEPARATE BENCHMARK-RUN AUTHORIZATION
SLICE 14 CLOSEOUT
```

**14A:** contracts; identities; statistics; timing; resources; machine
profile; passive stage instrumentation; unit tests.

**14B:** Level A/B/C runners; preflight; artifact persistence; paired
ordering; failure/exclusion handling; diagnostic dry runs.

**14C:** freeze exact query IDs; Gold identity; corpus/index identities;
models; configs; top-k; warm-up count; repetition count; suite identity.

**No 14B or 14C work is authorized by this design-lock commit.**

---

## 14. Slice 14 exit conditions

Slice 14 may eventually close only after:

1. benchmark harness accepted;
2. frozen hybrid vs hybrid+reranker suite accepted;
3. at least one valid terminal benchmark run;
4. one defensible quality-vs-cost report;
5. Level C generation metrics including TTFT/total/tokens-sec where evaluable;
6. machine/resource provenance;
7. README-facing evidence prepared without arbitrary winner/SLO claims.

This docs-only design-lock task does **not** perform these steps.

---

## 15. Future 14A implementation boundary (NOT AUTHORIZED here)

Future ownership (when separately authorized):

```text
src/offline_rag/evaluation/performance_14/**
tests/unit/test_performance14_*.py
```

Likely modules may include: `__init__.py`, `contracts.py`, `identity.py`,
`statistics.py`, `timing.py`, `resources.py`, `machine.py`,
`instrumentation.py`. Exact filenames may later be consolidated.

Minimal existing production files may be modified in 14A only if necessary for
**passive** timing hooks. Such hooks must: default to disabled/no-op; preserve
inputs/outputs; preserve ordering; preserve exceptions; preserve
ranking/batching/retries; avoid benchmark-runner imports; avoid
persistence/network side effects.

**14A implementation is NOT authorized by this commit.**

---

## 16. v1 contracts and identities

**Contracts:**

- `performance-benchmark-suite-v1`
- `performance-benchmark-run-manifest-v1`
- `performance-benchmark-case-v1`
- `performance-benchmark-observation-v1`
- `performance-machine-profile-v1`
- `performance-resource-observation-v1`
- `performance-benchmark-aggregate-v1`

**Identity prefixes:** `perfsuite_`, `perfrun_`, `perfcase_`, `perfhost_`,
`perfcfg_` (SHA-256).

**Canonical hashing:** SHA-256; canonical UTF-8 JSON; sorted keys; stable
separators; no pretty-print dependence; no filesystem ordering dependence.

Identity-bearing artifacts are immutable. Any identity-bearing field change
creates a new identity.

`perfsuite_` includes: contract/version; benchmark level; frozen membership;
population identity; variants; measurement protocol version; timing boundary
version; statistics semantics version. Excludes: executing SHA; machine
identity; timestamp; results; observed performance.

`perfcase_` includes: case kind; benchmark level; stage/path;
query/document/fixture identity; variant; cold/warm classification. Excludes
observations.

`perfrun_` uniquely identifies a concrete execution and incorporates the
complete pre-measurement run manifest plus a run nonce/timestamp so legitimate
reruns do not collide.

---

## HARD STOP

```text
14A IMPLEMENTATION: NOT AUTHORIZED
14B: NOT AUTHORIZED
14C: NOT AUTHORIZED
benchmark execution: NOT AUTHORIZED
M6 science: UNCHANGED
13C / 13D / recovery / LangGraph / NeMo / base.yaml / 12C / 13B retry:
  NOT AUTHORIZED / UNCHANGED
```

**Next (not opened by this design-lock candidate):** independent Slice 14
design audit → only if accepted, separate authorization of **14A**
implementation.
