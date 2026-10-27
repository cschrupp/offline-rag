# Post-L6 CUDA profile-aware large-PDF product policy

**Authority:** `S16-K-LARGE-SOURCE-CAPACITY-POST-L6-CUDA-PRODUCT-POLICY-DESIGN-AUTH-001`
**Design base:** `649292e06520bb5cd03f40b5fc1395fad8c8ff9e`
**Accepted CUDA evidence:** `9fcec2109e92bbd11749a6fd91a8430af6110bb4`
**Accepted L6 implementation:** `c4c0f7677783fa40b7b656bc96d8c0f2de0a9923`
**Canonical L6 promotion tip:** `df14ef6924fce32c6621e6b5f0b30fbe4cc7c870`
**Status:** `POST-L6 CUDA PROFILE-AWARE PRODUCT POLICY — DESIGN COMPLETE / READY FOR INDEPENDENT REVIEW`

This is a design-only tranche. It defines how the independently accepted CUDA
qualification joins the existing CPU large-PDF policy. It does not change
production code, configuration, APIs, UI behavior, scientific evidence, or
promotion state. A separate implementation authority is required.

## Decision boundary

L6 currently exposes a 90 MiB PDF policy only when the active runtime is the
qualified CPU profile. The post-L6 CUDA campaign independently qualified the
same 90 MiB PDF class for `cuda_fp16_v1`. This design makes both profiles a
closed qualified set while keeping the one-process/one-runtime architecture
and the existing `AUTO` resolver unchanged.

The design does not add request-scoped profile selection, a second embedder,
CPU-ingestion/CUDA-query split, hot fallback, runtime reconstruction, or any
new qualification run. The active resolved profile remains authoritative for
all admission and capability decisions.

## Evidence lineage

| Evidence | Subject or result | Meaning |
|---|---|---|
| CPU L5 | `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`; Q100 and Q100-CONFIRM passed | CPU Q100 class confirmed; CPU policy already accepted |
| CUDA campaign | `9fcec2109e92bbd11749a6fd91a8430af6110bb4` | `cuda_fp16_v1` Q25, Q100, and independent Q100 confirmation passed |
| CUDA IR-001 | acceptance record `649292e06520bb5cd03f40b5fc1395fad8c8ff9e` | CUDA 90 MiB evidence independently accepted |
| L6 production policy | technical subject `c4c0f7677783fa40b7b656bc96d8c0f2de0a9923`; promotion `df14ef6924fce32c6621e6b5f0b30fbe4cc7c870` | 90/25/100 MiB limits and existing admission semantics are active |

The CUDA Q100 whole-window RSS maximum was `10,398,654,464` bytes. A 25%
operational margin gives the host `MemAvailable` gate
`12,998,318,080` bytes. The CUDA campaign's maximum reserved VRAM was
`5,725,224,960` bytes; a 25% operational margin gives an effective CUDA
capacity requirement of `7,156,531,200` bytes. These are admission envelopes,
not mathematical memory bounds or claims about arbitrary PDF families.

## Frozen policy decisions

### D01 — Qualified profile set

The qualified large-PDF profile set is exactly:

```yaml
qualified_profiles:
  - cpu_onnx_fp32_v1
  - cuda_fp16_v1
```

No other profile receives a large-PDF qualification claim. The existing
singular `qualified_profile` field is not repurposed into a list.

### D02 — CPU profile policy remains unchanged

For `cpu_onnx_fp32_v1`, preserve the accepted L6 gates:

```yaml
MemTotal:     ">= 32,000,000,000"
MemAvailable: ">= 19,388,303,360"
```

The CPU effective PDF limit is 90 MiB only when both gates are observable and
pass. CPU rejection reasons and ordinary non-PDF behavior remain unchanged.

### D03 — CUDA host-memory policy

For `cuda_fp16_v1`, require:

```yaml
MemTotal:     ">= 32,000,000,000"
MemAvailable: ">= 12,998,318,080"
```

The lower CUDA `MemAvailable` threshold is profile-specific and is not applied
to CPU. Missing or unreliable host telemetry fails closed.

### D04 — CUDA VRAM class gate

The active qualified CUDA device must report total VRAM of at least
`8,000,000,000` bytes. This is a product resource class gate, not a promise
that every GPU with that nominal size can run every PDF.

### D05 — CUDA effective-capacity gate

Admission uses the active qualified runtime's exact CUDA device. Define:

```text
effective_cuda_capacity_bytes
    = global_free_bytes
    + current_process_cuda_reserved_bytes
```

Require:

```text
effective_cuda_capacity_bytes >= 7,156,531,200
```

The current process reservation is included because it is already occupied by
the active embedder but remains available to that same runtime for the
operation. Free bytes from other devices, estimated process headroom, or
external consumer reservations are not substituted. Telemetry for the active
device must be read from the qualified runtime's device context.

### D06 — Telemetry fail-closed semantics

If host or CUDA telemetry cannot be read, is malformed, or cannot be tied to
the active runtime/device, the large-PDF capability is ineligible and a
large-PDF mutation is rejected before vault persistence. Public reasons are
stable and contain no local paths or raw driver diagnostics:

```yaml
host telemetry unavailable: memory_telemetry_unavailable
CUDA telemetry unavailable: memory_telemetry_unavailable
host gate failed: large_pdf_host_memory_insufficient
CUDA capacity failed: large_pdf_gpu_memory_insufficient
```

Resource failures use `service_overloaded` / HTTP 503 where they are
retryable. Profile and policy failures remain non-retryable request errors.

### D07 — Profile authority

The active process profile is the only profile used for large-PDF admission.
The resolver's result and the qualified runtime's profile identity must agree.
No request may select a different profile or instantiate a second embedder.

### D08 — AUTO behavior is unchanged

`AUTO` continues to resolve as follows:

```text
usable CUDA -> cuda_fp16_v1
CUDA unavailable or probe failure -> cpu_onnx_fp32_v1
```

This design does not alter resolver precedence, CUDA probing, or startup
configuration.

### D09 — No hot fallback or switching

If the active CUDA runtime fails its large-PDF resource gate, the operation
fails closed. It does not switch to CPU, rebuild a runtime, or retry through a
different profile. The operator may change the process profile through the
existing deployment/startup procedure, outside this tranche.

### D10 — Limits remain frozen

```yaml
PDF per source:             94,371,840 bytes (90 MiB)
non-PDF per source:         26,214,400 bytes (25 MiB)
request envelope:          104,857,600 bytes (100 MiB)
workspace active raw bytes: 94,371,840 bytes (90 MiB)
files per request:          32
```

No Q250/Q512 result is implied, and no product limit is raised by this
design.

### D11 — Desired-set semantics

The existing complete post-mutation desired-set predicate remains authoritative:

```text
large_pdf_execution_required = any(
    source.media_type == "application/pdf"
    and source.byte_size > 25 MiB
    for source in post_mutation_desired_set
)
```

An unrelated mutation that reconstructs an already-active large PDF therefore
uses the active profile's gates. Removing the last large PDF does not require
large-PDF resource admission.

### D12 — Admission ordering

For a mutation requiring reconstruction, apply gates in this order:

1. establish and validate the complete desired set;
2. enforce request, file, per-source, and workspace-byte limits;
3. verify the active profile is in `qualified_profiles`;
4. apply that profile's host-memory gate;
5. if CUDA is active, apply total-VRAM and effective-capacity gates;
6. apply the existing reconstruction disk rule;
7. only then write to the vault, project, parse, index, and publish.

All rejection paths are atomic with respect to durable source and publication
state. `SOURCE_REMOVE` from an oversized legacy workspace remains available;
the existing empty-workspace disk exception remains in force.

### D13 — Disk policy is unchanged

For a non-empty reconstruction desired set, let `A` be post-mutation active
raw-source bytes. Preserve:

```text
required_free_bytes = max(known_lower_bound_bytes, 5 * A) + 1 GiB
```

This design does not change disk admission or its ordering.

### D14 — Capabilities are additive and runtime-effective

`GET /v1/capabilities` must preserve the accepted L6 fields and add the
authoritative closed set:

```json
{
  "large_pdf": {
    "policy_supported": true,
    "policy_max_bytes": 94371840,
    "qualified_profiles": ["cpu_onnx_fp32_v1", "cuda_fp16_v1"],
    "qualified_profile": "cpu_onnx_fp32_v1",
    "runtime_eligible": true,
    "effective_max_bytes": 94371840,
    "unavailable_reason": null
  }
}
```

The singular `qualified_profile` remains as a deprecated CPU-baseline field
for compatibility; clients must use `qualified_profiles` and the effective
runtime fields for current behavior. Under an active eligible CPU or CUDA
runtime, the effective limit is 90 MiB. Under an unqualified profile, failed
host gate, failed CUDA gate, or unavailable telemetry, it is 25 MiB with the
corresponding stable reason. The existing workspace capacity and transport
fields retain their L6 meanings.

### D15 — UI contract

The UI continues to consume `large_pdf.effective_max_bytes` and the existing
workspace capacity fields. It does not expose profile selectors, CUDA-specific
thresholds, fallback controls, or Q250/Q512 claims. The backend remains the
authority.

### D16 — API and error semantics

Preserve the existing top-level error model. The implementation may use these
stable details reasons:

```yaml
large_pdf_profile_not_qualified: request_invalid / 422
large_pdf_host_memory_insufficient: service_overloaded / 503
large_pdf_gpu_memory_insufficient: service_overloaded / 503
memory_telemetry_unavailable: service_overloaded / 503
storage_insufficient: service_overloaded / 503
```

No absolute filesystem paths, driver dumps, or memory inventories are
returned. Existing aliases remain migration-compatible.

### D17 — Backward compatibility

Existing workspaces, generic 25 MiB non-PDF semantics, request limits, source
identity reuse, and ordinary CUDA query behavior remain unchanged. The only
new capability is that an eligible active CUDA runtime may use the already
accepted 90 MiB PDF policy.

### D18 — Implementation and science boundary

Expected implementation scope is limited to the existing capacity admission,
capabilities types/projection, API error typing, and focused tests. The CUDA
resolver is not changed. No new dependency, parser contract, ingestion
architecture, UI profile flow, Q250/Q512 run, or other scientific execution
is authorized by this design.

## Validation required for a future implementation

The implementation must add deterministic tests for:

- the exact CPU and CUDA host-memory thresholds;
- CUDA total-VRAM and effective-capacity calculations;
- inclusion of current-process CUDA reservation;
- active-device selection and telemetry-unavailable fail-closed behavior;
- unqualified profile rejection;
- `AUTO` capability projection for usable CUDA and CPU fallback;
- 90 MiB effective capability for eligible CPU and CUDA runtimes;
- 25 MiB effective capability and stable reasons for each failed gate;
- complete desired-set admission when an existing large PDF is reconstructed;
- all resource rejections occurring before `vault.put_path()` or
  `vault.put_bytes()`;
- unchanged removal, disk, identity, request, and non-PDF behavior;
- UI projection through `effective_max_bytes` without profile controls.

Tests must use independent telemetry fixtures and must not synthesize a
profile identity by copying the requested profile string.

## Explicit non-scope

This tranche does not authorize production implementation, configuration
changes, migration, UI changes, CUDA runtime changes, profile switching,
request-scoped routing, Q250/Q512 execution, a new capacity campaign, L5
evidence edits, branch promotion, or changes to the accepted 90/25/100 MiB
limits.

## Review handoff

```yaml
terminal: POST-L6 CUDA PROFILE-AWARE PRODUCT POLICY
status: DESIGN COMPLETE / READY FOR INDEPENDENT REVIEW
authority: S16-K-LARGE-SOURCE-CAPACITY-POST-L6-CUDA-PRODUCT-POLICY-DESIGN-AUTH-001
base: 649292e06520bb5cd03f40b5fc1395fad8c8ff9e
accepted_cuda_evidence: 9fcec2109e92bbd11749a6fd91a8430af6110bb4
production_behavior_changed: false
scientific_executions: NONE
implementation: NOT AUTHORIZED
promotion: NOT AUTHORIZED
```
