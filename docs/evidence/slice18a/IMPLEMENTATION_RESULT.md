# Slice 18A — Engineering Evidence Reconciliation

**Disposition:** Implementation complete; ready for independent review.
**Implementation branch:** `feature/slice18a-engineering-evidence-reconciliation`
**Base:** canonical `main` at `0a1b5a45bff94ae12c8fe8d423c825572bc1c480`
**Audit/design:** Slice 18A-0 complete; corrected audit and design freeze are in
[`docs/slice18a_engineering_evidence_reconciliation.md`](../../slice18a_engineering_evidence_reconciliation.md).

## Scope delivered

The registry/exporter/UI chain now uses the versioned v2 contract for the
question-driven Engineering portfolio. The original v1 registry and generated
manifest remain present and unchanged as historical artifacts. The two
existing routes remain `/engineering/evaluation` and
`/engineering/architecture`.

The active manifest is
`engmanifest_64fae8b88b042800952b9868ef6f33b0ede026185f17893cada125f296ccebec`.
The v2 registry adds exactly these six records approved by the audit:

- `product.current-configuration`
- `generation.grounding-and-external-boundary`
- `runtime.compute-portability`
- `capacity.large-source-envelope`
- `release.verification`
- `conversation.decision-history`

The six previous evidence records remain underlying evidence. Their accepted
metrics and source hashes were retained; record currency and decision effect
were added. `evidence_authority` is limited to `accepted` or `authoritative`;
`currency` is separately `current` or `historical`; `promotion_status` means
product/configuration promotion, not Git promotion. Authority, currency,
decision effect, and product/config promotion render as separate fields.
Fact currency defaults to the record. Explicit mixed-currency overrides are
used for recovery (current operational recovery and disabled product recovery),
conversation decision history (historical 01A/01B, current 01C), large-source
qualification (historical CPU/CUDA Q100 observations, current L6 admission),
and release verification (historical hosted-run counts, current REL-01 image
qualification).

The generic `key_facts` presentation requires claim, explicit scope, currency,
and one or more source references for every fact. Historical Q100 and hosted
run facts are explicitly marked historical inside otherwise current records.
New measured values require a source binding: JSON Pointer or YAML path
extraction, or a numeric literal verified against the cited source. The six new records source-bind numeric claims including the Q100 fixture
byte counts, 90 MiB product PDF limit, 25 MiB large-PDF threshold, REL-01 image
size, and bounded hosted test totals.
Historical curated values in the existing records remain hash-pinned; no
retroactive bulk literal-validation project was added. Visible portfolio
metrics use rounded precision while exact values remain in the static manifest
and the collapsed exact-presentation provenance view.

The Evaluation page now distinguishes current product/configuration facts from
historical pilot results. It states that citation membership is checked
against the current query's `EvidenceUnit[]` and provenance is resolved, while
explicitly warning that membership validity does not prove semantic support.
The current retrieval description is dense + BM25 → RRF → BGE reranker.
ADR-005 explains RRF's use because dense and lexical scores are not directly
calibrated; ADR-006 keeps reranking separate so candidate retrieval and
cross-encoder ranking remain independently measurable. The descriptive Slice
9H-P and 14C evidence did not promote a retrieval winner. Large-source
qualification is separate from L6 product admission: PDFs are limited to 90
MiB, and only a desired set containing a PDF over the ordinary 25 MiB threshold
requires the qualified CPU profile and accepted host/resource gates. Slice 12C
query/retrieval rewrite-and-retry recovery is distinguished from accepted
operational crash/restart recovery.

The Architecture route has exactly five diagrams: life of a question,
snapshot/provenance, runtime portability, deployment/trust boundary, and the
evidence publication chain. Runtime portability shows CPU ONNX and CUDA FP16 as
alternatives selected by the existing AUTO policy, with provisioned assets
external to the image. The REL-03 trust note covers grounded answer generation,
explicit conversation transformations, and Gold authoring; retrieval, embeddings,
reranking, evidence selection, citation membership/provenance authority, and
Gold truth remain local. No routes or execution controls were added.

## IR-001 corrective summary

The large-PDF claim now distinguishes the 90 MiB PDF maximum from the 25 MiB
threshold that activates the CPU profile and host/resource gates; both values
are source-bound. CPU and CUDA runtime profiles are presented as AUTO-selected
alternatives. The current-configuration record cites ADR-005/006 for the RRF
and separate-reranker rationale and explicitly preserves the non-promotion
status of Slice 9H-P/14C. The REL-03 architecture note names grounded answers,
explicit conversation transformations, and Gold authoring while retaining the
local retrieval/evidence/citation authority boundary.

## Historical source preservation

The accepted source hash for the old Level-C presentation was
`0821d4fa117a003aab6a274af262104f17263673fd666acb9b685949a8422eac`, while the
current mutable Milestone 7 projection had since changed. To preserve the
accepted source bytes and keep the hash check fail-closed, the v2 registry
references the exact historical bytes at
`docs/evidence/slice18a/source_snapshots/milestone7_performance_ui_0821d4fa.md`.
The snapshot's SHA-256 is unchanged from the accepted hash. The v1 registry and
manifest were not rewritten.

## Validation

- Exporter determinism, source hash and binding validation: **26 passed** in
  `tests/unit/test_slice16e_engineering_evidence.py`.
- UI evidence and integration regressions: **29 passed** across the two focused
  test files.
- TypeScript project check: **passed**.
- Targeted ESLint: **passed**.
- UI production build: **passed** and copied the v2 manifest into `dist`.
  Vite emitted a non-blocking >500 kB chunk-size advisory.
- Exporter manifest drift check: **passed**.
- Targeted Ruff lint and formatting: **passed**.
- `git diff --check`: **passed**.

No corpus, security, benchmark, or model-inference activity was performed. No
application API, scientific policy, retrieval, generation, compute, or
admission behavior was changed.

## Remaining boundary

This is an accepted-evidence presentation implementation candidate, not
independent review, Human implementation acceptance, a broader portfolio
release, or promotion. No promotion was performed. Slices 18B–18D, a CUDA
release image, and Milestone 7 closeout remain unauthorized. The historical
security record remains bounded to its stated campaign and does not imply
security completeness.
