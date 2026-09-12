# Memory: Post–Slice 8 smoke test through title-section ranking A/B

**Scope:** Work after commit `6bf5802` (*Implement Slice 8 grounded local generation with closed-world citations.*) through the metadata-aware candidate-generation experiment classification **B4**.

**Corpus:** `ics_modules` (7 Module PDFs under `data/raw/*.pdf`)  
**Smoke query:** `What is the purpose of Module 1?`  
**Answer-bearing child:** `chunk_0a8f3dd79101aaf6a826080ed9f16982b0c6c20436ae4fd9e8527ed84dbb74b4`  
(Module 1 INTRODUCTION — “This unit explains… classical / Naturalistic Decision Making / Command Sequence”)

Do **not** treat this file as an architecture ADR. It records diagnostics, locks, experiments, and results so the next session can resume without re-deriving the ladder.

---

## 1. Smoke-test setup

### Corpus / retrieval stack

- Ingested only the seven Module PDFs; corpus name `ics_modules`.
- Provisioned real embedding (`Qwen3-Embedding-0.6B`) and reranker (`BAAI/bge-reranker-v2-m3`) artifacts under `models/` (weights gitignored).
- Chunked → dense + lexical indexes; doctor reported Context / Hybrid / Hybrid-rerank READY.
- Baseline chunk set: `chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2`.

### Generation connectivity journey

1. **Local Ollama (Docker, `qwen3.5:9b`):** Generation READY, but `query` timed out / empty on CPU; abandoned; model removed.
2. **Unsloth on Windows host:** Added optional Bearer `generation.api_key` / `OFFLINE_RAG_LLM_API_KEY`. WSL networking / Hyper-V / host bind issues; laptop too slow → abandoned.
3. **LAN Unsloth** at `192.168.2.142:8888`: first attempt failed (wrong Wi‑Fi). After network fix: `/v1/models` OK.
   - Configured model id must match API list exactly (drop `:UD-Q4_K_XL` suffix).
   - Model used: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`.

### Slice 8 generation hardening (code)

- Optional API key on probe/generate (not hashed into `gencfg_`).
- Env overrides: timeout, approved endpoints/models; doctor shows API key configured|not set.
- Docling markdown export tweak (`export_to_markdown(doc=…)`).
- **`reasoning_contract = direct-output-v1`:** per-request `chat_template_kwargs.enable_thinking = false` for OpenAI-compatible path; hashed into `gencfg_`. Parser still reads only `choices[0].message.content` (never `reasoning_content`).

---

## 2. Issues found (ordered)

### G1 — Thinking-budget exhaustion (generation)

Raw completion diagnostic (same prompt / schema / `max_tokens=1200`):

- `finish_reason = length`
- `message.content = ""`
- `reasoning_content` long CoT
- `completion_tokens = 1200`

**Not** a parser bug; not yet evidence that 1200 is too small for the final JSON.

**Fix locked & implemented:** `direct-output-v1` → disable thinking per request.  
**Re-probe:** `finish_reason=stop`, content = canonical abstention JSON, `status=insufficient_evidence` / `model_abstain`. Sampling left at `temperature=0.0`.

### G2 — `model_abstain` with structurally healthy generation

After G1 fix, generation contracts were healthy; abstention meant **evidence quality**, not generation failure.

`retrieve hybrid-rerank-context --json` showed five evidence units from Modules 2/3/7 — **no `Module 1` string**, false friends (“Purpose” / “This module focuses…”).

**Case A:** supplied evidence does not identify Module 1 → abstention correct. Do not weaken ADR-012 / sampling to force an answer.

### R — Retrieval ladder (document vs answer-supporting recall)

| Level | Finding |
|---|---|
| Document-level | Some Module 1 children *can* enter hybrid/rerank (e.g. Command Sequence proxy hybrid #19 → rerank #9) |
| Answer-supporting | INTRODUCTION purpose child **`chunk_0a8f3dd7…`** absent from dense **and** lexical top 30 under `plain-v1` → **R1-A** |

Root cause: ranking uses exact `Chunk.text` only (`plain-v1` / `plain-pair-v1`). Identity **“Module 1”** lives in filename / corpus `source_name`; body says **“this unit”**.

Not primarily: chunk boundary, missing source, Slice 6 demotion of *this* chunk, Slice 7 bug, or generation.

---

## 3. Proposed solution (locked Q1–Q6)

**Do not** mutate canonical `Chunk.text` or chunk identities.

Introduce ranking-only representation:

| Contract | Role |
|---|---|
| `document-title-v1` | Normalize corpus `source_name` → `document_title` (basename; strip one of `.pdf`/`.txt`/`.md`; collapse whitespace; no semantic rewrite). **Ignore `Document.title`.** |
| `title-section-text-v1` | Envelope: `DOCUMENT:` + optional `SECTION:` + blank line + exact `Chunk.text` |
| `RankingTextInputs` | Shared DTO; one `build(inputs)` protocol for plain + metadata builders |

**Stage adoption for first A/B:**

- Dense + lexical → `title-section-text-v1` (new indexes)
- Reranker → still `plain-pair-v1` (isolate candidate-generation variable)
- Evidence / Slice 7–8 → still exact source text (no `DOCUMENT:` lines in prompts)

**Config:** keep `base.yaml` on `plain-v1`; experiment profile `config/experiments/title_section_ranking.yaml` sets both branches to `title_section` / `title-section-text-v1`.

**Fail closed** under metadata strategy if `document_id` / `source_name` / title resolution fails. No mixed plain+metadata index.

---

## 4. Implementation summary

Shared module: `src/offline_rag/retrieval/ranking_text.py`

- Resolve title once per document from corpus manifest `source_name`.
- Dense/lexical builders: `Plain*` → `inputs.chunk_text`; `TitleSection*` → envelope.
- Config hashes include `document_title_contract` + `ranking_text_contract` only for metadata-aware (historical plain-v1 index IDs unchanged).
- Unit tests: `tests/unit/test_ranking_text.py` (+ builder call-site updates).

Also in this working tree (post–Slice 8, pre-memory commit): generation API key, `direct-output-v1`, docs/env example updates, related tests.

---

## 5. Experiment A/B results

### Immutable index IDs

| Arm | Dense | Lexical |
|---|---|---|
| **A `plain-v1`** | `denseindex_80f7da5c50c6de0a00502e169c75198af3f7f2f48d56dcae8ca961d3e42710e9` | `lexical_9c43385ecf20cacbbe31e1243d37afca3ce88520e30be39f1aa2017a2bb1c337` |
| **B `title-section-text-v1`** | `denseindex_b4d60dd391f355714b8e42cd4f6aeb06b0150ae25e4265b62fee5f003733f83e` | `lexical_cf6f9c18b646426f33fb7f571ca3015bb8f81aa23a3e11a0f08518e970eee08a` |

Same chunk set. Reranker remained `plain-pair-v1`. Depths/RRF/`anchor_k` unchanged.

### Target INTRODUCTION ladder

| Stage | A (`plain-v1`) | B (`title-section`) |
|---|---|---|
| Dense top 30 | ABSENT | **ABSENT** |
| Lexical top 30 | ABSENT | **YES — rank 23** (BM25 ≈ 4.27) |
| Hybrid RRF | ABSENT | **rank 45** (lexical-only; dense_rank=null) |
| Reranker input (`input_k=30`) | NO | **NO** |
| `anchor_k=5` | NO | NO |
| Slice 7 purpose text in evidence | NO | NO (Module 1 BIR sibling appeared as anchor #4; INTRODUCTION purpose still missing) |
| Slice 8 | — | `insufficient_evidence` / `model_abstain` |

### Classification: **B4**

`title-section-text-v1` was **insufficient** for this query’s answer-bearing chunk to reach the reranker pool.

- Lexical improved (absent → #23) but RRF single-branch score left it at #45 (> 30).
- Dense still missed the INTRODUCTION in top 30 despite title/section envelope.
- Primary acceptance criterion (`target reaches hybrid→reranker input`) **not met**.

### What was *not* changed (hard stop after B report)

- No Slice 6 metadata pair contract
- No raised `dense_top_k` / `lexical_top_k` / `input_k` / `anchor_k`
- No RRF weight change
- No chunking / `Chunk.text` mutation
- No generation / sampling / prompt changes
- No `base.yaml` default migration to metadata-aware text

---

## 6. Open next decisions (not authorized)

For **B4**, diagnose before patching:

1. Why dense still excludes the rendered envelope for this INTRODUCTION (embedding similarity vs title-bearing false friends / heading-only chunks).
2. Whether equal-weight RRF systematically under-ranks strong single-branch lexical hits (fusion/depth), separately from representation.
3. Only after that: consider Slice 6 `title-section-pair-v1`, depth changes, or further representation fields — each as its own locked decision.

Generation remains healthy for smoke when evidence is adequate; do not “fix” abstention by sampling.

---

## 7. Operational notes

- LAN generator: exact `/v1/models` id; Bearer via env; WSL↔Windows localhost pitfalls documented in history.
- Qdrant Local: only one client process at a time (lock errors if overlapping retrieve/index).
- Dense reindex under title-section is CPU-heavy (full re-embed of children); lexical rebuild is comparatively fast.
- Switching config between plain and title-section makes CURRENT index `INDEX_CONFIG_STALE` under the other config — expected; compare by immutable `index_id`, not CURRENT alone.

---

## 8. Success criteria reminder

Judge this smoke by the **ranking ladder**, not final LLM answer success.

```text
R1-A fixed  ⇔  target INTRODUCTION in hybrid top 30 / reranker input
B2          ⇔  in reranker input but below anchor_k=5  → then design Slice 6 metadata
B3          ⇔  survives anchor_k / Slice 7 purpose evidence
B4          ⇔  still outside reranker input (current state)
```
