# Slice 9F Pilot Report Template

Copy to `docs/pilots/slice9f_ics_modules.md` **after** executing the authoritative pilot. Do not fill this template file in place. Do not create `docs/pilots/` until that executed report is written.

Blank placeholders only. See [`slice9f_pilot_runbook.md`](slice9f_pilot_runbook.md) for procedure.

---

## Pilot identity

```text
corpus_name:
corpus_id:
chunk_set_id:
authoring_run_id:
authorcfg_id:
sampling_seed: 0
requested_proposal_count: 40

run path (logical):
  paths.corpora/ics_modules/gold_authoring/runs/<authoring_run_id>.json

GoldDataset dataset_id:
gold directory (logical):
  paths.corpora/ics_modules/gold_authoring/gold/<authoring_run_id>/

absolute paths (optional diagnostics only):
```

---

## Preflight

```text
doctor_result:
Authoring READY: yes/no
9C retrieval prerequisites verified for recorded chunk_set_id: yes/no
notes:
```

---

## Module 1 accounting authority

```text
document_id:
canonical title:
matching rule:
  source_seed.document_id exact match;
  canonical source_seed.document_title fallback only when document_id absent
Module 1 accepted|edited finalized count:
Module 1 deferrals (reopen→pending), if any:
```

---

## Run counts

```text
requested proposal attempts: 40
eligible seed population:
actual selected seeds:
shortfall from requested count:

proposal successes / SilverCases:
9B rejected/failed attempts:

pool successes:
pool failures:
prelabel successes:
prelabel failures:

accepted:
edited:
rejected:
pending:

finalized GoldCases:
```

---

## Module / document distribution

```text
source document/module counts (from source-seed provenance):
concentration notes:
```

---

## Query-type coverage

Mark present / absent / corpus-unsupported. Notes required if absent.

```text
definition / concept:
identity / factual lookup:
procedure / sequence:
purpose / rationale:
comparison / distinction:
multi-chunk / supporting-evidence:
other observed categories:
```

---

## Process measurements (descriptive; not gates)

### Proposal

```text
human accepted unchanged:
human edited:
human rejected:
common failure patterns:
```

### Pool

```text
typical candidate counts:
answer-bearing evidence present:
supporting-only evidence:
missed-evidence observations:
noisy/redundant pool observations:
```

### Prelabel

```text
agreement:
adjacent disagreement:
polar disagreement:
reviewer-perceived usefulness:
```

### Review

```text
all-zero maps:
query edits:
other notes:
```

---

## Four process judgments (required)

Each must be exactly one of: **GO** | **ADJUST** | **NO-GO**, with short rationale and concrete examples.

### 1. Proposal quality

```text
Judgment:
Rationale / examples:
```

### 2. Candidate-pool usefulness

```text
Judgment:
Rationale / examples:
```

### 3. Relevance-rubric consistency (0 / 1 / 2)

```text
Judgment:
Rationale / examples:
```

### 4. Model-assistance value (9D)

```text
Judgment:
Rationale / examples:
```

---

## Contract / workflow defects discovered

```text
Status: none | present

description:
severity:
gold correctness affected: yes/no
resolved: yes/no
commit/fix reference (if any):
cosmetic / usability notes (non-blocking):
```

---

## Retrieval / model hypotheses observed during pilot

Hypotheses only. Explicit statement required:

```text
No production retrieval/model promotion is authorized from 9F pilot cases alone.
```

```text
observations / hypotheses for 9G–9H:
```

---

## Five-part 9F-1 gate

```text
[ ] >=20 accepted/edited finalized cases from one authoring-run lineage
[ ] meaningful query-type coverage recorded
[ ] four process judgments completed
[ ] no unresolved contract-breaking defect
[ ] no pilot-only retrieval/model promotion
```

Notes for any unchecked item:

```text
```

---

## Final pilot decision

```text
9F outcome: GO | ADJUST | NO-GO

summary:
next actions (if ADJUST / NO-GO):
```
