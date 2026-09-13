# Memory: Dense query/heading peers through provenance-v2 prompt

**Scope:** Uncommitted work after `7dacd4b` (*Record provisioned embedding and reranker model card READMEs.*) — continuing from prior memory `docs/memory_post_slice8_smoketest.md` (**B4** title-section ranking).

**Corpus:** `ics_modules`  
**Smoke query:** `What is the purpose of Module 1?`  
**Answer-bearing child:** `chunk_0a8f3dd79101aaf6a826080ed9f16982b0c6c20436ae4fd9e8527ed84dbb74b4`  
(Module 1 INTRODUCTION — “This unit explains…”)

Do **not** treat this as an architecture ADR. Resume aid only.

---

## 1. Starting point (after B4)

- Arm A plain indexes: `denseindex_80f7da5c…` / `lexical_9c43385e…`
- Arm B title-section: `denseindex_b4d60dd3…` / `lexical_cf6f9c18…`
- Target INTRODUCTION still outside reranker `input_k=30` under title-section (RRF #45 lexical-only).
- `base.yaml` still `plain-v1`; generation still `prompt-grounded-v1`.
- Generator: LAN Unsloth `unsloth/Qwen3.6-35B-A3B-MTP-GGUF` @ `192.168.2.142:8888`.

---

## 2. Dense beyond top-30 (D1–D5)

On plain vs title-section dense:

| Arm | Target dense rank | Approx score |
|---|---|---|
| A plain | **77** | ~0.325 |
| B title-section | **96** | ~0.366 (score up, rank worse) |

B dense top 10 dominated by short heading/title chunks.  
RRF #45 = expected single-branch behavior (not a fusion defect).

**Classification:** `DENSE-METADATA-HURT` + `RRF-CUTOFF-NOT-MATERIAL`.

Do **not** promote `title-section-text-v1` for dense. Ranking envelope remains a separate experiment axis.

---

## 3. Query contract A/B (Arm Q)

**Finding:** production dense previously used bare `model.encode(query)` with no prompt. Model exposes `prompts["query"]` (non-empty instruct) and `prompts["document"]=""` (empty → bare doc encode is intended).

**Contracts:**

| Contract | Behavior |
|---|---|
| `raw-query-v1` | historical bare encode (default) |
| `model-query-prompt-v1` | `prompt_name="query"` |

Config: `dense.query_text` (strategy/contract pair). Identity in `denseretrievecfg_`, **not** dense index identity.

Experiment: `config/experiments/dense_query_prompt.yaml`  
Code: `src/offline_rag/dense/query_text.py`, `embedder.py`, `config_hash.py`

On plain-v1: target rank **77 → 49**; margin vs title-only **−0.152 → −0.036**; still outside top 30.

**Classification:** `QUERY-CONTRACT-HELPFUL-BUT-INSUFFICIENT`  
**Not promoted** to `base.yaml`.

---

## 4. Passage / short-chunk diagnostics (P1–P6)

- No usable asymmetric document prompt (`document` prompt empty) → skip P1.
- Heading-like ~13.6% of corpus but ~83% of dense top 30 under Q+plain.
- Non-heading counterfactual: target rank **49 → 16** (large crowding effect).
- Metadata prefixes / body-first DOCUMENT worsen target–title margin.

Implication: heading-only children crowd dense peers; next lever is eligibility policy, not more title envelope on dense.

---

## 5. Heading-peer policy (Arm H)

**Classifier (authoritative):** `Chunk.content_type == "heading"` (single heading-block child) — not length heuristics.

**Contracts:**

| Contract | Dense eligibility |
|---|---|
| `all-children-v1` | default; omitted from hash for stability |
| `exclude-heading-only-v1` | exclude heading-only children from dense vectors |

Dense-only exclusion; lexical keeps all children.  
Module: `src/offline_rag/dense/searchable_units.py`  
Experiment: `config/experiments/dense_no_heading_peers.yaml`  
(also selects `model-query-prompt-v1` + plain passages/lexical)

**New index:** `denseindex_61c8c1bc…` (290 vectors; 42 headings excluded)  
Lexical CURRENT unchanged: `lexical_9c43385e…` (plain-v1)

### Ladder for Module 1 purpose

| Stage | Result |
|---|---|
| Dense | **#17** |
| RRF | **#30** (dense-only) |
| Reranker pool (`input_k=30`) | **YES** (#30) |
| Reranker | **#5** |
| `anchor_k` | **YES** |
| Slice 7 evidence | **YES** — purpose prose present |

Nav probes: no hybrid/document-level regression observed on this smoke set.

**Classification:** `HEADING-PEER-POLICY-MATERIAL`  
**Not promoted** to `base.yaml`.

Note: target sits on cutoffs (RRF #30, reranker #5) — fragile for single-example promotion.

---

## 6. End-to-end on Arm H (before provenance)

| Run | Status | Notes |
|---|---|---|
| E2E-D | `generation_failed` / `provider_error` | endpoint unavailable (~54ms) |
| E2E-B | `insufficient_evidence` / `model_abstain` | generator OK; purpose evidence `ev_9fa9a974…` present |

Reclassification: **not** yet “generation overly conservative.”

---

## 7. Provenance-gap diagnosis (G1–G3)

`prompt-grounded-v1` presents only:

```text
### BEGIN/END EVIDENCE ev_...
<exact EvidenceUnit.text>
```

No `document_title` / section in the prompt. Retrieval knows Module 1 via provenance; the generator does not.

### G1 — prompt-visible identity

Across five Arm H evidence units for Module 1 purpose query:

- `"Module 1"` / `"MODULE 1"` / `"Incident Scene Decision Making"` **absent** from all `EvidenceUnit.text`
- Purpose body: “This unit explains…”
- `"Module 1"` appears only in `QUERY:`

**G1-A** → abstention still grounded/correct.

### G2 — synthetic identity+purpose EvidenceUnit

Same model / `temperature=0.0` / `direct-output-v1` / `no-retry-v1` → **answered** with synthetic `ev_…` citation.

### G3 — diagnostic provenance wrapper (not production)

```text
DOCUMENT: ...
SECTION: ...
<exact EvidenceUnit.text>
```

→ **answered** citing real `ev_9fa9a974…`.

**Classification:** `GENERATION-VISIBLE-PROVENANCE-GAP`  
Do **not** reuse `title-section-text-v1` ranking envelope as generation evidence.

---

## 8. Provenance-v2 design locks (Decisions 1–10)

Implemented exactly as locked; summary:

| # | Lock |
|---|---|
| 1 | Orchestrator resolves titles → `PromptEvidence`; no corpus I/O in prompt builder; no title on `EvidenceUnit` |
| 2 | Move `resolve_document_title_v1` / `render_section_path_v1` → `core/document_metadata.py`; ranking keeps envelope |
| 3 | `generation.prompt` strategy/contract pairs; `gencfg_` hashes effective `prompt_contract` only; v1 hash stable |
| 4 | Fail closed → `generation_failed` / `prompt_provenance_unavailable` / `generator_invoked=false` |
| 5 | `PromptEvidence` only for provenance-v2; v1 stays on `EvidenceUnit[]` |
| 6 | Dedicated v2 system prompt; v1 system prompt byte-identical |
| 7 | Thin `generation_provenance_prompt.yaml`; compose with Arm H; no `experiment.name` overwrite; no `base.yaml` change |
| 8 | Orchestrator-owned corpus `source_name` lookup (reuse existing loaders); v1 skips it |
| 9 | Freeze P0–P3 from CURRENT Arm H before A/B |
| 10 | Implementation authorized |

### Config pairs

```text
grounded                 ↔ prompt-grounded-v1
grounded_provenance      ↔ prompt-grounded-provenance-v2
```

### Canonical Module 1 composition

```text
base
+ dense_no_heading_peers
+ generation_provenance_prompt
```

---

## 9. Provenance-v2 implementation map

| Area | Path |
|---|---|
| Title/section primitives | `src/offline_rag/core/document_metadata.py` |
| Ranking re-exports | `src/offline_rag/retrieval/ranking_text.py` |
| Prompt DTO | `src/offline_rag/generation/prompt_evidence.py` |
| Builders | `src/offline_rag/generation/prompt.py` |
| Orchestrator adaptation | `src/offline_rag/generation/orchestrate.py` |
| Settings | `generation.prompt` in `config/models.py` |
| Experiment | `config/experiments/generation_provenance_prompt.yaml` |
| Tests | `test_document_metadata.py`, `test_provenance_prompt.py`, ranking + grounded suites |

Live A/B `gencfg_` (with current approved model):

```text
v1 = gencfg_39562a28dd73be538b54a0448a21298b29cf827fbed13f885c34f7754dd96d9f
v2 = gencfg_5b9e2cb84f63e833bb1368f9810f991b6f64ad5f0348debb61745d60ca6429c0
```

---

## 10. Frozen regression probes + A/B

Retrieval fixed: Arm H dense + `model-query-prompt-v1` + plain lexical + unchanged RRF/reranker/context.

| Probe | Query | Category | G1 (`prompt-grounded-v1`) | G2 (`prompt-grounded-provenance-v2`) |
|---|---|---|---|---|
| P0 | What is the purpose of Module 1? | identity-dependent | `model_abstain` | **answered** · `ev_9fa9a974…` · Module 1 |
| P1 | What is the main purpose of the PIA? | self-contained | answered · Module 7 | answered · Module 7 |
| P2 | What is the purpose of Module 2? | multi-doc | `model_abstain` | **answered** · `ev_c72350de…` · Module 2 only |
| P3 | What is the ISBN of Module 1 Incident Scene Decision Making? | abstention | `model_abstain` | `model_abstain` |

Retrieval equality: identical dense/lexical/fusion/reranker/context hashes per probe.

**Classification:** `PROVENANCE-PROMPT-MATERIAL`

Exact Module 1 v2 wrapper shape:

```text
### BEGIN EVIDENCE ev_9fa9a974…
DOCUMENT: Module 1 Incident Scene Decision Making SM
SECTION: INCIDENT SCENE DECISION MAKING / INTRODUCTION

INTRODUCTION
This  unit explains...
### END EVIDENCE ev_9fa9a974…
```

---

## 11. Active experimental state (CURRENT pointers)

| Axis | Active experiment value | In `base.yaml`? |
|---|---|---|
| Dense passages | `plain-v1` | yes (default) |
| Dense query | `model-query-prompt-v1` via Arm H overlay | **no** |
| Dense searchable units | `exclude-heading-only-v1` | **no** |
| Lexical | `plain-v1` | yes |
| Generation prompt | `prompt-grounded-provenance-v2` via overlay | **no** (default remains v1) |

Indexes:

```text
dense CURRENT (Arm H): denseindex_61c8c1bc…
lexical CURRENT:       lexical_9c43385e…
```

Independent axes (compose via multi-config deep merge):

```text
Query:            raw-query-v1 | model-query-prompt-v1
Passage:          plain-v1 | title-section-text-v1
Dense eligibility: all-children-v1 | exclude-heading-only-v1
Generation prompt: prompt-grounded-v1 | prompt-grounded-provenance-v2
```

---

## 12. Hard stops still in force

Do **not** without a new explicit decision:

- Promote Arm H or provenance-v2 to `base.yaml`
- Change temperature / max tokens / thinking / retries
- Weaken abstention wording
- Accept uncited answers
- Raise top_k / RRF / reranker depths
- Filter lexical headings
- Mutate `Chunk.text` / `EvidenceUnit.text` / citation namespace
- Reuse ranking envelope as generation presentation
- Add semantic answer judges

---

## 13. Open next decisions (not authorized)

1. Whether to promote `model-query-prompt-v1` and/or `exclude-heading-only-v1` after broader multi-query regression.
2. Whether to promote `prompt-grounded-provenance-v2` (or a successor) after more probes / corpora.
3. Fragility of RRF #30 / reranker #5 for the Module 1 INTRODUCTION — depth vs representation tradeoffs.
4. Whether title-section ranking remains useful for **lexical-only** paths despite dense hurt.

Generation abstention on identity-dependent queries under v1 remains the **correct** behavior when provenance is hidden.
