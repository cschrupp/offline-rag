# Slice 18D — Implementation result

**State:** IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW.

Human accepted the detailed design and authorized 18D-A–E as one implementation
tranche. Base: `c296e21afa740aa8fa7199d88ffda68c59d1be03`.
Branch: `implementation/slice18d-metrics-audit`.
Implementation subject: `f0c0fc4b61774dc67cbcb98a33e8bf1ef8b390fb`.
Human implementation acceptance and promotion remain pending.

## Delivered

- One catalog with 50 versioned definitions, explicit display kinds, source
  authority, population/aggregation, availability and interpretation semantics.
- Engineering v3 registry → existing exporter → v3 manifest → UI. All 107
  accepted v2 observations retain their values, units, availability and original
  qualifiers. No accepted v2 registry, manifest or scientific source was changed.
- Explicit population labels and inherited record provenance; 14C binds its
  frozen suite identity and Level-C its separate run identity. No inferred
  historical numerators, denominators or applicable counts were added.
- Catalog-driven proportions, ranking scores and binary-byte formatting; shared
  live workspace-byte and Gold-coverage formatting. Current-step progress and
  dense-generation throughput describe their actual measurement boundaries.
- Server-owned contribution points, weighting explanation and relevance-task
  coverage denominator. Unknown counts/compute fields use Unavailable, while
  runtime lifecycle and UI loading remain separate.
- Runtime portability's REL-01-only evidence is now historical, with an explicit
  18C evolution caveat. Its accepted numeric values remain unchanged.
- Supported-surface inventory: 200 rows = 92 production JSX source components,
  one supported doctor surface, and 107 explicit Engineering observations.
  Every row has an audit disposition and clearance. Component rows include
  candidate source expressions and reviewed API/derivation families; wrappers
  and provenance-only controls are explicitly exempt where appropriate.
- Ten ledger defects RESOLVED. Zero open scientific escalations or accepted
  deferrals. Inventory coverage and defect clearance have independent checks.

Catalog: `indicatorcatalog_ebff8403baafe162cd4dbb2984971e1437363ed59df2a64ba053d1b52775125c`.
Manifest: `engmanifest_5b0e7763dcee4aa67bf41a9e226f0d29e22e87b3594a6f60cb1e056723ca328d`.

## Executed validation

| Command / population | Result |
| --- | --- |
| `.venv/bin/pytest -q tests/unit/test_slice16e_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | 36 passed |
| `cd ui && npm test -- --maxWorkers=2` | 50 files / 463 tests passed; 129.15 s |
| `cd ui && npm run typecheck` | PASS |
| `cd ui && npm run lint` | PASS; no final lint warning |
| `cd ui && npm run build` | PASS; Vite chunk-size advisory |
| `.venv/bin/ruff check scripts/build_seneca_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `.venv/bin/ruff format --check scripts/build_seneca_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `.venv/bin/python -m py_compile scripts/build_seneca_engineering_evidence.py tests/unit/test_slice18d_indicator_catalog.py` | PASS |
| `.venv/bin/python scripts/build_seneca_engineering_evidence.py --check` | PASS |
| `git diff --cached --check` / `git diff --check` | PASS after EOF whitespace cleanup |

The full UI run initially found two assertions affected by the new labels/byte
formatting. They were corrected to assert the accepted semantics; the final full
population passed. Earlier partial-migration red runs remain development feedback,
not passing evidence. The sandbox runs that did not finish were replaced by a
completed compatible-host run. No startup/application infrastructure was changed.
The benign jsdom document-navigation notice and Vite chunk advisory remain visible.

These results are local implementation evidence, not independent execution or
hosted CI evidence. No model, provider, benchmark, ingestion, security or
performance campaign was executed. No production Python module or dependency
metadata changed. Existing authoritative producer formulas remain intact.

## Boundaries and limitations

The source census and expression locations make omissions mechanically visible;
they do not prove absolute semantic completeness. Static inventory coverage is
supplemented by API/source review and rendered tests. The inventory intentionally
includes shared wrappers and plumbing, and groups live count/status fields by
producer contract rather than adding definition objects to backend APIs.

Historical curated values keep their original source-reporting precision and
source hashes. This tranche does not retroactively establish stronger precision,
semantic entailment, causal performance conclusions or a new SLO. Full backend
scientific qualification was not rerun for a presentation/export change.

No interactive browser visual smoke was performed. All UI verification here is
deterministic rendered regression coverage and a successful production build.

18E, 18F, Milestone 7 closeout and promotion to main remain unauthorized.

## Exact implementation paths
docs/evidence/slice18d_metrics/DEFECT_LEDGER.json
docs/evidence/slice18d_metrics/SURFACE_INVENTORY.json
docs/slice18d_metrics_audit.md
eval/presentation/accepted_evidence_registry_v3.json
eval/presentation/indicator_catalog_v1.json
scripts/build_seneca_engineering_evidence.py
tests/unit/test_slice18d_indicator_catalog.py
ui/public/evidence/engineering-evidence-v3.json
ui/src/components/OperationProgress.tsx
ui/src/features/ask/SourceRail.tsx
ui/src/features/engineering/EvidenceMetric.tsx
ui/src/features/engineering/evidenceClient.ts
ui/src/features/engineering/evidenceTypes.ts
ui/src/features/goldLab/contribution/ContributionDashboard.tsx
ui/src/features/goldLab/quickPlay/QuickPlayContributionRail.tsx
ui/src/features/indicators/catalog.ts
ui/src/features/indicators/format.ts
ui/src/pages/SettingsPage.tsx
ui/src/pages/WorkspacePage.tsx
ui/src/test/beta_game_02b_visual_polish.test.tsx
ui/src/test/slice16c.app.test.tsx
ui/src/test/slice16e_engineering_evidence.test.tsx
ui/src/test/slice16g_i4_contribution.test.tsx
ui/src/test/slice16h_integration_acceptance.test.tsx
ui/src/test/slice16k_e_ingestion_worklist.test.tsx
ui/src/test/slice18d_indicator_semantics.test.tsx
