# 16K-F Preparation Readiness Report

## Scope and disposition

This report records the authorized preparation-only tranche. It does not claim
16K-F execution, scientific qualification, or corpus acceptance.

```yaml
preparation: COMPLETE_WITH_READINESS_BLOCKERS
real_corpus_runs: NONE
scientific_or_CUDA_execution: NONE
production_code_or_policy_changed: false
16K-F_execution_authorized: false
promotion_authorized: false
```

The canonical preparation base is `7c85a9b14cd1d96a16caca971135fe8f7c978e08`.
The work is on `prep/16k-f-corpus-acceptance`. The accepted 16K-F design remains
`0839b565cd60958141366048520236a71bf16fd0`; it was not changed.

## Prepared harness

The preparation tooling is content-free with respect to document bodies:

- `scripts/diag_16k_f/prepare_corpus.py` streams source hashes and compiles a
  primary corpus only from an explicit curator roster, or a single-source
  manifest only after explicit text-bearing confirmation. It reports
  `NO_CONFIGURED_CEILING` when the workspace byte ceiling is null; the utility
  no longer invents a 90 MiB aggregate ceiling.
- `scripts/diag_16k_f/execution_harness.py` is an explicit-authority, one-cell
  API runner. It verifies manifest and source hashes, batches streamed uploads
  to the active 32-file / 100 MiB request envelope, verifies the declared cold
  or warm data root, checks the runtime workspace was persisted under that
  root, polls durable operations, validates worklist/source counts and stage
  metrics, verifies final publication, and runs a private query deck.
- Structured evidence records identities, counts, statuses, timings, stage
  metrics, and citation counts. It omits source text, query text, answers,
  filenames, and per-document worklist contents.
- `compare` pairs cold/warm evidence only when the exact source identity digest
  matches. It reports observed generated-work and timing reductions without
  imposing an unfrozen materiality threshold.
- The live runner requires both `--execute-real-corpus` and an explicit
  authority string. No invocation with those flags was made.

Because the API accepts no more than 100 MiB per request, manifests larger than
that envelope are submitted in multiple sequential `SOURCE_ADD` operations.
Evidence retains each operation separately and labels aggregate metrics as a
sum across those operations, including the repeated full-workspace rebuilds.

## Manifest and corpus findings

The accepted D0 proxy artifacts were mechanically verified:

| Artifact | SHA-256 | Result |
|---|---|---|
| `data/manifests/corpus_3c74b057074e928cccf7da048c06db0cf6df63bbe546ec14c071604949f160e3.json` | `69cefa61214e0e5e0a5eb71df01e323ede6f1807226181ef4134faeceb91b353` | 5 source identities resolve by exact SHA-256 |
| `data/chunk-manifests/chunkset_d0b1fee57392071172e54bb1f4b234965fa9993813319e39d52802eec07db65d.json` | `de4ad6b5ab661ba74e8ab2ec5344aa41518fc1dd0e9d94eb08edfbc3073076c3` | 1,296 child chunks |

Some historical paths in the proxy manifest are stale. The runner recovers
those inputs only by unique exact content hash, with the recorded source name
used to disambiguate identical bytes; all five inputs resolved in the available
`data/raw` tree. The accepted manifests were not modified.

The current local `data/raw` inventory is **not** the accepted 16K-F corpus:

```yaml
supported files: 52
ignored files: 8
distinct supported byte identities: 44
duplicate-path excess by byte identity: 8
supported raw bytes: 1,127,281,763
largest supported file: 284,535,224 bytes
```

The accepted design's source accounting is 45 supplied representations:
39 primary logical documents, 3 non-OCR alternates, and 3 OCR-only exclusions.
No matching curator roster or query deck was found. The raw directory also
contains a file larger than the active 90 MiB PDF limit, so choosing files by
directory order or byte identity alone would not establish corpus membership,
logical deduplication, or OCR classification.

The largest locally available cached non-OCR text-bearing candidate within
the PDF transport limit is `the_book_of_shupe.pdf`: 67,199,839 bytes, 883 parsed
blocks, and 269,941 extracted characters. Its source SHA-256 is
`1f22131a12fccfd0f5ecca9d6e84e7a4314720eeb2abef602be7ebe9932f7c54`. This is a
**provisional local candidate**, not a finding that it is the largest member
of the frozen beta corpus; the accepted roster is required to establish that.

## Execution readiness blockers

1. **Frozen roster absent.** Supply the exact 45 supplied-file roster with
   logical-document IDs, primary/alternate/OCR-excluded roles, and text-bearing
   classification. The tool will bind it to the local corpus by paths, sizes,
   and streaming SHA-256 and enforce the accepted 39 / 42 / 3 counts.
2. **Largest-source membership unverified.** The Shupe candidate above must be
   confirmed against that roster; if another eligible text-bearing
   representation is larger, the manifest must select that one instead.
3. **Query deck absent.** Supply private query IDs and questions for the
   post-publication retrieval check. The harness stores only question hashes
   and result status/citation counts.
4. **Dedicated runtime required.** Each cold cell must use an isolated data
   root whose cache/workspace directories are empty. The full-corpus warm cell
   must immediately reuse the same data root after the full-corpus cold cell.
   The harness checks cache state and confirms that the API's created workspace
   is persisted under the declared root. It must not target the normal beta
   data tree.
5. **Current host capability must be observed at execution time.** The runner
   checks the live transport/profile/workspace-capacity capabilities before
   creating a workspace and fails closed if the corpus exceeds them. A sandboxed
   direct request to the currently running localhost server was denied by the
   environment, so this report does not claim a fresh live capability read.

The accepted 16K-F matrix, once these inputs are supplied and a separate full
execution authority is granted, remains:

1. D0 ~1.3k-child cold proxy in an isolated empty data root;
2. largest roster-confirmed text-bearing source/representation, cold;
3. complete 39-document primary non-OCR corpus, cold;
4. immediate warm repeat of that exact primary corpus using the same cache root
   and a new workspace.

For the full corpus, the harness submits sequential upload batches bounded by
the unchanged 32-file / 100 MiB request envelope. It records per-operation
revisions, snapshots, worklists, generated/reused counters, stage durations,
and total elapsed time, followed by post-publication queries. The frozen
primary-corpus dense-generation threshold remains 60 minutes; no substitute
linear extrapolation is used. No source content or local inventory JSON is
added to this repository.

## Validation performed

```text
11 synthetic preparation / API-harness tests: PASS
Ruff check on preparation tooling and focused tests: PASS
Ruff format on preparation tooling and focused tests: PASS
git diff --check: PASS
```

The synthetic API test exercises create → streamed `SOURCE_ADD` → fresh GET
polling of the durable operation → publication/source-count checks → query and
content-free evidence serialization. It is harness validation only and is not
16K-F or model/CUDA execution evidence.

The canonical API capability endpoint could not be contacted from the sandbox
(`Operation not permitted`); configuration defaults and current repository
code keep aggregate active-source bytes unset. No live-server capability
claim is made by this report.

## Documentation-reconciliation proposal (not applied)

After the preparation report is reviewed, reconcile only the live projections:

1. In the top beta path of `ROADMAP.md`, replace “Complete Slice 16F beta
   functionality” with an explicit statement that the original Slice 16F Gold
   Lab data plane is `COMPLETE / ACCEPTED / SEALED` at
   `f25f8358aead7fcfe161fff388012cec23b5a573`, and identify 16K-F as the
   separate real beta-corpus acceptance tranche.
2. In `docs/BACKLOG.md`, change 16K-E from planned / implementation not
   authorized to `CLOSED / INDEPENDENTLY ACCEPTED / HUMAN ACCEPTED`, linking
   `docs/evidence/16k_e_ingestion_worklist_progress/16K_E_CLOSURE.md` and exact
   accepted subject `37883b7a90d5f5b73077aa72d478e5b9c38b1b52`.
3. Preserve historical `NOT AUTHORIZED` snapshots as provenance. Keep 16K-F
   execution explicitly unauthorized until its own execution authority.

No roadmap or backlog projection was modified under this preparation authority.
