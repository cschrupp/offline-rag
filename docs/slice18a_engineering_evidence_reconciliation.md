# Slice 18A-0 — Engineering Evidence Audit and Design Freeze

**Status:** Evidence audit complete; design proposal only; implementation not
authorized.

**Audit baseline:** canonical `main` at
`0a1b5a45bff94ae12c8fe8d423c825572bc1c480`

**Branch:** `feature/slice18a-engineering-evidence-reconciliation`
**Scope:** claim/evidence reconciliation for a future read-only Engineering
surface. This document does not change the registry, exporter, generated
manifest, or UI.

## 1. Current project disposition

- Slice 17 — Regression CI: **COMPLETE / HUMAN ACCEPTED / PROMOTED**. Hosted
  backend and frontend CI passed on the promoted head; bounded lint scope and
  repository-wide Ruff debt remain accurately distinguished.
- REL-01 — CPU release packaging: **COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN
  ACCEPTED / PROMOTED**. The evidence closeout is on canonical `main` at
  `0a1b5a45`. The default release image is CPU-only. A separate CUDA release
  image remains **DEFERRED**; CUDA-capable developer installs/profile support
  remain distinct from a CUDA release artifact.
- Slice 18A: **OPEN — evidence audit and design freeze only**. This phase
  produces a reviewed claim/evidence map and a proposed presentation design.
- Slices 18B–18D: **NOT AUTHORIZED**. No registry, exporter, manifest, UI,
  release workflow, or portfolio publication changes are included here.

Historical roadmap and evidence documents retain their original status as of
the event they recorded. Their historical wording must not be read as current
project disposition; the live summaries in `ROADMAP.md` and `docs/BACKLOG.md`
are updated separately.

## 2. Evidence audit matrix

“Authority” below identifies the repository evidence/disposition, not a claim
that every observation is a production guarantee. “Currency” describes whether
the claim is a current configuration fact, a currently applicable contract, or
historical/descriptive evidence. “Include?” is a proposal for review, not an
approval to publish.

| Reviewer question | Proposed answer/claim | Evidence source | Authority | Decision effect | Currency | Machine-extracted? | Current product relevance | Include? |
|---|---|---|---|---|---|---|---|---|
| What configuration does a canonical install start with, and why? | `config/base.yaml` sets `strict_offline: true`, deployment profile `standalone_ollama`, Qwen3 0.6B embeddings (1024 dimensions, `device: auto`), BM25 lexical retrieval, RRF fusion, enabled BGE reranking, and parent context. This is the checked-in baseline, not every operator's effective settings. | `config/base.yaml`; REL-01 qualification; compute resolver and settings-ownership contracts | Canonical config; REL-01 accepted and promoted | Local/strict-offline behavior and profile resolution are reproducible; actual deployments can override permitted settings | Current for repository defaults; deployment-specific values vary | Config fields can be extracted; explanation of why is curated and cited | High | Yes, with “repository default” qualifier |
| What retrieval quality/cost tradeoff has been measured? | Slice 9H-P reports six descriptive arms on `full-22` and `human-16`; query-prompt dense and hybrid+rereanker scored well on these small populations, while reranking had much higher measured latency. Arm ordering changes by population; no winner or production promotion follows. The current config uses lexical + RRF + reranker. | `docs/pilots/slice9h_p_results.md`; registry `retrieval.slice9hp`; `config/base.yaml`; `performance.slice14c` result artifacts | Accepted pilot, explicitly non-promotional; 14C authoritative descriptive evidence, no promotion | Explains evidence and costs without justifying a new winner | Measurements historical; configured pipeline current | Existing 14C is extracted; Slice 9H numbers are curated and hash-bound only | High | Yes, if descriptive, population-limited, and latency caveats remain adjacent |
| What supports grounded answers and citations? | The application performs retrieval and citation authority locally; generated answer text is validated against locally assembled evidence. The 10E comparison is a development-only prompt pilot with same-model self-judge limitations. Run_002 provides five grounded queries in each accepted cold/warm cell; REL-03 separately demonstrated external generation while citation authority stayed local. | `docs/pilots/slice10e_generation_prompt_ab.md`; `RUN_002_EVIDENCE_INDEX.md`; REL-03 live smoke; generation/citation contracts | 10E non-promotional; run_002 Human accepted scoped beta; REL-03 live qualified/promoted | Demonstrates bounded product behavior, not universal answer accuracy | Current architecture; individual campaign results remain population-specific | Run_002 identities/hashes are fixed; 10E metrics curated; runtime traces could be extracted in future | High | Yes, distinguish architecture contract, user-observed behavior, and measured rates |
| Does Seneca work on CPU and CUDA? | Default release package is CPU-only and AUTO selects the qualified CPU ONNX FP32 profile. CUDA FP16 has separate local/runtime qualifications, including the bounded 90 MiB PDF campaign on the represented host. This does not mean a CUDA release image exists or that CUDA is universally qualified. | `docs/evidence/rel01/QUALIFICATION.md`; `docs/evidence/large_source_capacity/cuda_90m/CUDA_90M_QUALIFICATION_ASSESSMENT.md`; L5 assessment; compute profiles | REL-01 accepted/promoted; CUDA scientific qualification accepted for represented host/workload; CPU L5 through confirmed Q100 class | Supports honest portability statements and explains the deferred CUDA release artifact | Current packaging; host-specific qualification remains bounded | REL-01 values/config are machine-readable in artifacts; L5/CUDA campaign values are mostly artifact-derived but not currently presented by the registry | High | Yes, with release-image vs developer/runtime profile distinction |
| What large-source size is qualified? | CPU L5 passed Q100 (96,152,520-byte PDF) with an independent confirmation; Q250 was invalid evidence due host termination and Q512 was not run. A separate CUDA campaign passed through the existing 90 MiB product envelope on its represented RTX 2080 Super host. Product limits and profile-aware admission are policy, not blanket capacity guarantees. | `L5_QUALIFICATION_ASSESSMENT.md`, L5 evidence index and cell JSON; `CUDA_90M_QUALIFICATION_ASSESSMENT.md`; L6 policy and parser corrective | Accepted qualification with explicit partial/host-scoped outcome; policy implementation separately accepted | Constrains accurate large-source claims and operational warnings | Current product policy; empirical cells are bounded to specific parser/profile/host conditions | Source fixture sizes and result fields machine-extractable from JSON; caveat and applicability curated | High | Yes, only with profile/host/fixture boundaries and Q250/Q512 disposition |
| What does CI/release engineering guarantee? | Slice 17 provides hosted deterministic backend/frontend lanes with 209 backend and 459 frontend tests in its final accepted run; it does not certify the full repository test suite or GPU/model/corpus performance. REL-01 packages the CPU default release image and records image/runtime checks. | `docs/evidence/slice17/IMPLEMENTATION_RESULT.md`, hosted run `42641831431`; REL-01 qualification | Slice 17 accepted/promoted; REL-01 accepted/promoted | Shows repeatable checks and their bounded scope | Current workflows and image subject to future change | CI counts/status and image metadata can be machine-extracted; bounded test set/risk interpretation curated | High | Yes, explicitly say which lanes are and are not covered |
| What changed in REL-01 packaging? | Final CPU image measured 2,346,582,188 bytes on the recorded Docker Desktop/WSL2 host, 77.52% smaller than the same-host baseline. CPU Torch has no CUDA build, no `nvidia-*` distributions, and no provisioned Seneca embedding/reranker/generator weights are in the image. Dependency-owned RapidOCR assets remain. | `docs/evidence/rel01/QUALIFICATION.md`, `BASELINE.md`, accepted closeout `0a1b5a45` | Final independent review ACCEPT; Human acceptance and promotion verified | Supports packaging/result claims, not universal image size or OCR asset absence | Current accepted release packaging measurement; host/metric scoped | Image digest/size/package inventory machine-readable; percentage is deterministic derivation; explanatory boundary curated | High | Yes, include exact metric/host and allowed dependency resources |
| What does REL-03 external inference do? | Optional operator-selected OpenRouter profile externalizes only generation for grounded answers, explicit conversation actions, and Gold authoring. Retrieval, embeddings, reranking, citation creation/validation, and Gold truth remain local. A bounded live smoke completed three intended inference calls and secret audit found no persisted key/header values. | `docs/rel03_external_inference_demo_profile.md`; `REL03_P0_LIVE_SMOKE.md` | Implementation Human accepted, live-qualified, promoted; not hosted deployment | Defines a safe inference boundary and demonstrates the seam | Current profile contract; smoke is point-in-time | Profile config is machine-extractable; call count and audit counts derive from evidence; architecture wording curated | High | Yes, clearly label optional profile and no hosted deployment claim |
| What happened across Conversation 01A → 01B → 01C? | 01A planner feasibility was archived after a negative dev pilot; 01B natural-language router closed NO-GO after a Spanish mixed-intent safety failure; 01C explicit user-requested actions were accepted/promoted, while grounded free-text routing remains deterministic. Do not collapse these into a generic “LLM conversation” claim. | `PILOT_01_RESULTS.md`; `BETA_CONV_01B_CLOSEOUT.md`; BETA-CONV-01C implementation/evidence and current code | 01A/01B archived/NO-GO; 01C Human product accepted/promoted | Shows deliberate capability boundary and why free-text routing remains conservative | 01A/01B historical; 01C current | Commit/status facts machine-extractable; pilot counts derive from immutable report; rationale curated | High | Yes, timeline/contrast is useful, but label each status and avoid implying planner activation |
| Does recovery work? | Live interrupted source-add recovery preserved the published snapshot, surfaced the in-flight operation as `INTERRUPTED`, and allowed a subsequent source addition. This covers the exercised crash path, not every journal phase. Managed TestClient startup hang remains separately tracked and non-blocking. | `docs/evidence/beta_persistence_recovery/RESULT.md`; `docs/BACKLOG.md` TEST-STARTUP-01; 16K-F robustness report | Human accepted live-path result; regression CI evidence separately bounded | Demonstrates a concrete recovery property and its limits | Product behavior evidence current for exercised case; test harness caveat remains | Revision/snapshot/operation fields extractable; scenario conclusion curated | High | Yes, state exact exercised crash point and separate harness limitation |
| What are the security and open-boundary results? | Slice 13B campaign completed but failed closed because a required invariant was unevaluable; this is not a security PASS or proof of coverage completeness. Recovery efficacy was insufficient and product recovery is disabled. Strict-offline remains default; REL-03 external profile is explicit/operator enabled. | `milestone6_agentic_recovery_security.md`; existing registry `security.slice13b`, `recovery.slice12c`; REL-03 profile docs | Security/recovery dispositions authoritative; no broad security-completeness claim | Makes limits and disabled features visible; prevents overclaiming | Current product boundaries plus historical campaign results | Security cohort counts are curated; profile inputs extractable; interpretation curated | High | Yes, prominently show FAIL-closed/disabled and bounded scope |

## 3. Existing Engineering registry audit

The sealed registry currently has six records. The fields `evidence_authority`
and `promotion_status` are present on every record, but neither currently says
whether a claim is current, historical, or superseded. They describe review or
promotion disposition and must not be used as a freshness proxy.

| Existing record | Authority / promotion | Actual temporal/product status | Numeric content and validation | Audit disposition |
|---|---|---|---|---|
| `retrieval.slice9hp` | `accepted` / `non_promotional` | Historical descriptive pilot; no current winner | Two populations × six arms × five metrics (60 values) and population labels/order; curated in registry. Source file SHA-256 is verified, but displayed literal values are not compared to source literals by exporter. | Retain as historical comparison; add explicit currency and literal validation or extract from structured source. |
| `generation.slice10e` | `accepted` / `non_promotional` | Historical development-only prompt pilot; not current prompt authority | Two prompts × eight metrics (16 values), plus full-22 label; curated, source SHA-256 checked, values not literal-validated. | Retain only with self-judge and non-promotion caveats; add currency and literal validation. |
| `recovery.slice12c` | `authoritative` / `disabled` | Historical disposition still accurately describes product recovery disabled | No curated numeric metric. | Retain; clarify that `authoritative` means accepted disposition authority, not feature enabled/current runtime evidence. |
| `security.slice13b` | `authoritative` / `non_promotional` | Historical adversarial campaign; fail-closed, not product security status | Cohort counts 7 adversarial failures, 5 benign failures, zero false positives/passes are curated literals; exporter does not compare them with report text. | Retain with explicit historical currency; preserve fail-closed outcome and no-completeness caveat. |
| `performance.slice14c` | `authoritative` / `non_promotional` | Historical descriptive performance fixture; no configuration promotion | Quality/latency extraction from pinned aggregate and run manifest; exporter extracts and checks source identity. | Retain as historical; it is the only record whose performance values are machine-extracted. |
| `performance.slice14-level-c` | `authoritative` / `non_promotional` | Historical approximate Level-C measurements; distinct population from 14C | Four measured approximate timings and three null/unavailable fields are curated; source hash is checked, displayed literals are not. | Retain with explicit currency and separate population; literal-validate against accepted Markdown or use structured artifacts. |

### Numeric-field audit summary

- Machine-extracted: Slice 14C values generated from `aggregate.json` and
  `run_manifest.json` by `extract_performance_14c()`; source hashes are
  verified and fields are selected through a constrained extraction map.
- Curated and source-hash-bound, but not literal-validated: all 60 Slice 9H-P
  metrics; all 16 Slice 10E metrics; Slice 13B's numeric cohort counts; and
  Slice 14 Level-C's four measured approximate values plus unavailable nulls.
- Non-metric numeric labels (for example `full-22`, `human-16`, `13B`, and
  `Level-C`) are curated context strings, not extracted measurement values.
- The exporter validates metric types, availability, qualifiers, finiteness,
  source paths, and SHA-256 identity. A pinned Markdown hash proves source
  identity, not that a curated number matches the number printed in that file.
- Numeric mismatch risk is therefore concentrated in the curated records;
  Slice 14C is the only current machine-extracted numeric presentation.

### Governance inconsistencies

1. **ADR-004 title is stale as a description of current configuration.** Its
   decision—measure dense and BM25 independently before combining—remains a
   valid historical method. But “Hybrid retrieval is a target, not the
   baseline” conflicts with current `config/base.yaml`, which enables BM25,
   RRF fusion, and the reranker. Proposed amendment: retain the decision and
   historical rationale, then add a dated status note that hybrid/RRF is now
   the repository default and that the old title is not a statement of current
   runtime configuration. No retrieval winner is inferred from this change.
2. **Current roadmap/backlog status drift:** their live summaries still marked
   Slice 17 active and REL-01 active / Slice 18 unopened, despite accepted
   promotion of Slice 17 and REL-01. The live summaries are corrected in this
   documentation commit; dated historical records are retained.
3. **REL-01 status drift:** `docs/rel01_cpu_release_packaging.md` still calls
   implementation review pending and describes Slice 18 as unopened. Its
   historical stage contract remains useful, but its header/current disposition
   is updated to point to the accepted qualification and promotion.
4. **Authority vocabulary is easy to misread:** `authoritative` can describe
   a governing disposition while the feature is disabled or the campaign
   failed. `promotion_status` means product/config promotion in the old
   evidence vocabulary, not Git-branch promotion. Proposed schema text should
   define these meanings and avoid displaying them as a single “current” flag.

## 4. Proposed question-driven Engineering page structure

1. **Overview — What can I rely on?** Current repository defaults, local-first
   boundary, accepted product capabilities, and a short list of what is not
   claimed. Link directly to evidence cards.
2. **Evaluation — What was measured, on which population, and what changed?**
   Retrieval quality/cost; generation/citation observations; corpus and
   large-source limits; every population, qualifier, and caveat beside its
   number.
3. **Runtime and scale — Where does it run and what has been qualified?** CPU
   release image, CUDA runtime/profile evidence, large-source results, and
   distinction between a qualified profile and a CUDA release artifact.
4. **Architecture and operations — Where are the trust boundaries?** Local
   retrieval/citation authority, optional REL-03 generation seam, conversation
   action vs grounded query paths, restart recovery, disabled recovery
   automation, and security evaluation limits.
5. **Build and verification — What is continuously checked?** Slice 17 CI
   lanes, REL-01 image evidence, repository-wide known debt, and explicit
   exclusions from CI.

## 5. Proposed schema changes for a later implementation phase

These are proposals only. No schema or registry changes are made in 18A-0.

- Add a required `currency` field with a small controlled vocabulary such as
  `current`, `historical`, `superseded`, and `not_applicable`. Define it as
  claim temporal/product applicability, independent of evidence acceptance or
  promotion.
- The current family vocabulary is limited to `retrieval`, `generation`,
  `recovery`, `security`, and `performance`. If records for runtime, capacity,
  release engineering, or operations are approved, extend the family vocabulary
  deliberately in the versioned schema rather than overloading `performance`.
- Preserve `evidence_authority`, but document the exact semantics of
  `accepted`, `authoritative`, and `historical`. Do not infer freshness from
  authority.
- Rename or explicitly define `promotion_status` as product/config promotion
  status; do not conflate with Git branch promotion. A later schema version
  should use one term consistently.
- Add `key_facts` as a generic presentation kind for compact, sourced facts
  that do not naturally fit retrieval/generation/performance result schemas.
  Require each fact to carry a source reference, scope/qualifier, and currency.
- For curated numeric facts, add a deterministic literal-validation binding
  (source path, locator, expected value and comparison rule) or migrate values
  into structured source artifacts. A file SHA pin alone is not numeric-value
  validation.
- Continue to fail closed on source hash mismatch and preserve the
  one-directional evidence → registry → exporter → manifest → UI pipeline.

## 6. Proposed architecture diagrams (maximum five)

1. **Evidence publication chain:** frozen evidence → reviewed registry →
   deterministic exporter → static manifest → read-only Engineering UI.
2. **Grounded request trust boundary:** local query/retrieval/reranking/context
   → generator (local or explicitly selected REL-03) → local citation
   validation/response.
3. **Runtime portability:** repository CPU release image vs developer CUDA
   profile, with external provisioned model assets and unchanged AUTO
   resolution.
4. **Conversation lanes:** ordinary factual request → deterministic grounded
   path; explicit action → bounded transformation with conversation
   provenance/no retrieval; rejected mixed/ambiguous intent → clarification or
   grounded path per accepted contract.
5. **Release verification boundary:** deterministic Slice 17 CI + REL-01 image
   qualification, with model/corpus/GPU campaigns shown outside generic CI.

## 7. Proposed registry records

The maximum is six new records. These are the exact proposed identity families
and claims; IDs are placeholders to freeze only after claim review. No record
is added in this phase.

| Proposed record ID | Proposed content | Primary sources | Reason it is necessary |
|---|---|---|---|
| `runtime.configuration-and-profiles` | Checked-in default settings plus qualified CPU/CUDA profile boundary; distinguish CPU release artifact from CUDA-capable developer/runtime support. | `config/base.yaml`; REL-01 qualification; L5/CUDA profile evidence | Answers configuration and portability questions not represented by existing registry records. |
| `retrieval.current-profile-and-tradeoff` | Current config is BM25 + RRF + reranker; historical 9H-P/14C data remain descriptive and do not prove the current config is a universal winner. | `config/base.yaml`; 9H-P report; 14C structured artifacts | Connects current configuration to the actual evidence without mislabeling pilot results. |
| `generation.grounded-citation-evidence` | Local citation construction/validation, scoped 10E prompt evidence, run_002 grounded-query result, REL-03 local citation authority. | 10E report; run_002 index; REL-03 smoke/contract | Answers how generation is supported and what “grounded” means without overstating accuracy. |
| `capacity.large-source-qualified-envelope` | CPU Q100-class qualification; CUDA 90 MiB host-scoped qualification; current admission policy; Q250 invalid evidence/Q512 not run. | L5, L6, CUDA 90 MiB and parser corrective evidence | Gives a precise large-source answer and preserves partial qualification. |
| `release.cpu-packaging-and-ci` | REL-01 image size/runtime boundary and Slice 17 hosted CI scope, with named non-coverage. | REL-01 qualification/closeout; Slice 17 result and run identity | Makes current release engineering independently reviewable and clarifies what CI does not establish. |
| `operations.external-inference-and-conversation` | REL-03 explicit generation-only seam and local trust authority; 01A/01B negative outcomes and 01C explicit-action behavior. | REL-03 contract/smoke; 01A/01B/01C closeouts | Covers current external-inference and conversation boundaries not answered by the existing six records. Keep each subclaim separately sourced within the generic key-facts presentation. |

Recovery and security already have dedicated records (`recovery.slice12c` and
`security.slice13b`); amend those with currency rather than duplicating them.

## 8. Existing records proposed for amendment

Amend existing records rather than duplicating their evidence:

- `retrieval.slice9hp`: add historical currency; literal-validate curated
  metrics or migrate them to a structured source; retain population sensitivity
  and non-promotion caveats.
- `generation.slice10e`: add historical/development-only currency; literal-
  validate all curated metrics; keep same-model self-judge and non-promotion
  caveats.
- `recovery.slice12c`: clarify authoritative disposition vs disabled product
  recovery; add current/historical currency.
- `security.slice13b`: clarify authoritative campaign record vs failed
  fail-closed outcome and non-completeness; add historical currency and literal
  validation for cohort counts.
- `performance.slice14c`: add historical currency and state that its metrics
  are machine-extracted from the bound artifacts.
- `performance.slice14-level-c`: add historical currency; literal-validate
  approximate values and preserve unevaluable nulls/population separation.

Do not amend these sealed records until a later implementation authority
approves the registry/schema migration and exact source bindings.

## 9. Explicit non-scope

- No registry, exporter, generated manifest, UI, architecture-page, or
  engineering-evaluation-page changes.
- No new evidence execution, benchmark, model inference, security campaign, or
  corpus run.
- No retrieval, generation, citation, compute, capacity, recovery, or
  deployment-policy change.
- No CUDA release image; it remains deferred.
- No promotion of 18B, 18C, or 18D and no public portfolio claims beyond
  accepted evidence.
- No rewriting historical accepted evidence or turning descriptive evidence
  into a promotional winner.

## 10. Recommendation

Approve the claim/evidence map and proposed page/schema boundaries before any
registry/exporter/manifest/UI implementation. The largest presentation risks
are (a) presenting historical small-population comparisons as current winners,
(b) conflating accepted evidence with product promotion/currentness, (c)
mistaking a CPU release image for absence of CUDA runtime support, and (d)
presenting bounded qualification as a universal performance/security claim.

**Stop point:** Slice 18A-0 audit is ready for review. No downstream
implementation has been performed or is authorized by this document.
