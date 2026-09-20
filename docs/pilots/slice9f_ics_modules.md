# Slice 9F Pilot Report — `ics_modules`

Executed authoritative pilot report (not the blank template).
Procedure: [`docs/slice9f_pilot_runbook.md`](../slice9f_pilot_runbook.md).

---

## Pilot identity

```text
corpus_name: ics_modules
corpus_id: corpus_040e49a1d261dba4e853939b36348dc40109551d6fdb49b38c7a9d896409eadb
chunk_set_id: chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2
authoring_run_id: authorrun_b28d88f64054491a837cb4a144cbe056
authorcfg_id: authorcfg_9396160feb17154a6cfdc8493788ba6175bd1694a981b72a9e77d30d616fbd8c
sampling_seed: 0
requested_proposal_count: 40

run path (logical):
  paths.corpora/ics_modules/gold_authoring/runs/authorrun_b28d88f64054491a837cb4a144cbe056.json

GoldDataset dataset_id:
  gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172

gold directory (logical):
  paths.corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056/
```

### Publication lineage (provisional vs authoritative)

```text
provisional mini GoldDataset (smoke only):
  cases: 2
  dataset_id: gold_7798b4f455ebd73e2d6a9165b60fdb19d19c4f2d56c28abbd04ec0cb0928408d
  purpose: pipeline smoke (dense + hybrid-rerank); NOT a promotion basis
  smoke observation (n=2 only): dense HitRate@1=1.0 / nDCG@10≈0.68;
    hybrid-rerank HitRate@1=0.0 / nDCG@10≈0.46
  status: superseded by force-finalize on the same default directory

authoritative 9F GoldDataset:
  cases: 22
  dataset_id: gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172
  finalized_at: 2026-09-20 (force replace of provisional publication)
```

---

## Preflight

```text
doctor_result: Authoring READY (recorded during propose/pool/prelabel sequence)
Authoring READY: yes
9C retrieval prerequisites verified for recorded chunk_set_id: yes
notes:
  Operational overlay used during later stages (local authoring LLM / recovery).
  Pages expert-review side-path used for offline adjudication handoff; Silver
  remained the durable store. Private bundle text was never committed.
```

---

## Module 1 accounting authority

```text
document_id: doc_c3084e336e87f2bbcc915a3c12b0e9bbd6128d8c34298637abbfb0ea6ac390cc
canonical title: Module 1 Incident Scene Decision Making SM
matching rule:
  source_seed.document_id exact match;
  canonical source_seed.document_title fallback only when document_id absent
Module 1 accepted|edited finalized count: 1
  case 19 — size-up primary objective (expert-reviewed)
Module 1 deferrals (reopen→pending), if any:
  case 12 — classical-process conditions (judgments retained; pending)
  case 16 — NDM four steps (judgments + repair retained; pending)
  case 24 — Classical Method situations (judgments retained; pending)
```

---

## Run counts

```text
requested proposal attempts: 40
eligible seed population: 290
actual selected seeds: 40
shortfall from requested count: 0 selected; 6 proposal attempts rejected_quality → 34 SilverCases

proposal successes / SilverCases: 34
9B rejected/failed attempts: 6 (rejected_quality)

pool successes: 34
pool failures: 0
prelabel successes: 34
prelabel failures: 0
  note: prelabel recovery required prompt-body rationale-length fix + --force
  re-prelabel (see docs/slice9f_prelabel_recovery_metrics.md); authorcfg_id
  unchanged under current semantic hash for prompt-body-only edits.

accepted: 22
edited: 0
rejected: 9
pending: 3

finalized GoldCases: 22
```

### Accepted-case provenance (hybrid; audit layers retained)

The authoritative 22-case GoldDataset is **hybrid-adjudicated**.

```text
16 finalized cases have direct human review/confirmation.
6 finalized cases retain assistant-completed relevance maps without subsequent
human confirmation.

For cases 31, 33, and 34, assistant-produced candidate maps were subsequently
inspected and explicitly confirmed by Carlos without relevance changes.

The original annotation provenance remains retained in the audit trail.
```

Do **not** call assistant-only cases human-reviewed merely because their grades
reside in Silver `human_review` after import. Durable grades are operationally
authoritative for eval; provenance accounting is separate.

```text
tracked audit: docs/pilots/slice9f_gold_provenance_audit.json
local package audit (gitignored mirror):
  eval/reports/RAG.preannotation_package/RAG.final.consolidated.audit.json

total finalized GoldCases: 22
human-reviewed finalized: 16
  original expert-reviewed finalized: 13
    (1, 3, 8, 9, 11, 13, 15, 17, 19, 20, 21, 23, 29)
  subsequent human confirmation of assistant maps: 3
    (31, 33, 34) — Carlos; original_annotation_source=assistant_completion;
    subsequent_validation=human_confirmed; no relevance changes
assistant-completed only: 6
  (2, 22, 26, 27, 30, 32)

expert-rejected (not exported): 9
Module 1 pending deferrals (not exported): 3 (12, 16, 24)
case 16 repair: missing NDM-introduction candidate retained as relevance 0
```

---

## Module / document distribution

```text
source document/module counts (finalized GoldCases, from source-seed):
  Module 3 Preincident Preparation SM: 10
  Module 4 Resource Allocation SM: 6
  Module 2 Safety Management SM: 4
  Module 1 Incident Scene Decision Making SM: 1
  Module 7 Post Incident Analysis SM: 1
concentration notes:
  Module 3 dominates finalized set; Modules 5–6 absent from finalized gold.
  Module 1 capped at 1 by locked 9F accounting (three additional reviewed
  Module 1 maps remain pending on Silver for later reuse).
```

---

## Query-type coverage

Mark present / absent / corpus-unsupported. Notes required if absent.

```text
definition / concept: present
  (e.g. flashover characteristics; fire-protection hazards by construction)
identity / factual lookup: present
  (e.g. roof decking materials; Iowa Formula credit; abbreviations; orgs)
procedure / sequence: present
  (e.g. ventilation strategy factors; environmental relief conditions)
purpose / rationale: present
  (e.g. size-up objective; interagency capability identification; PIA purpose)
comparison / distinction: present
  (e.g. NFA vs Iowa; hazard vs bridge-truss; FLSA influence framing)
multi-chunk / supporting-evidence: present
  (accepted maps include grade-1 supporting judgments alongside grade-2)
other observed categories:
  calculation / quantitative (fire-flow); policy statement (risk policy)
gaps:
  no dedicated adversarial/abstention cases in this pilot set
  limited Module 5–6 topical coverage in finalized gold
```

---

## Process measurements (descriptive; not gates)

### Proposal

```text
human accepted unchanged: 22
human edited: 0
human rejected: 9
common failure patterns:
  expert comment rejects concentrated on underspecified / weakly answerable
  or low-value operational questions (resource forms, radio-traffic impact,
  structural-strength assessment, liability wording, etc.)
```

### Pool

```text
typical candidate counts: min 75 / median 92 / max 111 (accepted cases)
answer-bearing evidence present: yes for all 22 accepted (each ≥1 positive)
supporting-only evidence: yes (grade 1 used alongside grade 2)
missed-evidence observations:
  not systematically audited beyond human maps; pools were large enough that
  accepted cases found positives without query edits
noisy/redundant pool observations:
  large near-duplicate / neighboring-section noise expected for ICS modules;
  human 0 judgments dominate (hybrid consolidation graded extensively)
```

### Prelabel

```text
agreement: very high on exported cases (~2027 agree vs ~6 disagree candidate rows)
adjacent disagreement: present on a minority of exported cases (5 cases with any disagreement)
polar disagreement: 0 exported cases flagged polar
reviewer-perceived usefulness:
  9D prelabels were advisory in review UI; external Pages handoff + hybrid
  consolidation carried the bulk of adjudication throughput
```

### Review

```text
all-zero maps: none among accepted/finalized
query edits: none among accepted (no overrides; grade_basis = proposed query)
other notes:
  Pages JSON transfer fragility (bad control character) observed once; mitigated
  by re-share / zip. Case 16 missing-judgment repair retained through cap deferral.
```

---

## Four process judgments (required)

Each must be exactly one of: **GO** | **ADJUST** | **NO-GO**, with short rationale and concrete examples.

### 1. Proposal quality

```text
Judgment: GO
Rationale / examples:
  34/40 proposals became SilverCases; 22 accepted without query edits; 9
  expert rejects were content-quality decisions rather than schema failures.
  Example accepts: flashover characteristics; roof decking materials; size-up
  objective. Example rejects: dedicated resource-status forms; radio-traffic
  monitoring impact — judged not worth gold retention by expert comment.
```

### 2. Candidate-pool usefulness

```text
Judgment: GO
Rationale / examples:
  All 34 pools succeeded; every accepted case had complete coverage and ≥1
  positive in-pool judgment. Candidate depths (75–111) supported both direct
  answer chunks and supporting evidence without CURRENT substitution.
```

### 3. Relevance-rubric consistency (0 / 1 / 2)

```text
Judgment: GO
Rationale / examples:
  Consolidation used explicit 0/1/2 rubric; gold exports positive-only 1|2.
  Expert review, assistant completion, and later human confirmation of selected
  assistant maps (31/33/34) followed the same grade meanings. Audit retains
  layered provenance; assistant-only maps are not relabeled as independent
  expert authorship.
```

### 4. Model-assistance value (9D)

```text
Judgment: ADJUST
Rationale / examples:
  Local 9D double-pass agreed often and was useful as advisory signal, but
  pilot throughput required a Pages side-path plus frontier-model completion
  for a subset of cases after expert capacity limits. Treat 9D as assistance
  only; do not equate model agreement with gold. Follow-up: harden Pages
  transfer + importer for future pilots (process/docs), not a 9A–9E reopen.
```

---

## Contract / workflow defects discovered

```text
Status: present (resolved for gold correctness; non-blocking residual process notes)

description:
  1) Prelabel rationale-length invalidations slowed 9D; fixed via prompt-body
     MUST NOT exceed RATIONALE_MAX_CHARS + --force recovery.
  2) Pages bundle transfer could break JSON (raw control characters) when
     shared via messaging apps.
  3) Module 1 cap required deferring three otherwise-valid reviewed cases to
     pending (judgments retained).
severity:
  (1) high for ops time, resolved before review completion
  (2) medium for external handoff, mitigated operationally
  (3) expected pilot accounting, applied correctly
gold correctness affected: no (final 22-case set validated)
resolved: yes for (1) and (3); (2) mitigated, importer hardening deferred
commit/fix reference (if any):
  docs/slice9f_prelabel_recovery_metrics.md; Pages branch pages/9f-expert-review
cosmetic / usability notes (non-blocking):
  n=2 smoke showed dense > hybrid-rerank at HitRate@1 — observation only
```

---

## Retrieval / model hypotheses observed during pilot

Hypotheses only. Explicit statement required:

```text
No production retrieval/model promotion is authorized from 9F pilot cases alone.
```

```text
observations / hypotheses for 9G–9H:
  - n=2 smoke is insufficient and must not drive promotion; 22-case authoritative
    gold is the first pilot set sized for controlled 9H compare.
  - Dense vs hybrid-rerank ranking quality may diverge on ICS multi-positive maps;
    re-test on the 22-case set under 9H.
  - Large noisy pools with many human-0 neighbors may stress Precision@k even
    when HitRate remains high — watch metric interpretation in 9H.
```

---

## Five-part 9F-1 gate

```text
[x] >=20 accepted/edited finalized cases from one authoring-run lineage
[x] meaningful query-type coverage recorded
[x] four process judgments completed
[x] no unresolved contract-breaking defect
[x] no pilot-only retrieval/model promotion
```

### Dataset-gate amendment (transparent; historical criterion retained)

```text
Original locked 9F-1 dataset gate (unchanged in history):
  >=20 accepted/edited finalized cases from one authoring-run lineage
  (satisfied: 22 finalized GoldCases)

Amended pilot acceptance criterion (post-pilot scope decision):
  >=16 human-reviewed finalized cases
  (satisfied: 16 = 13 expert-reviewed finalized + Carlos confirmations of 31/33/34)

Rationale:
  Deliberate post-pilot scope decision based on available reviewer capacity —
  not a silent rewrite of the original locked case-count gate.
  Six finalized cases (2, 22, 26, 27, 30, 32) remain assistant-completed only.
```

Notes for any unchecked item:

```text
(none — all five original gates satisfied; human-review amendment also satisfied)
Process judgment #4 is ADJUST (model-assistance value) which is allowed under
9F-1; it does not alone force NO-GO when the five gates hold and no
contract-breaking defect remains unresolved.
```

---

## Final pilot decision

```text
9F outcome: GO

summary:
  Authoritative GoldDataset
  gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172
  publishes 22 hybrid-adjudicated cases from one frozen lineage with Module 1
  accounting satisfied (1 finalized / 3 deferred pending).
  Of those 22: 16 have direct human review/confirmation; 6 retain
  assistant-completed maps without subsequent human confirmation.
  Cases 31/33/34 keep original assistant provenance with subsequent
  Carlos confirmation (no relevance changes).
  Provisional 2-case publication and its smoke metrics are superseded and are
  not a promotion basis.

next actions:
  Authorize Slice 9H retrieval A/B (eval retrieve / eval compare) against this
  22-case dataset only after explicit go-ahead. Do not start 9H in the same
  operation as this report. Optional later: resume pending Module 1 cases 12/16/24
  under a future accounting policy; harden Pages import path; optionally
  human-confirm remaining assistant-only cases 2/22/26/27/30/32.
```