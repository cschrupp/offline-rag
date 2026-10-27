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
43 passed — focused capacity and bounded workspace lifecycle suites
Ruff — PASS
git diff --check — PASS
```

The focused suites cover exact CPU/CUDA thresholds, VRAM class and effective
capacity, current-process reservation accounting, telemetry fail-closed
behavior, capability projection, unloaded-runtime preservation, and
pre-vault lifecycle rejection/acceptance ordering.

## Bounded real-product CUDA smoke

The required real CUDA smoke was attempted in this execution environment but
could not be completed:

```text
torch.cuda.is_available(): False
torch CUDA build: 13.0
Seneca server: startup completed, but loopback binding was unavailable
```

Therefore the normal `AUTO -> cuda_fp16_v1` capability projection has not been
claimed as a real-host smoke result here. No synthetic CUDA smoke is promoted
to scientific or product evidence. A qualified CUDA host/server must execute
the bounded smoke before this implementation can be declared
`READY_FOR_INDEPENDENT_REVIEW` under the implementation authority.

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
IMPLEMENTATION COMPLETE / CUDA PRODUCT SMOKE BLOCKED
reason: no CUDA runtime or reachable bound Seneca server in this environment
independent_review: NOT YET READY
```
