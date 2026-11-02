# 16K-F Human campaign closeout — scoped beta

**Decision:** `ACCEPT`\
**Date:** 2026-11-02\
**Scope:** Documentation and governance closeout only\
**Evidence index:** [`RUN_002_EVIDENCE_INDEX.md`](RUN_002_EVIDENCE_INDEX.md)

## Human disposition

The Human accepts the `run_002` evidence for the current beta corpus and closes
16K-F as **COMPLETE / HUMAN ACCEPTED — SCOPED BETA**. The accepted evidence
shows successful replacement-corpus ingestion and publication, cache reuse,
grounded retrieval, robustness handling, largest eligible PDF ingestion, a
managed Markdown smoke, and the single cold 1,296-child proxy. The sanitized
index records the exact evidence hashes and descriptive results.

This acceptance is scoped to the available beta corpus. It does not convert
the replacement workload into a comparable version of the historical
39-primary benchmark.

## Historical campaign disposition

The original corpus included intermediate representations produced during PDF
compression, text extraction, and other experiments. The exact original
39-primary population can no longer be reliably reconstructed. The Human
therefore approved retiring the original approximately 7,500–8,000-child,
60-minute cold dense-phase benchmark as a current-beta gate:

```yaml
historical_39_primary_benchmark:
  disposition: RETIRED_FOR_CURRENT_BETA
  result: NOT_EVALUATED
  historical_decision_label: HUMAN_APPROVED_EXCEPTION
  pass_or_fail_claim: NONE
  frozen_requirement_and_provenance: PRESERVED_UNCHANGED
```

The run_002 replacement-corpus measurements do not satisfy, waive, or fail the
historical threshold. In particular, the aggregate cold operation duration is
not the frozen dense-phase metric. The historical design and evidence remain
unchanged.

## Methodological clarification — 2026-11-02

This dated clarification refines the interpretation of the historical target;
it does not change the original Human acceptance or the observed campaign
results. The 39-primary and 7,500–8,000-child figures were estimates for a
changing set of representations, not a verified, stable corpus manifest. The
60-minute value was a legitimate engineering usability objective, but it was
not empirically calibrated as an upper bound on that complete estimated
workload before being frozen.

The initial empirical basis was the separate 1,296-child D0 incident, not a
complete 39-primary corpus run. The design explicitly warned that linear
extrapolation to approximately 8,000 children was not justified and required
direct full-corpus measurement. D0, the original design, and their historical
threshold wording are preserved unchanged.

Run_002 is the current accepted empirical baseline for the verified available
38-source corpus. Its results are descriptive for that workload. The corpus
change and loss of the exact historical roster—not an unfavorable observed
60-minute result—make the old number an unsuitable current-beta comparator.
This clarification claims neither that the original objective was met nor
that the replacement corpus met a newly defined numerical threshold. No
current full-corpus latency SLO is established. The 16K-F functional
acceptance remains **COMPLETE / HUMAN ACCEPTED — SCOPED BETA**.

## Accepted campaign results

- 38-source replacement-corpus cold and warm publication: accepted descriptive
  evidence, with exact source and data-root linkage.
- Robustness matrix: 17/17 cases passed, including all three mixed-batch
  retries and atomic-rejection checks.
- Grounded query deck: 5/5 cold and 5/5 warm.
- Cache behavior: warm run generated zero embeddings and reused 25,797 across
  rebuild operations; timing fields unavailable under the accepted schema were
  left unavailable.
- Largest eligible PDF: 67,199,839 bytes, 374 children and embeddings, cited
  retrieval passed.
- Managed Markdown: synthetic managed `SOURCE_ADD` and cited retrieval passed.
- 1,296-child proxy: single cold run accepted as descriptive evidence; it does
  not establish repeatability.

The 38-source corpus contains 37 PDFs and one TXT file, with no Markdown file.
The Markdown smoke is supplemental and does not change the frozen corpus
manifest.

## Preservation and remaining state

```yaml
run_001_evidence: PRESERVED_UNCHANGED
run_002_evidence: PRESERVED_UNCHANGED
GPU_RESIDENCY_01: OPEN / SEPARATE OWNER
TEST_STARTUP_01: OPEN / NON_BLOCKING / SEPARATE OWNER
promotion_to_main: NOT_AUTHORIZED
16K_G_regression_handoff: NOT_AUTHORIZED
production_changes: NONE
additional_scientific_execution: NONE
```

This closeout grants no authority to promote to `main`, begin 16K-G, or alter
production behavior. Promotion remains a separate mainline gate.
