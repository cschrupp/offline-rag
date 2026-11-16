# Slice 18D-R — Implementation Result

## Disposition

```yaml
slice: 18D-R
base: 8591aacc1810ba7265014c55a4d9327f7f755a02
implementation_commit: ebcf3db3160add5cd25c3068949f3fd6ba0e251a
final_implementation_candidate: ef606f667ad13a4730ef04fef648ff1f800d8652
status: IMPLEMENTATION COMPLETE
automated_qualification: PASS
independent_review: PENDING
human_review: PENDING
promotion: NOT AUTHORIZED
18E_and_later: NOT AUTHORIZED
```

The change places a portfolio-facing Engineering Summary before the existing
evidence audit surface. The existing v3 registry → exporter → manifest → UI
chain remains authoritative. The Summary selects accepted records, facts,
variants, retrieval arms, and metrics by semantic identity and fails visibly
when a required binding is missing or unavailable.

## Evidence and source identity

| Artifact | Identity |
| --- | --- |
| Registry | `eval/presentation/accepted_evidence_registry_v3.json`; SHA-256 `ac4db2af380d2a94086ab4fc56f7245814b372b9cd86528013dff60dd070ae06` |
| Indicator catalog | `indicatorcatalog_24735a5597763f36fb954e9898f206390af6200fecec75daeb8bdc5b29f60586`; file SHA-256 `a43d97f4e17e5d0fd9a98e5dcd01c06d2b44ce2d93c71e7f3f7c84979d897404` |
| Exported manifest | `engmanifest_bc26cf281178f81e043d542318a6ec198e58c6c6a49c74eda9b64481906199c5`; file SHA-256 `ddf818d55024d6b2c5084c2002296b4f56cb06726e8322b4418233ec9fb8001f` |
| Generation report | `docs/pilots/slice10e_generation_prompt_ab.md`; SHA-256 `27220cfe69d35f38b6f0e952b262dd21901d0dabce564ae5fec82bd489997a15` |
| REL-01 qualification | `docs/evidence/rel01/QUALIFICATION.md`; SHA-256 `5f67af09ba81e7d26221b57403544a0f41bdd92d3f904d5512ecd4b603ba2287` |
| 18C qualification | `docs/evidence/slice18c_universal_distribution/QUALIFICATION.md`; SHA-256 `7d320c76c597dfd8e0d5467905eeeca29b6319bffb5d23446415eaa0d7cc7189` |
| Metric surface inventory | `docs/evidence/slice18d_metrics/SURFACE_INVENTORY.json`; SHA-256 `299db99616b45b3a2063956f49b21e4bb2214350d262279187734f15bc3000c8`; 201 rows, all cleared |
| Metric defect ledger | `docs/evidence/slice18d_metrics/DEFECT_LEDGER.json`; 10 defects, all `RESOLVED` |

The three new catalog definitions support source-recorded answer counts,
question counts, and image-reduction proportion. Five generation counts and
four release-image facts are additive source-bound bindings. The source
generation counts are literal-validated against the accepted report; the
image-size and reduction facts are literal-validated against their accepted
qualification records. The current CPU-image measurement comes from the
accepted 18C qualification. No scientific observations were recomputed.

The existing 107 v2 observation tuples
`(availability, value, unit, value_qualifier)` remain identical in the v3
projection. Exactly nine additional source-bound observations were added for
the Summary.

## Claim bindings

| Summary claim / content | Binding class | Basis |
| --- | --- | --- |
| Local-first document parsing, semantic and lexical retrieval, reranking, grounded generation, citation membership/provenance | `BOUND` | Accepted current architecture and product evidence; citation explanation explicitly does not claim semantic entailment. |
| External generation is an optional operator-approved seam; other evidence authority remains local | `BOUND` | Accepted REL-03 boundary and current product configuration evidence. |
| Lexical retrieval remains alongside semantic retrieval for exact technical identifiers, codes, terminology, and names | `HUMAN` | Human-approved engineering rationale; not presented as a measured benchmark conclusion. |
| 14C hybrid versus hybrid-plus-reranker nDCG@10 and retrieval p50 | `BOUND` | Existing accepted `performance.slice14c` variants and metric definitions. Direction wording is derived from the selected values; no delta is calculated. |
| Dense pilot C/D values and ordering sensitivity | `BOUND` | Existing accepted `retrieval.slice9hp` arms and population notes. The page states the pilot did not establish a universal winner. |
| Answer, generation-failure, grade-2-hit, and invalid-citation values | `BOUND` | Accepted generation prompt metrics plus the source-bound full-22 and eligible-subset counts. Same-model and same-endpoint judging is disclosed. |
| Citation validation establishes citation membership and provenance, not entailment or faithfulness | `BOUND` | Accepted conversation/citation contract and evidence caveat. |
| CPU/CUDA execution profiles and current 90 MiB PDF limit / large-PDF threshold | `BOUND` | Accepted current runtime and capacity evidence. Historical CPU/CUDA campaign results are not represented as current. |
| Original and optimized REL-01 image sizes and recorded 77.52% reduction | `BOUND` | Accepted REL-01 source-recorded values, labeled historical. |
| Current CPU image size | `BOUND` | Accepted 18C qualification, separated from the historical optimization comparison. |
| Level-C end-to-end and generation p50 | `BOUND` | Accepted Level-C record and its population label; shown only in a disclosure with descriptive/no-SLO limits. The 14C retrieval p50 remains explicitly a different population and path. |
| Learned router rejection, query-retry-disabled status, security campaign fail-closed disposition | `BOUND` | Existing accepted decision, recovery, and security evidence. No new campaign ran. |
| Public-safe cited-answer screenshot or external demo corpus | `PUBLIC_EXAMPLE` | Not used; no public example was required or added. |
| Unsupported accuracy, entailment, universal-winner, security-completeness, or release-SLO claims | `OMIT` | Unsupported or disallowed by the accepted narrative contract. |

## Routes and user-facing structure

- `/engineering` redirects to `/engineering/summary`.
- `/engineering/summary` is the new six-section portfolio page.
- `/engineering/architecture` remains the Architecture page, with bounded
  terminology cleanup only.
- `/engineering/evidence` serves the existing detailed audit console.
- `/engineering/evaluation` remains as a compatibility redirect to Evidence.
- Engineering navigation now reads Summary / Architecture / Evidence; the
  Overview primary Engineering CTA opens Summary.
- Summary evidence links target stable IDs on the corresponding Evidence card.

The implementation was committed in `ebcf3db3160add5cd25c3068949f3fd6ba0e251a`, followed by the narrative correction `3577047f9507f67ca4b86f4b958b2893b6b0278e`. Corrective commit `111348d6f1c51fc3aba41ec03074a65cb7061241` reconciles Architecture with the current CPU/CUDA distribution, makes the generation-count link point to its source record, adds the current-configuration evidence link, and clarifies the historical CUDA caveat. It changes no accepted measurements.

Presentation corrective `2094fe8d402688f7cb454f7fe09b3bc2c7c5cb03` replaces auditor-facing Summary prose with reader-facing component copy while retaining manifest-bound measurements and fail-closed evidence guards. It adds the retrieval comparison chart, limits each narrative section to one evidence link, and scrolls asynchronous Evidence cards into view for hash links. The regression uses the bundled manifest and checks visible copy for audit vocabulary and internal identifiers. No registry, catalog, exporter, manifest, or scientific measurement changed. The subsequent header corrective `ef606f667ad13a4730ef04fef648ff1f800d8652` applies the requested Engineering page title/description and extends the visible-copy regression to include the page header; it updates the older route expectation accordingly. The final technical candidate is `ef606f667ad13a4730ef04fef648ff1f800d8652`.

Changed implementation paths across the implementation and four corrective code commits:

```text
docs/evidence/slice18d_metrics/SURFACE_INVENTORY.json
eval/presentation/accepted_evidence_registry_v3.json
eval/presentation/indicator_catalog_v1.json
scripts/build_seneca_engineering_evidence.py
tests/unit/test_slice16e_engineering_evidence.py
tests/unit/test_slice18d_indicator_catalog.py
ui/public/evidence/engineering-evidence-v3.json
ui/src/app/router.tsx
ui/src/features/engineering/EngineeringNav.tsx
ui/src/features/engineering/evidenceTypes.ts
ui/src/features/engineering/portfolioProjection.ts
ui/src/pages/EngineeringArchitecturePage.tsx
ui/src/pages/EngineeringEvaluationPage.tsx
ui/src/pages/EngineeringSummaryPage.tsx
ui/src/pages/OverviewPage.tsx
ui/src/styles/global.css
ui/src/test/slice16e_engineering_evidence.test.tsx
ui/src/test/slice16h_integration_acceptance.test.tsx
ui/src/test/slice18d_r_engineering_summary.test.tsx
```

## Qualification

The exact-candidate commands and results are:

| Command | Result |
| --- | --- |
| `python scripts/build_seneca_engineering_evidence.py --check` | PASS; final corrective manifest identity above |
| `pytest -q tests/unit/test_slice16e_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | 37 passed on final corrective candidate |
| `cd ui && npm test` | 473 passed across 51 files on pre-corrective candidate `3577047f`; final corrective was checked by the focused suite below |
| `cd ui && npm test -- --run src/test/slice18d_r_engineering_summary.test.tsx src/test/slice16e_engineering_evidence.test.tsx` | 26 passed across 2 files on final presentation corrective candidate |
| `cd ui && npm run lint` | PASS |
| `cd ui && npm run typecheck` | PASS |
| `cd ui && npm run build` | PASS; existing Vite advisory that the main minified chunk exceeds 500 kB |
| `ruff check scripts/build_seneca_engineering_evidence.py tests/unit/test_slice16e_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `ruff format --check scripts/build_seneca_engineering_evidence.py tests/unit/test_slice16e_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `python -m py_compile scripts/build_seneca_engineering_evidence.py tests/unit/test_slice16e_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `git diff --check` | PASS |

The presentation corrective's focused tests cover the reader-facing copy,
bundled-manifest identifier/audit-language exclusion, one-per-section evidence
links, and deferred Evidence-card scroll target, alongside the existing
Engineering evidence tests.
The build warning is advisory and unrelated to this tranche. No model, benchmark,
security, GPU, ingestion, or scientific campaign was run. No live/Human UI
presentation was performed.

## Planning/status reconciliation

Current planning now records 18D as complete / Human accepted / promoted at
`8591aacc`; 18D-R as implementation complete with automated qualification
passed and independent/Human review pending; 18E Storage Location & Data Root
Selection, 18F Canonical Documentation & Portfolio Narrative, 18G Public
Release & Demo Assembly, and M7 closeout remain unauthorized. Historical
status passages remain historical.

## Remaining gates

```yaml
implementation: COMPLETE
candidate: ef606f667ad13a4730ef04fef648ff1f800d8652
automated_qualification: PASS
H1_presentation: PENDING
H2_fresh_reviewer: PENDING
H2_result: PENDING
independent_review: PENDING
human_acceptance: PENDING
promotion_to_main: NOT AUTHORIZED
18E_and_later: NOT AUTHORIZED
```

H1 requires the Human owner to present the exact candidate Summary for about
five minutes and record confusion and disposition. H2 requires a named,
technically competent fresh reviewer and an approximately ten-minute review of
the exact candidate; no reviewer or result is fabricated here.
