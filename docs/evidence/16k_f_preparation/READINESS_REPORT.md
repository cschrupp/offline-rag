# 16K-F Preparation Readiness Report

## Current terminal — scoped beta closeout

The preparation work below is retained as a record of what was ready before
real-corpus execution. It is superseded as the current 16K-F status by the
Human campaign closeout and sanitized run_002 evidence index:
[`../16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md`](../16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md).

```yaml
preparation_candidate: 52e740579259e82181fdbbb3c0335c7e0320e3ee
preparation_human_acceptance_record: 895870cb5ff12a7ffdf438759a3070dd224f4daf
current_performance_status: EMPIRICALLY_CHARACTERIZED / ACCEPTED_DESCRIPTIVE
run_002_replacement_corpus_evidence: ACCEPTED_DESCRIPTIVE
run_002_metrics:
  cold_operation_total_ms: 3759581
  cold_full_cell_elapsed_minutes: 66.09
  warm_operation_total_ms: 56615
  warm_full_cell_elapsed_minutes: 5.14
  aggregate_operation_time_reduction_percent: 98.49
robustness_matrix: PASS_17_OF_17
grounded_queries: PASS_5_OF_5_COLD_AND_WARM
largest_eligible_pdf_and_managed_markdown: PASS
proxy_1296_children: PASS_SINGLE_RUN
historical_39_primary_60_minute_benchmark:
  status: SUPERSEDED_AS_CURRENT_CORPUS_COMPARATOR
  result: NOT_EVALUATED
  no_pass_or_fail_claim: true
historical_requirement: PRESERVED_UNCHANGED
current_full_corpus_latency_slo: NONE_ESTABLISHED
16K_F: COMPLETE / HUMAN ACCEPTED — SCOPED BETA
promotion: NOT_AUTHORIZED
16K_G: NOT_AUTHORIZED
```

The historical 60-minute full-corpus objective is not reported as passed or
failed. The separate D0 run exceeded the 10-minute proxy objective for its
1,296-child incident workload. The run_002 replacement population is not
comparable to the historical curator-selected
39-primary workload. `run_001` and `run_002` evidence files remain unchanged.
`GPU-RESIDENCY-01` and `TEST-STARTUP-01` remain separately registered.
The original 60-minute figure was an engineering planning objective based on
estimated corpus size, not an empirically calibrated full-corpus upper bound.
There is no active full-corpus latency SLO. The dated methodological
clarification is recorded in
[`../16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md`](../16k_f_execution/16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md#methodological-clarification--2026-11-02)
and the run_002 evidence index's performance-provenance section.

## Preparation revision disposition at completion

This is the Human-accepted bounded preparation revision for the **Minimum Beta
Dataset and Robustness Preparation**. It does not claim real-corpus execution,
scientific qualification, or empirical acceptance of ingestion results.

```yaml
preparation_revision: COMPLETE / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED
accepted_technical_subject: 52e740579259e82181fdbbb3c0335c7e0320e3ee
independent_review: S16K-F-PREP-IR-005_ACCEPT
replacement_baseline_and_amendment_human_acceptance: ACCEPTED
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
provenance. The accepted replacement dataset is documented separately in
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
largest_eligible_source_bytes: 67199839
largest_eligible_source_sha256: 1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54
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

The largest eligible source is 67,199,839 bytes. The eligible population
partitions into three request-bounded upload batches (19, 9, and 10 files).
Each batch rebuilds the workspace; operation metrics must remain separate, and
aggregates must be labelled as sums across those rebuilds.

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

Replacement cold/warm execution requires both prepared artifact digests from
the later execution authority. The runner verifies them before its first API
request and records them in cell evidence. The prepared canonical manifest
SHA-256 is
`4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b`; the
query-deck file-byte SHA-256 is
`f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a`.

The private manifest prepares individual oversized, OCR-required, and exact
duplicate cases, plus mixed valid/invalid atomicity scenarios, safe error
reporting checks, retries, and a successful subsequent valid mutation. Their
outcomes are not asserted before execution. Expected rejection is a successful
robustness result when it is understandable, preserves the workspace, and does
not block a later valid mutation.

`ROBUSTNESS_EXECUTION_RUNBOOK.md` provides the bounded real-API sequence and
structured private evidence schema for these scenarios. Case validation binds
scenario IDs, ordinals, and exact input hashes to the pinned manifest, derives
retry requirements from scenario type, and leaves case status at
`NOT_EVALUATED` for campaign completion. The matrix validator requires exact
coverage of every rejection case, retries for all three mixed scenarios, and
passing grounded queries bound to the same manifest/deck before returning
campaign `PASS`. Synthetic tests cover missing retries, unapproved identities,
arbitrary IDs, incomplete coverage, and full synthetic matrix acceptance. No
live rejection or retry was run during preparation.

The replacement population has 37 PDFs, one TXT, and no Markdown. The focused
preparation suite includes a deterministic synthetic Markdown parser smoke;
pre-existing managed Markdown `SOURCE_ADD` tests remain in the broader API
suite. An isolated `TestClient` run of that API path hung during lifespan
startup and was stopped after 30 seconds, consistent with the registered
`TEST-STARTUP-01`; this preparation does not claim that API smoke as passing.

The complete robustness-matrix validator requires both the cold and warm cell
records. It verifies their exact pair ID/order, data-root identity, cold
evidence digest, manifest/deck pins, published source identity/count, and
published workspace source count. Each cell's observed API `content_hash` set
must exactly match the manifest set before query validation; the observed
identity digest is recorded in cell evidence. For each approved query it
checks the exact question SHA-256 and requires answered status, positive
citation and answer-block counts, valid source mappings, valid answer-block
references, and the same published revision/snapshot. Synthetic negative
coverage rejects missing citation evidence, changed question hashes, wrong
published source identity, and a broken cold-to-warm evidence link.

## Proposed execution matrix — awaiting separate execution authority

1. Re-run the accepted 1,296-child cold proxy cell.
2. Run the manifest-confirmed largest eligible text-bearing source, rechecking
   its exact hash at execution preflight.
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
  28 passed

.venv/bin/ruff check scripts/diag_16k_f/execution_harness.py \
  tests/unit/test_slice16k_f_corpus_preparation.py
  PASS; all checks passed

.venv/bin/ruff format --check scripts/diag_16k_f/execution_harness.py \
  tests/unit/test_slice16k_f_corpus_preparation.py
  PASS; two files already formatted

execution_harness validator CLI help
  PASS; per-case and complete-matrix commands visible

execution_harness.load_sources(data/raw, replacement manifest)
  PASS; prepared artifact pins matched, all 52 paths reverified, and 38
  eligible sources loaded

isolated supplemental Markdown API TestClient smoke attempt
  STOPPED after 30 seconds waiting in application lifespan startup; no
  assertion result; consistent with registered TEST-STARTUP-01

git diff --check
  PASS
```

These are synthetic preparation and harness checks only. They do not invoke
the API, ingest real sources, perform OCR, load embedding models, create CUDA
contexts, or run a scientific campaign.

## Preparation-time gates (subsequently superseded)

1. A separate bounded real-corpus execution authority covering the matrix
   above.
2. At execution time, verify the dedicated API/data root, active capabilities,
   disk headroom, and exact corpus and query-deck hashes against the accepted
   values.

Real Markdown ingestion remains unproven by the 52-path corpus. The parser
smoke is supplemental and does not resolve `TEST-STARTUP-01`.

No production-policy change, OCR implementation, real-corpus ingestion,
scientific execution, or promotion is authorized by this preparation revision.
