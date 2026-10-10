# Milestone 7 — Productization, Performance and Portfolio UI

Historical short title “Performance and UI” remains valid for Slice 14
authority context; Milestone 7 scope also includes Slice 15 product/API
packaging, Slice 16 portfolio UI, Slice 17 regression CI, and Slice 18
portfolio release packaging.

```text
MILESTONE 7: IN PROGRESS
M7 CLOSEOUT: NOT AUTHORIZED
M7 ENTRY AUTHORITY: dcc6b07c20f97472cf506c4665af1f88f00a886b

SLICE 14: COMPLETE / ACCEPTED
DESIGN AUTHORITY: 89a395ae4df7aff23c2da2c8c44fd6fe405459a6

14A: COMPLETE / ACCEPTED
  Authority: c087b8c1f038bd049809db2bf7e761ee0db93b58
14B: COMPLETE / ACCEPTED
  Authority: 97d38031b99029c2e9b3fd028eadc3a60efef6c0
14C SUITE FREEZE: LOCKED / ACCEPTED
  Authority: a662efc50d712bd6a986da05809dc864342139df
  perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba
  perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d
14C AUTHORITATIVE HARNESS REWORK: COMPLETE / ACCEPTED
  Authority: ec7383f1612c2ddf86ca595cb3f9f0d8b4fb432c
  F001 / F002 / F003: CLOSED
CORRECTED 14C AUTHORITATIVE RUN: COMPLETE / ACCEPTED
  perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca
  Evidence commit: 153376b28545017c6134f9858d330548a7d8c6c7
  Executing SHA: affbd1127b1afc677e31c132da1c000c6cf246b5

LEVEL-C INSTRUMENTATION: COMPLETE / ACCEPTED
  Authority: d25f5f85bd20aff18873dfd26fc8926da9a6dade
LEVEL-C SUITE/CONFIG FREEZE: LOCKED / ACCEPTED
  Authority: f3ff6de00d90ebae24639d1569ef0f91b25b3c65
  perfsuite_d9241ed2cad9473e399ae30d875729c8d2b1faf65580457fe2a872d75ca924b0
  perfcfg_a26a0fb336905dfa681c6cfe96721cf1fd446da64004336156f0336420025a25
  gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3
  ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876
LEVEL-C PREFLIGHT: COMPLETE / ACCEPTED
  Authority: 6327a9d018c252f339c342ddbc9e0c01fc998457
LEVEL-C AUTHORITATIVE RUNNER: COMPLETE / ACCEPTED
  Authority: 30b5abb627e16e50b2b848b44676b89b2372c3d6
LEVEL-C AUTHORITATIVE RUN: COMPLETE / ACCEPTED
  perfrun_211ebf1f9bcdef93d1f14421b754ef5ff387e2e091dc7f603f455dd083fdbf39
  Executing SHA: 30b5abb627e16e50b2b848b44676b89b2372c3d6

SLICE 14 CLOSEOUT: COMPLETE / ACCEPTED

SLICE 15: COMPLETE / ACCEPTED
15A–15H: COMPLETE / ACCEPTED
15H FF head: 1c1d94eada502523d44ec8e9c9a6e23b1f863d49
Evidence: docs/slice15h_integration_acceptance.md

SLICE 16: DESIGN INTERVIEW COMPLETE
           DESIGN AUTHORITY ACCEPTED / LOCKED
           AUTHORITY SHA e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
           IMPLEMENTATION PLAN ACCEPTED
           16A COMPLETE / ACCEPTED
           ACCEPTED SHA e73959be508541a1c50d4919606aaf3157a5fa8a
           Evidence: docs/slice16a_workspace_foundation.md
           16B COMPLETE / ACCEPTED
           ACCEPTED SHA eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
           Evidence: docs/slice16b_workspace_lifecycle_api.md
           16C COMPLETE / ACCEPTED
           ACCEPTED SHA 936e41446eb1e3697f6b7d245659831f19cf0613
           Evidence: docs/slice16c_react_shell_source_ui.md
           AMENDMENT A1 ACCEPTED / LOCKED
             5060e2aeb4825f265072a1f870c3c963eace3b30
           AMENDMENT A2 ACCEPTED / LOCKED / SEALED
             dce3456e519cb6c96570e20f5af800d00cafb5a7
             docs/slice16_amendment_a2_conversational_grounding.md
             A2 CLOSEOUT f0bdf78d0ae6a79737055d324b22fc35e1e501f5
           16D-A COMPLETE / ACCEPTED / SEALED
             4f8962f2893ab433e6ea269ad54e46f67771ca70
           LAST SEALED IMPLEMENTATION BASELINE
             a952a75bc07191b213a5113eee53cb967fef8326
           OBSERVED 16D-B1 CANDIDATE
             6b6524001f063a628505f572e7ca13d954a38260
             PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
           B1 FOUNDATION REMEDIATION ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION c68cc3f8f16a2588ba093886f3e48e1c7037f83f
             VERIFIED CLOSEOUT b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
             INDEPENDENT CLOSEOUT REVIEW PASSED
           LEGACY B1 PRODUCT UX
             PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
           16D-B2 COMPLETE / ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
             INDEPENDENT REVIEW PASSED
             HUMAN ACCEPTANCE ACCEPTED
             REWORK 1 COMPLETE
           16D-B3 COMPLETE / ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION 9c178ffb033cde41849379fc914f321697ff8691
             INDEPENDENT REVIEW PASSED
             HUMAN ACCEPTANCE ACCEPTED
             REWORK 1–3A COMPLETE
             A3 ACCEPTED / LOCKED / SEALED (da1082d95630c12eaf0ce1a3b8d005aaa60d2f73)
           16D-C COMPLETE / ACCEPTED / SEALED
           A4 ACCEPTED / LOCKED / SEALED
           16E COMPLETE / ACCEPTED / SEALED
             ACCEPTED ENGINEERING IMPLEMENTATION
               3e1ce4c94fc511abb4e1d94bd194736d5497e64f
             WORKSPACE SOURCE-LOADING REMEDIATION
               9dd2b008ebf9feee279dc6d0e58fafb006288ee5
             REMEDIATION EVIDENCE TIP
               9cd5528ab6c6e22d2dca55aca221b65eac50269e
             Evidence: docs/slice16e_engineering_evidence.md
             Remediation: docs/workspace_source_loading_remediation.md
           16F CLOSURE READY / TECHNICALLY ACCEPTED / NOT SEALED
             FINAL TIP f25f8358aead7fcfe161fff388012cec23b5a573
             CLOSEOUT CANDIDATE: docs/slice16f_closeout.md
           16G–16H NOT AUTHORIZED
           Slice 16 overall IN PROGRESS / NOT COMPLETE
  Authority: docs/slice16_design_authority.md
  Plan: docs/slice16_implementation_plan.md
  Historical pre-design frame: docs/slice16_portfolio_ui.md
SLICE 17: PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED
SLICE 18: PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED

PORTFOLIO_DEMO.md UPDATE: NOT AUTHORIZED
MILESTONE 7 CLOSEOUT: NOT AUTHORIZED
issue #1 image-size debt: DEFERRED
```

**Authoritative for:** Milestone 7 / Slice 14 performance & resource benchmark
design, accepted implementation authorities, corrected 14C quality-vs-cost
evidence, and accepted Level-C authoritative evidence recorded in this document.
**Not authoritative for:** publication-grade validation; portfolio demo
claims; Milestone 6 science; 13C/13D; recovery enablement; LangGraph; NeMo;
`config/base.yaml` mutation; Slice 15/16/17/18 design beyond status pointers
in this gate block; performance optimization or configuration promotion from
these results. Slice 15 architecture authority remains
`docs/slice15_developer_api_packaging.md`. Slice 16 design authority:
`docs/slice16_design_authority.md` (**ACCEPTED / LOCKED** at
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`). 16A accepted at
`e73959be508541a1c50d4919606aaf3157a5fa8a`; 16B accepted at
`eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`; 16C accepted at
`936e41446eb1e3697f6b7d245659831f19cf0613`; Amendment A1 **ACCEPTED / LOCKED**
at `5060e2aeb4825f265072a1f870c3c963eace3b30`
(`docs/slice16_amendment_a1_seneca_product_ux.md`); Amendment A2 **ACCEPTED /
LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7`
(`docs/slice16_amendment_a2_conversational_grounding.md`; closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`); **16D-A COMPLETE / ACCEPTED /
SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`; observed 16D-B1
candidate `6b652400…` has **PRODUCT ACCEPTANCE WITHHELD**; B1 foundation
remediation **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`); legacy B1 product UX remains
superseded / acceptance withheld; **16D-B2 COMPLETE / ACCEPTED / SEALED**
at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`; **16D-B3 COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691`;
A3 **ACCEPTED / LOCKED / SEALED**; **16D-C COMPLETE / ACCEPTED / SEALED**.
Historical pre-design frame: `docs/slice16_portfolio_ui.md`.

**Milestone 6 remains COMPLETE / ACCEPTED** at closeout
`dcc6b07c20f97472cf506c4665af1f88f00a886b`. Sealed 13B executable / Q1
`7baca2d0fd0d89b6358d04bd943c8c14ea6e742c` **UNCHANGED**. 13C remains
DEFERRED / OPEN / NOT REQUIRED FOR M6 / NOT AUTHORIZED. 13D remains
DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / NOT AUTHORIZED. Slice 14 closeout
does **not** reopen M6 science and does **not** complete Milestone 7.

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

**Historical note:** the original design-lock commit did not authorize 14B/14C. Those phases are now separately accepted (see status banner).

---

## 14. Slice 14 exit conditions

Slice 14 closeout required:

1. benchmark harness accepted;
2. frozen hybrid vs hybrid+reranker suite accepted;
3. at least one valid terminal benchmark run;
4. one defensible quality-vs-cost report;
5. Level C generation metrics including TTFT/total/tokens-sec where evaluable
   (TTFT / decode / tokens-sec remain UNEVALUABLE on the accepted non-streaming
   generator path; total generation latency and provider completion_tokens are
   recorded);
6. machine/resource provenance;
7. README-facing evidence prepared without arbitrary winner/SLO claims.

These conditions are now met. See §17–§19 for accepted terminal run IDs and
descriptive findings.

---

## 15. 14A implementation boundary (COMPLETE / ACCEPTED)

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

**Historical note:** 14A was not authorized by the design-lock commit; 14A is now **COMPLETE / ACCEPTED** at `c087b8c1f038bd049809db2bf7e761ee0db93b58`.

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

## 17. Corrected 14C authoritative quality-vs-cost evidence

Historical prior terminal runs remain immutable and are **not** the accepted
corrected quality-vs-cost result:

```text
perfrun_87771f72… — failed_during_execution / PRESERVED
perfrun_f5ed426a… — completed / AUDIT NOT ACCEPTED / PRESERVED
```

Accepted corrected 14C run:

```text
RUN: perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca
EVIDENCE COMMIT: 153376b28545017c6134f9858d330548a7d8c6c7
EXECUTING SHA: affbd1127b1afc677e31c132da1c000c6cf246b5
SUITE: perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba
CONFIG: perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d
```

Accepted population:

```text
44 cases
440 measured observations
88 warm-ups
0 failures
0 exclusions
```

Accepted descriptive latency (measured):

```text
overall:
  p50 = 6.4741 s
  p95 = 11.4928 s

hybrid total:
  p50 = 5.6171 s
  p95 = 8.3118 s

hybrid + reranker total:
  p50 = 7.4129 s
  p95 = 13.5332 s

rerank stage:
  p50 = 1.9140 s
  p95 = 4.4787 s

observed rerank maximum:
  62.455 s
  retained in evidence
```

Descriptive finding only: on the frozen development fixture, the hybrid +
reranker treatment had higher accepted retrieval-quality metrics than hybrid
alone while also adding latency. This does **not** declare the treatment
superior, does **not** say the latency is “worth it,” and does **not**
authorize promotion. The 22-case Gold population remains a
development/regression fixture, not publication-grade evidence.

---

## 18. Level-C authoritative end-to-end evidence

Authority chain:

```text
INSTRUMENTATION: d25f5f85bd20aff18873dfd26fc8926da9a6dade
SUITE/CONFIG FREEZE: f3ff6de00d90ebae24639d1569ef0f91b25b3c65
PREFLIGHT: 6327a9d018c252f339c342ddbc9e0c01fc998457
RUNNER: 30b5abb627e16e50b2b848b44676b89b2372c3d6

LOCKED:
  perfsuite_d9241ed2cad9473e399ae30d875729c8d2b1faf65580457fe2a872d75ca924b0
  perfcfg_a26a0fb336905dfa681c6cfe96721cf1fd446da64004336156f0336420025a25
  gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3
  ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876
```

Accepted Level-C run:

```text
RUN: perfrun_211ebf1f9bcdef93d1f14421b754ef5ff387e2e091dc7f603f455dd083fdbf39
EXECUTING SHA: 30b5abb627e16e50b2b848b44676b89b2372c3d6
STATUS: completed
EVIDENCE CLASS: AUTHORITATIVE
CASES: 5
WARM-UPS: 5
MEASURED: 25
TOTAL ATTEMPTS: 30
MACHINE: perfhost_9e010ef916cc1f6dd5211c069316abca938ec26bd11693f9402a88d805e71a65
GENERATOR: qwen3.6-35b-a3b
PIN CLASS: runtime_model_id
ENDPOINT (provenance only): http://192.168.2.140:8888/v1
```

No exact generator-weight digest is claimed. Endpoint is run provenance, not
scientific identity.

### 18.1 Measured stage timing

```text
END TO END
  n = 25
  valid = 25
  failure = 0
  excluded = 0
  not applicable = 0
  p50 = 50.829869060078636 s
  p95 = 144.58895409759128 s
  min = 26.95193731796462 s
  max = 319.35493657097686 s

GENERATION
  n = 25
  valid = 25
  failure = 0
  excluded = 0
  not applicable = 0
  p50 = 13.71354714804329 s
  p95 = 64.0607417835854 s
  min = 7.102435945998877 s
  max = 64.43286684306804 s

CONTEXT ASSEMBLY
  n = 25
  valid = 25
  failure = 0
  excluded = 0
  not applicable = 0
  p50 = 0.013580686994828284 s
  p95 = 0.024858880578540264 s

POST-GENERATION / CITATION-VALIDATION STAGE
  attempted = 25
  valid = 20
  failed = 5
  excluded = 0
  not applicable = 0
  p50 over valid samples = 0.00015273148892447352 s
  p95 over valid samples = 0.000679892918560654 s
```

Readable summary (exact values retained above): warm Level-C end-to-end
p50 ≈ 50.83 s and p95 ≈ 144.59 s; generation p95 ≈ 64.06 s. Observed
end-to-end variability is therefore not explained by the timed generation
stage alone. No root cause for the remaining latency is asserted here. The
benchmark does not define a latency SLO.

### 18.2 Terminal outcomes

Across all 30 attempts:

```text
answered = 24
generation_failed = 6
insufficient_evidence = 0
model_abstain = 0
citation_invalid = 0
orchestration_failed = 0
```

Measured only:

```text
answered = 20
generation_failed = 5
```

All six `generation_failed` attempts (including the warm-up) belong to
`draft_08f83eaef198495d92ff557eda974bf4`. Every one has:

```text
terminal_status = generation_failed
generation_failure_reason = response_parse_error
generator_invoked = true
generation stage = valid
citation/post-generation validation stage = failed
completion_tokens = 1200
```

These are **not** generator transport failures and are **not** failed
generation timing. Evidence-supported observation: one frozen query
consistently reached the configured 1,200-token output limit and then produced
a response parse failure in all six attempts. The pattern is consistent with
output truncation at the configured token ceiling; stronger causation is not
claimed. No max-token or configuration change is authorized by Slice 14
closeout.

**Deferred follow-up — generation output ceiling:** One frozen Level-C query
hit the configured `max_output_tokens=1200` on all six attempts and
subsequently produced `response_parse_error`. The pattern is strongly
consistent with response truncation before the structured output completed,
although the current benchmark does not retain sufficient raw provider
termination metadata to prove causation. Revisit in a separate post-Slice-14
investigation: inspect/persist `finish_reason` or equivalent provider metadata
and run a controlled comparison with a higher output-token ceiling. No
configuration change or rerun is authorized as part of Slice 14.

### 18.3 Generation telemetry limitations

```text
TTFT: UNEVALUABLE
decode duration: UNEVALUABLE
tokens/sec: UNEVALUABLE
reason: accepted generator path is non-streaming

output-token count: AVAILABLE on 30 / 30 attempts
source: provider usage.completion_tokens
```

Do not calculate tokens/sec from total generation latency. Do not retokenize
output.

### 18.4 Resource evidence

```text
RAM: available
RSS-before: 30 / 30 attempts
RAM peak: unavailable
observed RSS-before range: 583,819,264 bytes to 3,821,662,208 bytes
VRAM: unavailable
```

Do not infer zero VRAM usage. The measured process ran under Linux / WSL2,
Intel Core i9-10885H, 8 physical / 16 logical cores, ~33.5 GB reported system
RAM, Python 3.14.5.

---

## 19. Slice 14 closeout interpretation boundary

Slice 14 evidence is descriptive.

- The corrected 14C and Level-C runs completed under their frozen protocols.
- No latency SLO is defined.
- No winner, best configuration, or promotion candidate is declared.
- No performance optimization, generator max-token change, reranker config
  change, or `base.yaml` promotion is authorized by this closeout.
- Retrieval quality-vs-cost (14C) and end-to-end generation-path (Level-C)
  latency populations remain separate and must not be merged.

---

## Current gate

```text
SLICE 14: COMPLETE / ACCEPTED
14A / 14B / 14C freeze / 14C harness / corrected 14C run: ACCEPTED
LEVEL-C instrumentation / freeze / preflight / runner / run: ACCEPTED

SLICE 15: COMPLETE / ACCEPTED (15A–15H)
15H FF head: 1c1d94eada502523d44ec8e9c9a6e23b1f863d49

SLICE 16: DESIGN INTERVIEW COMPLETE
           DESIGN AUTHORITY ACCEPTED / LOCKED
           AUTHORITY SHA e2e7475076ad18d4c4ae8d939389ceeffdeff6d8
           IMPLEMENTATION PLAN ACCEPTED
           16A COMPLETE / ACCEPTED
           ACCEPTED SHA e73959be508541a1c50d4919606aaf3157a5fa8a
           16B COMPLETE / ACCEPTED
           ACCEPTED SHA eb8baefc6e3eaf7df33668c85fbbfef22364bb0e
           16C COMPLETE / ACCEPTED
           ACCEPTED SHA 936e41446eb1e3697f6b7d245659831f19cf0613
           AMENDMENT A1 ACCEPTED / LOCKED
             5060e2aeb4825f265072a1f870c3c963eace3b30
           AMENDMENT A2 ACCEPTED / LOCKED / SEALED
             dce3456e519cb6c96570e20f5af800d00cafb5a7
             docs/slice16_amendment_a2_conversational_grounding.md
             A2 CLOSEOUT f0bdf78d0ae6a79737055d324b22fc35e1e501f5
           16D-A COMPLETE / ACCEPTED / SEALED
             4f8962f2893ab433e6ea269ad54e46f67771ca70
           LAST SEALED IMPLEMENTATION BASELINE
             a952a75bc07191b213a5113eee53cb967fef8326
           OBSERVED 16D-B1 CANDIDATE
             6b6524001f063a628505f572e7ca13d954a38260
             PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
           B1 FOUNDATION REMEDIATION ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION c68cc3f8f16a2588ba093886f3e48e1c7037f83f
             VERIFIED CLOSEOUT b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
             INDEPENDENT CLOSEOUT REVIEW PASSED
           LEGACY B1 PRODUCT UX
             PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
           16D-B2 COMPLETE / ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
             INDEPENDENT REVIEW PASSED
             HUMAN ACCEPTANCE ACCEPTED
             REWORK 1 COMPLETE
           16D-B3 COMPLETE / ACCEPTED / SEALED
             ACCEPTED IMPLEMENTATION 9c178ffb033cde41849379fc914f321697ff8691
             INDEPENDENT REVIEW PASSED
             HUMAN ACCEPTANCE ACCEPTED
             REWORK 1–3A COMPLETE
             A3 ACCEPTED / LOCKED / SEALED (da1082d95630c12eaf0ce1a3b8d005aaa60d2f73)
           16D-C COMPLETE / ACCEPTED / SEALED
           16E COMPLETE / ACCEPTED / SEALED
             ACCEPTED ENGINEERING IMPLEMENTATION
               3e1ce4c94fc511abb4e1d94bd194736d5497e64f
             WORKSPACE SOURCE-LOADING REMEDIATION
               9dd2b008ebf9feee279dc6d0e58fafb006288ee5
             REMEDIATION EVIDENCE TIP
               9cd5528ab6c6e22d2dca55aca221b65eac50269e
             Evidence: docs/slice16e_engineering_evidence.md
             Remediation: docs/workspace_source_loading_remediation.md
           16F CLOSURE READY / TECHNICALLY ACCEPTED / NOT SEALED
             FINAL TIP f25f8358aead7fcfe161fff388012cec23b5a573
             CLOSEOUT CANDIDATE: docs/slice16f_closeout.md
           16G–16H NOT AUTHORIZED
           Slice 16 overall IN PROGRESS / NOT COMPLETE
SLICE 17: PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED
SLICE 18: PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED

MILESTONE 7: IN PROGRESS
PORTFOLIO_DEMO.md UPDATE: NOT AUTHORIZED
MILESTONE 7 CLOSEOUT: NOT AUTHORIZED
PERFORMANCE OPTIMIZATION: NOT AUTHORIZED
issue #1 image-size debt: DEFERRED
M6 science: UNCHANGED
13C / 13D / recovery / LangGraph / NeMo / base.yaml:
  NOT AUTHORIZED / UNCHANGED
```

**Next governance sequence:** **16D-B2** and **16D-B3** are
**COMPLETE / ACCEPTED / SEALED** (B3 at `9c178ffb033cde41849379fc914f321697ff8691`).
**16D-C** and Amendment **A4** are **COMPLETE / ACCEPTED / SEALED** at
`0381e0461f68c5fc09e7be2c7699d434e8b8a9cb` (closeout
`docs/slice16d_c_a4_closeout.md`). **16E** is **COMPLETE / ACCEPTED / SEALED**
(Engineering `3e1ce4c94fc511abb4e1d94bd194736d5497e64f`; Workspace
source-loading remediation `9dd2b008ebf9feee279dc6d0e58fafb006288ee5`; tip
`9cd5528ab6c6e22d2dca55aca221b65eac50269e`). **16F** is **CLOSURE READY /
TECHNICALLY ACCEPTED / NOT SEALED** at
`f25f8358aead7fcfe161fff388012cec23b5a573` (closeout candidate
`docs/slice16f_closeout.md`). → separate later-phase authorization
(**16G–16H**, Slice 17, Slice 18, M7 closeout). Slice 14 and Slice 15 are
closed.
Slice 16 design is **ACCEPTED / LOCKED**. Amendment A2 is **ACCEPTED / LOCKED /
SEALED**. **16A**, **16B**, **16C**, **16D-A**, and **16D-B2** are **COMPLETE /
ACCEPTED**. B1 foundation remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`). Legacy B1 product UX remains
**PRODUCT ACCEPTANCE WITHHELD**. **16D-B2** is **COMPLETE / ACCEPTED /
SEALED** at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`. **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691`
(A3 **ACCEPTED / LOCKED / SEALED**). **16G–16H**, Slice 17, Slice 18, and M7
closeout remain **NOT AUTHORIZED**. Slice 16 overall is **IN PROGRESS / NOT
COMPLETE**.
