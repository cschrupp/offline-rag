# Slice 9F — 20-Case Authoring Pilot Runbook

**Status:** operational contract locked (Decisions 9F-1 through 9F-11).  
**Nature:** ops + documentation pilot — not a feature/architecture slice.  
**Corpus:** `ics_modules` only.

This runbook is reusable procedure. It is **not** an execution record. After the real pilot, fill [`docs/slice9f_pilot_report_template.md`](slice9f_pilot_report_template.md) into `docs/pilots/slice9f_ics_modules.md` (create `docs/pilots/` only then).

Authoritative machine artifacts remain ordinary:

```text
paths.corpora/ics_modules/gold_authoring/runs/<authoring_run_id>.json
paths.corpora/ics_modules/gold_authoring/gold/<authoring_run_id>/
```

Do not invent pilot-specific CLI commands, flags, schemas, freeze locks, append-propose, or retrieval/model promotions for 9F.

---

## Locked success gate (9F-1)

The pilot is **GO to 9G** only when all five hold:

1. ≥20 `accepted`/`edited` cases finalize from **one** authoring-run lineage into one valid `offline-rag-gold-v1` dataset  
2. Meaningful query-type coverage is exercised and recorded  
3. Explicit GO / ADJUST / NO-GO judgments for proposal quality, pool usefulness, rubric consistency, and model-assistance value  
4. No unresolved contract-breaking authoring/review/finalize defect  
5. No production retrieval/model promotion from the 20 pilot cases alone  

`ADJUST` on a process judgment means smallest process/docs correction before 9G (without reopening locked 9A–9E architecture).  
`NO-GO` means correction + another pilot pass before production-scale gold.

Numeric rates (acceptance, agreement, recall, latency, …) are **measurements**, not pass/fail thresholds.

---

## Lineage rules (9F-2)

```text
ics_modules
  → one historical chunk_set_id (bound at propose)
  → one authoring_run_id
  → propose → pool → prelabel → review → finalize
  → GoldDataset v1
```

- No other corpora, ad-hoc PDFs, synthetic docs, or public IR cases  
- No stitching accepted cases across unrelated runs or ChunkSets  
- No CURRENT substitution during review/finalize  
- If CURRENT is rebuilt mid-pilot, this lineage stays on its original `chunk_set_id`  
- Oversized initial propose only; **no** append-to-run propose API for 9F  
- Module 1 may contribute **≤1** finalized case (see Module 1 accounting)

### Review freeze

```text
first durable human mutation on the run
  → upstream pilot lineage frozen
```

After freeze, do **not** run against that run:

```text
gold propose
gold pool --force
gold prelabel --force
```

or any operation that changes case membership, candidates, candidate provenance, 9D advisory state, or proposal population.

Allowed after freeze: `gold review`, then `gold finalize`, plus read-only inspection.

If an upstream defect requires regeneration after freeze: **stop the pilot**; do not silently mutate the frozen run.

---

## Module 1 accounting (9F-5)

Identify Module 1 from the historical corpus document (same lineage as authoring), then record:

```text
document_id
canonical document title (document-title-v1)
```

**Primary:** `case.source_seed.document_id == recorded Module 1 document_id`  
**Fallback:** only if `document_id` is legitimately absent — exact canonical `source_seed.document_title` match  
**Never:** query text, candidate provenance, path/filename heuristics, fuzzy title match  

Before finalize, ensure Module 1–origin `accepted`/`edited` count ≤ 1. Extra otherwise-valid Module 1 cases: **reopen → pending** (do not false-`reject`).  

GoldDataset does not carry source-seed fields; accounting uses the silver run.

---

## Preflight (9F-8) — fail closed before propose

Do **not** start the authoritative lineage until preflight passes.

### 1. Doctor

```text
offline-rag doctor --corpus ics_modules
```

Require:

- Authoring status **READY** (9A meaning: configured/authorized to attempt — **not** a live model probe)  
- Retrieval/indexing/reranker/hybrid components needed by locked 9C six-arm pooling **READY**

If not READY: fix environment/artifacts; rerun doctor. Do not create the run.

### 2. Record CURRENT identities

From doctor notes / existing corpus+chunk state (same values `gold propose` will bind):

```text
corpus_name = ics_modules
corpus_id   = <CURRENT corpus id>
chunk_set_id = <CURRENT chunk-set id>
```

Confirm corpus ↔ ChunkState ↔ `source_corpus_id` consistency. Abort if stale/missing/inconsistent.

Also record Module 1 accounting authority (`document_id` + canonical title) from this historical corpus.

If readily available from existing CURRENT ChunkSet / sampling-eligible population information, also estimate:

```text
eligible_population N
```

Prefer starting propose with `--count 40` when `N >= 40`. If `N < 40` is already known, use `--count N --seed 0` as the authoritative first invocation (see Propose below). Do not change 9B sampling behavior.

### 3. Stop corpus/chunk mutation

After recording `chunk_set_id`, do not ingest/rechunk `ics_modules` before propose. If rebuild is required: abort, rebuild, obtain new CURRENT, **rerun complete preflight**.

### 4. Same-`chunk_set_id` 9C dependencies

Verify lexical, dense baseline, dense `model-query-prompt-v1`, Arm H, hybrid RRF, and hybrid-rerank dependencies resolve for the **recorded** `chunk_set_id` (use existing doctor/index/lexical/hybrid status evidence). Do not relax 9C’s own preflight later.

### 5. Authoring config for both stages

Confirm existing authoring config authorizes the intended local endpoint/model for both `question-proposal-v1` and `relevance-prelabel-v1` (same 9A allowlists/network policy). No new probe command.

### 6. Authoritative start boundary

Only after successful preflight:

```text
offline-rag gold propose \
  --corpus ics_modules \
  --count 40 \
  --seed 0
```

Omit `--output` (default run path). Failed preflight attempts are environment prep, not pilot runs.

---

## Authoritative stage sequence (9F-6, 9F-7, 9F-9)

Use ordinary defaults. One run path for all later stages.

### Propose

Requested operational budget (9F-6):

```text
requested_proposal_count = 40
sampling_seed = 0
```

Normal authoritative invocation when the eligible population can support it:

```text
offline-rag gold propose \
  --corpus ics_modules \
  --count 40 \
  --seed 0
```

- `40` = requested proposal-**attempt** budget (not a SilverCase or gold-size target)  
- `seed = 0` = ordinary deterministic sampler; no seed shopping  
- Omit `--output` (default run path)

**Eligible population smaller than 40 (fail-closed 9B — do not change code):**

Existing `source-sampling-random-v1` / `sample_source_seeds()` raises when:

```text
requested count > eligible_population_count
```

`gold propose` then exits as a **pre-run failure** and does **not** create or persist an `authoring_run_id`. It does **not** clamp to `N`.

Therefore:

1. Prefer determining eligible population `N` during preflight from existing CURRENT ChunkSet information when readily available.  
2. If `N < 40` is known before propose, the authoritative invocation is:

```text
offline-rag gold propose \
  --corpus ics_modules \
  --count N \
  --seed 0
```

3. If a `--count 40` attempt is what reveals `requested count 40 exceeds eligible population N`, that failed invocation is **not** a pilot lineage. Rerun **once** with `--count N --seed 0`.  

This one recovery is **not** adaptive top-up, seed shopping, resampling, or append-propose: no authoring run was created by the rejected `--count 40` call, and the seed remains `0`.

Record in the filled report:

```text
requested_proposal_count = 40
eligible_population = N
actual_selected = N
shortfall = 40 - N
```

The 9F-1 gate remains `>= 20` finalized cases; a shortfall does not redefine success.

Default artifact when propose succeeds:

```text
paths.corpora/ics_modules/gold_authoring/runs/<authoring_run_id>.json
```

Record from CLI/run JSON: `authoring_run_id`, `chunk_set_id`, `corpus_id`, `authorcfg_id`, `sampling_seed`, path.

### Pool

```text
offline-rag gold pool --run <authoritative-run-path>
```

Omit `--output` (in-place). No `--force` on the normal path. `--force` only for failed/incomplete recovery **before** review freeze, under existing 9C semantics — record any recovery.

### Prelabel

```text
offline-rag gold prelabel --run <authoritative-run-path>
```

Omit `--output` (in-place). No `--force` on the normal path. Forced retry only for failed/incomplete recovery before freeze under existing 9D semantics — record any recovery.

### Pre-review check

Before any human mutation: confirm pool + durable 9D advisory state are present for cases intended for review. Do not manually prune proposals to manufacture yield.

### Declare freeze, then review

```text
offline-rag gold review \
  --run <authoritative-run-path> \
  --host 127.0.0.1 \
  --port 8765
```

(Defaults may be shown explicitly; another free port only if 8765 is unavailable.)

Human review mutates the same JSON in place. After first durable human mutation: freeze (see above).

### Finalize readiness (9F-10)

First normal finalize when:

1. `accepted + edited >= 20`  
2. Every accepted/edited case is 9E-valid (full map, query↔grade binding, status rules)  
3. Module 1–origin accepted/edited ≤ 1 (reopen extras to pending if needed)  
4. No publication-blocking contract defect  
5. Enough review to support the four process judgments + coverage notes  

`pending` / `rejected` may remain; they do not export and do not block finalize. Do not force `pending == 0`. Do not trim non–Module-1 cases down to exactly 20.

```text
offline-rag gold finalize --run <authoritative-run-path>
```

Omit `--output`. **No `--force` on first finalize.** Default gold dir:

```text
paths.corpora/ics_modules/gold_authoring/gold/<authoring_run_id>/
```

Contract-clean contents only: `meta.json` + `cases.jsonl`.

If finalize fails before publication: fix under 9E rules and retry without force. If a valid dataset already exists, do not casually `--force`; record any forced replace if truly required under 9E overwrite semantics.

### After finalize

1. Load/inspect the GoldDataset (`dataset_id`, case count)  
2. Complete `docs/pilots/slice9f_ics_modules.md` from the template  
3. Issue GO / ADJUST / NO-GO under 9F-1  

Do not manually assemble or edit gold after finalization. Do not promote retrieval/model changes from pilot cases alone (hypotheses → 9G–9H only).

---

## What not to do in 9F

```text
code-enforced freeze
append-propose / adaptive top-up
coverage quotas / balancing sampler
pilot schema / status enum / pilot CLI
Label Studio / LAN review
seed shopping
cross-run stitching
false-reject for Module 1 accounting
retrieval/model tuning or Arm H promotion
non-contract files inside GoldDataset or silver JSON
```

Correct only genuine workflow/correctness defects if discovered; usability ideas become report observations.

---

## Decision index

| ID | Lock |
|---|---|
| 9F-1 | Five-part written GO/ADJUST/NO-GO gate |
| 9F-2 | `ics_modules`; one ChunkSet/run; freeze; Module 1 ≤1; no stitching |
| 9F-3 | Ops + docs only |
| 9F-4 | Runbook/template under `docs/`; filled report under `docs/pilots/` after execution |
| 9F-5 | Module 1 via source-seed `document_id` (title fallback only) |
| 9F-6 | `--count 40` requested budget; if `N < 40`, authoritative `--count N` (9B fail-closed, no clamp) |
| 9F-7 | `--seed 0` |
| 9F-8 | Fail-closed existing-tool preflight |
| 9F-9 | Default artifact paths; in-place pool/prelabel |
| 9F-10 | Finalize with pending allowed; ≥20; Module 1 ≤1 |
| 9F-11 | Pre-execution docs commit scope |
| 9F-12 | Docs-only commit authorized; execution later |
