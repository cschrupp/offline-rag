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

**GAP-16G-02 — Gold baseline bootstrap / candidate-generation product flow:**
**CLOSEOUT ACCEPTED** (`GAP-16G-02-CLOSEOUT-HA-001`; IR-002 **ACCEPT**;
exact subject `e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087`). Seneca provides
the accepted browser orchestration over existing 9B proposal → 9C pooling →
optional advisory 9D, producing an eligible Gold Lab baseline. See
[`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](docs/gap16g_02_gold_baseline_bootstrap_closeout.md)
and
[`docs/slice16g_gap_registry_addendum.md`](docs/slice16g_gap_registry_addendum.md).
**Main promotion:** **COMPLETE** (`GAP-16G-02-MAIN-PROMOTION-AUTH-001`
**EXECUTED**; promoted main `f7fb999758ce6219be27d27a3f1c0a16ece97506`).
Slice **9G** remains **DEFERRED / NOT AUTHORIZED**.

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
     AMENDMENT A2 ACCEPTED / LOCKED / SEALED
       dce3456e519cb6c96570e20f5af800d00cafb5a7
       docs/slice16_amendment_a2_conversational_grounding.md
       A2 CLOSEOUT f0bdf78d0ae6a79737055d324b22fc35e1e501f5
     16D-A COMPLETE / ACCEPTED / SEALED
       ACCEPTED SHA 4f8962f2893ab433e6ea269ad54e46f67771ca70
       Evidence: docs/slice16d_a_seneca_product_foundation_query_scope.md
     LAST SEALED IMPLEMENTATION BASELINE
       a952a75bc07191b213a5113eee53cb967fef8326
     OBSERVED 16D-B1 CANDIDATE
       6b6524001f063a628505f572e7ca13d954a38260
       PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
     16D-B1 FOUNDATION REMEDIATION ACCEPTED / SEALED
       ACCEPTED IMPLEMENTATION c68cc3f8f16a2588ba093886f3e48e1c7037f83f
       VERIFIED CLOSEOUT b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90
       INDEPENDENT CLOSEOUT REVIEW PASSED
       Evidence: docs/slice16d_b1_upload_foundation_remediation.md
     LEGACY B1 PRODUCT UX
       PRODUCT ACCEPTANCE WITHHELD / NOT SEALED
     16D-B2 COMPLETE / ACCEPTED / SEALED
       ACCEPTED IMPLEMENTATION baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149
       INDEPENDENT REVIEW PASSED
       HUMAN ACCEPTANCE ACCEPTED
       REWORK 1 COMPLETE
       Evidence: docs/slice16d_b2_grounded_answer_v2.md
     16D-B3 COMPLETE / ACCEPTED / SEALED
       AUTHORIZED BASELINE 28aad06f89e6d00a0b81b51f9c2de38fed06cb22
       IMPLEMENTATION CANDIDATE adbf2fcd01c4c2db08fe146993c04ce91b9b97c3
       Evidence: docs/slice16d_b3_conversational_workspace.md
     16D-C COMPLETE / ACCEPTED / SEALED
       ACCEPTED IMPLEMENTATION 0381e0461f68c5fc09e7be2c7699d434e8b8a9cb
       Evidence: docs/slice16d_c_training_mode.md
       Closeout: docs/slice16d_c_a4_closeout.md
     Amendment A4 ACCEPTED / LOCKED / SEALED
       A4 MATERIALIZATION d12f6322ef13915002b49dcc8f1211052a66dcc5
       A4 DOC: docs/slice16_amendment_a4_workspace_portability_shell.md
     16E COMPLETE / ACCEPTED / SEALED
       ACCEPTED ENGINEERING IMPLEMENTATION 3e1ce4c94fc511abb4e1d94bd194736d5497e64f
       WORKSPACE SOURCE-LOADING REMEDIATION 9dd2b008ebf9feee279dc6d0e58fafb006288ee5
       REMEDIATION EVIDENCE TIP 9cd5528ab6c6e22d2dca55aca221b65eac50269e
       Evidence: docs/slice16e_engineering_evidence.md
       Remediation: docs/workspace_source_loading_remediation.md
       Closeout: docs/slice16e_closeout.md
     16F COMPLETE / ACCEPTED / SEALED
       FINAL TIP f25f8358aead7fcfe161fff388012cec23b5a573
       CLOSEOUT: docs/slice16f_closeout.md
     16G-D0 ACCEPTED / FROZEN
       DESIGN TIP 8af2dbab72d1a79f53b0f3958e7c7142b4273693
       FROZEN DESIGN: docs/slice16g_gold_lab_games_pedagogy_design.md
     16G-I1 ACCEPTED
     16G-I2 ACCEPTED
     16G-I3 ACCEPTED
     GAP-16G-01 ACCEPTED
     16G-I4 ACCEPTED
     16G-I5 ACCEPTED
     GAP-16G-02 CLOSEOUT ACCEPTED / PROMOTED TO MAIN
       IR-002 ACCEPT / HA-001 ACCEPTED
       HUMAN-ACCEPTED SUBJECT e5d116b8a2990f3b0ac7f3fe1cbf052b4f6ac087
       ACCEPTED IMPLEMENTATION 120c03cd79f3af142144a6b73e05bcb43fdacb76
       ACCEPTED DESIGN 4b872cc0e9caf3323196cc2c3afe4772e249f191
       Closeout: docs/gap16g_02_gold_baseline_bootstrap_closeout.md
       Addendum: docs/slice16g_gap_registry_addendum.md
       MAIN PROMOTION COMPLETE
       PROMOTION AUTHORITY GAP-16G-02-MAIN-PROMOTION-AUTH-001 — EXECUTED
       PROMOTED MAIN f7fb999758ce6219be27d27a3f1c0a16ece97506
     16G-I6 COMPLETE / ACCEPTED
       IR-002 ACCEPT
       HUMAN TECHNICAL ACCEPTANCE ACCEPTED
       EXACT ACCEPTED CANDIDATE cc7ff520eb146fa555f2b48e1f7dcc89a7952729
     16G IMPLEMENTATION COMPLETE / ACCEPTED
     16H COMPLETE / ACCEPTED
       IR-003 ACCEPT
       16H-HA-001 — ACCEPTED
       EXACT HUMAN-ACCEPTED SUBJECT 01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10
     16I COMPLETE / ACCEPTED
       IR-003 ACCEPT
       Authority: S16-I-MANAGED-OP-PROGRESS-AUTH-001
       Exact accepted candidate: a3e65ce4bfa698f49e3aa21c4c5a7ddb0ea356a5
       Managed-operation progress telemetry
     16J PAUSED
       Seneca public-surface branding cleanup
     16K DESIGN ACCEPTED / FROZEN
       Design-open: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
       Rework: S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001 — AUTHORIZED
         (addresses DESIGN-OPEN-IR-001 R1–R5)
       Human acceptance: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001 — ACCEPTED
       HA record: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001 — AUTHORIZED
       HA-record IR: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001 — ACCEPT
       Exact Human-accepted design subject:
         0839b565cd60958141366048520236a71bf16fd0
       Design: docs/slice16k_beta_ingestion_readiness_design.md
       Detached managed-ingest lifetime ≠ HTTP request deadline; transport
         safety ≠ searchable workload (post-closeout; does NOT reopen Slice 16)
       Frozen order: 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D
         → 16K-E → 16K-F → 16K-G
       16K-A: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
         Implementation authority:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-AUTH-001
           — AUTHORIZED
         Independent review:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002 — ACCEPT
         Human acceptance:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001 — ACCEPTED
         HA record:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001 — AUTHORIZED
         Exact Human-accepted technical subject:
           1370b99327124045ad96005e829095683842c06f
         Branch: implementation/16k-a-managed-ingestion-correctness
         HA-record IR:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001 — ACCEPT
       16K-B: COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED /
         HA RECORD INDEPENDENTLY ACCEPTED
         Implementation authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001 — AUTHORIZED
         Exact implementation base:
           39e5e09363193b2315ada9e56cb3e1c14ba9377d
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001
           — REWORK REQUIRED (R1–R4)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact rework base:
           85f01f40080fe485b6ddb7700855aa34280c9c75
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002
           — REWORK REQUIRED (R3 / R4a / R4b)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002
           — AUTHORIZED
         Exact rework-002 base / parent:
           533a07c3d1313d08eae5647e4c266d4fa3a439c5
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-003
           — REWORK REQUIRED (R3 orphan ownership)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-003
           — AUTHORIZED
         Exact rework-003 base / parent:
           2c0e7bf21c8c427ee99b1b9518342a8080596463
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004 — ACCEPT
         IR-004 acceptance-record authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact independently accepted technical subject (IR-004 historical):
           91dba2e2885346ee595b920fd7dd02f671d2f7af
         Post-qualification remediation authority:
           S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact post-qual remediation parent:
           037a39531abfd5f5335151a946dbede776c5f492
         Post-qualification chunk-ID collision IR:
           S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-IR-001 — ACCEPT
         Exact chunk-ID collision remediation subject:
           f4707b828a85dcc538fc1510a52ed416d7a89935
         Post-qualification lexical zero-term eligibility remediation authority:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact lexical zero-term remediation parent:
           f4707b828a85dcc538fc1510a52ed416d7a89935
         Post-qualification lexical zero-term eligibility IR:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001 — ACCEPT
         Exact independently accepted lexical zero-term remediation subject:
           349de6a55f0f362a42e646d946f0433cb33e6489
         Lexical zero-term IR-001 acceptance-record authority:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           349de6a55f0f362a42e646d946f0433cb33e6489
         Exact lexical zero-term IR-001 acceptance-record tip:
           fbc8bb17a51f800aaa8bcc030c163427d8dc1821
         Post-qualification dense-failure observability remediation authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact dense-failure observability remediation parent:
           fbc8bb17a51f800aaa8bcc030c163427d8dc1821
         Post-qualification dense-failure observability IR:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
           — REWORK REQUIRED (R1)
         Exact dense-failure observability IR-001 subject:
           6f61f18441c2348faa81a1852196b7d300a1c4da
         Dense-failure observability rework authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact dense-failure observability rework parent:
           6f61f18441c2348faa81a1852196b7d300a1c4da
         Dense-failure observability rework IR:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
           — ACCEPT
         Exact independently accepted dense-failure observability technical subject:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         R1: CLOSED
         Dense-failure observability IR-002 acceptance-record authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         Exact IR-002 acceptance-record tip:
           9f9734efb7a534f054415b32c73c039ae59369e3
         Human technical acceptance:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-001 — ACCEPTED
         Exact Human-accepted technical subject:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         HA-record authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-AUTH-001
           — AUTHORIZED
         Exact HA-record parent:
           9f9734efb7a534f054415b32c73c039ae59369e3
         Technical lineage (durable):
           91dba2e2885346ee595b920fd7dd02f671d2f7af
             — IR-004 ACCEPT (historical 16K-B subject)
           → f4707b828a85dcc538fc1510a52ed416d7a89935
             — post-qual chunk-ID remediation IR-001 ACCEPT
           → 349de6a55f0f362a42e646d946f0433cb33e6489
             — post-qual lexical zero-term remediation IR-001 ACCEPT
           → fbc8bb17a51f800aaa8bcc030c163427d8dc1821
             — lexical zero-term IR-001 acceptance-record tip
           → 6f61f18441c2348faa81a1852196b7d300a1c4da
             — dense-failure observability IR-001 REWORK REQUIRED (R1)
           → 40c6eb3824ac9f9c1cbc35c889e3e4110b229469
             — exact technical subject; IR-002 ACCEPT; HA-001 ACCEPTED; R1 CLOSED
           → 9f9734efb7a534f054415b32c73c039ae59369e3
             — IR-002 durable acceptance-record tip
           → 4f2c045717e2f8fe5b583173847a3bfa97046061
             — durable HA-record tip; HA-RECORD-IR-001 ACCEPT;
               not the technical HA subject
         HA-record IR:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-IR-001
           — ACCEPT
         Exact accepted HA-record subject:
           4f2c045717e2f8fe5b583173847a3bfa97046061
         Fireground CUDA/cublasGemmEx runtime issue:
           OPEN / SEPARATE / NOT FIXED
         Branch: implementation/16k-b-ingestion-observability
       16K baseline evidence: FROZEN / INDEPENDENTLY ACCEPTED
         Campaign authority:
           S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001 — AUTHORIZED
         AUTH-open:
           S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-OPEN-001
         Exact AUTH-open execution pin:
           eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e
         Exact governance parent:
           4f2c045717e2f8fe5b583173847a3bfa97046061
         Technical subject under measurement:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         Freeze subject:
           S16-K-BASELINE-EVIDENCE-FREEZE-001
         Independent review:
           S16-K-BASELINE-EVIDENCE-FREEZE-IR-001 — REWORK REQUIRED (R1–R4)
         Exact IR-001 subject:
           0d169ae62d620709b220e8ebc97b2932d64a843b
         Rework authority:
           S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001 — AUTHORIZED
         Exact rework parent:
           0d169ae62d620709b220e8ebc97b2932d64a843b
         Independent review:
           S16-K-BASELINE-EVIDENCE-FREEZE-IR-002 — ACCEPT
         Exact independently accepted freeze subject:
           3abc3a6c0ef31cc255ea6de8796203d26700ec23
         Human disposition:
           HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS
         Regression:
           workspace query/conversation HTTP 500
           after retrieval-model initialization
         Diagnostic authority:
           S16-K-POST-BASELINE-LIVE-QUERY-REGRESSION-DIAGNOSTIC-AUTH-001
           — AUTHORIZED
         Exact diagnostic parent:
           3abc3a6c0ef31cc255ea6de8796203d26700ec23
         Diagnostic branch: diagnostic/16k-live-query-regression
         Observability remediation authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact remediation parent:
           b65d1beda2ef8e19e59acebe498043b4188712c5
         Exact AUTH-open pin:
           0894a54bf5c8c8a06c0ec4821ebf3d804a92fc15
         Remediation branch: implementation/16k-query-failure-observability
         Independent review:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
           — REWORK REQUIRED (R1–R4)
         Exact IR-001 subject:
           9a8d30333bdc9fad800411b861bb05d2a038ea35
         Exact IR-001 handoff tip:
           0ac6cd298e02f69133559aa682ac796ba90abfc8
         Rework authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact rework parent:
           0ac6cd298e02f69133559aa682ac796ba90abfc8
         Exact rework AUTH-open pin:
           ea763e5da7eb55dc08a58bb783c360c43e75f3cb
         Exact rework review subject / technical subject:
           163078753eeda33959c9957cfad4e82876a7a5f5
         Exact rework handoff tip:
           17fc511b3ac12a1a7822ca012b7a6d2309f859bf
         Observability remediation:
           IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
         Independent review:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
           — ACCEPT
         Exact independently accepted technical subject:
           163078753eeda33959c9957cfad4e82876a7a5f5
         IR-002 acceptance-record authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           17fc511b3ac12a1a7822ca012b7a6d2309f859bf
         Exact IR-002 acceptance-record tip:
           6d1902c10ead7ee5a3b0ccfe640112c78ae0b9fd
         Human acceptance of observability remediation:
           NOT RECORDED under this authority
         Constrained-VRAM diagnostic authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-AUTH-001
           — AUTHORIZED
         Exact constrained-VRAM diagnostic parent:
           98a5d1f6dceb6c51943c6888b39adb28926eb27f
         Diagnostic branch: diagnostic/16k-constrained-free-vram-reproduction
         Diagnostic status: EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW
         Constrained-VRAM diagnostic status: EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED
         Scientific diagnostic execution: EXECUTION COMPLETE / NO RERUN REQUIRED
         Constrained-VRAM diagnostic IR-001:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-001
           — REWORK REQUIRED (R1–R2)
         Constrained-VRAM rework authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-REWORK-AUTH-001
           — AUTHORIZED
         Exact constrained-VRAM rework parent:
           a71f4fe2202be0fd1f7a4460d0287e407eec953a
         Constrained-VRAM rework status: COMPLETE / INDEPENDENTLY ACCEPTED
         Independent review:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002
           — ACCEPT
         Exact independently accepted subject:
           7ad48b71dcdc096669399a4ea9b165cffa2d226b
         Acceptance-record authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           7ad48b71dcdc096669399a4ea9b165cffa2d226b
         Historical HTTP 500: NOT REPRODUCED / ROOT CAUSE UNRESOLVED
         CUDA-class failure: NOT OBSERVED
         M0–M2 eligibility gate: NOT SATISFIED
         GPU residency/allocator diagnostic design authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-AUTH-001
           — AUTHORIZED
         Exact GPU residency design parent:
           bd450fd601e655fc03e9c7c929075aa9c3673e9c
         Design branch: design/16k-gpu-residency-allocator-diagnostic
         Design status: DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW
         GPU residency/allocator diagnostic design status: DESIGN COMPLETE / INDEPENDENTLY ACCEPTED
         Independent design review:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001
           — ACCEPT
         Exact independently accepted design subject:
           2417e47fc2aef1d59c31f0307a0cdb222c56e618
         Acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           2417e47fc2aef1d59c31f0307a0cdb222c56e618
         GPU residency/allocator diagnostic tooling authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-AUTH-001
           — AUTHORIZED
         Exact GPU residency tooling parent:
           d501370aef96c953f4780d2048d11b91306ee856
         Tooling branch: implementation/16k-gpu-residency-allocator-diagnostic-tooling
         Tooling status: TOOLING IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT TOOLING REVIEW
         GPU residency/allocator diagnostic tooling status: TOOLING IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
         Independent tooling review:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001
           — ACCEPT
         Exact independently accepted tooling subject:
           a26ea53f6ce32c6454d21a6d6af988d50299ae49
         Tooling acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact tooling acceptance-record parent:
           a26ea53f6ce32c6454d21a6d6af988d50299ae49
         GPU residency/allocator diagnostic execution authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001
           — AUTHORIZED
         Exact GPU residency execution parent:
           a04d8f6131553beed0585a3c877cfbc2641c1863
         Execution branch: diagnostic/16k-gpu-residency-allocator
         Historical execution handoff:
           EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW
         Execution subject: c9daa88fb80c63c7ce6106e8d73df1976aae09d4
         Independent diagnostic review (IR-001):
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-001
           — REWORK REQUIRED (F001: evidence not repository-visible)
           — preserved as provenance
         Evidence publication authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EVIDENCE-PUBLICATION-AUTH-001
           — AUTHORIZED
         Exact evidence publication parent:
           c9daa88fb80c63c7ce6106e8d73df1976aae09d4
         Evidence path: docs/evidence/16k_gpu_residency_allocator/
         Exact independently accepted review/evidence subject:
           579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2
         Independent diagnostic review (IR-002):
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002
           — ACCEPT
         GPU residency/allocator diagnostic status:
           EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED
         Scientific disposition: NEGATIVE / INDEPENDENTLY ACCEPTED
         M0–M2 eligibility gate: NOT SATISFIED / INDEPENDENTLY ACCEPTED
         Acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2
         Historical HTTP 500 (GPU residency campaign): ROOT CAUSE UNRESOLVED
         Further GPU residency/allocator diagnostic tranche:
           NOT IMPLIED / NOT AUTHORIZED
         Execution document: docs/slice16k_gpu_residency_allocator_diagnostic_execution.md
         Execution scope:
           frozen C0/H3/H1/H2/H4 matrix; scientific rerun / further GPU
           diagnostic tranche NOT AUTHORIZED under acceptance-record AUTH;
           M0–M2 / 16K-C/D / device-CUDA / fireground / main NOT AUTHORIZED
         Tooling document: docs/slice16k_gpu_residency_allocator_diagnostic_tooling.md
         Tooling scope: env-gated in-process probe + runner; campaign execution NOT AUTHORIZED
         Design document: docs/slice16k_gpu_residency_allocator_diagnostic_design.md
         Design scope:
           state/history-dependent residency + allocator hypotheses beyond static free-VRAM;
           execution NOT AUTHORIZED; M0–M2 / 16K-C/D / device-CUDA / fireground / main NOT AUTHORIZED
         Exact constrained-VRAM execution tip: c921c954da25a2f61415707d2f5b54579bc48571
         Evidence path: docs/evidence/16k_constrained_vram/
         Campaign outcome: no CUDA-class failure at B1/B2; B1-repeat skipped; all primary turns HTTP 200 / model_abstain; historical 500 not reproduced
         Diagnostic scope:
           controlled free-VRAM reproduction on instrumented build;
           external CUDA occupant only; M0–M2 NOT AUTHORIZED
         Rework scope:
           close IR-001 R1–R4 only; no VRAM/device/CUDA behavioral fix
         Remediation scope:
           durable internal_failure + server traceback for grounded-query
           internal_error; public D08 / GET /v1/trace/{id} sanitized;
           no VRAM/device/CUDA behavioral fix
         Public projection:
           GET /v1/trace/{id} allowlist excludes internal_failure
         Device/VRAM/CUDA behavior: unchanged
         Manifest: docs/slice16k_baseline_evidence_campaign.md
         Freeze narrative: docs/slice16k_baseline_evidence.md
         Evidence: docs/evidence/16k_baseline/
         Accepted B0–B3 evidence: retained / not rewritten
         Fireground CUDA/cublasGemmEx:
           OPEN / SEPARATE / NOT FIXED
       16K-C authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-AUTH-001
         — AUTHORIZED
       Exact 16K-C parent: f2741c105db48aea081b5282dc48e4b7f11fd6b6
       16K-C branch: implementation/16k-c-first-user-capacity-model
       16K-C status: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
       16K-C independent review (IR-001):
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-001
         — REWORK REQUIRED (F001) — preserved as provenance
       16K-C rework authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-C rework parent: 40e5b096041805fb149516b6eb89c793f6519213
       16K-C independent review (IR-002):
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002 — ACCEPT
       Exact independently accepted 16K-C subject:
         219c8551d208530ec93c5697ca5591ad52bfb228
       16K-C acceptance-record authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-C acceptance-record parent:
         219c8551d208530ec93c5697ca5591ad52bfb228
       F001: CLOSED
       16K-C document: docs/slice16k_c_first_user_capacity_model.md
       16K-D authority:
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001
         — AUTHORIZED
       Exact 16K-D parent: 33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f
       Exact independently accepted 16K-D technical subject:
         32e52024df47b9add7ce02675a1d40555ac55eae
       Exact independently accepted 16K-D evidence subject:
         70abf3003ba37cd983772e084f9616fe3678a17a
       16K-D independent review (IR-001):
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-001
         — REWORK REQUIRED (F001) — preserved as provenance
       16K-D rework authority:
         S16-K-D-D0-BASELINE-EVIDENCE-PROVENANCE-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D rework subject:
         32e52024df47b9add7ce02675a1d40555ac55eae
       16K-D independent review (IR-002):
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002 — ACCEPT
       16K-D IR-002 acceptance-record authority:
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-D acceptance-record parent:
         70abf3003ba37cd983772e084f9616fe3678a17a
       16K-D branch: implementation/16k-d-dense-cuda-profiling
       16K-D D0: BASELINE COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D F001: CLOSED
       16K-D experimental-plan reconciliation authority:
         S16-K-D-EXPERIMENTAL-PLAN-RECONCILIATION-AUTH-001 — AUTHORIZED
       Exact 16K-D reconciliation parent:
         c801401a486c6ecd425840649fdd6f6893c50f18
       Exact 16K-D reconciliation tip / D1 tooling parent:
         4449f0053faf972726955db889e83ffcda8a2143
       16K-D experimental plan: RECONCILED (docs-only)
       16K-D D1 stall-attribution tooling authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling parent:
         4449f0053faf972726955db889e83ffcda8a2143
       16K-D D1 tooling IR-001:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-001
         — REWORK REQUIRED (F001) — preserved
       16K-D D1 tooling rework authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling rework parent:
         9690ffb7b55502c8060563e94e3a8cf024c82360
       16K-D D1 tooling IR-002:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002 — ACCEPT
       16K-D D1 tooling IR-002 acceptance-record authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling acceptance-record parent:
         c98d878e2e1327e984e60ceb59e507b6965962fe
       Exact independently accepted 16K-D D1 tooling technical subject:
         433725952c15a2feed4b65986d03e254d08d1568
       Exact independently accepted 16K-D D1 tooling evidence/docs subject:
         c98d878e2e1327e984e60ceb59e507b6965962fe
       16K-D D1 tooling: COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D D1 tooling F001: CLOSED
       16K-D D1 tooling contract: dense-cuda-profile-v2
       16K-D D1 scientific matrix freeze authority:
         S16-K-D-D1-SCIENTIFIC-MATRIX-FREEZE-AUTH-001 — AUTHORIZED
       Exact 16K-D D1 matrix freeze parent:
         016e338bf2b848e30cd89c7ba6ace6e6f39d1139
       16K-D D1 matrix freeze document:
         docs/slice16k_d_d1_scientific_matrix_freeze.md
       16K-D D1 scientific execution authority:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 scientific execution parent:
         0ecf2f74e4d283f59ab932abbdaee6ebb821a5ac
       Exact 16K-D D1 scientific execution subject:
         177620a3440c310759775dbf303420b80df7a05c
       Exact 16K-D D1 sealed cell evidence tip:
         4326586fe0ce3b7ca4c40ded743272d72ba53036
       16K-D D1 scientific IR-001:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-001
         — REWORK REQUIRED (F001 analysis) — preserved
       16K-D D1 analysis publication rework authority:
         S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 analysis rework parent:
         4326586fe0ce3b7ca4c40ded743272d72ba53036
       16K-D D1 scientific IR-002:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-002 — ACCEPT
       Exact independently accepted 16K-D D1 analysis publication subject:
         7be6a2b5c7ca7b521f0c642d6a024a1e421d6636
       16K-D D1 F001: CLOSED
       16K-D D1: COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D D2 practical execution optimization design authority:
         S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-AUTH-001
         — AUTHORIZED
       Exact 16K-D D2 design parent:
         7be6a2b5c7ca7b521f0c642d6a024a1e421d6636
       16K-D D2 design document:
         docs/slice16k_d_d2_practical_execution_optimization_design.md
       16K-D status: D2 PRACTICAL EXECUTION OPTIMIZATION DESIGN COMPLETE /
         READY FOR INDEPENDENT REVIEW
       16K-D D2: DESIGN ONLY / EXECUTION NOT AUTHORIZED
       16K-D program pivot: scientific optimization →
         bounded product-engineering optimization
       16K-D document: docs/slice16k_d_dense_cuda_profiling.md
       16K-D evidence: docs/evidence/16k_d_dense_cuda/
       16K-D D1 tooling evidence:
         docs/evidence/16k_d_dense_cuda_tooling/
       16K-D D1 scientific evidence:
         docs/evidence/16k_d_dense_cuda/d1/
       16K-D authoritative current lane: CUDA / BF16 / batch 32 / SDPA
       16K-D frozen proxy usability (§9.4): median ≤10 min; no run >12 min;
         3 clean cold confirmations; 16K-F full-corpus ≤60 min
       16K-D practical sequence:
         D0 → D1 attribution → D2 practical execution optimization → decision
       16K-D mechanical D2→D3→D4→D5 sequence: SUPERSEDED
       16K-D closed under this design AUTH:
         D2 harness/execution / FP16/CPU calls / model replacement /
         mechanical D3–D5 / production/default / threshold changes /
         HTTP-500 reopen / 16K-E→G / main
       16K-E → 16K-G: NOT AUTHORIZED
       Main promotion: NOT AUTHORIZED
       Historical closeout disposition (inventory I-11): DEFERRED / NOT REQUIRED
         / NOT AUTHORIZED — preserved as provenance
     16L COMPLETE / ACCEPTED
       Authority: S16-L-EMBEDDING-AUTO-DEVICE-UX-AUTH-002
       Exact accepted subject: 88fadc7c3e8e70c4886cbff0c7863cccc63ef14a
       Embedding accelerator auto-selection + Compute settings
     16M COMPLETE / ACCEPTED
       Authority: S16-M-GOLD-POOL-AUX-INDEX-AUTH-001
       Exact accepted subject: dcf6bf02a77a4e68678d8887f836c471448422bc
       Gold pooling auxiliary-index integration (Arm-H fail-closed)
     16N DESIGN FROZEN
       Authority: S16-N-GOLD-EXPERT-ENTRY-AUTH-001
       Q1–Q11 FROZEN — expert entry + presentation review
     16N-A COMPLETE / INDEPENDENTLY ACCEPTED
       Authority: S16-N-A-IMPLEMENTATION-AUTH-001
       Independent review: S16-N-A-IMPLEMENTATION-IR-002 — ACCEPT
       Exact accepted technical subject:
         36de7feaab33fddf77d4bdf5818f3cc60e8a1832
       Presentation Review bootstrap (non-mutating)
       Human QC presentation disposition:
         S16-N-A-QC-PRESENTATION-HA-001 — ACCEPTED
       QC ALLOW_PRODUCTION: ACCEPTED SUBJECT
         21dfb3e88920c40fe227d51efc8022995ef41c9e
       Human RF presentation disposition:
         S16-N-A-RF-PRESENTATION-HA-001 — ACCEPTED
       RF ALLOW_PRODUCTION: ACCEPTED SUBJECT
         Authority: S16-N-A-RF-ALLOW-PRODUCTION-AUTH-001
         Exact accepted subject:
           aac51029f279f07cafd1078160efbd592d5fc4be
       Evidence Sweep: NOT APPROVED
       Chunk Duel: NOT APPROVED
     16N-B COMPLETE / HUMAN ACCEPTED
       Authority: S16-N-B-IMPLEMENTATION-AUTH-001
       Frozen design: S16-N-GOLD-EXPERT-ENTRY-DESIGN-FREEZE-001
       Independent review: S16-N-B-IMPLEMENTATION-IR-003 — ACCEPT
       Human acceptance: S16-N-B-HA-001 — ACCEPTED
       Exact Human-accepted technical subject:
         ae137649565881ed295dc51dba422446fa81e682
       Prior reviewed lineage:
         IR-001: 1b993b5a111f18a0b8148e57e597b5332fe17179 — REWORK REQUIRED
         IR-002: 244e064356ad99ff65589acdecd60eb9cce60022 — REWORK REQUIRED
         IR-003: ae137649565881ed295dc51dba422446fa81e682 — ACCEPT
       IR-003 acceptance-record successor:
         c704ba4752225f8204195015fecc5e2ae4feea44
       16J: NOT AUTHORIZED FROM THIS DISPOSITION
       16K: NOT AUTHORIZED FROM THIS DISPOSITION
       Authoring-server failure UX defect: CLOSED
     Authoring-server failure UX design ACCEPTED
       Authority: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-AUTH-001
       Design freeze: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-FREEZE-001 — ACCEPTED / FROZEN
         (amended by R1–R4)
       Design doc: docs/slice16_closure_authoring_failure_ux_design.md
       Independent design review: S16-CLOSURE-AUTHORING-FAILURE-UX-DESIGN-IR-003 — ACCEPT
       Exact accepted design subject:
         5922e0b9fa9f8986b23d801507b879a321124395
       Prior design review lineage:
         IR-001: ea95a2fe5261a42c8d841a4789f6aed1b9028cc7 — REWORK REQUIRED
         IR-002: 5faae42410ee38ef9e291a94f496a0a48da5739b — REWORK REQUIRED
         IR-003: 5922e0b9fa9f8986b23d801507b879a321124395 — ACCEPT
       Design rework R1–R4: ACCEPTED / FROZEN
       Q1–Q7 ACCEPTED / FROZEN (amended by R1–R4)
     Authoring-server failure UX COMPLETE / HUMAN ACCEPTED
       Authority: S16-CLOSURE-AUTHORING-FAILURE-UX-IMPLEMENTATION-AUTH-001 — AUTHORIZED
       Exact implementation base:
         5922e0b9fa9f8986b23d801507b879a321124395
       Branch: implementation/s16-closure-authoring-failure-ux
       Independent implementation review:
         S16-CLOSURE-AUTHORING-FAILURE-UX-IMPLEMENTATION-IR-001 — ACCEPT
       Human acceptance: S16-CLOSURE-AUTHORING-FAILURE-UX-HA-001 — ACCEPTED
       Exact Human-accepted technical subject:
         5cb63dad7344b9f6a3766ef83760801f375b5217
       IR acceptance-record tip:
         6591c07c5c61d4cf3eb41cd445f3bcc602fb78b2
       Pre-Human gate-footer successor:
         b7871738a5d986f24d9e9408ea0aa696f34f6e91
       Implementation-review handoff / docs tip:
         133f9c37cb82d8541e3347a0eec3d9c246f4ac0d
       Status: COMPLETE / HUMAN ACCEPTED
       Original misleading server-unreachable defect: CLOSED
       Repository lint baseline: STILL RED (pre-existing; not a candidate regression)
       Slice 16 final closeout: NOT AUTHORIZED FROM THIS DISPOSITION
     Accepted-lineage documentation reconciliation AUTHORIZED
       Authority: S16-ACCEPTED-LINEAGE-RECONCILIATION-AUTH-001 — AUTHORIZED
       Purpose: docs-only correction of RF accepted status and 16H
         BuildKit-secret CA wording before canonical promotion
       Exact base: 19694dac3cc9d405621f297bb1a237359a1c7327
       Does NOT claim: Slice 16 complete, 16J resumed, 16K/9G/17 authorized,
         or canonical main promotion complete
     16J FINAL BRANDING: COMPLETE / HUMAN ACCEPTED / CANONICAL
       Design freeze: S16-J-REOPEN-BRANDING-UX-DESIGN-FREEZE-001 — ACCEPTED / FROZEN
       Implementation authority: S16-J-FINAL-BRANDING-IMPLEMENTATION-AUTH-001 — AUTHORIZED
       Acceptance-record authority:
         S16-J-FINAL-BRANDING-IR-002-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
       Design doc: docs/slice16j_final_branding.md
       Canonical technical base:
         09407ae0e5186b262a0b034e752672424e237fa2
       Branch: implementation/16j-final-branding
       Independent review:
         S16-J-FINAL-BRANDING-IMPLEMENTATION-IR-002 — ACCEPT
       Exact independently accepted technical subject:
         8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
       Human acceptance: S16-J-FINAL-BRANDING-HA-001 — ACCEPTED
       Exact Human-accepted technical subject:
         8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
       IR-002 acceptance-record tip:
         65aced367d92f3b411d476676f532c1727c78d70
       HA-001 acceptance-record tip:
         29d74c3a884d10f222eab07b92411e5a921bbba8
       F001: CLOSED
       MAIN PROMOTION COMPLETE
       Promotion authority:
         S16-J-FINAL-BRANDING-MAIN-PROMOTION-AUTH-001 — EXECUTED
       Promotion target / pre-reconciliation main:
         29d74c3a884d10f222eab07b92411e5a921bbba8
       Canonical main carries Human-accepted technical subject:
         8208f86e3c4bb2508d35048ceb0ba9033f3de2ef
       Product: Seneca — Grounded knowledge workspace
       Author: Carlos A. Schrupp
       Contact: carlos.schrupp@berkeley.edu
       Does NOT close Slice 16
     Slice-16 closeout inventory: HUMAN ACCEPTED
       Authority: S16-CLOSEOUT-INVENTORY-AUTH-001 — AUTHORIZED
       HA acceptance-record authority:
         S16-CLOSEOUT-INVENTORY-HA-001-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
       Exact inventory base: 168af70b54fba39f0efba69100d57b41a574667f
       Artifact: docs/slice16_closeout_inventory.md
       Historical IR-002 ACCEPT (exact subject d284776…): remains valid provenance
       IR-002 acceptance-record authority:
         S16-CLOSEOUT-INVENTORY-IR-002-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
       IR-002 acceptance-record tip (provenance): 5df7af2…
       I-32 amendment + IR-003 F003 wording correction: historical
       Independent review: S16-CLOSEOUT-INVENTORY-IR-004 — ACCEPT
       Human acceptance: S16-CLOSEOUT-INVENTORY-HA-001 — ACCEPTED
       Exact Human-accepted inventory subject:
         e24c11df70a59c41c494f302a19ae211bf787bf9
       Human acceptance of d284776…: NOT GRANTED — superseded as Human
         acceptance target by e24c11d…
       Historical inventory verdict (at inventory HA):
         CLOSEOUT BLOCKED — REQUIRED RESIDUALS REMAIN
       Live technical residual verdict: CLEAR
       Authoritative residual set (closed):
         I-26, I-27, I-28, I-30, I-31, I-32
         HUMAN ACCEPTED / CLOSED
       Reconciliation authority:
         S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-AUTH-001 — AUTHORIZED
       Exact reconciliation base: 73b7fc99d7dc24930962f40a584ed957de4e716a
       Reconciliation IR-001: REWORK REQUIRED (F001)
       Reconciliation IR-002: ACCEPT
       IR-002 acceptance-record authority:
         S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       IR-002 acceptance-record tip:
         e7305f06df22da4898e2246c40bf256c9535ccad
       Exact Human-accepted reconciliation subject:
         fc36aa8013a90b6355e85d97a00dc145b5802cd5
       Human acceptance:
         S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-HA-001 — ACCEPTED
       HA acceptance-record authority:
         S16-CLOSEOUT-REQUIRED-RESIDUALS-RECONCILIATION-HA-001-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       HA acceptance-record tip:
         3b36630952f34a147c3c8e82fdec7c0649620c0b
       Reconciliation status: COMPLETE / HUMAN ACCEPTED
       Final Slice-16 closeout authority:
         S16-FINAL-CLOSEOUT-AUTH-001 — AUTHORIZED
       Exact final-closeout base:
         3b36630952f34a147c3c8e82fdec7c0649620c0b
       Exact Human-accepted final-closeout subject:
         c4ba1e7956a6812279fdf45f28c24738856dec44
       Independent review: S16-FINAL-CLOSEOUT-IR-001 — ACCEPT
       Human acceptance: S16-FINAL-CLOSEOUT-HA-001 — ACCEPTED
       HA acceptance-record authority:
         S16-FINAL-CLOSEOUT-HA-001-ACCEPTANCE-RECORD-AUTH-001 — AUTHORIZED
       Final Slice-16 closeout: HUMAN ACCEPTED / CANONICAL
       Technical residual verdict: CLEAR
       Repairs I-26…I-32: HUMAN ACCEPTED / CLOSED
       HA acceptance-record tip:
         feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
       Canonical main promotion: COMPLETE / EXECUTED
       Main-promotion authority:
         S16-FINAL-CLOSEOUT-MAIN-PROMOTION-AUTH-001 — EXECUTED
       Post-promotion record authority:
         S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-AUTH-001 — AUTHORIZED
       Exact Human-accepted post-promotion record subject:
         76caab2a68ef42c0c2b216b7e3b3e989ab4d56b3
       Post-promotion record IR-001: ACCEPT
       Post-promotion record HA-001: ACCEPTED
       Post-promotion record HA acceptance-record authority:
         S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-001-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Post-promotion record status: COMPLETE / HUMAN ACCEPTED / CANONICAL
       HA acceptance-record tip lineage:
         e21b3e6013c743d7d09f13836704dd88969d4d4a
       Current canonical origin/main:
         e21b3e6013c743d7d09f13836704dd88969d4d4a
       Second main promotion (HA acceptance-record tip): COMPLETE / EXECUTED
       Second-promotion authority:
         S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-MAIN-PROMOTION-AUTH-001
         — EXECUTED
       Second-promotion record authority:
         S16-FINAL-CLOSEOUT-MAIN-PROMOTION-RECORD-HA-MAIN-PROMOTION-RECORD-AUTH-001
         — AUTHORIZED
       Second promotion operation: PURE FAST-FORWARD
       Pre-second-promotion canonical main:
         feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
       Promoted canonical main (second FF):
         e21b3e6013c743d7d09f13836704dd88969d4d4a
       Target vs canonical main after second promotion: 0 / 0
       Historical pre-second-promotion live claim (at tip e21b3e6… as authored):
         This HA acceptance-record successor: NOT YET PROMOTED TO MAIN
         (provenance only)
       Promotion operation: PURE FAST-FORWARD
       Pre-promotion canonical main:
         168af70b54fba39f0efba69100d57b41a574667f
       Promoted canonical main:
         feab2b2778aeec2f73b8a6f64f8d82e7921ae2a6
       Target vs canonical main after promotion: 0 / 0
       Historical pre-promotion live claim (at HA tip feab2b2…):
         Canonical main promotion: NOT AUTHORIZED / NOT YET EXECUTED
         (provenance only)
       Scope: docs/governance only; no product code; no 16K/9G/17/18
     9G DEFERRED / NOT AUTHORIZED
     16K: DESIGN ACCEPTED / FROZEN
       Design-open: S16-K-BETA-INGESTION-READINESS-DESIGN-OPEN-AUTH-001 — AUTHORIZED
       Rework: S16-K-BETA-INGESTION-READINESS-DESIGN-REWORK-AUTH-001 — AUTHORIZED
         (addresses DESIGN-OPEN-IR-001 R1–R5)
       Human acceptance: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-001 — ACCEPTED
       HA record: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-AUTH-001 — AUTHORIZED
       HA-record IR: S16-K-BETA-INGESTION-READINESS-DESIGN-HA-RECORD-IR-001 — ACCEPT
       Exact Human-accepted design subject:
         0839b565cd60958141366048520236a71bf16fd0
       Design: docs/slice16k_beta_ingestion_readiness_design.md
       Detached managed-ingest lifetime ≠ HTTP request deadline; transport
         safety ≠ searchable workload (does NOT reopen Slice 16)
       Frozen order: 16K-A → 16K-B → baseline evidence → 16K-C → 16K-D
         → 16K-E → 16K-F → 16K-G
       16K-A: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
         Implementation authority:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-AUTH-001
           — AUTHORIZED
         Independent review:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-IR-002 — ACCEPT
         Human acceptance:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-IMPLEMENTATION-HA-001 — ACCEPTED
         HA record:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-AUTH-001 — AUTHORIZED
         Exact Human-accepted technical subject:
           1370b99327124045ad96005e829095683842c06f
         Branch: implementation/16k-a-managed-ingestion-correctness
         HA-record IR:
           S16-K-A-MANAGED-INGESTION-CORRECTNESS-HA-RECORD-IR-001 — ACCEPT
       16K-B: COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED /
         HA RECORD INDEPENDENTLY ACCEPTED
         Implementation authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-AUTH-001 — AUTHORIZED
         Exact implementation base:
           39e5e09363193b2315ada9e56cb3e1c14ba9377d
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-001
           — REWORK REQUIRED (R1–R4)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact rework base:
           85f01f40080fe485b6ddb7700855aa34280c9c75
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-002
           — REWORK REQUIRED (R3 / R4a / R4b)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-002
           — AUTHORIZED
         Exact rework-002 base / parent:
           533a07c3d1313d08eae5647e4c266d4fa3a439c5
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-003
           — REWORK REQUIRED (R3 orphan ownership)
         Rework authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-REWORK-AUTH-003
           — AUTHORIZED
         Exact rework-003 base / parent:
           2c0e7bf21c8c427ee99b1b9518342a8080596463
         Independent review:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004 — ACCEPT
         IR-004 acceptance-record authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-IR-004-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact independently accepted technical subject (IR-004 historical):
           91dba2e2885346ee595b920fd7dd02f671d2f7af
         Post-qualification remediation authority:
           S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact post-qual remediation parent:
           037a39531abfd5f5335151a946dbede776c5f492
         Post-qualification chunk-ID collision IR:
           S16-K-B-POST-QUAL-CHUNK-ID-COLLISION-REMEDIATION-IR-001 — ACCEPT
         Exact chunk-ID collision remediation subject:
           f4707b828a85dcc538fc1510a52ed416d7a89935
         Post-qualification lexical zero-term eligibility remediation authority:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact lexical zero-term remediation parent:
           f4707b828a85dcc538fc1510a52ed416d7a89935
         Post-qualification lexical zero-term eligibility IR:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001 — ACCEPT
         Exact independently accepted lexical zero-term remediation subject:
           349de6a55f0f362a42e646d946f0433cb33e6489
         Lexical zero-term IR-001 acceptance-record authority:
           S16-K-B-POST-QUAL-LEXICAL-ZERO-TERM-ELIGIBILITY-REMEDIATION-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           349de6a55f0f362a42e646d946f0433cb33e6489
         Exact lexical zero-term IR-001 acceptance-record tip:
           fbc8bb17a51f800aaa8bcc030c163427d8dc1821
         Post-qualification dense-failure observability remediation authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact dense-failure observability remediation parent:
           fbc8bb17a51f800aaa8bcc030c163427d8dc1821
         Post-qualification dense-failure observability IR:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
           — REWORK REQUIRED (R1)
         Exact dense-failure observability IR-001 subject:
           6f61f18441c2348faa81a1852196b7d300a1c4da
         Dense-failure observability rework authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact dense-failure observability rework parent:
           6f61f18441c2348faa81a1852196b7d300a1c4da
         Dense-failure observability rework IR:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
           — ACCEPT
         Exact independently accepted dense-failure observability technical subject:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         R1: CLOSED
         Dense-failure observability IR-002 acceptance-record authority:
           S16-K-B-POST-QUAL-DENSE-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         Exact IR-002 acceptance-record tip:
           9f9734efb7a534f054415b32c73c039ae59369e3
         Human technical acceptance:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-001 — ACCEPTED
         Exact Human-accepted technical subject:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         HA-record authority:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-AUTH-001
           — AUTHORIZED
         Exact HA-record parent:
           9f9734efb7a534f054415b32c73c039ae59369e3
         Technical lineage (durable):
           91dba2e2885346ee595b920fd7dd02f671d2f7af
             — IR-004 ACCEPT (historical 16K-B subject)
           → f4707b828a85dcc538fc1510a52ed416d7a89935
             — post-qual chunk-ID remediation IR-001 ACCEPT
           → 349de6a55f0f362a42e646d946f0433cb33e6489
             — post-qual lexical zero-term remediation IR-001 ACCEPT
           → fbc8bb17a51f800aaa8bcc030c163427d8dc1821
             — lexical zero-term IR-001 acceptance-record tip
           → 6f61f18441c2348faa81a1852196b7d300a1c4da
             — dense-failure observability IR-001 REWORK REQUIRED (R1)
           → 40c6eb3824ac9f9c1cbc35c889e3e4110b229469
             — exact technical subject; IR-002 ACCEPT; HA-001 ACCEPTED; R1 CLOSED
           → 9f9734efb7a534f054415b32c73c039ae59369e3
             — IR-002 durable acceptance-record tip
           → 4f2c045717e2f8fe5b583173847a3bfa97046061
             — durable HA-record tip; HA-RECORD-IR-001 ACCEPT;
               not the technical HA subject
         HA-record IR:
           S16-K-B-INGESTION-OBSERVABILITY-IMPLEMENTATION-HA-RECORD-IR-001
           — ACCEPT
         Exact accepted HA-record subject:
           4f2c045717e2f8fe5b583173847a3bfa97046061
         Fireground CUDA/cublasGemmEx runtime issue:
           OPEN / SEPARATE / NOT FIXED
         Branch: implementation/16k-b-ingestion-observability
       16K baseline evidence: FROZEN / INDEPENDENTLY ACCEPTED
         Campaign authority:
           S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-001 — AUTHORIZED
         AUTH-open:
           S16-K-BASELINE-EVIDENCE-CAMPAIGN-AUTH-OPEN-001
         Exact AUTH-open execution pin:
           eb0ebd86f5d69378acc8142f63a6fa0b5a16d85e
         Exact governance parent:
           4f2c045717e2f8fe5b583173847a3bfa97046061
         Technical subject under measurement:
           40c6eb3824ac9f9c1cbc35c889e3e4110b229469
         Freeze subject:
           S16-K-BASELINE-EVIDENCE-FREEZE-001
         Independent review:
           S16-K-BASELINE-EVIDENCE-FREEZE-IR-001 — REWORK REQUIRED (R1–R4)
         Exact IR-001 subject:
           0d169ae62d620709b220e8ebc97b2932d64a843b
         Rework authority:
           S16-K-BASELINE-EVIDENCE-FREEZE-REWORK-AUTH-001 — AUTHORIZED
         Exact rework parent:
           0d169ae62d620709b220e8ebc97b2932d64a843b
         Independent review:
           S16-K-BASELINE-EVIDENCE-FREEZE-IR-002 — ACCEPT
         Exact independently accepted freeze subject:
           3abc3a6c0ef31cc255ea6de8796203d26700ec23
         Human disposition:
           HELD — LIVE PRODUCT REGRESSION UNDER DIAGNOSIS
         Regression:
           workspace query/conversation HTTP 500
           after retrieval-model initialization
         Diagnostic authority:
           S16-K-POST-BASELINE-LIVE-QUERY-REGRESSION-DIAGNOSTIC-AUTH-001
           — AUTHORIZED
         Exact diagnostic parent:
           3abc3a6c0ef31cc255ea6de8796203d26700ec23
         Diagnostic branch: diagnostic/16k-live-query-regression
         Observability remediation authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-AUTH-001
           — AUTHORIZED
         Exact remediation parent:
           b65d1beda2ef8e19e59acebe498043b4188712c5
         Exact AUTH-open pin:
           0894a54bf5c8c8a06c0ec4821ebf3d804a92fc15
         Remediation branch: implementation/16k-query-failure-observability
         Independent review:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-001
           — REWORK REQUIRED (R1–R4)
         Exact IR-001 subject:
           9a8d30333bdc9fad800411b861bb05d2a038ea35
         Exact IR-001 handoff tip:
           0ac6cd298e02f69133559aa682ac796ba90abfc8
         Rework authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-REWORK-AUTH-001
           — AUTHORIZED
         Exact rework parent:
           0ac6cd298e02f69133559aa682ac796ba90abfc8
         Exact rework AUTH-open pin:
           ea763e5da7eb55dc08a58bb783c360c43e75f3cb
         Exact rework review subject / technical subject:
           163078753eeda33959c9957cfad4e82876a7a5f5
         Exact rework handoff tip:
           17fc511b3ac12a1a7822ca012b7a6d2309f859bf
         Observability remediation:
           IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
         Independent review:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002
           — ACCEPT
         Exact independently accepted technical subject:
           163078753eeda33959c9957cfad4e82876a7a5f5
         IR-002 acceptance-record authority:
           S16-K-POST-BASELINE-GROUNDED-QUERY-FAILURE-OBSERVABILITY-REMEDIATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           17fc511b3ac12a1a7822ca012b7a6d2309f859bf
         Exact IR-002 acceptance-record tip:
           6d1902c10ead7ee5a3b0ccfe640112c78ae0b9fd
         Human acceptance of observability remediation:
           NOT RECORDED under this authority
         Constrained-VRAM diagnostic authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-AUTH-001
           — AUTHORIZED
         Exact constrained-VRAM diagnostic parent:
           98a5d1f6dceb6c51943c6888b39adb28926eb27f
         Diagnostic branch: diagnostic/16k-constrained-free-vram-reproduction
         Diagnostic status: EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW
         Constrained-VRAM diagnostic status: EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED
         Scientific diagnostic execution: EXECUTION COMPLETE / NO RERUN REQUIRED
         Constrained-VRAM diagnostic IR-001:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-001
           — REWORK REQUIRED (R1–R2)
         Constrained-VRAM rework authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-REWORK-AUTH-001
           — AUTHORIZED
         Exact constrained-VRAM rework parent:
           a71f4fe2202be0fd1f7a4460d0287e407eec953a
         Constrained-VRAM rework status: COMPLETE / INDEPENDENTLY ACCEPTED
         Independent review:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002
           — ACCEPT
         Exact independently accepted subject:
           7ad48b71dcdc096669399a4ea9b165cffa2d226b
         Acceptance-record authority:
           S16-K-POST-BASELINE-CONSTRAINED-FREE-VRAM-REPRODUCTION-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           7ad48b71dcdc096669399a4ea9b165cffa2d226b
         Historical HTTP 500: NOT REPRODUCED / ROOT CAUSE UNRESOLVED
         CUDA-class failure: NOT OBSERVED
         M0–M2 eligibility gate: NOT SATISFIED
         GPU residency/allocator diagnostic design authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-AUTH-001
           — AUTHORIZED
         Exact GPU residency design parent:
           bd450fd601e655fc03e9c7c929075aa9c3673e9c
         Design branch: design/16k-gpu-residency-allocator-diagnostic
         Design status: DESIGN COMPLETE / READY FOR INDEPENDENT DESIGN REVIEW
         GPU residency/allocator diagnostic design status: DESIGN COMPLETE / INDEPENDENTLY ACCEPTED
         Independent design review:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001
           — ACCEPT
         Exact independently accepted design subject:
           2417e47fc2aef1d59c31f0307a0cdb222c56e618
         Acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-DESIGN-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           2417e47fc2aef1d59c31f0307a0cdb222c56e618
         GPU residency/allocator diagnostic tooling authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-AUTH-001
           — AUTHORIZED
         Exact GPU residency tooling parent:
           d501370aef96c953f4780d2048d11b91306ee856
         Tooling branch: implementation/16k-gpu-residency-allocator-diagnostic-tooling
         Tooling status: TOOLING IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT TOOLING REVIEW
         GPU residency/allocator diagnostic tooling status: TOOLING IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
         Independent tooling review:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001
           — ACCEPT
         Exact independently accepted tooling subject:
           a26ea53f6ce32c6454d21a6d6af988d50299ae49
         Tooling acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-TOOLING-IR-001-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact tooling acceptance-record parent:
           a26ea53f6ce32c6454d21a6d6af988d50299ae49
         GPU residency/allocator diagnostic execution authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EXECUTION-AUTH-001
           — AUTHORIZED
         Exact GPU residency execution parent:
           a04d8f6131553beed0585a3c877cfbc2641c1863
         Execution branch: diagnostic/16k-gpu-residency-allocator
         Historical execution handoff:
           EXECUTION COMPLETE / STOP FOR INDEPENDENT DIAGNOSTIC REVIEW
         Execution subject: c9daa88fb80c63c7ce6106e8d73df1976aae09d4
         Independent diagnostic review (IR-001):
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-001
           — REWORK REQUIRED (F001: evidence not repository-visible)
           — preserved as provenance
         Evidence publication authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-EVIDENCE-PUBLICATION-AUTH-001
           — AUTHORIZED
         Exact evidence publication parent:
           c9daa88fb80c63c7ce6106e8d73df1976aae09d4
         Evidence path: docs/evidence/16k_gpu_residency_allocator/
         Exact independently accepted review/evidence subject:
           579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2
         Independent diagnostic review (IR-002):
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002
           — ACCEPT
         GPU residency/allocator diagnostic status:
           EXECUTION COMPLETE / INDEPENDENTLY ACCEPTED
         Scientific disposition: NEGATIVE / INDEPENDENTLY ACCEPTED
         M0–M2 eligibility gate: NOT SATISFIED / INDEPENDENTLY ACCEPTED
         Acceptance-record authority:
           S16-K-POST-BASELINE-GPU-RESIDENCY-ALLOCATOR-DIAGNOSTIC-IR-002-ACCEPTANCE-RECORD-AUTH-001
           — AUTHORIZED
         Exact acceptance-record parent:
           579d1fa1fdfcef8a34dbcc9d4fb21f287259aeb2
         Historical HTTP 500 (GPU residency campaign): ROOT CAUSE UNRESOLVED
         Further GPU residency/allocator diagnostic tranche:
           NOT IMPLIED / NOT AUTHORIZED
         Execution document: docs/slice16k_gpu_residency_allocator_diagnostic_execution.md
         Execution scope:
           frozen C0/H3/H1/H2/H4 matrix; scientific rerun / further GPU
           diagnostic tranche NOT AUTHORIZED under acceptance-record AUTH;
           M0–M2 / 16K-C/D / device-CUDA / fireground / main NOT AUTHORIZED
         Tooling document: docs/slice16k_gpu_residency_allocator_diagnostic_tooling.md
         Tooling scope: env-gated in-process probe + runner; campaign execution NOT AUTHORIZED
         Design document: docs/slice16k_gpu_residency_allocator_diagnostic_design.md
         Design scope:
           state/history-dependent residency + allocator hypotheses beyond static free-VRAM;
           execution NOT AUTHORIZED; M0–M2 / 16K-C/D / device-CUDA / fireground / main NOT AUTHORIZED
         Exact constrained-VRAM execution tip: c921c954da25a2f61415707d2f5b54579bc48571
         Evidence path: docs/evidence/16k_constrained_vram/
         Campaign outcome: no CUDA-class failure at B1/B2; B1-repeat skipped; all primary turns HTTP 200 / model_abstain; historical 500 not reproduced
         Diagnostic scope:
           controlled free-VRAM reproduction on instrumented build;
           external CUDA occupant only; M0–M2 NOT AUTHORIZED
         Rework scope:
           close IR-001 R1–R4 only; no VRAM/device/CUDA behavioral fix
         Remediation scope:
           durable internal_failure + server traceback for grounded-query
           internal_error; public D08 / GET /v1/trace/{id} sanitized;
           no VRAM/device/CUDA behavioral fix
         Public projection:
           GET /v1/trace/{id} allowlist excludes internal_failure
         Device/VRAM/CUDA behavior: unchanged
         Manifest: docs/slice16k_baseline_evidence_campaign.md
         Freeze narrative: docs/slice16k_baseline_evidence.md
         Evidence: docs/evidence/16k_baseline/
         Accepted B0–B3 evidence: retained / not rewritten
         Fireground CUDA/cublasGemmEx:
           OPEN / SEPARATE / NOT FIXED
       16K-C authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-AUTH-001
         — AUTHORIZED
       Exact 16K-C parent: f2741c105db48aea081b5282dc48e4b7f11fd6b6
       16K-C branch: implementation/16k-c-first-user-capacity-model
       16K-C status: IMPLEMENTATION COMPLETE / INDEPENDENTLY ACCEPTED
       16K-C independent review (IR-001):
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-001
         — REWORK REQUIRED (F001) — preserved as provenance
       16K-C rework authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-C rework parent: 40e5b096041805fb149516b6eb89c793f6519213
       16K-C independent review (IR-002):
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002 — ACCEPT
       Exact independently accepted 16K-C subject:
         219c8551d208530ec93c5697ca5591ad52bfb228
       16K-C acceptance-record authority:
         S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-C acceptance-record parent:
         219c8551d208530ec93c5697ca5591ad52bfb228
       F001: CLOSED
       16K-C document: docs/slice16k_c_first_user_capacity_model.md
       16K-D authority:
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IMPLEMENTATION-AUTH-001
         — AUTHORIZED
       Exact 16K-D parent: 33a031b6a1bbda0b3b80fa96c8bff0fdfcece06f
       Exact independently accepted 16K-D technical subject:
         32e52024df47b9add7ce02675a1d40555ac55eae
       Exact independently accepted 16K-D evidence subject:
         70abf3003ba37cd983772e084f9616fe3678a17a
       16K-D independent review (IR-001):
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-001
         — REWORK REQUIRED (F001) — preserved as provenance
       16K-D rework authority:
         S16-K-D-D0-BASELINE-EVIDENCE-PROVENANCE-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D rework subject:
         32e52024df47b9add7ce02675a1d40555ac55eae
       16K-D independent review (IR-002):
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002 — ACCEPT
       16K-D IR-002 acceptance-record authority:
         S16-K-D-DENSE-CUDA-PROFILING-BASELINE-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-D acceptance-record parent:
         70abf3003ba37cd983772e084f9616fe3678a17a
       16K-D branch: implementation/16k-d-dense-cuda-profiling
       16K-D D0: BASELINE COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D F001: CLOSED
       16K-D experimental-plan reconciliation authority:
         S16-K-D-EXPERIMENTAL-PLAN-RECONCILIATION-AUTH-001 — AUTHORIZED
       Exact 16K-D reconciliation parent:
         c801401a486c6ecd425840649fdd6f6893c50f18
       Exact 16K-D reconciliation tip / D1 tooling parent:
         4449f0053faf972726955db889e83ffcda8a2143
       16K-D experimental plan: RECONCILED (docs-only)
       16K-D D1 stall-attribution tooling authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling parent:
         4449f0053faf972726955db889e83ffcda8a2143
       16K-D D1 tooling IR-001:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-001
         — REWORK REQUIRED (F001) — preserved
       16K-D D1 tooling rework authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling rework parent:
         9690ffb7b55502c8060563e94e3a8cf024c82360
       16K-D D1 tooling IR-002:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002 — ACCEPT
       16K-D D1 tooling IR-002 acceptance-record authority:
         S16-K-D-D1-STALL-ATTRIBUTION-DIAGNOSTIC-TOOLING-IR-002-ACCEPTANCE-RECORD-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 tooling acceptance-record parent:
         c98d878e2e1327e984e60ceb59e507b6965962fe
       Exact independently accepted 16K-D D1 tooling technical subject:
         433725952c15a2feed4b65986d03e254d08d1568
       Exact independently accepted 16K-D D1 tooling evidence/docs subject:
         c98d878e2e1327e984e60ceb59e507b6965962fe
       16K-D D1 tooling: COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D D1 tooling F001: CLOSED
       16K-D D1 tooling contract: dense-cuda-profile-v2
       16K-D D1 scientific matrix freeze authority:
         S16-K-D-D1-SCIENTIFIC-MATRIX-FREEZE-AUTH-001 — AUTHORIZED
       Exact 16K-D D1 matrix freeze parent:
         016e338bf2b848e30cd89c7ba6ace6e6f39d1139
       16K-D D1 matrix freeze document:
         docs/slice16k_d_d1_scientific_matrix_freeze.md
       16K-D D1 scientific execution authority:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 scientific execution parent:
         0ecf2f74e4d283f59ab932abbdaee6ebb821a5ac
       Exact 16K-D D1 scientific execution subject:
         177620a3440c310759775dbf303420b80df7a05c
       Exact 16K-D D1 sealed cell evidence tip:
         4326586fe0ce3b7ca4c40ded743272d72ba53036
       16K-D D1 scientific IR-001:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-001
         — REWORK REQUIRED (F001 analysis) — preserved
       16K-D D1 analysis publication rework authority:
         S16-K-D-D1-SCIENTIFIC-ANALYSIS-PUBLICATION-REWORK-AUTH-001
         — AUTHORIZED
       Exact 16K-D D1 analysis rework parent:
         4326586fe0ce3b7ca4c40ded743272d72ba53036
       16K-D D1 scientific IR-002:
         S16-K-D-D1-STALL-ATTRIBUTION-SCIENTIFIC-EXECUTION-IR-002 — ACCEPT
       Exact independently accepted 16K-D D1 analysis publication subject:
         7be6a2b5c7ca7b521f0c642d6a024a1e421d6636
       16K-D D1 F001: CLOSED
       16K-D D1: COMPLETE / INDEPENDENTLY ACCEPTED
       16K-D D2 practical execution optimization design authority:
         S16-K-D-D2-PRACTICAL-EXECUTION-OPTIMIZATION-DESIGN-AUTH-001
         — AUTHORIZED
       Exact 16K-D D2 design parent:
         7be6a2b5c7ca7b521f0c642d6a024a1e421d6636
       16K-D D2 design document:
         docs/slice16k_d_d2_practical_execution_optimization_design.md
       16K-D status: D2 PRACTICAL EXECUTION OPTIMIZATION DESIGN COMPLETE /
         READY FOR INDEPENDENT REVIEW
       16K-D D2: DESIGN ONLY / EXECUTION NOT AUTHORIZED
       16K-D program pivot: scientific optimization →
         bounded product-engineering optimization
       16K-D document: docs/slice16k_d_dense_cuda_profiling.md
       16K-D evidence: docs/evidence/16k_d_dense_cuda/
       16K-D D1 tooling evidence:
         docs/evidence/16k_d_dense_cuda_tooling/
       16K-D D1 scientific evidence:
         docs/evidence/16k_d_dense_cuda/d1/
       16K-D authoritative current lane: CUDA / BF16 / batch 32 / SDPA
       16K-D frozen proxy usability (§9.4): median ≤10 min; no run >12 min;
         3 clean cold confirmations; 16K-F full-corpus ≤60 min
       16K-D practical sequence:
         D0 → D1 attribution → D2 practical execution optimization → decision
       16K-D mechanical D2→D3→D4→D5 sequence: SUPERSEDED
       16K-D closed under this design AUTH:
         D2 harness/execution / FP16/CPU calls / model replacement /
         mechanical D3–D5 / production/default / threshold changes /
         HTTP-500 reopen / 16K-E→G / main
       16K-E → 16K-G: NOT AUTHORIZED
       Main promotion: NOT AUTHORIZED
       Historical closeout disposition (inventory I-11): DEFERRED / NOT REQUIRED
         / NOT AUTHORIZED — preserved as provenance; not rewritten
     Slice 16: COMPLETE / HUMAN ACCEPTED / CANONICAL
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

POST-M7 CANDIDATE-01  PLANNING REGISTERED
     Answer-level user feedback / continuous evaluation
     DESIGN NOT OPEN
     IMPLEMENTATION NOT AUTHORIZED
     Addendum: docs/slice16g_gap_registry_addendum.md

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
knowledge workspace**); Amendment A2 is **ACCEPTED / LOCKED / SEALED** at
`dce3456e519cb6c96570e20f5af800d00cafb5a7` (closeout
`f0bdf78d0ae6a79737055d324b22fc35e1e501f5`); **16D-A** is **COMPLETE /
ACCEPTED / SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`; observed
16D-B1 candidate `6b652400…` has **PRODUCT ACCEPTANCE WITHHELD**; B1
foundation remediation is **ACCEPTED / SEALED** (implementation
`c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout
`b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`); **16D-B2** is
**COMPLETE / ACCEPTED / SEALED** at
`baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`; **16D-B3** is **COMPLETE / ACCEPTED / SEALED** at
`9c178ffb033cde41849379fc914f321697ff8691`; **16D-C** is
**COMPLETE / ACCEPTED / SEALED** at `0381e0461f68c5fc09e7be2c7699d434e8b8a9cb`
(A4 **ACCEPTED / LOCKED / SEALED**). Slice 16 overall is
**COMPLETE / HUMAN ACCEPTED / CANONICAL** (final closeout HA-001 on subject
`c4ba1e7…`; canonical main promotion COMPLETE / EXECUTED at `feab2b2…`).

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

**Slice 16 — Portfolio Demo UI:** **DESIGN AUTHORITY ACCEPTED / LOCKED**; **16A COMPLETE / ACCEPTED**; **16B COMPLETE / ACCEPTED**; **16C COMPLETE / ACCEPTED** at `936e41446eb1e3697f6b7d245659831f19cf0613`; **Amendment A1 ACCEPTED / LOCKED** at `5060e2aeb4825f265072a1f870c3c963eace3b30` (Seneca — Grounded knowledge workspace); **Amendment A2 ACCEPTED / LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7`; **16D-A COMPLETE / ACCEPTED / SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`; observed 16D-B1 candidate `6b652400…` **PRODUCT ACCEPTANCE WITHHELD**; B1 foundation remediation **ACCEPTED / SEALED** (implementation `c68cc3f8f16a2588ba093886f3e48e1c7037f83f`; verified closeout `b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`); legacy B1 product UX **PRODUCT ACCEPTANCE WITHHELD / NOT SEALED**; **16D-B2 COMPLETE / ACCEPTED / SEALED** at `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`; **16D-B3 COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691` (A3 **ACCEPTED / LOCKED / SEALED**); **16D-C COMPLETE / ACCEPTED / SEALED**; **16E COMPLETE / ACCEPTED / SEALED** (Engineering `3e1ce4c94fc511abb4e1d94bd194736d5497e64f`; Workspace source-loading remediation `9dd2b008ebf9feee279dc6d0e58fafb006288ee5`; tip `9cd5528ab6c6e22d2dca55aca221b65eac50269e`); **16F COMPLETE / ACCEPTED / SEALED** at `f25f8358aead7fcfe161fff388012cec23b5a573` ([`docs/slice16f_closeout.md`](docs/slice16f_closeout.md)); **16G-D0 ACCEPTED / FROZEN** ([`docs/slice16g_gold_lab_games_pedagogy_design.md`](docs/slice16g_gold_lab_games_pedagogy_design.md)); **16G-I1…I5 / GAP-16G-01 ACCEPTED**; **GAP-16G-02 CLOSEOUT ACCEPTED / PROMOTED TO MAIN** (`HA-001` / IR-002; subject `e5d116b8…`; main promotion **COMPLETE** at `f7fb999…`) ([`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](docs/gap16g_02_gold_baseline_bootstrap_closeout.md)); **16G-I6 COMPLETE / ACCEPTED** (IR-002 **ACCEPT**; exact candidate `cc7ff520eb146fa555f2b48e1f7dcc89a7952729`); **16G IMPLEMENTATION COMPLETE / ACCEPTED**; **16H COMPLETE / ACCEPTED** (16H-IR-003 **ACCEPT**; 16H-HA-001 **ACCEPTED**; exact subject `01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`); **9G DEFERRED / NOT AUTHORIZED**; Slice 16 overall **COMPLETE / HUMAN ACCEPTED / CANONICAL**
- Authority: [`docs/slice16_design_authority.md`](docs/slice16_design_authority.md)
  (S16-D01 … S16-D35; **ACCEPTED / LOCKED**; A2 supersedes enumerated clauses only)
- AUTHORITY SHA: `e2e7475076ad18d4c4ae8d939389ceeffdeff6d8`
- Amendment A1: [`docs/slice16_amendment_a1_seneca_product_ux.md`](docs/slice16_amendment_a1_seneca_product_ux.md)
  (**ACCEPTED / LOCKED** at `5060e2aeb4825f265072a1f870c3c963eace3b30`;
  supplemental design authority; does **not** authorize later phase implementation)
- Amendment A2: [`docs/slice16_amendment_a2_conversational_grounding.md`](docs/slice16_amendment_a2_conversational_grounding.md)
  (**ACCEPTED / LOCKED / SEALED** at `dce3456e519cb6c96570e20f5af800d00cafb5a7`;
  closeout `f0bdf78d0ae6a79737055d324b22fc35e1e501f5`; A2 acceptance alone
  did **not** authorize B2 / B3 / C)
- Implementation plan: [`docs/slice16_implementation_plan.md`](docs/slice16_implementation_plan.md)
  (16A–16H; plan **ACCEPTED**; **16A/16B/16C/16D-A/16D-B2 COMPLETE / ACCEPTED**;
  A2 B1/B2/B3 Ask decomposition; B1 rem **ACCEPTED / SEALED**;
  **16D-B3 COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691`; A3 **ACCEPTED / LOCKED / SEALED**; **16D-C COMPLETE / ACCEPTED / SEALED**)
- **16A** workspace foundation: **COMPLETE / ACCEPTED** at
  `e73959be508541a1c50d4919606aaf3157a5fa8a`
  ([`docs/slice16a_workspace_foundation.md`](docs/slice16a_workspace_foundation.md))
- **16B** workspace lifecycle API: **COMPLETE / ACCEPTED** at
  `eb8baefc6e3eaf7df33668c85fbbfef22364bb0e`
  ([`docs/slice16b_workspace_lifecycle_api.md`](docs/slice16b_workspace_lifecycle_api.md))
- **16C** React shell / source-management UI: **COMPLETE / ACCEPTED** at
  `936e41446eb1e3697f6b7d245659831f19cf0613`
  ([`docs/slice16c_react_shell_source_ui.md`](docs/slice16c_react_shell_source_ui.md))
- **16D-A** Seneca product foundation & query-scope substrate:
  **COMPLETE / ACCEPTED / SEALED** at `4f8962f2893ab433e6ea269ad54e46f67771ca70`
  ([`docs/slice16d_a_seneca_product_foundation_query_scope.md`](docs/slice16d_a_seneca_product_foundation_query_scope.md))
- Last sealed implementation baseline: `a952a75bc07191b213a5113eee53cb967fef8326`
- Observed 16D-B1 candidate: `6b6524001f063a628505f572e7ca13d954a38260`
  (**OBSERVED CANDIDATE / PRODUCT ACCEPTANCE WITHHELD / NOT SEALED**)
- B1 foundation upload remediation: **ACCEPTED / SEALED**
  (implementation `c68cc3f8f16a2588ba093886f3e48e1c7037f83f`;
  verified closeout `b5fa1e8572ec79c0e68aa3fa6fc6c024d9e25d90`;
  [`docs/slice16d_b1_upload_foundation_remediation.md`](docs/slice16d_b1_upload_foundation_remediation.md))
- Legacy B1 Ask/Evidence product UX: **PRODUCT ACCEPTANCE WITHHELD / NOT SEALED**
  (F7/F8/F9/F10 remain downstream to B3 where applicable)
- **16D-B2:** **COMPLETE / ACCEPTED / SEALED** at
  `baa16eba36d1f9d0e8bbfdbdc8cb4b93a6e31149`
  ([`docs/slice16d_b2_grounded_answer_v2.md`](docs/slice16d_b2_grounded_answer_v2.md);
  Rework 1 complete; independent review PASSED; human acceptance ACCEPTED)
- **16D-B3:** **COMPLETE / ACCEPTED / SEALED** at
  `9c178ffb033cde41849379fc914f321697ff8691`
  ([`docs/slice16d_b3_conversational_workspace.md`](docs/slice16d_b3_conversational_workspace.md);
  A3 **ACCEPTED / LOCKED / SEALED** at `da1082d95630c12eaf0ce1a3b8d005aaa60d2f73`)
- **16D-C:** **COMPLETE / ACCEPTED / SEALED** at
  `0381e0461f68c5fc09e7be2c7699d434e8b8a9cb`
  ([`docs/slice16d_c_training_mode.md`](docs/slice16d_c_training_mode.md);
  A4 **ACCEPTED / LOCKED / SEALED**; closeout [`docs/slice16d_c_a4_closeout.md`](docs/slice16d_c_a4_closeout.md))
- Historical pre-design frame: [`docs/slice16_portfolio_ui.md`](docs/slice16_portfolio_ui.md)
  (contextual only)
- UI remains an adapter/client of `src/offline_rag/app/` (no direct Qdrant /
  retriever / generator access; no UI-owned RAG pipeline) — S16-D03
- Canonical `/query` remains independent single-turn `grounded_v1`; factual
  conversational memory remains forbidden; A2 adds linguistic conversation
  turns above that pipeline (activated supersession) — S16-D17 / A2
- Evaluation surfaces are read-only presentation of accepted artifacts; no live
  scientific knobs — S16-D20 / S16-D21
- Gold Lab redesigns adjudication workflow granularity while preserving
  GoldDataset v1 / Silver→Gold truth criteria — S16-D23–S16-D34
- **16D-C** / A4 closeout complete; **16E** is **COMPLETE / ACCEPTED / SEALED**;
  **16F** is **COMPLETE / ACCEPTED / SEALED**
  ([`docs/slice16f_closeout.md`](docs/slice16f_closeout.md));
  **16G-D0** is **ACCEPTED / FROZEN**
  ([`docs/slice16g_gold_lab_games_pedagogy_design.md`](docs/slice16g_gold_lab_games_pedagogy_design.md));
  **16G-I1…I5** and **GAP-16G-01** are **ACCEPTED**;
  **GAP-16G-02** is **CLOSEOUT ACCEPTED** (`HA-001`; IR-002 **ACCEPT**;
  subject `e5d116b8…`)
  ([`docs/gap16g_02_gold_baseline_bootstrap_closeout.md`](docs/gap16g_02_gold_baseline_bootstrap_closeout.md));
  **main promotion** is **COMPLETE** (`MAIN-PROMOTION-AUTH-001` **EXECUTED**;
  promoted main `f7fb999…`);
  **16G-I6** is **COMPLETE / ACCEPTED** (IR-002 **ACCEPT**; exact candidate
  `cc7ff520eb146fa555f2b48e1f7dcc89a7952729`);
  **16G** is **IMPLEMENTATION COMPLETE / ACCEPTED**;
  **16H** is **COMPLETE / ACCEPTED** (16H-IR-003 **ACCEPT**; 16H-HA-001
  **ACCEPTED**; exact subject `01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`);
  **9G** remains **DEFERRED / NOT AUTHORIZED**; Slice 16 overall is
  **COMPLETE / HUMAN ACCEPTED / CANONICAL** (`S16-FINAL-CLOSEOUT-IR-001` — ACCEPT;
  `S16-FINAL-CLOSEOUT-HA-001` — ACCEPTED; exact subject `c4ba1e7…`;
  technical residual verdict **CLEAR**; canonical main promotion
  **COMPLETE / EXECUTED** at `feab2b2…`)
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

**Post-M7 candidate — Answer-level user feedback / continuous evaluation:**
**PLANNING REGISTERED / DESIGN NOT OPEN / IMPLEMENTATION NOT AUTHORIZED**
([`docs/slice16g_gap_registry_addendum.md`](docs/slice16g_gap_registry_addendum.md)
as `NEXT-MILESTONE-CANDIDATE-01`). Named planning candidate only — not a formal
milestone number yet (Milestone 8 remains a historical stub superseded by
Slice 18). Candidate direction: response-level thumbs; optional
structured/free-text feedback; exact response provenance; append-only feedback
history; observational product metrics; reviewed bridge to regression
candidates. Explicitly **not** Gold, **not** benchmark truth, **not** automatic
training data, and **not** automatic promotion authority.

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
- [x] Portfolio Demo UI (Slice 16 — design **ACCEPTED / LOCKED** at `e2e7475…`; **16A COMPLETE / ACCEPTED** at `e73959be…`; **16B COMPLETE / ACCEPTED** at `eb8baef…`; **16C COMPLETE / ACCEPTED** at `936e414…`; **A1 ACCEPTED / LOCKED** at `5060e2ae…`; **A2 ACCEPTED / LOCKED / SEALED** at `dce3456e…`; **16D-A COMPLETE / ACCEPTED / SEALED** at `4f8962f…`; observed B1 `6b652400…` **ACCEPTANCE WITHHELD**; B1 upload remediation **ACCEPTED / SEALED** at `c68cc3f8…` / closeout `b5fa1e85…`; **16D-B2 COMPLETE / ACCEPTED / SEALED** at `baa16eba…`; **16D-B3 COMPLETE / ACCEPTED / SEALED** at `9c178ffb…`; **16D-C COMPLETE / ACCEPTED / SEALED** at `0381e046…`; A4 **ACCEPTED / LOCKED / SEALED**; **16E COMPLETE / ACCEPTED / SEALED** at Engineering `3e1ce4c9…` / remediation `9dd2b008…`; **16F COMPLETE / ACCEPTED / SEALED** at `f25f835…`; **16G-D0 ACCEPTED / FROZEN**; **16G-I1…I5 / GAP-16G-01 ACCEPTED**; **GAP-16G-02 CLOSEOUT ACCEPTED / PROMOTED TO MAIN** (`HA-001` / IR-002; subject `e5d116b8…`; main promotion **COMPLETE** at `f7fb999…`); **16G-I6 COMPLETE / ACCEPTED** (IR-002 **ACCEPT**; exact candidate `cc7ff520eb146fa555f2b48e1f7dcc89a7952729`); **16G IMPLEMENTATION COMPLETE / ACCEPTED**; **16H COMPLETE / ACCEPTED** (16H-IR-003 **ACCEPT**; 16H-HA-001 **ACCEPTED**; exact subject `01a4a984d438d5bb7c4e3d0fa2f5bb908e0b4a10`); **9G DEFERRED / NOT AUTHORIZED**; Slice 16 overall **COMPLETE / HUMAN ACCEPTED / CANONICAL**)
- [ ] Regression CI (Slice 17 — **PLANNED / DESIGN NOT OPEN**)
- [ ] Portfolio release package (Slice 18 — **PLANNED / DESIGN NOT OPEN**)
- [ ] Milestone 7 closeout (**NOT AUTHORIZED**)
- [ ] Container image size / CPU–CUDA variants ([issue #1](https://github.com/cschrupp/offline-rag/issues/1) — **DEFERRED**)

**M7 release direction (not a Slice-15 exit criterion):** a reviewer can use the
accepted product/API surface and, after Slice 16 implementation (16A/16B/16C
and 16D-A/16D-B2 accepted; A1/A2 accepted/locked/sealed; B1 upload remediation
**ACCEPTED / SEALED**; legacy B1 product UX acceptance withheld; 16D-B3
COMPLETE / ACCEPTED / SEALED; 16D-C COMPLETE / ACCEPTED / SEALED; 16E COMPLETE / ACCEPTED / SEALED),
inspect evidence flow through a UI that remains a client of that surface —
without expanding product query scientific knobs.

Milestone **6** remains **COMPLETE / ACCEPTED** at `dcc6b07…`. Milestone **7**
remains **IN PROGRESS** (Slice 15 through **15H** landed; Slice 16 design
**ACCEPTED / LOCKED**; **16A/16B/16C/16D-A/16D-B2 COMPLETE / ACCEPTED**;
Amendment A1 **ACCEPTED / LOCKED**; Amendment A2 **ACCEPTED / LOCKED /
SEALED**; B1 foundation remediation **ACCEPTED / SEALED**; **16D-B3
COMPLETE / ACCEPTED / SEALED** at `9c178ffb033cde41849379fc914f321697ff8691`; **16D-C** COMPLETE / ACCEPTED / SEALED;
**Slices 17–18**, and **M7 closeout** remain **NOT AUTHORIZED**). Performance
optimization,
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
