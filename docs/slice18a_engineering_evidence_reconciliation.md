# Slice 18A-0 — Engineering Evidence Audit and Design Freeze

**Current status:** Audit/design is complete. The bounded Slice 18A
implementation is complete and awaiting independent review. Slices 18B–18D
remain unauthorized.

**Audit baseline:** canonical `main` at
`0a1b5a45bff94ae12c8fe8d423c825572bc1c480`

**Branch:** `feature/slice18a-engineering-evidence-reconciliation`
**Scope:** claim/evidence reconciliation for a future read-only Engineering
surface. The original 18A-0 audit commit changed none of the registry,
exporter, generated manifest, or UI; the separately authorized implementation
is recorded in `docs/evidence/slice18a/IMPLEMENTATION_RESULT.md`.

## 1. Current project disposition

- Slice 17 — Regression CI: **COMPLETE / HUMAN ACCEPTED / PROMOTED**. Hosted
  backend and frontend CI passed on the promoted head; bounded lint scope and
  repository-wide Ruff debt remain accurately distinguished.
- REL-01 — CPU release packaging: **COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN
  ACCEPTED / PROMOTED**. The evidence closeout is on canonical `main` at
  `0a1b5a45`. The default release image is CPU-only. A separate CUDA release
  image remains **DEFERRED**; CUDA-capable developer installs/profile support
  remain distinct from a CUDA release artifact.
- Slice 18A-0 audit/design: **COMPLETE**. Slice 18A implementation is
  **COMPLETE / READY FOR INDEPENDENT REVIEW**, within the six-record,
  two-route scope recorded here.
- Slices 18B–18D: **NOT AUTHORIZED**. No release workflow or broader portfolio
  publication is included in Slice 18A.

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
| What configuration does a canonical install start with, and why? | `config/base.yaml` sets `strict_offline: true`, deployment profile `standalone_ollama`, Qwen3 0.6B embeddings (1024 dimensions, `device: auto`), dense + BM25 retrieval, RRF fusion, enabled BGE reranking, and parent context. RRF avoids combining uncalibrated dense/lexical scores; separate reranking keeps retrieval and cross-encoder ranking independently measurable. This is the checked-in baseline, not every operator's effective settings. ADR rationale does not make Slice 9H-P or 14C configuration-promotion evidence; neither established a winner. | `config/base.yaml`; ADR-005/006; Slice 9H-P and 14C non-promotion evidence; REL-01 qualification; compute resolver and settings-ownership contracts | Canonical config; REL-01 accepted and promoted; descriptive retrieval evidence remains non-promotional | Local/strict-offline behavior and profile resolution are reproducible; actual deployments can override permitted settings | Current for repository defaults; deployment-specific values vary; pilot observations historical | Config fields can be extracted; rationale is curated and cited | High | Yes, with “repository default” qualifier and explicit non-promotion caveat |
| What retrieval quality/cost tradeoff has been measured? | Slice 9H-P reports six descriptive arms on `full-22` and `human-16`; query-prompt dense and hybrid+rereanker scored well on these small populations, while reranking had much higher measured latency. Arm ordering changes by population; no winner or production promotion follows. Current `config/base.yaml` is dense + BM25 → RRF → BGE reranker. | `docs/pilots/slice9h_p_results.md`; registry `retrieval.slice9hp`; `config/base.yaml`; `performance.slice14c` result artifacts | Accepted pilot, explicitly non-promotional; 14C authoritative descriptive evidence, no promotion | Explains evidence and costs without justifying a new winner | Measurements historical; configured pipeline current | Existing 14C is extracted; Slice 9H numbers are curated and hash-bound only | High | Yes, if descriptive, population-limited, and latency caveats remain adjacent |
| What does “grounded answer” validation establish? | Seneca validates citation IDs against the current query's `EvidenceUnit[]` and resolves valid IDs to source provenance. It validates response structure and citation membership; it does **not** runtime-prove that answer prose is entailed by, faithful to, or semantically supported by cited text. `Membership validity ≠ semantic support.` 10E is a development-only prompt pilot with same-model self-judge limitations; run_002's five queries per full-corpus cell are bounded functional observations, not a semantic accuracy estimate. | `src/offline_rag/generation/citations.py`; `docs/slice8_grounded_generation.md` (“Membership validity ≠ semantic support”); 10E report; `RUN_002_EVIDENCE_INDEX.md` | Citation membership/runtime contract; 10E non-promotional; run_002 Human accepted scoped beta | Prevents a citation-presence claim from becoming a semantic-grounding guarantee | Contract current; campaigns population-specific | Citation membership is computed at runtime; 10E values curated; run_002 counts and hashes evidence-bound | High | Yes, with explicit semantic-faithfulness limitation |
| What generation boundary does REL-03 add? | Optional operator-selected OpenRouter inference handles generation for grounded answers, explicit conversation actions, and Gold authoring. Retrieval, evidence selection, citation identity/membership validation, and Gold truth remain local; external inference does not prove semantic support. | `docs/rel03_external_inference_demo_profile.md`; `REL03_P0_LIVE_SMOKE.md` | Human accepted, live-qualified, promoted; not hosted deployment | Defines an explicit inference seam and local authority boundary | Current profile contract; smoke is point-in-time | Profile config and call count are machine/evidence-derived; wording curated | High | Yes, distinguish inference transport from evidence/citation authority |
| Does Seneca work on CPU and CUDA? | Default release package is CPU-only and AUTO selects the qualified CPU ONNX FP32 profile. CUDA FP16 has separate runtime and large-PDF scientific qualification on a represented host. This does not mean a CUDA release image exists or that CUDA is universally qualified. | `docs/evidence/rel01/QUALIFICATION.md`; `docs/evidence/large_source_capacity/cuda_90m/CUDA_90M_QUALIFICATION_ASSESSMENT.md`; L5 assessment; compute profiles | REL-01 accepted/promoted; CUDA scientific qualification accepted for represented host/workload; CPU L5 through confirmed Q100 class | Supports honest portability statements and explains the deferred CUDA release artifact | Current packaging; host-specific qualification remains bounded | REL-01 values/config are machine-readable in artifacts; L5/CUDA campaign values are mostly artifact-derived but not currently presented by the registry | High | Yes, with release-image vs developer/runtime profile distinction |
| What is the large-source scientific qualification, and what does product admission allow? | CPU L5 Q100 and confirmation used a 96,152,520-byte PDF (91.70 MiB); Q250 was invalid evidence due host termination and Q512 was not run. The CUDA campaign also used that Q100 fixture and a fresh-tree confirmation on its represented RTX 2080 Super host. Current L6 product PDF limit is 90 MiB. Only a desired set containing a PDF over the ordinary 25 MiB per-source threshold enters the large-PDF admission path, which requires `cpu_onnx_fp32_v1`, 32 GB-class physical memory, `MemAvailable ≥ 19,388,303,360` bytes, and the documented disk-reserve gate. PDFs at or below 25 MiB do not require those large-PDF gates. The CUDA scientific result did not promote CUDA into production large-PDF admission. Keep the 91.70 MiB qualification fixture distinct from the 90 MiB product limit. | `L5_QUALIFICATION_ASSESSMENT.md`, L5 cell JSON; `CUDA_90M_QUALIFICATION_ASSESSMENT.md` and campaign summary; L6 design and implementation result | Accepted, host/profile-scoped scientific qualification; separately accepted L6 product admission policy | Prevents empirical workload qualification from being confused with current product limits | Policy current; measurements bounded to fixture/profile/host | Raw sizes and resource gates are structured; scope and interpretation curated | High | Yes, show scientific envelope and production admission as separate claims |
| What does CI/release engineering guarantee? | Slice 17 provides hosted deterministic backend/frontend lanes with 209 backend and 459 frontend tests in its final accepted run; it does not certify the full repository test suite or GPU/model/corpus performance. REL-01 packages the CPU default release image and records image/runtime checks. | `docs/evidence/slice17/IMPLEMENTATION_RESULT.md`, hosted run `42641831431`; REL-01 qualification | Slice 17 accepted/promoted; REL-01 accepted/promoted | Shows repeatable checks and their bounded scope | Current workflows and image subject to future change | CI counts/status and image metadata can be machine-extracted; bounded test set/risk interpretation curated | High | Yes, explicitly say which lanes are and are not covered |
| What changed in REL-01 packaging? | Final CPU image measured 2,346,582,188 bytes on the recorded Docker Desktop/WSL2 host, 77.52% smaller than the same-host baseline. CPU Torch has no CUDA build, no `nvidia-*` distributions, and no provisioned Seneca embedding/reranker/generator weights are in the image. Dependency-owned RapidOCR assets remain. | `docs/evidence/rel01/QUALIFICATION.md`, `BASELINE.md`, accepted closeout `0a1b5a45` | Final independent review ACCEPT; Human acceptance and promotion verified | Supports packaging/result claims, not universal image size or OCR asset absence | Current accepted release packaging measurement; host/metric scoped | Image digest/size/package inventory machine-readable; percentage is deterministic derivation; explanatory boundary curated | High | Yes, include exact metric/host and allowed dependency resources |
| What does REL-03 external inference do? | Optional operator-selected OpenRouter profile externalizes only generation for grounded answers, explicit conversation actions, and Gold authoring. Retrieval, embeddings, reranking, citation creation/validation, and Gold truth remain local. A bounded live smoke completed three intended inference calls and secret audit found no persisted key/header values. | `docs/rel03_external_inference_demo_profile.md`; `REL03_P0_LIVE_SMOKE.md` | Implementation Human accepted, live-qualified, promoted; not hosted deployment | Defines a safe inference boundary and demonstrates the seam | Current profile contract; smoke is point-in-time | Profile config is machine-extractable; call count and audit counts derive from evidence; architecture wording curated | High | Yes, clearly label optional profile and no hosted deployment claim |
| What happened across Conversation 01A → 01B → 01C? | 01A planner feasibility was archived after a negative dev pilot; 01B natural-language router closed NO-GO after a Spanish mixed-intent safety failure; 01C explicit user-requested actions were accepted/promoted, while grounded free-text routing remains deterministic. Do not collapse these into a generic “LLM conversation” claim. | `PILOT_01_RESULTS.md`; `BETA_CONV_01B_CLOSEOUT.md`; BETA-CONV-01C implementation/evidence and current code | 01A/01B archived/NO-GO; 01C Human product accepted/promoted | Shows deliberate capability boundary and why free-text routing remains conservative | 01A/01B historical; 01C current | Commit/status facts machine-extractable; pilot counts derive from immutable report; rationale curated | High | Yes, timeline/contrast is useful, but label each status and avoid implying planner activation |
| Does query/retrieval recovery work? | Slice 12C evaluated bounded query rewrite/retry; evidence for efficacy was insufficient and product query recovery remains disabled. | `docs/milestone6_agentic_recovery_security.md`; existing registry `recovery.slice12c` | Authoritative disposition; recovery feature disabled | Prevents the disabled query-recovery design from being presented as available | Current product status; evaluation is historical | Status is curated from accepted disposition | High | Yes, state “disabled” and insufficient efficacy evidence |
| Does operational restart recovery work? | In the exercised abrupt API exit during a source-add, the published snapshot remained intact, the operation recovered as `INTERRUPTED`, and a later source addition succeeded in the recovered process. This covers that crash path only. The TestClient startup hang remains separate. | `docs/evidence/beta_persistence_recovery/RESULT.md`; `docs/BACKLOG.md` TEST-STARTUP-01; 16K-F robustness report | Human accepted live-path result; regression CI evidence separately bounded | Demonstrates one concrete process-restart recovery behavior | Product behavior evidence current for exercised case; test harness caveat remains | Revision/snapshot/operation fields extractable; scenario conclusion curated | High | Yes, name it operational restart recovery and keep query recovery separate |
| What are the security and open-boundary results? | Slice 13B campaign completed but failed closed because a required invariant was unevaluable; this is not a security PASS or proof of coverage completeness. Recovery efficacy was insufficient and product recovery is disabled. Strict-offline remains default; REL-03 external profile is explicit/operator enabled. | `milestone6_agentic_recovery_security.md`; existing registry `security.slice13b`, `recovery.slice12c`; REL-03 profile docs | Security/recovery dispositions authoritative; no broad security-completeness claim | Makes limits and disabled features visible; prevents overclaiming | Current product boundaries plus historical campaign results | Security cohort counts are curated; profile inputs extractable; interpretation curated | High | Yes, prominently show FAIL-closed/disabled and bounded scope |

## 3. Existing Engineering registry audit

The sealed registry currently has six records. It has separate
`evidence_authority` and `promotion_status` fields but no currency field.
Authority, currency, and product/config promotion are three distinct axes.
Historical evidence can remain authoritative as a record of a past disposition;
that does not make its claim current.

| Existing record | Authority / promotion | Actual temporal/product status | Numeric content and validation | Audit disposition |
|---|---|---|---|---|
| `retrieval.slice9hp` | `accepted` / `non_promotional` | Historical descriptive pilot; no current winner | Two populations × six arms × five metrics (60 values) and population labels/order; curated in registry. Source file SHA-256 is verified, but displayed literal values are not compared to source literals by exporter. | Retain as historical comparison; add explicit currency and literal validation or extract from structured source. |
| `generation.slice10e` | `accepted` / `non_promotional` | Historical development-only prompt pilot; not current prompt authority | Two prompts × eight metrics (16 values), plus full-22 label; curated, source SHA-256 checked, values not literal-validated. | Retain only with self-judge and non-promotion caveats; add currency and literal validation. |
| `recovery.slice12c` | `authoritative` / `disabled` | Query/retrieval recovery (bounded rewrite/retry) was evaluated; efficacy evidence was insufficient and product query recovery remains disabled. This is distinct from operational restart recovery. | No curated numeric metric. | Keep as the query-recovery disposition; add historical evidence currency while separately stating current disabled status. |
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
  Slice 14C is the only current machine-extracted numeric presentation. This is
  an inventory of existing limitations, not a requirement to launch a broad
  retrospective literal-validation project. Preserve the old source hashes and
  values; migrate old bindings only where inexpensive. For new numeric claims,
  prefer structured extraction or bind the literal to a source locator/value.

### Governance inconsistencies

1. **ADR-004 title is stale as a description of current configuration.** Its
   decision—measure dense and BM25 independently before combining—remains a
   valid historical method. But “Hybrid retrieval is a target, not the
   baseline” conflicts with current `config/base.yaml`, which enables BM25,
   RRF fusion, and the reranker. A dated note was added to `ADR-004` retaining
   the decision/method while clarifying that its title is not current runtime
   configuration. No retrieval winner is inferred from this change.
2. **Current roadmap/backlog status drift:** their live summaries still marked
   Slice 17 active and REL-01 active / Slice 18 unopened, despite accepted
   promotion of Slice 17 and REL-01. The live summaries are corrected in this
   documentation commit; dated historical records are retained.
3. **REL-01 status drift:** `docs/rel01_cpu_release_packaging.md` still calls
   implementation review pending and describes Slice 18 as unopened. Its
   historical stage contract remains useful, but its header/current disposition
   is updated to point to the accepted qualification and promotion.
4. **Three status axes need explicit semantics:** `evidence_authority` should
   describe review standing (`accepted` or `authoritative`); `currency` should
   describe whether a fact is `current` or `historical`; `promotion_status`
   should remain separate and describe product/config promotion, never Git
   branch promotion. The current exporter accepts `historical` in the
   authority vocabulary, but no current record uses it; the proposed schema
   should remove it from authority. A mixed key-facts record uses record-level
   currency by default and a fact-level override only where it deliberately
   contains both current and historical claims.

## 4. Proposed question-driven content within the existing routes

Keep exactly the existing routes: `/engineering/evaluation` and
`/engineering/architecture`. These are conceptual sections and reviewer
questions within the routes, not proposed pages/routes.

**Evaluation route —** What is the current configuration? What was measured,
on which population, and with what effect? What retrieval/cost tradeoff is
observed? What are the generation/citation limits? What large-source workloads
and release checks are qualified? Which results are historical, and what does
CI not cover? Place population, currency, qualifier, and decision effect next
to each metric.

**Architecture route —** How does a question move through snapshot admission,
retrieval, reranking/context, evidence sufficiency, generation, and local
citation-membership validation? Where does the explicit conversation-action
branch diverge? Which boundaries remain local under REL-03? How do snapshot
provenance and runtime portability work? Keep operational restart recovery
separate from disabled query/retrieval recovery.

## 5. Schema and presentation implementation design

These are the reviewed design for Slice 18A implementation. The 18A-0 audit
commit itself made no schema or registry changes.

- Add a required `currency` field with the controlled vocabulary `current` or
  `historical`. Keep it independent of evidence acceptance or product/config
  promotion. Do not add `superseded` or `not_applicable` absent a real claim
  that requires them.
- Record-level currency is the default for its facts. A fact-level currency
  override is allowed only when a record deliberately contains both current
  and historical claims; otherwise keep facts in separate records.
- Extend the current family vocabulary (`retrieval`, `generation`, `recovery`,
  `security`, `performance`) deliberately with `product`, `runtime`, `capacity`,
  `release`, and `conversation` for the six reviewed record families; do not
  overload `performance`.
- Restrict `evidence_authority` to `accepted` or `authoritative`; `historical`
  belongs only in currency. Define authority independently from currentness.
- Rename or explicitly define `promotion_status` as product/config promotion
  status; do not conflate with Git branch promotion. A later schema version
  should use one term consistently.
- Add `key_facts` as a generic presentation kind for compact, sourced facts
  that do not naturally fit retrieval/generation/performance result schemas.
  Require each fact to carry a source reference, scope/qualifier, and currency.
- For new numeric facts, prefer structured extraction. Where a number remains
  curated, bind it to a source locator and expected literal. Keep the existing
  hash-pinned historical values; retrofit literal bindings only when cheap and
  without changing their accepted values.
- Render `evidence_authority`, decision effect, currency, and promotion
  independently. Do not hardcode “Exploratory result” from a
  `non_promotional` status. Round visible portfolio numbers sensibly (for
  example `0.791`, `5.62 s`) while retaining exact values in the manifest and
  provenance details.
- Continue to fail closed on source hash mismatch and preserve the
  one-directional evidence → registry → exporter → manifest → UI pipeline.

## 6. Proposed Architecture diagrams (maximum five total)

These five are the complete Architecture diagram budget, including any
existing diagrams retained or replaced:

1. **Snapshot and provenance:** active workspace/snapshot binding and evidence
   identity.
2. **Runtime portability:** CPU release image vs qualified CUDA runtime,
   external model assets, unchanged AUTO resolution.
3. **Deployment/trust boundary:** local strict-offline default and explicitly
   operator-selected REL-03 inference boundary.
4. **Evidence publication chain:** frozen evidence → reviewed registry →
   deterministic exporter → static manifest → read-only Engineering UI.
5. **Life of a question:** snapshot admission → retrieval → rerank/context →
   sufficiency → generation → local citation-membership validation, including
   the explicit conversation-action branch.

Release verification belongs in Evaluation content, not a separate diagram.

## 7. Proposed registry records

The maximum is six new records. These are the exact approved IDs and claims for
the bounded implementation. The 18A-0 audit commit added none of them.

| Proposed record ID | Proposed content | Primary sources | Reason it is necessary |
|---|---|---|---|
| `product.current-configuration` | Current defaults and decision basis: strict-offline/standalone default; dense + BM25 → RRF → BGE reranker; ADR-005/006 rationale; current compute and generation boundaries. Descriptive Slice 9H-P/14C results remain non-promotional. | `config/base.yaml`; ADR-005/006; Slice 9H-P/14C evidence; settings/runtime contracts | Answers current configuration without treating historical pilots as configuration authority. |
| `generation.grounding-and-external-boundary` | Citation-membership contract and semantic-support limitation; local evidence/citation authority; optional REL-03 external generation boundary. | `citations.py`; Slice 8 design; REL-03 contract/smoke | Combines current grounding contract and external inference boundary without claiming semantic entailment validation. |
| `runtime.compute-portability` | CPU-only default release image vs qualified CPU and CUDA runtime profiles; provisioned model assets remain external. | REL-01 qualification; CPU L5/CUDA qualification | Answers compute portability and distinguishes runtime qualification from a CUDA release artifact. |
| `capacity.large-source-envelope` | Scientific qualification vs 90 MiB product admission policy, including host/profile/disk gates and the 91.70 MiB Q100 fixture. | L5, L6, CUDA campaign and parser corrective | Prevents product-limit claims from being inferred from qualification workload size. |
| `release.verification` | Slice 17 hosted CI scope and REL-01 image/build qualification with explicit non-coverage. | Slice 17 result/run identity; REL-01 qualification/closeout | Explains continuous checks and bounded release evidence. |
| `conversation.decision-history` | 01A negative feasibility pilot → 01B safety NO-GO → 01C explicit actions accepted/promoted; deterministic factual free-text path remains. | 01A/01B/01C reports and current implementation | Explains current capability boundary without duplicating historical generation or retrieval metric cards. |

The existing `retrieval.slice9hp`, `generation.slice10e`, `recovery.slice12c`,
`security.slice13b`, and performance records remain evidence sources rather
than being copied into new cards. Operational restart recovery is a separate
claim from query/retrieval recovery and should be sourced explicitly in the
relevant question content.

## 8. Existing records proposed for amendment

Amend existing records rather than duplicating their evidence:

- `retrieval.slice9hp`, `generation.slice10e`, and all performance records:
  add historical currency; keep their accepted/source-bound values and
  caveats. Prefer leaving historical curated numbers as-is; migrate bindings
  only where inexpensive.
- `recovery.slice12c`: clarify that it concerns query/retrieval rewrite/retry;
  evidence supports insufficient efficacy and a product-disabled disposition.
  Separate current disabled status from historical evaluation currency.
- `security.slice13b`: add historical currency and retain its fail-closed
  outcome/non-completeness caveat; preserve the pinned source and numeric
  cohort values.
- Add no new persistence-recovery record unless the product question requires
  it; describe its separate accepted evidence from
  `beta_persistence_recovery/RESULT.md`.

The accepted evidence values and source hashes remain immutable. Amend the
presentation metadata and add current source bindings only as needed by the
approved schema migration.

## 9. Explicit non-scope

- No new evidence execution, benchmark, model inference, security campaign, or
  corpus run.
- No retrieval, generation, citation, compute, capacity, recovery, or
  deployment-policy change.
- No new routes: keep `/engineering/evaluation` and
  `/engineering/architecture`.
- No CUDA release image; it remains deferred.
- No promotion of 18B, 18C, or 18D and no public portfolio claims beyond
  accepted evidence.
- No rewriting historical accepted evidence or turning descriptive evidence
  into a promotional winner.

## 10. Recommendation and scope boundary

Implement the reviewed claim/evidence map and page/schema boundaries in Slice
18A. The largest presentation risks
are (a) presenting historical small-population comparisons as current winners,
(b) conflating accepted evidence with product promotion/currentness, (c)
mistaking a CPU release image for absence of CUDA runtime support, and (d)
presenting bounded qualification as a universal performance/security claim.

The Slice 18A implementation must stop for independent review before
promotion. Slices 18B–18D remain unauthorized.
