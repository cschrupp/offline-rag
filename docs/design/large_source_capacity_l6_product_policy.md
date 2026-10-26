# Large-source capacity L6 product policy design

**Authority:** `S16-K-LARGE-SOURCE-CAPACITY-L6-PRODUCT-LIMIT-RESOURCE-ADMISSION-DESIGN-AUTH-001`
**Design base:** `4adc1f024a078c19192485cbabfc420c462eb01a`
**Accepted predecessor:** L5 PDF qualification, independently accepted
**Status:** `LARGE-SOURCE CAPACITY L6 PRODUCT POLICY IR-001 REWORK COMPLETE / READY FOR INDEPENDENT RE-REVIEW`

This is a design-only tranche. It does not change production settings, APIs,
UI behavior, or resource admission, and it does not authorize another PDF
qualification run.

## Evidence boundary

L5 established a CPU-only PDF/Docling result through a confirmed Q100 class.
The confirmed fixture was 96,152,520 bytes (91.70 MiB), while the campaign
terminal was `PROFILE_PARTIAL_QUALIFICATION` because CUDA was not evaluable.
The product policy therefore makes a conservative claim below the confirmed
fixture and names the qualified CPU profile explicitly.

The L5 whole-window RSS peaks were 15,223,230,464 bytes for Q100 and
15,510,642,688 bytes for Q100-CONFIRM. The parser-stage sampled peaks were
6,593,409,024 and 6,600,499,200 bytes. The latter values describe the parser
phase only; they are not the process memory envelope. Peak qualifying disk
amplification was 4.00005× source bytes. These measurements inform admission
policy but are not mathematical capacity bounds.

## Frozen product limits

All byte values below are binary MiB/GiB values where stated.

| Policy | Exact value | Scope |
|---|---:|---|
| Default/non-PDF per-source limit | `26,214,400` bytes (25 MiB) | TXT, Markdown, and other currently supported non-PDF media |
| PDF per-source limit | `94,371,840` bytes (90 MiB) | `application/pdf` only |
| Upload request envelope | `104,857,600` bytes (100 MiB) | Incoming HTTP request total; unchanged |
| Active raw-source workspace ceiling | `94,371,840` bytes (90 MiB) | Post-mutation sum of active source `byte_size` values |
| Upload file-count limit | `32` | Incoming request; unchanged |

The generic `max_bytes_per_document` remains 25 MiB. A new media-specific
`max_pdf_bytes_per_document` is 90 MiB. The request total remains independent
of both per-source and workspace limits. A request may contain one 90 MiB PDF
plus other files only while its total remains at or below 100 MiB and the
post-mutation workspace remains at or below 90 MiB.

No MIME type other than PDF receives a new limit claim. Media classification
uses the existing server-validated supported-extension/media-type mapping; a
client filename alone is not authority for a new type.

## Admission order and mutation semantics

The implementation will apply these gates in this order:

1. Validate the HTTP envelope and stream the upload to the existing spool.
2. Apply the media-specific per-source limit while bytes are streamed. The
   same policy applies to path-backed `SOURCE_ADD` and `SOURCE_REPLACE` after
   their streamed spool/digest step; internal reconstruction continues to
   bypass HTTP request limits.
3. Build the exact desired active source set for the mutation and sum its
   stored `byte_size` values.
4. Derive whether the desired set requires large-PDF execution, then apply the
   workspace active-byte gate, disk gate, and any relevant host/profile gate;
   only then begin vault projection and Docling work.

The resource predicate is defined over the complete post-mutation desired set,
not only the incoming file:

```text
large_pdf_execution_required = any(
    source.media_type == "application/pdf"
    and source.byte_size > 25 MiB
    for source in post_mutation_desired_set
)
```

This predicate is true when an already-active large PDF will be reconstructed
because of an unrelated add, replacement, or removal. When it is true, the
active profile, host-memory, and `MemAvailable` gates below apply before
reconstruction. Removing the last large PDF makes the predicate false.

For `SOURCE_ADD` and `SOURCE_REPLACE`, the desired post-mutation sum must not
exceed 90 MiB. The incoming replacement is included in that exact sum. For
`SOURCE_REMOVE`, the active-byte ceiling is not applied: removal must remain
available from an oversized legacy workspace so the user can return below the
supported envelope. A removal that leaves a non-empty desired set still uses
the post-mutation value for reconstruction disk admission and fails atomically
if storage cannot support the reconstruction. A removal that produces an empty
desired set uses the existing empty-workspace transition and does not require
the reconstruction-specific 5× envelope or its 1 GiB reserve.

An existing workspace that is already above 90 MiB remains readable and
queryable. New additions or replacements that leave it above 90 MiB fail
before expensive reconstruction. A replacement that reduces the desired set
to 90 MiB or less is allowed. No mutation partially changes durable source or
publication state on an admission failure.

## Disk admission

Disk admission is an operational envelope backed by the maximum observed L5
amplification plus an explicit reserve. It is not an upper-bound proof.

For a reconstruction-required mutation with a non-empty desired set, let `A`
be the exact post-mutation active raw-source byte sum. For each filesystem
containing a mutable Seneca path used by the operation (staging, workspace
vault, corpus/candidate, chunk, embedding, lexical, manifest, or Qdrant
roots), calculate:

```text
required_free_bytes(fs) = max(known_lower_bound_bytes(fs), 5 * A) + 1 GiB
```

`known_lower_bound_bytes(fs)` accounts for copies the operation can enumerate
on that filesystem. If accounting is unavailable, the implementation uses
`5 * A` as the lower-bound input rather than inventing a smaller value. The
filesystem passes only when its current free bytes meet the requirement. A
path/stat failure is fail-closed as `storage_insufficient`.

The factor 5 is a measured-supported-envelope margin above the observed
approximately 4× qualifying peak. It is not a mathematical upper bound. The
1 GiB fixed reserve covers non-accounted application, logs, stale temporary
files, and filesystem activity; it is an explicit operational reserve rather
than a claim derived from L5. The rule uses post-mutation `A`, so a removal
reduces the target and does not inherit the incoming request size.

For an empty desired set, the existing empty-workspace transition performs
only its established minimal journal/state writes. It does not apply this
large-source reconstruction formula. This keeps final-source removal possible
when less than 1 GiB is free.

The check runs before vault writes, projection, parser execution, or dense
embedding. It reports no absolute filesystem paths.

## Memory and profile support

Large-PDF support is a CPU-only product claim:

```yaml
qualified_profile: cpu_onnx_fp32_v1
cuda_large_pdf_claim: none
```

Normal CUDA behavior remains unchanged for ordinary supported documents. When
`large_pdf_execution_required` is true, the active profile must be the
qualified CPU profile; if another profile is active, admission fails closed
before reconstruction. The same desired-set predicate controls the memory
gate, so a small incoming TXT cannot bypass resource admission while an
already-active large PDF is reconstructed.

The supported host tier is **32 GB-class**, defined operationally as
`MemTotal >= 32,000,000,000` bytes. The 33,507,905,536-byte L5 host meets
that class; the policy does not claim that a machine with only the measured
14.45 GiB process peak is sufficient.

When `large_pdf_execution_required` is true, require:

```text
MemAvailable >= 19,388,303,360 bytes
```

This is `ceil(1.25 × 15,510,642,688)`, a 25% operational margin over the
largest observed whole-window Q100 confirmation peak. It is an admission
margin, not a universal memory bound. When the predicate is true, if physical
memory, `MemAvailable`, or the platform memory source cannot be read reliably,
the mutation is rejected with `large_pdf_host_memory_insufficient`; ordinary
mutations whose desired set contains no >25 MiB PDF are unchanged.

## Capabilities contract

`GET /v1/capabilities` reports both the product policy and the current
runtime's ability to use that policy. It must not advertise a currently usable
90 MiB limit when the active profile or host cannot pass the large-PDF gates.
The implementation adds structured fields without exposing experimental
Q250/Q512 claims:

```json
{
  "transport_limits": {
    "max_files_per_upload_request": 32,
    "max_bytes_per_uploaded_file": 26214400,
    "max_bytes_per_upload_request": 104857600
  },
  "workspace_capacity": {
    "max_active_sources": null,
    "max_active_source_bytes": 94371840,
    "max_searchable_child_chunks": null
  },
  "source_limits": {
    "max_bytes_per_source": 26214400,
    "max_active_source_bytes": 104857600
  },
  "large_pdf": {
    "policy_supported": true,
    "policy_max_bytes": 94371840,
    "qualified_profile": "cpu_onnx_fp32_v1",
    "reference_host_memory_bytes": 33507905536,
    "runtime_eligible": true,
    "effective_max_bytes": 94371840,
    "unavailable_reason": null
  }
}
```

`transport_limits` is authoritative for request validation. The new
`workspace_capacity.max_active_source_bytes` field is authoritative for the
aggregate active-byte ceiling. The existing
`source_limits.max_active_source_bytes` field retains its current request-
envelope alias semantics (`max_total_upload_bytes = 100 MiB`) and is
deprecated; its meaning is not silently changed. The new large-PDF fields
are runtime-effective: when the active profile or host fails the gate,
`runtime_eligible` is false, `effective_max_bytes` is 25 MiB, and
`unavailable_reason` is one of `profile_not_qualified`,
`host_memory_insufficient`, or `memory_telemetry_unavailable`. The UI uses
`large_pdf.effective_max_bytes` and the structured workspace field.

## UI behavior

The workspace upload and replace flows will classify each selected file by
supported media type and display:

```text
PDF files: up to 90 MiB
Other supported documents: up to 25 MiB
Maximum upload request: 100 MiB
Workspace active-source budget remaining: <computed bytes>
```

Client-side checks are advisory and improve feedback; the server remains the
authority. A legacy workspace above the aggregate ceiling displays that new
additions/replacements require removal first while keeping source removal
available. UI copy does not mention CUDA qualification, Q250/Q512, or internal
amplification factors.

## Stable rejection semantics

The implementation preserves the existing top-level error model and adds
stable safe `details.reason` values. No absolute local paths or host memory
diagnostic paths are returned.

| Reason | Top-level code | HTTP | Retryable |
|---|---|---:|---:|
| `source_file_too_large` | `document_invalid` | 422 | No |
| `request_too_large` | `request_invalid` | 422 | No |
| `workspace_source_bytes_exceeded` | `request_invalid` | 422 | No |
| `large_pdf_profile_not_qualified` | `request_invalid` | 422 | No |
| `storage_insufficient` | `service_overloaded` | 503 | Yes |
| `large_pdf_host_memory_insufficient` | `service_overloaded` | 503 | Yes |

Existing aliases such as `document_too_large` and `upload_too_large` may be
accepted internally during migration, but all new API responses use the
stable reasons above. Admission errors occur before Docling and before any
publication mutation.

## Backward compatibility

Existing durable workspaces are not rewritten or invalidated when this policy
is introduced. Oversized legacy workspaces remain readable/queryable. Their
users can remove sources; removal is never blocked by the 90 MiB aggregate
ceiling. Add/replace operations are allowed only when the exact desired state
is within the new envelope and passes resource admission. Existing generic
25 MiB non-PDF behavior remains unchanged.

The settings migration adds explicit media-specific and resource-admission
fields with defaults matching this design. Configuration overlays and
environment names are additive. Scientific configuration hashes continue to
exclude product/packaging policy fields.

## Implementation and validation plan

Implementation remains unauthorized until this design is independently
accepted. The bounded follow-up will touch only the capacity settings/loader,
streamed upload admission, workspace capacity and lifecycle admission, error
projection, capabilities, the workspace upload UI/types, and their tests.

Required deterministic validation:

- PDF exactly at and below 90 MiB is accepted; PDF above 90 MiB is rejected.
- TXT/Markdown above 25 MiB remain rejected.
- Requests above 100 MiB remain rejected.
- Desired active bytes above 90 MiB fail before vault projection/Docling.
- An unrelated mutation that reconstructs an active >25 MiB PDF applies the
  desired-set profile and memory gates; removing the last large PDF does not.
- `SOURCE_REMOVE` from an oversized legacy workspace remains possible.
- Non-empty reconstruction uses post-mutation bytes and the exact 5× + 1 GiB
  rule; the empty-workspace transition bypasses that reconstruction reserve.
- Missing free space or memory fails before parser execution with stable reasons.
- Capabilities separate policy fields from runtime eligibility, preserve the
  old request-envelope alias, and expose workspace capacity canonically.
- UI copy and client checks match capabilities; server checks remain decisive.
- Existing ordinary profile behavior and production limits outside this policy
  remain unchanged.

Synthetic byte streams and small temporary directories are sufficient. No
large PDF fixture and no Q25/Q100/Q250/Q512 rerun is authorized or required.

## Terminal state

```yaml
large_source_capacity: L6
terminal: LARGE-SOURCE CAPACITY L6 PRODUCT POLICY IR-001 REWORK COMPLETE / READY FOR INDEPENDENT RE-REVIEW
authority: S16-K-LARGE-SOURCE-CAPACITY-L6-PRODUCT-LIMIT-RESOURCE-ADMISSION-DESIGN-AUTH-001
base: 6476d286e2278292cc5b8f0aac1a6d0692969985
pdf_limit_bytes: 94371840
non_pdf_limit_bytes: 26214400
request_limit_bytes: 104857600
workspace_active_source_limit_bytes: 94371840
disk_rule: max(known_lower_bound, 5 * A) + 1073741824 for reconstruction-required non-empty desired sets
memory_rule: MemTotal >= 32000000000 and MemAvailable >= 19388303360
qualified_profile: cpu_onnx_fp32_v1
cuda_large_pdf_claim: NONE
scientific_reruns_required: NO
implementation_authorized: NO
```
