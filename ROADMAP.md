# Roadmap

## Milestone 0 — Design complete

- [x] Product definition
- [x] Architecture decision log
- [x] Implementation slices
- [x] Project structure
- [x] Evaluation strategy
- [x] Security model
- [x] Demo strategy

## Milestone 1 — Measurable dense RAG baseline

- [x] Repository and domain contracts (Slice 0)
- [x] Docling ingestion (Slice 1)
- [x] Structure-aware chunks (Slice 2)
- [x] Local dense embeddings (Slice 3; Qwen3-Embedding-0.6B + FakeEmbedder for CI)
- [x] Qdrant persistence (Slice 3; Qdrant Local)
- [x] Dense retrieval benchmark (`offline-rag eval retrieve`)
- [x] Minimal local retrieve CLI (`offline-rag retrieve`; grounded `query` arrives in Milestone 3 / Slice 8)

**Release criterion:** reproducible Recall@k/MRR baseline on a small gold set.

**Status:** Slice 0–3 dense baseline done. See Milestone 2 for Slice 4+.

## Milestone 2 — Modern retrieval stack

- [x] BM25 / lexical baseline (Slice 4; project-owned inverted index + bm25-okapi-v1)
- [x] Hybrid retrieval / RRF fusion (Slice 5; query-time rrf-v1 over dense+lexical)
- [x] Cross-encoder reranking over fused pools (Slice 6; BGE bge-reranker-v2-m3 + FakeReranker)
- [x] Parent/neighbor context expansion (Slice 7; hybrid-rerank-context + ContextExpander)
- [ ] Ablation report (Dense → +BM25 → +RRF → +reranker → +expansion)

**Release criterion:** measured comparison of dense, BM25, hybrid, hybrid+reranker, and +context assembly.

**Status:** Slice 7 hybrid-rerank-context implemented. Ablation report deferred until Milestone 4 gold + Slice 9H comparisons.

## Milestone 3 — Grounded local QA

- [x] OpenAI-compatible generation client
- [x] Ollama-on-host default profile
- [x] strict-offline endpoint/model preflight
- [x] structured answer schema
- [x] citation provenance
- [x] citation validator
- [x] abstention path

**Release criterion:** grounded answer with resolvable source citations and explicit insufficient-evidence output.

**Status:** Slice 8 grounded generation implemented (`offline-rag query` / `eval query`).

### Validated end-to-end smoke profile

Slice 8 was validated end-to-end on the `ics_modules` corpus using the
following composed profile:

- Dense passage: `plain-v1`
- Dense query: `model-query-prompt-v1`
- Dense searchable units: `exclude-heading-only-v1`
- Lexical: `plain-v1`
- Fusion: `rrf-v1`
- Reranker: `plain-pair-v1`
- Context: Slice 7 baseline contract
- Generation prompt: `prompt-grounded-provenance-v2`
- Output: `grounded-answer-v1`
- Reasoning: `direct-output-v1`
- Recovery: `no-retry-v1`

Result: `PROVENANCE-PROMPT-MATERIAL`.

Identity-dependent Module 1 and Module 2 queries became grounded answers
when trusted document/section provenance was exposed to generation, while
self-contained answerability and genuine abstention behavior were preserved.
Retrieval/context inputs were identical across the generation A/B.

`model-query-prompt-v1`, `exclude-heading-only-v1`, and
`prompt-grounded-provenance-v2` are validated experimental candidates,
not defaults. Historical/base contracts remain unchanged pending broader
retrieval evidence under Milestone 4 gold (Slice 9H) and generation
semantics under Milestone 5 / Slice 10. `prompt-grounded-v1` remains the
generation control/default.

Reproduce the smoke profile by composing existing orthogonal overlays
(`base` + `dense_no_heading_peers` + `generation_provenance_prompt`); do
not treat that composition as a promoted default.

See [`docs/memory_query_heading_provenance.md`](docs/memory_query_heading_provenance.md)
for the detailed retrieval-heading, query-contract, and
generation-provenance investigation and A/B results.

### Slice 9 — Retrieval evaluation harness v1 (complete)

- [x] GoldDataset v1 (`offline-rag-gold-v1`)
- [x] deterministic retrieval metrics + eligibility rules
- [x] shared `offline-rag-retrieval-eval-result-v1` artifacts
- [x] `offline-rag eval compare` (`offline-rag-retrieval-eval-comparison-v1`)
- [x] category aggregates; method diagnostics retained

**Completed at:** commit `9073c37`. See [`docs/slice9_retrieval_evaluation.md`](docs/slice9_retrieval_evaluation.md), `eval/README.md`, and `EVALUATION_HARNESS.md`.

---

## Milestone 4 — Offline Gold Authoring & Retrieval Benchmarking

**Milestone 4 engineering checkpoint reached.**

Slice **9F** is **GO** and the non-promotional **9H-P** retrieval pilot is **COMPLETE**.
Slice **9G** production-gold expansion is **DEFERRED — PUBLICATION READINESS**,
when the target corpus is substantially complete and a redesigned
quiz/puzzle-style adjudication workflow is available.

**Cross-reference (not an authorization):** Slice 16 Gold Lab
([`docs/slice16_design_authority.md`](docs/slice16_design_authority.md)
S16-D23–S16-D34; plan
[`docs/slice16_implementation_plan.md`](docs/slice16_implementation_plan.md)
16F/16G) is the proposed redesigned adjudication surface for future 9G-style
human gold work. Slice **9G** remains **DEFERRED / NOT AUTHORIZED** and is
**not** resumed by Slice 16 design acceptance/lock.

Formal **9H** remains **FROZEN** behind future 9G.

The 22-case / human-16 9F benchmark remains a **development/regression fixture
only** (`gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`).

**Milestone 5 development checkpoint reached** (Slice 10A–10E). Milestone **6**
is **IN PROGRESS**; next gate is separate Slice **13B** authoritative
measure-once authorization (not authorized here).

Canonical **publication** order remains **9G → formal 9H** (not a near-term
engineering dependency).

**Canonical plan:** [`docs/milestone4_offline_gold_authoring.md`](docs/milestone4_offline_gold_authoring.md). Slice 9A notes: [`docs/slice9a_gold_authoring.md`](docs/slice9a_gold_authoring.md). Slice 9B notes: [`docs/slice9b_gold_propose.md`](docs/slice9b_gold_propose.md). Slice 9C notes: [`docs/slice9c_candidate_pooling.md`](docs/slice9c_candidate_pooling.md). Slice 9D notes: [`docs/slice9d_relevance_prelabel.md`](docs/slice9d_relevance_prelabel.md). Slice 9E notes: [`docs/slice9e_human_review.md`](docs/slice9e_human_review.md). Slice 9F ops: [`docs/slice9f_pilot_runbook.md`](docs/slice9f_pilot_runbook.md). 9H-P: [`docs/pilots/slice9h_p_pilot_contract.md`](docs/pilots/slice9h_p_pilot_contract.md) / [`docs/pilots/slice9h_p_results.md`](docs/pilots/slice9h_p_results.md).

### Objective

Build a practical, fully local workflow for constructing human-adjudicated
retrieval gold from private corpora, then use that gold with the Slice 9
harness for evidence-based retrieval comparisons and promotion decisions.

Privacy: private source text must not require cloud models or external
annotation services. The local LLM is an annotation assistant, not ground truth.

### Slices

- [x] **9A** Gold authoring contracts & privacy boundary (`localhost_only`, silver artifact, authoring generator config)
- [x] **9B** Deterministic source sampling & local question proposal (`offline-rag gold propose`)
- [x] **9C** Multi-retriever candidate pooling (`offline-rag gold pool`, `candidate-pooling-v1`)
- [x] **9D** Local blind double-pass relevance pre-labeling (`offline-rag gold prelabel`)
- [x] **9E** Local human review UI + GoldDataset v1 finalization (`gold review` / `gold finalize`) — **CLOSED / VERIFIED**
- [x] **9F** ~20-case `ics_modules` operational pilot — **GO** (22-case authoritative gold; report [`docs/pilots/slice9f_ics_modules.md`](docs/pilots/slice9f_ics_modules.md))
- [x] **9H-P** Pilot Retrieval A/B — **COMPLETE / NON-PROMOTIONAL** ([`docs/pilots/slice9h_p_results.md`](docs/pilots/slice9h_p_results.md))
- [ ] **9G** ~100–150 case production gold + development/held-out freeze — **DEFERRED / PUBLICATION READINESS**
- [ ] **9H** Formal retrieval A/B + promotion decision — **FROZEN** behind future 9G

### Target CLI (surface locked during 9A+)

```text
offline-rag gold propose | pool | prelabel | review | finalize | status
```

### Release criterion

A reviewer can refresh a private-corpus retrieval benchmark without sending
source text outside an approved local/private environment, then run
comparable retrieval evaluations and make an explicit promotion decision.

**Status:** Engineering checkpoint reached (9A–9F + 9H-P). Publication-quality
9G→9H remains deferred. Do not promote Arm H, `model-query-prompt-v1`, or
`prompt-grounded-provenance-v2` from pilot fixtures alone.

**9G deferral rationale:** Resume production-gold expansion only once the target
corpus is substantially complete and stable and publication-quality benchmarking
is approaching. Current corpus coverage is too partial to justify expert effort
for a 100–150 case production benchmark now. The candidate-by-candidate review
UI was operationally validated but is not the scale path.

**Future 9G requirement (not authorized now):** Redesign human adjudication
around quiz/puzzle-style evidence validation (e.g. best-passage, multi-select
support, none-of-the-above, direct vs supporting) while preserving explicit
human ground truth and provenance behind the scenes. Do not scale the current
candidate-by-candidate workflow for production gold. See the Slice 16 Gold Lab
cross-reference under the Milestone 4 engineering checkpoint above (not an
authorization of 9G).

---

## Milestone 5 — Generation and citation semantic evaluation

- [x] generation metrics (Slice 10)
- [x] citation semantic metrics (Slice 10)
- [x] evidence for or against promoting `prompt-grounded-provenance-v2`
- [ ] negative / abstention set expansion (as needed)
- [ ] optional local judge adapters (secondary; not required architecture)

**Release criterion:** generation and citation quality are measured separately
from retrieval, with deterministic checks preferred where applicable.

**Status:** Slice **10A–10E IMPLEMENTED / VERIFIED**. Milestone 5 **development
checkpoint complete**. Publication validation is **not** claimed; 9G / formal
9H remain deferred/frozen. `prompt-grounded-v1` remains the generation
control/default — provenance-v2 was **not** promoted.
Authoritative contract: [`docs/slice10_generation_semantic_evaluation.md`](docs/slice10_generation_semantic_evaluation.md).
Development A/B report: [`docs/pilots/slice10e_generation_prompt_ab.md`](docs/pilots/slice10e_generation_prompt_ab.md).

- [x] 10A — semantic evaluation contracts & fixed evidence (`GroundedGenerationExecutor`, `gold-evidence-v1`)
- [x] 10B — deterministic generation/citation metrics + CLI (`offline-rag eval generation`)
- [x] 10C — local semantic judge (`--judge`, independent `evaluation.generation_semantic_judge`)
- [x] 10D — human hard-negative abstention fixture (`human-grade0-hard-negative-v1`)
- [x] 10E — controlled prompt A/B + development report (`offline-rag eval generation-compare`)

Slice 10 may use the frozen 9F pilot GoldDataset
(`gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`)
as a **non-promotional development/regression fixture** for generation and
citation semantic evaluation (contracts, deterministic checks, citation support,
abstention, machinery validation). Primary mode is fixed `gold-evidence-v1`
(generation quality given supplied evidence), separated from retrieval quality.
Publication-grade claims and final promotion decisions remain deferred until
future **9G → formal 9H**. Results involving `prompt-grounded-provenance-v2`
on the 22-case fixture are development evidence only — not sole grounds for
promoting defaults.

**Next operational track:** Milestone **6** — Agentic recovery and security
(**IN PROGRESS**; see
[`docs/milestone6_agentic_recovery_security.md`](docs/milestone6_agentic_recovery_security.md)).
Next gate: separate Slice **13B** authoritative measure-once authorization
(not authorized here). Order: Slice **11** → **12** → **13**.


---

## Milestone 6 — Agentic recovery and security

**Status:** Milestone **6 COMPLETE / ACCEPTED** under revised disposition — Slice **11 COMPLETE / ACCEPTED**; Slice **12 COMPLETE / ACCEPTED** (recovery disabled; `insufficient_evidence_for_recovery_efficacy` retained); Slice **13 COMPLETE / ACCEPTED UNDER REVISED DISPOSITION** (**13A** / **13B** COMPLETE / ACCEPTED at `7baca2d` `completed` / `fail`; **13C** DEFERRED / OPEN / NOT REQUIRED FOR M6 / **NOT AUTHORIZED**; **13D** DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / **NOT AUTHORIZED**)
**Baseline:** `1983ff1376ea27fc1e8774b35136dc8c8ec93f40`
**Design authority:** [`docs/milestone6_agentic_recovery_security.md`](docs/milestone6_agentic_recovery_security.md)
**OD-12 design-lock baseline:** `4194d525211d994b97aa8abba93237cd8a23cbb9`
**12B docs closeout / 12C design authority baseline:** `692da961904e16a2a1bfa1ee1c2ece82a097df60`
**12C-1 accepted harness:** `c4f8734d57f45d3aa111997abf2bc8890322ff33`
**12C-2 authority baseline:** `47656d17b1e907f5965a60b0fe988a83942855ca`
**12C-2 accepted implementation:** `f213960bc494cd2180233345abf798f74313e8bd`
**12C-2 authoritative result:** `dc82432b7060c6adba189e96f8a053f76a6b2721`
**Slice 13 design-open / authority baseline:** `6a3806bdc89a17bcdf992dba068e843f8535de6a`
**Slice 13 design lock (accepted):** `571882e062359e258f5843b4289b2f556d22d7f7`
**Post-13B M6 status review authority baseline:** `0f14388e71cd0010d64d41c592c6df0aa308fd9c`
**13A accepted technical result:** `c2c1ff85c5383e224fc8767be1abbd5c435dd789`
**13B design-open baseline:** `1b87b90cad610ba40513d4ac0ca5e3239c2d7c3d`
**13B design authority:** `d3fc8616e5dfe474a53659bc3e276594d8eaa9c7`
**13B accepted harness:** `87b936789b2cf91e202be5ff4b818e3909460fd8`
**13B docs/provenance authority baseline:** `4efcda174d27f92f75cd3e04b96137d92a5c0ab5`
**13B sealed/executed executable SHA:** `7baca2d0fd0d89b6358d04bd943c8c14ea6e742c`
**13B Q1 seal:** `refs/offline-rag/authority/security_13b/q1` → `7baca2d0fd0d89b6358d04bd943c8c14ea6e742c`
**13B frozen campaign Git blob:** `7951ad964e7a91d5e89589acb4544fb99ca3079c`
**OD-13-4 amendment:** **LOCKED / AMENDED / ACCEPTED** (`efe7e1240974af27a1b8448215346abd094181a4`)
**M6 docs/status closeout:** this commit (`0f14388` → `efe7e12` → this SHA)

**Implementation order (locked):** Slice **11** → Slice **12** → Slice **13**

Do **not** interpret the checklist below as authorization to build LangGraph
before a formal evidence-sufficiency gate exists (ADR-008). Slice 12 closed
without justifying LangGraph; any future orchestration requires separate
authorization.

- [x] Slice 11 — Evidence sufficiency & abstention policy (11A→11B→11C) — **COMPLETE / ACCEPTED**
- [x] Slice 12 — Bounded conditional retrieval recovery — **COMPLETE / ACCEPTED**
- [x] Slice 13 — Prompt-injection & security harness — **COMPLETE / ACCEPTED UNDER REVISED DISPOSITION** (**13A** / **13B** COMPLETE / ACCEPTED; **13C** DEFERRED / OPEN / NOT REQUIRED FOR M6 / **NOT AUTHORIZED**; **13D** DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / **NOT AUTHORIZED**)

Checklist detail (same order; not startable out of sequence):

- [x] evidence sufficiency policy (Slice 11; deterministic first) — **ACCEPTED**
- [x] **12A** project-owned recovery state/protocol contracts, invariants, deterministic replay — **COMPLETE / ACCEPTED**
- [x] bounded query rewrite/retry (**12B**; explicit rewriter + one recovery retrieval) — **COMPLETE / ACCEPTED**
- [x] recovery vs baseline evaluation harness (**12C-1**) — **COMPLETE / ACCEPTED**
- [x] recovery vs baseline authoritative measurement (**12C-2**) — **COMPLETE / ACCEPTED**
- [ ] **Post-Slice-12 / Future Recovery Orchestration (LangGraph adapter)** — **NOT AUTHORIZED**
- [x] **13A** security fixture contracts + deterministic invariants — **COMPLETE / ACCEPTED** (`c2c1ff8`)
- [x] **13B** query-path adversarial campaign — design **LOCKED / ACCEPTED** (`d3fc861`); harness **COMPLETE / ACCEPTED** (`87b9367`); measure-once **COMPLETE / ACCEPTED** (executed at `7baca2d`; `completed` / `fail`); 13B **COMPLETE / ACCEPTED**
- [ ] **13C** recovery-path adversarial harness — **DEFERRED / OPEN / NOT REQUIRED FOR M6 / NOT AUTHORIZED**
- [ ] optional NeMo Guardrails evaluation (**13D**; OD-13-2 OPEN/deferred) — **DEFERRED / OPTIONAL / NOT REQUIRED FOR M6 / NOT AUTHORIZED**

**M6 HUMAN SMOKE — LOCAL / NON-AUTHORITATIVE (supplementary only):**
ICS Part A Q1–Q4 `answered`, Q5 `insufficient_evidence` / `model_abstain`;
security-13b dry_run `m6-human-demo` `completed` / `fail` via
`security_policy_immutable_v1` UNEVALUABLE (expected). Paths
`/tmp/m6-human-demo/…` and `eval/results/security_13b_dryrun/m6-human-demo/`
are local demo evidence only — not authoritative science and not committed.

**Next (historical M6 closeout):** Milestone **7** — Performance and UI.
M7 is now **IN PROGRESS** (see Milestone 7 section). This M6 closeout did
**not** authorize 13C, 13D, recovery, LangGraph, NeMo, `base.yaml` mutation,
a 12C rerun, or any measure-once retry.

**Slice 13A COMPLETE / ACCEPTED**
- Design authority: `571882e`
- Initial implementation: `7fe978a`
- Accepted rework / technical result: `c2c1ff8`
- Chain: `571882e` → `7fe978a` → `c2c1ff8`
- Package: `src/offline_rag/evaluation/security_13/`
- Fixtures: `eval/fixtures/security/` — 7 query-path + 1 recovery-boundary (13A unit matrix only)
- Mode: `harness_fake` / offline only
- Product recovery remains disabled; OD-13-2 OPEN/deferred; LangGraph / NeMo /
  12C rerun **NOT AUTHORIZED**; no `base.yaml` mutation

**Slice 13 design lock (accepted)**
- Authority baseline: `6a3806b` → design lock `571882e`
- **OD-13-1 LOCKED / ACCEPTED** — deterministic PASS/FAIL + nine-invariant `secinv_` registry
- **OD-13-2 OPEN / DEFERRED** — NeMo / 13D not authorized
- **OD-13-3 LOCKED / ACCEPTED** — `adversarial-fixture-v1`
- **OD-13-4 LOCKED / AMENDED / ACCEPTED** — phased 13A/13B/13C matrix retained;
  M6 deterministic security exit = 13B query-path; full 7×2 remains future
  13C scope only (**DEFERRED / OPEN / NOT REQUIRED FOR M6**); 13D
  **DEFERRED / OPTIONAL / NOT REQUIRED FOR M6**
- **OD-13-5 LOCKED** — harness-only recovery; 13A=`harness_fake` satisfied
- **OD-13-6 COMPLETE / ACCEPTED** — exact 13A boundary delivered at `c2c1ff8`

**Slice 13B COMPLETE / ACCEPTED**
- Design authority: `d3fc861` (corrected lock; supersedes `4fd327b`)
- Accepted harness technical result: `87b9367`
- Chain: `d3fc861` → `0d7b7f3` → `8111c68` → `1977e3f` → `87b9367`
- Docs/provenance authority baseline: `4efcda1`
- Sealed/executed executable SHA: `7baca2d`
  (not a result-artifact commit)
- Q1 seal: `refs/offline-rag/authority/security_13b/q1` → `7baca2d`
- Frozen:
  `seccamp_8034446afeef2cc3b417666bda1059f0fa530d3b458e05645418cc8742816351`
  /
  `secinv_454ef5d54e0e3ac0cd1f3e347f1172e5d2763d66514c0b13810467897767363a`
  / campaign Git blob `7951ad964e7a91d5e89589acb4544fb99ca3079c`
- **OD-13-7 … OD-13-13 LOCKED / ACCEPTED**
- Authoritative measure-once: **COMPLETE / ACCEPTED**
  - `run_status=completed`, `campaign_outcome=fail`
  - adversarial: pass=0 fail=7 (all 7 classes once;
    `security_policy_immutable_v1` UNEVALUABLE×7)
  - benign: pass=0 fail=5 violations=0 unevaluable=5 false_positives=0
  - decisive invariant: `security_policy_immutable_v1`
    (UNEVALUABLE → campaign fail under OD-13-1)
  - expected fail-closed scientific outcome; not an execution defect;
    not grounds for repair or rerun
- Authorization: **CONSUMED / TERMINAL**; retry **FORBIDDEN**
- Q3 / evidence archive: local/acceptance evidence (not committed to `main`);
  archive SHA-256
  `ba454ca226d4ea3d85babd6a4d4f9fa0f21759d7bc01f36d5da891194f169004`
- 13C / 13D / LangGraph / NeMo / product recovery / `base.yaml` / 12C rerun:
  **NOT AUTHORIZED**
- Recovery remains disabled

**Slice 11 accepted chain**
- **11A-1** `4f0cebc` · **11A-2** `cd0dd91` · **11A-3** `24b2179`
- **Path-B** `7ce47c5` — authoritative `suffctxrun_9c15bf6eee2e7b18317df7daa95328827be62bfa2d369b20272d7820c7fb32d4`
- **11B** `e18110f` — human-reviewed A=16 / B=0; **no additional gate promoted**
- **11C** `07b9b32` — runtime `sufficiency-v1` / gate `empty_context_v1` (user-facing `abstention_reason=empty_context`)
- Development fixture had **no human Population-B cases**; no extra threshold is a conservative evidence decision, not a claim that score-based sufficiency can never help.
- **OD-11-2 … OD-11-54 + OD-11-DESIGN-CLOSURE LOCKED**

**Slice 12A accepted chain**
- **OD-12 design lock** `4194d52` — OD-12-1 / OD-12-2 / OD-12-3 **LOCKED**
- **12A contracts** `941fdb3` → integrity corrections `60d0d48` → no-op prepare fix `1be7fc8` — **COMPLETE / ACCEPTED**
- Package: `src/offline_rag/recovery/` — project-owned RecoveryProtocol; no LangGraph dependency

**Slice 12B accepted chain**
- **12A docs closeout** `22a5fa2` — authority baseline for 12B
- **12B implementation** `554f742` → security/provenance hardening `f1f9c5f` — **COMPLETE / ACCEPTED**
- Explicit `retrieval_recovery.rewriter`; bounded rewrite + one recovery retrieval; default `enabled=false`; no LangGraph

**Slice 12 COMPLETE / ACCEPTED** (12A → 12B → 12C-1 → 12C-2)
- Authority: `47656d1`
- Harness: `c4f8734`
- 12C-2: `3d58ff3` → `f213960` → `dc82432`
- **12C-2 accepted scientific outcome:** `insufficient_evidence_for_recovery_efficacy`
  (`T_H=0`, `T_A=0`, `stopped_not_evaluable`).
- Recovery remains disabled by default. The result does not establish that recovery
  works or fails; the frozen population provided no recovery opportunities under
  `sufficiency-v1`. LangGraph was not required for, and was not part of, the
  accepted Slice 12 deliverable.
- Package: `src/offline_rag/evaluation/recovery_12c/` — prepare/evaluate/aggregate + measure-once
- Result root: `eval/results/recovery_12c/receval_41b472dcdfd65d05a6dce1ee6ea4cdfcd551264b54ea06027be556d83f06dc66/`
- No generation / LLM judge; no 12C-2 rerun authorized

**Frozen runtime policy:** `sufficiency-v1` — `empty_context_v1` iff final EvidenceUnit[] is empty; non-empty proceeds to generation; `model_abstain` remains post-generation and distinct. That is the deterministic trigger ADR-008 requires for Slice 12.

**Release / closeout criterion (satisfied under revised disposition):**
Slice 11 COMPLETE / ACCEPTED; Slice 12 COMPLETE / ACCEPTED with recovery
disabled and the not-evaluable efficacy disposition retained; Slice 13
COMPLETE / ACCEPTED UNDER REVISED DISPOSITION (authoritative query-path 13B
accepted; 13C/13D deferred and not required for M6).

This does not claim measured recovery benefit, full 7×2 coverage, or absolute
security.

Recovery remains disabled by default. LangGraph was not added and is
**Post-Slice-12 / NOT AUTHORIZED** unless a future evaluation separately
justifies conditional orchestration.

## Milestone 7 — Productization, Performance and Portfolio UI

**Status:** Milestone **7 IN PROGRESS** (closeout **NOT AUTHORIZED**)
**Scope clarification:** retained historical short title “Performance and UI”
still applies, but M7 also includes API/product packaging, portfolio UI,
regression CI, and portfolio release packaging (Slices 14–18).
**M7 entry authority:** `dcc6b07c20f97472cf506c4665af1f88f00a886b`
**Slice 14 design authority:** [`docs/milestone7_performance_ui.md`](docs/milestone7_performance_ui.md)
**Slice 14 design (LOCKED / ACCEPTED):** `89a395ae4df7aff23c2da2c8c44fd6fe405459a6`
**Slice 14:** **COMPLETE / ACCEPTED**

```text
POST-SLICE-15 ROADMAP

SLICE 15  COMPLETE / ACCEPTED
15H       COMPLETE / ACCEPTED
          at 1c1d94eada502523d44ec8e9c9a6e23b1f863d49
          evidence: docs/slice15h_integration_acceptance.md

16   DESIGN INTERVIEW COMPLETE
     Portfolio Demo UI
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
       docs/slice16_amendment_a1_seneca_product_ux.md
       Product: Seneca — Grounded knowledge workspace
     16D-A NOT AUTHORIZED
     16D-B NOT AUTHORIZED
     16D-C NOT AUTHORIZED
     16E–16H NOT AUTHORIZED
     Slice 16 overall IN PROGRESS / NOT COMPLETE
     Authority: docs/slice16_design_authority.md
     Plan: docs/slice16_implementation_plan.md
     Historical pre-design frame: docs/slice16_portfolio_ui.md

17   PLANNED
     Regression CI
     DESIGN NOT OPEN
     IMPLEMENTATION NOT AUTHORIZED

18   PLANNED
     Portfolio Release Package
     DESIGN NOT OPEN
     IMPLEMENTATION NOT AUTHORIZED

M7 CLOSEOUT  NOT AUTHORIZED
issue #1 (image size / CPU-CUDA variants)  DEFERRED
```

Canonical dependency chain (sequential until explicitly redesigned):

```text
14 — Performance evidence
      ↓
15 — Product/API/container boundary
      ↓
15H — Integration acceptance / Slice-15 closeout
      ↓
16 — Portfolio UI
      ↓
17 — Regression CI
      ↓
18 — Portfolio release
      ↓
M7 closeout
```

**Important:** **15H is not the UI phase.** 15H closes Slice 15 and validates
the API/container product boundary. Slice 16 design interview is **COMPLETE**;
design authority is **ACCEPTED / LOCKED** at
`e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`; **16A** is **COMPLETE / ACCEPTED**
at `e73959be508541a1c50d4919606aaf3157a5fa8a`; **16B** is **COMPLETE / ACCEPTED**
at `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`; **16C** is **COMPLETE / ACCEPTED**
at `936e41446eb1e3697f6b7d245659831f19cf0613`; Amendment A1 is **ACCEPTED /
LOCKED** (`docs/slice16_amendment_a1_seneca_product_ux.md` at
`5060e2aeb4825f265072a1f870c3c963eace3b30`; product **Seneca — Grounded
knowledge workspace**); **16D-A / 16D-B / 16D-C** remain **NOT AUTHORIZED**.
Slice 16 overall is **IN PROGRESS / NOT COMPLETE**.

**Slice 14 — Performance and resource benchmark harness**
- Design: **LOCKED / ACCEPTED** (`89a395ae4df7aff23c2da2c8c44fd6fe405459a6`)
- **14A** contracts + instrumentation: **COMPLETE / ACCEPTED** (`c087b8c1f038bd049809db2bf7e761ee0db93b58`)
- **14B** runner + dry-run validation: **COMPLETE / ACCEPTED** (`97d38031b99029c2e9b3fd028eadc3a60efef6c0`)
- **14C** suite freeze: **LOCKED / ACCEPTED** (`a662efc50d712bd6a986da05809dc864342139df`)
  - Frozen `perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba`
  - Frozen `perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d`
- **14C** authoritative harness rework: **COMPLETE / ACCEPTED** (`ec7383f1612c2ddf86ca595cb3f9f0d8b4fb432c`)
  - F001 / F002 / F003: **CLOSED**
- Prior terminal runs (immutable; not accepted as the corrected quality-vs-cost result):
  - `perfrun_87771f72…` — failed_during_execution / PRESERVED
  - `perfrun_f5ed426a…` — completed / AUDIT NOT ACCEPTED / PRESERVED
- **Corrected 14C authoritative run:** **COMPLETE / ACCEPTED**
  - `perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca`
  - Evidence commit `153376b28545017c6134f9858d330548a7d8c6c7`
  - Executing SHA `affbd1127b1afc677e31c132da1c000c6cf246b5`
- **Level-C** instrumentation: **COMPLETE / ACCEPTED** (`d25f5f85bd20aff18873dfd26fc8926da9a6dade`)
- **Level-C** suite/config freeze: **LOCKED / ACCEPTED** (`f3ff6de00d90ebae24639d1569ef0f91b25b3c65`)
  - `perfsuite_d9241ed2cad9473e399ae30d875729c8d2b1faf65580457fe2a872d75ca924b0`
  - `perfcfg_a26a0fb336905dfa681c6cfe96721cf1fd446da64004336156f0336420025a25`
  - `gencfg_d6b98a84f20887142dbb56a20e1b7533f6006304442efc017bb80a8fa2feb4d3`
  - `ctxcfg_b1742f41ecc03defbcf7c4e270fe22b4aa72db4a1af2c02a70d5560cd2ac8876`
- **Level-C** preflight: **COMPLETE / ACCEPTED** (`6327a9d018c252f339c342ddbc9e0c01fc998457`)
- **Level-C** authoritative runner: **COMPLETE / ACCEPTED** (`30b5abb627e16e50b2b848b44676b89b2372c3d6`)
- **Level-C** authoritative run: **COMPLETE / ACCEPTED**
  - `perfrun_211ebf1f9bcdef93d1f14421b754ef5ff387e2e091dc7f603f455dd083fdbf39`
  - Executing SHA `30b5abb627e16e50b2b848b44676b89b2372c3d6`
- Slice 14 closeout: **COMPLETE / ACCEPTED**
- Observational measurement only; no optimization / no pipeline semantic change in-slice
- First quality-vs-cost design: baseline **hybrid** vs treatment **hybrid + reranker** (generation excluded)
- Level-C is a separate end-to-end generation-path benchmark (do not merge latency populations with 14C)

Slice 14 checklist:

- [x] stage latency instrumentation (14A — **COMPLETE / ACCEPTED**)
- [x] memory/VRAM metrics where evaluable (14A — **COMPLETE / ACCEPTED**; VRAM may remain unavailable)
- [x] diagnostic dry-run runner (14B — **COMPLETE / ACCEPTED**)
- [x] frozen hybrid vs hybrid+reranker suite (14C freeze — **LOCKED / ACCEPTED**)
- [x] authoritative harness rework (quality + semantic path timing + measured RAM — **COMPLETE / ACCEPTED**)
- [x] corrected authoritative quality-vs-cost run (**COMPLETE / ACCEPTED**)
- [x] Level-C instrumentation / freeze / preflight / runner / authoritative run (**COMPLETE / ACCEPTED**)
- [x] Slice 14 closeout (**COMPLETE / ACCEPTED**)

**Slice 15 — Developer API and single-container packaging**
- Architecture (S15-D01 … S15-D22): **COMPLETE / LOCKED**
- Design authority: [`docs/slice15_developer_api_packaging.md`](docs/slice15_developer_api_packaging.md)
  - Authority SHA: `6583fb3be64f2c66e8655b8b99166c358f8f0844`
- Residual A (pre-implementation contract): **LOCKED / ACCEPTED**
- Implementation plan: [`docs/slice15_implementation_plan.md`](docs/slice15_implementation_plan.md) — **ACCEPTED**
- **15A** app foundation + errors + Residual A settings: **COMPLETE / ACCEPTED**
  - Landed on main via FF through `4a1c8dbcddc8408dd8b8b46dc0f18df56561d2f8`
- **15B** runtime lifecycle + `/health*` + doctor non-mutation: **COMPLETE / ACCEPTED**
  - Implementation commits `a009bd7d975b090d03d0b9b6b8d580dbfee6f796`, `00282d67f43edad7cb4094228c482bf8f361d578`
- **15C** snapshots + leases + `/v1/documents*`: **COMPLETE / ACCEPTED**
  - Implementation head: `5d70be09a3534a093bad9754f4051840ed1fde92`
  - Merge commit: `47a11f1968be75cf772fc7a9e4447ee26e283c52`
- **15D** product multipart ingest + publish: **COMPLETE / ACCEPTED**
  - Implementation commits: `39ac270b19be2e87a2dc0bb48668a1c249709042`,
    `88908acd09e644e0107050d5a5fec28ffe2db7bf`,
    `2ef21d26b9513fa7bc98ab1ad8de3645d17cebd7`
  - Fast-forward onto main at `2ef21d26b9513fa7bc98ab1ad8de3645d17cebd7`
- **15E** product query + durable traces: **COMPLETE / ACCEPTED**
  - Implementation commits: `2a84ef015932980bda8757146e63ed6d1c1ed0ae`,
    `63f5965adae3c2a1c5a5b338bcc1243f9423bb5a`
  - Fast-forward onto main at `63f5965adae3c2a1c5a5b338bcc1243f9423bb5a`
- **15F** admission + deadlines + cancel + drain: **COMPLETE / ACCEPTED**
  - Implementation commits: `850d04e9861e9563a6ea35ea02a51a97f17222b6`,
    `f907c849a597b016b76e3382ea2f8e986ad27a31`,
    `7bfb0893e1537af99bdaad6f6af5336408afe750`
  - Fast-forward onto main at `7bfb0893e1537af99bdaad6f6af5336408afe750`
- **15G** container packaging + Compose contract: **COMPLETE / ACCEPTED**
  - Implementation head: `140350b8cc6eec6a2491c0a1696042e65b2d2b7e`
  - Fast-forward onto main at `140350b8cc6eec6a2491c0a1696042e65b2d2b7e`
- **15H** integration acceptance / Slice 15 closeout: **COMPLETE / ACCEPTED**
  - Fast-forward onto main at `1c1d94eada502523d44ec8e9c9a6e23b1f863d49`
  - Evidence: [`docs/slice15h_integration_acceptance.md`](docs/slice15h_integration_acceptance.md)
  - Product CLI ingest/query use `offline_rag.app` (§11)
  - Readiness-503 with mounted models diagnosed as host `/models` permissions
    (UID `10001` readability); see `DEPLOYMENT.md`
  - Image-size debt remains deferred ([issue #1](https://github.com/cschrupp/offline-rag/issues/1))
  - Unrelated full-suite failures outside the 15H diff remain known repository
    debt (not claimed as a globally green suite)
- **Slice 15:** **COMPLETE / ACCEPTED**

**Slice 16 — Portfolio Demo UI:** **DESIGN AUTHORITY ACCEPTED / LOCKED**; **16A COMPLETE / ACCEPTED**; **16B COMPLETE / ACCEPTED**; **16C COMPLETE / ACCEPTED** at `936e41446eb1e3697f6b7d245659831f19cf0613`; **Amendment A1 ACCEPTED / LOCKED** at `5060e2aeb4825f265072a1f870c3c963eace3b30` (Seneca — Grounded knowledge workspace); **16D-A / 16D-B / 16D-C NOT AUTHORIZED**; Slice 16 overall **IN PROGRESS / NOT COMPLETE**
- Authority: [`docs/slice16_design_authority.md`](docs/slice16_design_authority.md)
  (S16-D01 … S16-D35; **ACCEPTED / LOCKED**)
- AUTHORITY SHA: `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`
- Amendment A1: [`docs/slice16_amendment_a1_seneca_product_ux.md`](docs/slice16_amendment_a1_seneca_product_ux.md)
  (**ACCEPTED / LOCKED** at `5060e2aeb4825f265072a1f870c3c963eace3b30`;
  supplemental design authority; does **not** authorize implementation)
- Implementation plan: [`docs/slice16_implementation_plan.md`](docs/slice16_implementation_plan.md)
  (16A–16H; plan **ACCEPTED**; **16A/16B/16C COMPLETE / ACCEPTED**; authoritative
  16D-A/B/C sequence under A1; **16D-A/B/C NOT AUTHORIZED**)
- **16A** workspace foundation: **COMPLETE / ACCEPTED** at
  `e73959be508541a1c50d4919606aaf3157a5fa8a`
  ([`docs/slice16a_workspace_foundation.md`](docs/slice16a_workspace_foundation.md))
- **16B** workspace lifecycle API: **COMPLETE / ACCEPTED** at
  `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`
  ([`docs/slice16b_workspace_lifecycle_api.md`](docs/slice16b_workspace_lifecycle_api.md))
- **16C** React shell / source-management UI: **COMPLETE / ACCEPTED** at
  `936e41446eb1e3697f6b7d245659831f19cf0613`
  ([`docs/slice16c_react_shell_source_ui.md`](docs/slice16c_react_shell_source_ui.md))
- Historical pre-design frame: [`docs/slice16_portfolio_ui.md`](docs/slice16_portfolio_ui.md)
  (contextual only)
- UI remains an adapter/client of `src/offline_rag/app/` (no direct Qdrant /
  retriever / generator access; no UI-owned RAG pipeline) — S16-D03
- Product query remains single-turn `grounded_v1`; conversational memory deferred
  — S16-D17
- Evaluation surfaces are read-only presentation of accepted artifacts; no live
  scientific knobs — S16-D20 / S16-D21
- Gold Lab redesigns adjudication workflow granularity while preserving
  GoldDataset v1 / Silver→Gold truth criteria — S16-D23–S16-D34
- Do **not** start 16D-A / 16D-B / 16D-C without separate explicit implementation
  authorization
- Product: **Seneca — Grounded knowledge workspace**

**Slice 17 — Regression CI:** **PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED**
- Objective: prevent accepted product/retrieval/generation contracts and
  measured quality from silently regressing after the portfolio surface exists
- Candidate areas only (not locked / no thresholds defined here):
  deterministic unit/regression tests; CI-safe retrieval subset; citation-
  contract checks; API contract checks; security deterministic checks where
  appropriate; container build/smoke where feasible
- Do **not** invent SLOs or convert historical performance runs into gates here

**Slice 18 — Portfolio Release Package:** **PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED**
- Objective: reproducible public portfolio artifact backed by accepted evidence
- Candidate deliverables only (not locked): polished README; architecture
  diagram; public demo workflow; sample corpus instructions; benchmark
  methodology/results; ablation evidence; limitations; hardware/runtime
  profiles; demo media; reproducible install/run path; interview talking points
- Claims remain conservative; deferred scientific/publication-grade promotions
  stay unauthorized

Later M7 checklist:

- [x] FastAPI substrate + process lifecycle + `/health*` (15A/15B — **COMPLETE / ACCEPTED**)
- [x] doctor non-mutation / startup-owned `/data` creation (15B — **COMPLETE / ACCEPTED**)
- [x] product publication registry + leases + `/v1/documents*` (15C — **COMPLETE / ACCEPTED**)
- [x] product `/v1/ingest` full-replace publish (15D — **COMPLETE / ACCEPTED**)
- [x] product `/v1/{query,trace}` (15E — **COMPLETE / ACCEPTED**)
- [x] admission / deadlines / drain (15F — **COMPLETE / ACCEPTED**)
- [x] single-container OfflineRAG application image (15G — **COMPLETE / ACCEPTED**)
- [x] Qdrant Local standalone profile (15G — **COMPLETE / ACCEPTED**)
- [x] `/data` + `/models` volume packaging contract (15G — **COMPLETE / ACCEPTED**)
- [x] Slice 15 integration closeout (15H — **COMPLETE / ACCEPTED** at `1c1d94e…`)
- [ ] Portfolio Demo UI (Slice 16 — design **ACCEPTED / LOCKED** at `e2e7475…`; **16A COMPLETE / ACCEPTED** at `e73959be…`; **16B COMPLETE / ACCEPTED** at `eb8baef…`; **16C COMPLETE / ACCEPTED** at `936e414…`; **A1 ACCEPTED / LOCKED** at `5060e2ae…`; **16D-A/B/C NOT AUTHORIZED**; Slice 16 overall **IN PROGRESS / NOT COMPLETE**)
- [ ] Regression CI (Slice 17 — **PLANNED / DESIGN NOT OPEN**)
- [ ] Portfolio release package (Slice 18 — **PLANNED / DESIGN NOT OPEN**)
- [ ] Milestone 7 closeout (**NOT AUTHORIZED**)
- [ ] Container image size / CPU–CUDA variants ([issue #1](https://github.com/cschrupp/offline-rag/issues/1) — **DEFERRED**)

**M7 release direction (not a Slice-15 exit criterion):** a reviewer can use the
accepted product/API surface and, after Slice 16 implementation (16A/16B/16C
accepted; A1 accepted/locked; 16D-A/B/C not authorized by this update), inspect
evidence flow through a UI that remains a client of that surface — without
expanding product query scientific knobs.

Milestone **6** remains **COMPLETE / ACCEPTED** at `dcc6b07…`. Milestone **7**
remains **IN PROGRESS** (Slice 15 through **15H** landed; Slice 16 design
**ACCEPTED / LOCKED**; **16A/16B/16C COMPLETE / ACCEPTED**; Amendment A1
**ACCEPTED / LOCKED**; **16D-A/B/C**, **Slices 17–18**, and **M7
closeout** remain **NOT AUTHORIZED**). Performance optimization,
generator max-token change, reranker config change, `base.yaml` promotion,
`PORTFOLIO_DEMO.md` update, 13C/13D, recovery enablement, LangGraph, and NeMo
remain **NOT AUTHORIZED**.
Technical debt (post–Slice 15): investigate CPU-only PyTorch/retrieval
dependency resolution and/or CPU/CUDA image variants — tracked in GitHub
issue [#1](https://github.com/cschrupp/offline-rag/issues/1); not a 15G blocker.

## Milestone 8 — (historical stub; superseded by Slice 18 under M7)

The checklist below is retained as a historical portfolio-release stub.
Formal portfolio packaging work is now tracked as **Slice 18** under Milestone 7
(**PLANNED / DESIGN NOT OPEN / NOT AUTHORIZED**). Do not treat this section as a
separately authorized milestone while Slice 18 remains unopened.

- [ ] public demo corpus instructions
- [ ] benchmark methodology page
- [ ] final ablation table
- [ ] architecture diagram
- [ ] demo video/GIF
- [ ] setup guide
- [ ] host-Ollama deployment guide
- [ ] strict-offline verification report
- [ ] known limitations
- [ ] CI regression checks
- [ ] optional public IR benchmark adapters (BEIR / `ir_datasets`) after private gold workflow works

**Historical release criterion (now Slice 18 design territory):** repository
supports all public quality/security/performance claims with reproducible
evidence.

## Post-v1 candidates

Only prioritize these when failures justify them:

- learned sparse retrieval / SPLADE;
- ColBERT-style late interaction;
- table-specific retrieval;
- multimodal page reasoning;
- query decomposition for true multi-hop tasks;
- document version diffing;
- incremental indexing GC / lifecycle tooling;
- corpus-level access policies;
- GraphRAG / knowledge graph if relation-heavy benchmarks warrant it;
- synthetic gold expansion beyond the local authoring workflow;
- experiment registry UI beyond serialized eval artifacts.
