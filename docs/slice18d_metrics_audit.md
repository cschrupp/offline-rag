# Slice 18D — Product Metrics Audit and Explainability

Authority: detailed design Human accepted; implementation authorized as one
18D-A–E tranche on `implementation/slice18d-metrics-audit`, from
`c296e21afa740aa8fa7199d88ffda68c59d1be03`.

The canonical semantic catalog is `eval/presentation/indicator_catalog_v1.json`.
Its ID hashes canonical JSON excluding `catalog_id`. A definition is identified
by `(definition_id, definition_revision)` under that immutable catalog identity.
Formula, population, aggregation, unit/range or interpretation changes require
a new revision. Editorial changes change the catalog artifact identity. Historical
artifacts keep their own catalog identity and remain interpretable.

Authoritative producers retain ownership of observations. The catalog and
renderer describe and format values; they do not compute scientific results.
The Engineering v3 registry adds explicit JSON-pointer observation bindings to
the existing curated and machine-extracted records. The same exporter continues
supporting the accepted v2 chain for historical verification. It now defaults to
v3. No accepted source or v2 manifest/registry is rewritten.

Observation populations inherit record provenance and carry concrete source
labels. Missing historical applicable counts and availability reasons remain
absent. `source_reported_precision` means the accepted numeric literal is
preserved, not that the underlying measurement is mathematically exact.
An empty evaluator population is unevaluable, never measured zero.

Display kinds distinguish proportions, ranking scores, counts, points, durations,
bytes, throughput, ratios, scalars, percentage-point changes, relative changes,
and statuses. A proportion is multiplied by 100 only for display. nDCG/MRR remain
decimal ranking scores. Throughput units describe the actual numerator/interval.
Measurement availability, runtime lifecycle and UI request state remain distinct.

Live surface bindings live in the supported-surface inventory rather than API
payloads. Workspace source-byte and Gold coverage formatting use the same catalog.
Operation counts/timings, limits, settings, compute fields and pedagogical task
counts retain their existing producers and deterministic derivations. Gold points
are read from `gold-contribution-v1`; the weighting is explanatory only.

The inventory includes a full production JSX file census, candidate field/renderer
locations, per-observation Engineering bindings and the supported workstation
`doctor` diagnostic. Shared components inherit the caller's route. Candidate
locations intentionally include plumbing, so the census is conservative. Static
coverage checks establish source coverage, not absolute semantic completeness;
source/API review and rendered regressions complement them. IDs, citation locators,
decorative values and transient UI request state are explicitly exempt.

Inventory disposition and defect clearance are separate. A scientific escalation
can be inventoried but cannot satisfy clearance. Deferrals require governing
authority, rationale, affected surfaces and visibility/caveat policy. Accepted
historical evidence remains untouched during escalation; unrelated work continues.

Qualification uses deterministic catalog/export/UI tests and static checks only.
All performance observations remain descriptive and population/configuration
specific. No SLO, benchmark, model/security campaign, 18E/18F work, promotion or
Milestone 7 closeout is authorized by this implementation.
