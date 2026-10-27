# Post-L6 CUDA profile-aware product policy implementation result

**Authority:** `S16-K-LARGE-SOURCE-CAPACITY-POST-L6-CUDA-PRODUCT-POLICY-IMPLEMENTATION-AUTH-001`
**Accepted design subject:** `cf29d42b4163ca24f6734b1c1ecba1bedc24d97e`
**Implementation branch:** `implementation/16k-large-source-capacity-post-l6-cuda-product-policy`
**Implementation candidate:** `5e08fb710113ab2289254192be7a680898a8ca96`

The implementation candidate is the production-and-test commit that precedes
this durable result record. Its exact commit identity is recorded above for
review; this result artifact is added by the follow-up governance commit.

## Implemented decisions

- The qualified large-PDF set is exactly `cpu_onnx_fp32_v1` and
  `cuda_fp16_v1`.
- The legacy `qualified_profile` capability remains the CPU baseline and the
  additive `qualified_profiles` field is authoritative.
- CPU gates remain `MemTotal >= 32,000,000,000` and
  `MemAvailable >= 19,388,303,360` bytes.
- CUDA gates are `MemTotal >= 32,000,000,000`,
  `MemAvailable >= 12,998,318,080`, total VRAM `>= 8,000,000,000`, and
  effective CUDA capacity `global_free + current_process_reserved >=
  7,156,531,200` bytes.
- CUDA observation uses the active resolved device through a bounded PyTorch
  telemetry seam. It does not load or materialize the embedding backend.
- Host and CUDA telemetry failures retain distinct internal attribution while
  safely projecting `memory_telemetry_unavailable` publicly.
- Lifecycle admission occurs before pending vault writes and preserves the
  transport/reconstruction separation.
- AUTO resolution, one-process/one-runtime ownership, disk admission, and all
  product limits remain unchanged.

## Changed paths

Implementation candidate:

```text
src/offline_rag/app/workspace/capacity.py
src/offline_rag/app/workspace/lifecycle.py
src/offline_rag/api/capabilities.py
tests/unit/app/test_slice16k_c_capacity_model.py
tests/unit/app/test_slice16k_l2_bounded_workspace_path.py
```

This result record and `ROADMAP.md` are added in the governance follow-up
commit. No L5 or CUDA qualification evidence files changed.

## Validation

```text
44 passed — focused capacity and bounded workspace lifecycle suites
Ruff — PASS
git diff --check — PASS
```

The focused suites cover exact CPU/CUDA thresholds, VRAM class and effective
capacity, current-process reservation accounting, telemetry fail-closed
behavior, capability projection, unloaded-runtime preservation, and
pre-vault lifecycle rejection/acceptance ordering.

## Bounded real-product CUDA smoke

The bounded smoke was executed against the running host Seneca server through
`GET /v1/capabilities` and repeated twice. Both responses reported:

```yaml
configured_device: auto
active_device: cuda
profile_id: cuda_fp16_v1
selection_reason: auto_cuda_fp16
resolved_precision: fp16
embedding_state: UNLOADED
large_pdf.policy_supported: true
large_pdf.qualified_profiles:
  - cpu_onnx_fp32_v1
  - cuda_fp16_v1
large_pdf.runtime_eligible: true
large_pdf.effective_max_bytes: 94371840
large_pdf.unavailable_reason: null
```

The repeated capability call preserved `embedding_state: UNLOADED`, proving
that capability observation did not materialize the embedding backend. This
was a product capability smoke only; no PDF ingestion and no scientific
qualification cell ran.

## Scientific and policy boundaries

```yaml
scientific_executions: NONE
Q25/Q100/Q250/Q512: NOT RUN
L5 evidence changed: NO
CUDA qualification evidence changed: NO
product limits changed: NO
AUTO behavior changed: NO
hot switching/fallback added: NO
```

## Current terminal

```yaml
POST-L6 CUDA PROFILE-AWARE PRODUCT POLICY
IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW
capabilities_smoke: PASS
unloaded_runtime_preserved: PASS
```

## Post-L6 workspace raw-byte ceiling corrective

**Corrective design authority:**
`S16-K-LARGE-SOURCE-CAPACITY-POST-L6-WORKSPACE-RAW-BYTE-CEILING-CORRECTIVE-DESIGN-AUTH-001`

**Corrective implementation authority:**
`S16-K-LARGE-SOURCE-CAPACITY-POST-L6-WORKSPACE-RAW-BYTE-CEILING-CORRECTIVE-IMPLEMENTATION-AUTH-001`

**Corrective base:** `83971b9fa74409cffb5a3a7b772a699f687eb132`

**Corrective implementation candidate:** `PENDING — PINNED IN FOLLOW-UP GOVERNANCE COMMIT`

The beta default `api.max_active_source_bytes_per_workspace` is now null.
Aggregate active raw bytes remain storage/resource information used by the
reconstruction disk rule `max(known_lower_bound, 5 × A) + 1 GiB`; they are not
an unqualified searchable-workspace capacity ceiling. Explicit numeric
workspace byte settings remain supported for controlled tests and deployments.

Capabilities project the workspace byte field as nullable, preserve the legacy
100 MiB request alias, and the UI applies aggregate Add/Replace checks only
when the workspace field is numeric. PDF/non-PDF/request limits, CPU/CUDA
gates, AUTO behavior, publication semantics, and all L5/CUDA evidence remain
unchanged.

Corrective validation:

```text
Python focused corrective regressions: PASS
UI Shupe oversized-workspace regression: PASS
Scientific executions: NONE
Promotion: NOT AUTHORIZED
```

**Corrective terminal:**
`IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT REVIEW`
