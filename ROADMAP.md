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

Formal **9H** remains **FROZEN** behind future 9G.

The 22-case / human-16 9F benchmark remains a **development/regression fixture
only** (`gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`).

**Milestone 5 development checkpoint reached** (Slice 10A–10E). Next major
track: Milestone **6** — Agentic recovery and security (not started).

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
candidate-by-candidate workflow for production gold.

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
(**design contract drafted**; implementation not started — see
[`docs/milestone6_agentic_recovery_security.md`](docs/milestone6_agentic_recovery_security.md)).
Order: Slice **11** → **12** → **13**.


---

## Milestone 6 — Agentic recovery and security

**Status:** Slice **11 COMPLETE / ACCEPTED**; Slice **12A COMPLETE / ACCEPTED**; Slice **12B COMPLETE / ACCEPTED**; **12C design contract LOCKED** (OD-12C-1…8); **12C implementation not accepted**; **12C measurement not started**  
**Baseline:** `1983ff1376ea27fc1e8774b35136dc8c8ec93f40`  
**Design authority:** [`docs/milestone6_agentic_recovery_security.md`](docs/milestone6_agentic_recovery_security.md)  
**OD-12 design-lock baseline:** `4194d525211d994b97aa8abba93237cd8a23cbb9`  
**12B docs closeout / 12C authority baseline:** `692da961904e16a2a1bfa1ee1c2ece82a097df60`

**Implementation order (locked):** Slice **11** → Slice **12** → Slice **13**

Do **not** interpret the checklist below as authorization to build LangGraph
before a formal evidence-sufficiency gate exists (ADR-008).

- [x] Slice 11 — Evidence sufficiency & abstention policy (11A→11B→11C) — **COMPLETE / ACCEPTED**
- [ ] Slice 12 — Conditional LangGraph retrieval recovery (**12A/12B ACCEPTED**; **12C design LOCKED** → harness → measure-once)
- [ ] Slice 13 — Prompt-injection & security harness (13A→13C; optional 13D NeMo)

Checklist detail (same order; not startable out of sequence):

- [x] evidence sufficiency policy (Slice 11; deterministic first) — **ACCEPTED**
- [x] **12A** project-owned recovery state/protocol contracts, invariants, deterministic replay — **COMPLETE / ACCEPTED**
- [x] bounded query rewrite/retry (**12B**; explicit rewriter + one recovery retrieval) — **COMPLETE / ACCEPTED**
- [ ] recovery vs baseline evaluation (**12C**; design LOCKED; harness/measurement not started)
- [ ] LangGraph adapter / conditional recovery orchestration (**post-12B**; adapter-only per OD-12-3; separately authorized)
- [ ] indirect prompt-injection suite (Slice 13)
- [ ] optional NeMo Guardrails evaluation (Slice 13D; after deterministic controls)

**Next:** Authorize **12C-1** (evaluation harness only) against this design lock. Do **not** run measure-once (**12C-2**) until the harness itself is independently reviewed. Keep `retrieval_recovery.enabled=false` until 12C evidence supports a later human promotion decision. LangGraph remains out / adapter-only if separately authorized later.

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

**Slice 12C design lock**
- **12B docs closeout** `692da96` — authority baseline for 12C
- **OD-12C-1 … OD-12C-8 LOCKED** — paired shared-initial evaluation; frozen Gold + cohort map; trigger census before recovery; Gold-positive recovery efficacy; retrieval-only (no generation/judge); predeclared conclusion states; happy-path no-harm; one measure-once rewrite+retrieval
- **12C-1 harness** / **12C-2 measure-once** — not started
- `retrieval_recovery.enabled=false` remains the default until 12C evidence; LangGraph remains out

**Frozen runtime policy:** `sufficiency-v1` — `empty_context_v1` iff final EvidenceUnit[] is empty; non-empty proceeds to generation; `model_abstain` remains post-generation and distinct. That is the deterministic trigger ADR-008 requires for Slice 12.

**Release criterion:** agentic recovery demonstrates measured benefit and adversarial test results are documented.

LangGraph is not started. No LangGraph dependency has been added. Recovery remains disabled by default until 12C evidence.

## Milestone 7 — Performance and UI

- [ ] stage latency instrumentation
- [ ] memory/VRAM metrics
- [ ] FastAPI service
- [ ] single-container OfflineRAG application image
- [ ] Qdrant Local standalone profile
- [ ] `/data` + `/models` volume contracts
- [ ] retrieval inspector
- [ ] citation source viewer
- [ ] evaluation dashboard

**Release criterion:** a reviewer can interactively compare retrieval modes and inspect evidence flow.

## Milestone 8 — Portfolio release

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

**Release criterion:** repository supports all public quality/security/performance claims with reproducible evidence.

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
