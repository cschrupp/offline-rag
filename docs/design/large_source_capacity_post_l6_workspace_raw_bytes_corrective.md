# Post-L6 workspace raw-byte ceiling corrective

**Authorities**

- Design: `S16-K-LARGE-SOURCE-CAPACITY-POST-L6-WORKSPACE-RAW-BYTE-CEILING-CORRECTIVE-DESIGN-AUTH-001`
- Implementation: `S16-K-LARGE-SOURCE-CAPACITY-POST-L6-WORKSPACE-RAW-BYTE-CEILING-CORRECTIVE-IMPLEMENTATION-AUTH-001`
- Authorized base: `83971b9fa74409cffb5a3a7b772a699f687eb132`

## Corrective decision

The L6 aggregate workspace raw-source ceiling of 90 MiB was an invalid
workspace-capacity claim. The accepted 90 MiB PDF limit is a per-source
processing/product limit. Aggregate active raw bytes describe storage and
resource demand; they do not establish searchable-workspace capacity.

The beta default is therefore:

```yaml
api:
  max_active_source_bytes_per_workspace: null
```

An explicit positive numeric value remains supported for controlled tests and
deployments. When configured, the existing complete post-mutation desired-set
check still rejects values above that ceiling. When unset, no aggregate byte
rejection is made.

## Preserved policy and admission

PDF per source remains 90 MiB, non-PDF per source remains 25 MiB, and the HTTP
request envelope remains 100 MiB with 32 files. CPU and CUDA large-PDF gates,
AUTO profile selection, one runtime, atomic publication, and accepted L5/L6
evidence are unchanged. The aggregate
`A = sum(active raw source bytes)` remains an input to reconstruction disk
admission only:

```text
max(known_lower_bound, 5 × A) + 1 GiB
```

This disk rule applies to non-empty reconstruction-required desired sets and
does not turn `A` into a searchable-workspace capacity claim.

Capabilities expose the nullable workspace field. The historical
`source_limits.max_active_source_bytes` projection remains the 100 MiB request
alias. The UI consumes only `workspace_capacity.max_active_source_bytes` and
performs aggregate Add/Replace checks when that field is numeric.

## 16K-F baseline boundary

The next searchable-workspace evidence tranche remains 16K-F. Its baseline is
approximately 39 usable non-OCR sources and 7.5–8k searchable children, with
a stress point around 42 sources and 10.4k children. Approximately 270 MiB of
raw storage is descriptive only; the practical per-source envelope is about
100 MiB, and values above 100 MiB remain outside beta. The full-corpus cold
dense target remains at or below 60 minutes.

No scientific execution or qualification was performed by this corrective.
Promotion is not authorized. The implementation requires independent review
after the candidate is committed and pushed.
