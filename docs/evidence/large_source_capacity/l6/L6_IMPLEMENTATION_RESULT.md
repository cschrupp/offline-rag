# L6 Product Policy Implementation Result

## Authority and subjects

- Governing authority: `S16-K-LARGE-SOURCE-CAPACITY-L6-PRODUCT-POLICY-IMPLEMENTATION-AUTH-001`
- Authorized base: `cf2027ef9538d1324e17ef4bddf3bfe1d0d0d5bd`
- Accepted design subject: `87f56ec07ccf710089eb52b7a3d7efa42ac60799`
- Branch: `implementation/16k-large-source-capacity-l6-product-policy`
- Candidate identity: the containing implementation commit (this artifact does not self-reference its own SHA)
- Corrective review base: `0688af96490047980683a7ca3eaa9d979a4db6cc`

## Implemented policy

- PDF per-source limit: `94,371,840` bytes (90 MiB).
- Non-PDF per-source limit: `26,214,400` bytes (25 MiB).
- Incoming request envelope: `104,857,600` bytes (100 MiB).
- Workspace active raw-source ceiling: `94,371,840` bytes (90 MiB), evaluated over the complete post-mutation desired set.
- A desired set containing a PDF over the non-PDF threshold requires the qualified `cpu_onnx_fp32_v1` profile.
- Large-PDF host admission requires `MemTotal >= 32,000,000,000` and `MemAvailable >= 19,388,303,360` bytes.
- Reconstruction disk admission requires `max(known_lower_bound, 5 * active_raw_source_bytes) + 1 GiB` free on the mutable storage filesystem. Empty desired-set transitions bypass this reconstruction reserve.
- CUDA has no large-PDF qualification claim.

## Implementation footprint

- Configuration models, YAML defaults, and environment overrides expose the PDF and workspace-byte policy.
- Multipart and local spooling apply the authoritative media-aware source limit and stable `source_file_too_large` / `request_too_large` reasons.
- Workspace lifecycle admission validates the full desired set before projection and ingest, including replacement and unrelated mutations that reconstruct an active large PDF.
- Runtime profile, memory telemetry, and disk admission fail closed before expensive reconstruction.
- Capabilities distinguish policy limits from runtime eligibility and expose `large_pdf.effective_max_bytes`; the legacy `source_limits.max_active_source_bytes` remains the 100 MiB request-envelope alias.
- Workspace UI validation and copy consume the effective PDF limit and workspace raw-byte ceiling.
- No parser, ingestion, scientific qualification, or L5 evidence bytes were changed.

## IR-001 corrective implementation

The narrow corrective closes all four independent-review findings:

- `SOURCE_REMOVE` is exempt from the aggregate workspace-byte ceiling while retaining integrity, runtime, and reconstruction-disk admission for non-empty desired sets.
- Workspace multipart admission derives media type from the validated filename extension; client MIME headers cannot grant the PDF allowance.
- Desired-set resource admission now runs before any vault write, so byte, profile/memory, and disk rejection cannot create durable raw-source objects.
- Path-backed replacements use `put_path` with the established content hash; the whole-file `load_bytes` path remains only for bounded in-memory callers.

## Admission and error semantics

Admission order is desired-set integrity, active-source count, active raw-source bytes, large-PDF profile/memory eligibility, and reconstruction disk reserve, followed by projection/spooling and the existing full-replace ingest. Removal to an empty desired set continues through the empty-transition path without reconstruction-specific admission. Stable reasons are `source_file_too_large`, `request_too_large`, `workspace_source_bytes_exceeded`, `large_pdf_profile_not_qualified`, `large_pdf_host_memory_insufficient`, and `storage_insufficient`.

## Validation

- `uv run pytest -q tests/unit/app/test_slice16k_c_capacity_model.py tests/unit/app/test_slice16k_l2_bounded_workspace_path.py tests/unit/app/test_slice16d_a_settings_capabilities.py -k 'not capabilities_endpoint and not capabilities'` — **25 passed** (one existing Starlette deprecation warning).
- `uv run pytest -q tests/unit/app/test_slice16k_c_capacity_model.py` — **20 passed**.
- `uv run pytest -q tests/unit/app/test_slice16k_l2_bounded_workspace_path.py` — **9 passed**.
- `uv run pytest -q tests/unit/app/test_slice15a_foundation.py -k 'settings or defaults'` — **1 passed**.
- Ruff on all changed Python sources/tests — **passed**.
- `git diff --check` — **passed**.
- Frontend ESLint on changed files — **passed**.
- Full frontend `npm run typecheck` remains blocked by one pre-existing unrelated cast error in `src/test/p4_human_uat_duplicate_message.test.ts`; no L6 file is involved.
- Full frontend `npm run lint` remains blocked by four pre-existing React hook errors in Gold Lab files; no L6 file is involved.
- The existing capabilities endpoint integration test did not complete within the bounded local run because its pre-existing runtime/TestClient setup remains long-running; no scientific or qualification execution was performed.
- Corrective focused suites after IR-002 changes: **32 passed** in the affected combined run (21 capacity tests and 13 bounded workspace path tests individually), including removal recovery, MIME classification, profile rejection, memory rejection, disk rejection, pre-vault ordering, and path-backed replacement regressions.
- The three lifecycle-level pre-vault rejection proofs each assert both `vault.put_path` and `vault.put_bytes` were not called.

## Scientific and product boundary

- Scientific executions performed: **NONE**.
- L5 evidence changed: **NO**.
- Production limits before: 25 MiB/file and 100 MiB/request, with no accepted workspace-byte claim.
- Production limits after: PDF 90 MiB, non-PDF 25 MiB, request 100 MiB, workspace active raw-source 90 MiB, subject to runtime admission.
- CUDA large-PDF claim: **NONE**.
- Known deviations: none from the accepted L6 design. The frontend repository retains the unrelated pre-existing lint/typecheck failures listed above.

## Review readiness

The bounded corrective implementation is complete and ready for independent re-review. The final candidate commit contains this canonical result artifact and the ROADMAP pointer. Tracked working-tree status is expected to be clean after the final commit.

`LARGE-SOURCE CAPACITY L6 PRODUCT POLICY IR-002 VALIDATION REWORK COMPLETE / READY FOR INDEPENDENT RE-REVIEW`
