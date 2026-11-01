# 16K-F Preparation Readiness Report

## Current disposition

This is a bounded preparation revision under the user's authorization for the
**Minimum Beta Dataset and Robustness Preparation**. It does not claim real
corpus execution, scientific qualification, or acceptance of the replacement
dataset.

```yaml
preparation_revision: COMPLETE / READY FOR HUMAN DATASET REVIEW
real_corpus_ingestion: NONE
OCR_execution: NONE
scientific_or_CUDA_execution: NONE
production_code_or_policy_changed: false
accepted_16K_F_design_modified: false
real_corpus_execution: NOT_AUTHORIZED
promotion: NOT_AUTHORIZED
```

The work is on `prep/16k-f-corpus-acceptance`, based on Human-accepted
preparation tip `7c8edee2c3ef85aa8d31722e2a6c8d7ce512b5bc`. The accepted 16K-F
design remains `0839b565cd60958141366048520236a71bf16fd0`. The original
45-representation / 39-primary specification remains intact as historical
provenance. The proposed replacement dataset is documented separately in
[`CORPUS_BASELINE_AMENDMENT_001.md`](CORPUS_BASELINE_AMENDMENT_001.md).

## Verified replacement population

The inventory was regenerated from `data/raw`; all 52 supported paths were
stream-hashed and rechecked against disk.

```yaml
inventory_sha256: 87b9971d5857c141916033e7f826911b3804dd299bf223fee4dbd3189939a354
supported_paths: 52
distinct_byte_identities: 44
oversized_pdf_paths: 3
no_native_text_pdf_paths: 3
exact_duplicate_path_excess: 8
eligible_deduplicated_sources: 38
eligible_source_bytes: 261345436
```

Private local artifacts:

```yaml
manifest:
  path: data/16k_f_preparation/REPLACEMENT_ACCEPTANCE_MANIFEST.json
  canonical_sha256: 4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b
  file_sha256: 85770fc063287c4588c255ebd56947cd7ed3321a67d433883e3785a011ee1384
query_deck:
  path: data/16k_f_preparation/QUERY_DECK_CANDIDATE.json
  file_sha256: f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a
  manifest_binding: 4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b
  question_count: 5
```

The 38 eligible sources comprise 37 PDFs and one TXT. Each query target is
verified to be in that set. The private corpus inventory and query text are not
committed.

## Harness changes

`scripts/diag_16k_f/prepare_corpus.py` now builds a versioned replacement
manifest containing all 52 paths, exact byte identities, per-path dispositions,
expected rejection cases, and the successful-ingestion source list. It verifies
the inventory hash and rehashes every file while building. It derives the
38-source count rather than assuming 39.

`scripts/diag_16k_f/execution_harness.py` accepts both manifest generations:

- Historical `16k-f-primary-corpus-manifest-v1` retains its exact 39-primary
  guard unchanged.
- Replacement `16k-f-replacement-acceptance-manifest-v1` validates its own
  canonical hash, every population count, all 52 on-disk paths and byte
  identities, its deduplicated success set, and the query deck's binding to
  that exact manifest. The cold/warm pair uses the derived count.

Replacement evidence marks measurements as **not comparable** to the
historical 39-primary / approximately 7.5–8k-child threshold population. The
frozen 60-minute threshold and other scientific criteria are unchanged; this
replacement run cannot be claimed to pass that historical threshold without
separate workload-comparability evidence. Rejection attempts are separate from
cold/warm workload totals. Cold/warm provenance, streamed batching, durable
operation reconnect checks, truthful metrics, and grounded post-publication
queries remain in place.

The private manifest prepares individual oversized, OCR-required, and exact
duplicate cases, plus mixed valid/invalid atomicity scenarios, safe error
reporting checks, retries, and a successful subsequent valid mutation. Their
outcomes are not asserted before execution. Expected rejection is a successful
robustness result when it is understandable, preserves the workspace, and does
not block a later valid mutation.

## Proposed execution matrix after Human acceptance

1. Re-run the accepted 1,296-child cold proxy cell.
2. Run the largest eligible text-bearing source, confirmed from the replacement
   manifest at execution preflight.
3. Exercise all three oversized paths, all three OCR-required paths, and all
   eight exact-duplicate paths. Include mixed valid/oversized,
   valid/OCR-required, and valid/duplicate mutations; verify no partial
   publication, bounded error reporting, and successful same-process valid
   retries.
4. Run the exact 38-source replacement population cold.
5. Immediately repeat the same 38-source population warm against the same data
   root, manifest, and query deck.
6. Run the private grounded-query deck against the final publication.

The complete 38-source cold/warm measurements are descriptive for this
replacement dataset. The historical scientific thresholds remain frozen and
must not be represented as met by non-comparable workload results.

## Validation performed

```text
.venv/bin/pytest -q tests/unit/test_slice16k_f_corpus_preparation.py
  20 passed

.venv/bin/ruff check scripts/diag_16k_f/prepare_corpus.py \
  scripts/diag_16k_f/execution_harness.py \
  tests/unit/test_slice16k_f_corpus_preparation.py
  PASS

.venv/bin/ruff format --check <same three paths>
  PASS

prepare_corpus --help / execution_harness --help
  PASS; replacement-manifest and run-full-pair commands visible

execution_harness.load_sources(data/raw, replacement manifest)
  PASS; all 52 paths reverified; 38 eligible sources loaded

git diff --check
  PASS
```

These are synthetic preparation and harness checks only. They do not invoke
the API, ingest real sources, perform OCR, load embedding models, create CUDA
contexts, or run a scientific campaign.

## Remaining gates

1. Human review and acceptance of the exact replacement manifest baseline,
   private query deck, and
   [`CORPUS_BASELINE_AMENDMENT_001.md`](CORPUS_BASELINE_AMENDMENT_001.md).
2. Independent review of the preparation revision.
3. A separate bounded real-corpus execution authority.
4. Execution-time verification of the dedicated API/data root, active
   capabilities, disk headroom, and exact corpus hashes.

No production-policy change, OCR implementation, real-corpus ingestion,
scientific execution, or promotion is authorized by this preparation revision.
