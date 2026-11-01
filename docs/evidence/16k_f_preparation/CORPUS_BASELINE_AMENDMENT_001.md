# 16K-F Replacement Dataset Amendment 001

**Status:** `PREPARED — HUMAN ACCEPTANCE PENDING`

**Scope:** replacement corpus identity and bounded robustness matrix only
**Real-corpus execution:** `NOT AUTHORIZED`

## Purpose and provenance

This amendment proposes a replacement execution dataset from the currently
available supported-format corpus. It supplements the accepted 16K-F design's
§11 dataset for the upcoming beta acceptance run. It does not edit that accepted
design or rewrite its historical corpus record.

The original specification remains preserved as historical provenance:

```yaml
historical_specification:
  supplied_representations: 45
  primary_logical_documents: 39
  non_ocr_alternates: 3
  ocr_exclusions: 3
  status: HISTORICAL_ACCEPTED_SPECIFICATION
```

The local inventory does not contain curator evidence that maps its files to
those 45 representations or 39 logical documents. This amendment therefore
does not relabel the available directory as that historical roster.

## Exact replacement baseline

The source inventory was regenerated from `data/raw` and each of its 52 paths
was checked by streaming byte count and SHA-256.

```yaml
inventory_sha256: 87b9971d5857c141916033e7f826911b3804dd299bf223fee4dbd3189939a354
supported_paths: 52
  pdf: 51
  txt: 1
  markdown: 0
distinct_byte_identities: 44
replacement_manifest_sha256: 4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b
```

All paths remain represented in the private manifest. They are classified
using the existing supported extensions and product limits: PDF at or below
90 MiB; TXT/Markdown at or below 25 MiB. Native PDF text is determined from the
existing PDFium screen, with OCR disabled. A PDF with native text on some pages
is retained as natively readable; the measured page coverage remains metadata
for quality review.

```yaml
admission_and_robustness_population:
  file_paths: 52
  distinct_byte_identities: 44

path_dispositions:
  successful_ingestion_candidate: 38
  expected_oversize_rejection: 3
  expected_ocr_required_rejection: 3
  expected_exact_duplicate: 8

successful_ingestion_population:
  exact_sha256_deduplicated_sources: 38
  pdf: 37
  txt: 1
  markdown: 0
  unique_raw_source_bytes: 261345436
```

The count is derived from the verified manifest, not forced to 39:

```text
44 byte identities
- 3 over-limit PDF identities
- 3 distinct PDFs with no native text while OCR is disabled
= 38 eligible exact-byte identities
```

Eight additional paths are exact copies of eligible identities and remain in
the admission/robustness population. The three over-limit PDFs and three
OCR-required PDFs also remain in that population as expected rejection cases;
none is silently dropped from the test inventory.

Private artifacts, not committed to Git:

- `data/16k_f_preparation/REPLACEMENT_ACCEPTANCE_MANIFEST.json`
- `data/16k_f_preparation/QUERY_DECK_CANDIDATE.json`

The manifest carries its canonical `manifest_sha256` above. The query deck is
bound to that exact manifest SHA-256 and has file SHA-256
`f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a`. Its five
target identities are all members of the 38-source successful-ingestion
population. Query text and corpus paths remain private.

## Prepared robustness matrix

Each expected rejection is a robustness result, not a failed beta, when the
application gives an understandable bounded reason, leaves the published
workspace unchanged, and allows a later valid mutation to succeed.

The manifest binds the exact paths and SHA-256 values for these cases. Future
execution must record the observed HTTP response or durable operation, safe
error code and actionable reason, pre/post revision and snapshot, active source
identities, readiness, and retry result. Do not put private source text,
questions, answers, or paths in committed evidence.

| Case | Prepared population | Required observation |
|---|---:|---|
| Oversized PDF admission | All 3 | Rejected with `source_file_too_large`; no publication change |
| OCR-required PDF | All 3 | Actionable OCR-required terminal failure under the frozen OCR-disabled policy; no publication change |
| Exact duplicate | All 8 duplicate paths | Duplicate identity is rejected or safely reported; no second active source |
| Mixed valid + oversized | 1 valid plus 1 oversized | Entire mutation rejected atomically; original revision, snapshot, and source identities remain unchanged |
| Mixed valid + OCR-required | 1 valid plus 1 OCR-required | Entire mutation fails atomically; original publication remains unchanged |
| Mixed valid + duplicate | 1 new valid plus an already-active duplicate | Entire mutation has no partial publication; duplicate is reported clearly |
| Retry after each mixed rejection | Same valid source after invalid item is removed | A new valid operation succeeds in the same process; revision advances once |
| Post-publication query | Published eligible source set | Grounded answer and citations resolve to active sources at the published snapshot |

The accepted cold/warm harness measures only the 38 eligible unique sources.
Expected-rejection operations are separate evidence records and are excluded
from cold/warm workload totals. The harness binds query evidence to the exact
manifest, validates every one of the 52 source paths against that manifest,
and uses the manifest-derived source count for the full pair.

## Measurement interpretation

The accepted design's historical 60-minute dense-phase threshold and all other
scientific criteria remain unchanged. The replacement population is not
demonstrated to be comparable to the historical 39 logical-primary corpus or
its approximately 7.5–8k searchable-child workload. Every cold/warm result must
therefore carry:

```yaml
historical_39_primary_threshold_comparable: false
thresholds_changed: false
threshold_pass_claim_from_replacement_run: prohibited_without_separate_comparability_evidence
```

Cold and immediate warm runs remain paired against the same data root, exact
manifest, and query deck. Their cache reuse and timing results are valid for
this replacement workload, but they do not by themselves satisfy or waive the
historical workload threshold.

## Proposed execution matrix after Human acceptance

This is a proposed plan, not execution authority:

1. Re-run the accepted 1,296-child cold proxy cell.
2. Run the largest eligible text-bearing source cell (identified from the
   verified manifest at execution preflight).
3. Run all individual rejection cases above, mixed atomicity cases, and
   same-process valid retries.
4. Run the exact 38-source replacement cold corpus.
5. Immediately repeat the same 38-source corpus warm against the same data
   root and exact manifest.
6. Run the private grounded-query deck against the final published revision.

The 38-source measurement must be labelled non-comparable to the historical
39-primary threshold population. A separate report must preserve the frozen
thresholds and state whether independent workload evidence makes any threshold
comparison valid.

## Gate

```yaml
replacement_dataset:
  mechanically_prepared: true
  manifest_hash_verified: true
  human_acceptance: PENDING
synthetic_harness_validation: REQUIRED_BEFORE_REVIEW
real_corpus_execution: NOT_AUTHORIZED
scientific_execution: NOT_AUTHORIZED
production_or_policy_change: NONE
promotion: NOT_AUTHORIZED
```

Human acceptance of this exact replacement baseline and amendment is required
before a separate bounded authority for the proposed real-corpus matrix.
