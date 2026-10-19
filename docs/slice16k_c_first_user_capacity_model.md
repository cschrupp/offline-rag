# Slice 16K-C — First-user capacity model

**Authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-AUTH-001` — AUTHORIZED  
**Exact parent:** `f2741c105db48aea081b5282dc48e4b7f11fd6b6`  
**Branch:** `implementation/16k-c-first-user-capacity-model`  
**Controlling design:** `docs/slice16k_beta_ingestion_readiness_design.md`  
**Human-accepted design subject:** `0839b565cd60958141366048520236a71bf16fd0`  
**Independent review:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-IR-001` — REWORK REQUIRED (F001)  
**Rework authority:** `S16-K-C-FIRST-USER-CAPACITY-MODEL-IMPLEMENTATION-REWORK-AUTH-001` — AUTHORIZED  
**Exact rework parent:** `40e5b096041805fb149516b6eb89c793f6519213`  
**Historical IR-001 disposition:** IMPLEMENTATION COMPLETE / REWORK REQUIRED (F001)  
**Status:** 16K-C IMPLEMENTATION COMPLETE / READY FOR INDEPENDENT RE-REVIEW  

**F001:** The per-workspace searchable-child ceiling applies only to workspace
`SOURCE_ADD` / `SOURCE_REPLACE`. `SOURCE_REMOVE` is exempt.
`mutation_kind=None` (ordinary `POST /v1/ingest`) must leave legacy ingest
semantics unchanged and must not be constrained by
`max_searchable_child_chunks_per_workspace`.

## Frozen separation

| Dimension | Settings | Applies to |
|-----------|----------|------------|
| Transport file count | `api.max_files_per_ingest` (default 32) | Incoming HTTP upload request only |
| Transport per-file bytes | `api.max_bytes_per_document` (default 25 MiB) | Incoming HTTP upload request only |
| Transport request bytes | `api.max_total_upload_bytes` (default 100 MiB) | Incoming HTTP upload request only |
| Workspace active sources | `api.max_active_sources_per_workspace` (default unset/`null`) | Desired active set on Add/Replace |
| Searchable child workload | `api.max_searchable_child_chunks_per_workspace` (default unset/`null`) | After chunking, before dense on Add/Replace |

Unset workspace ceilings mean **no product-supported numeric envelope is claimed**.
Test/benchmark overrides may set them via env / product settings. Production
support numbers remain evidence-driven under **16K-F**.

## Critical rules

1. **Pre-dense fail-closed:** searchable-workload admission runs after chunking
   and before dense embedding/indexing for workspace Add/Replace only.
2. **Legacy ingest isolation (F001):** ordinary `POST /v1/ingest`
   (`mutation_kind=None`) is not constrained by the per-workspace searchable
   ceiling.
3. **Atomic publication:** capacity rejection raises `AppError` before
   publication commit; prior workspace revision/snapshot remains authoritative.
4. **Reconstruction:** `materialize_desired_sources` + `spool_local_files(...,
   apply_transport_limits=False)` do not reapply HTTP upload envelopes to
   already-vaulted sources.
5. **Remove:** never blocked by workspace/search ceilings.

## Capabilities projection

`GET /v1/capabilities` exposes:

- `transport_limits` — upload request envelope
- `workspace_capacity` — optional active-source / searchable-child ceilings
- legacy `source_limits` — bytes remain transport; `max_active_sources` mirrors
  workspace capacity (null when unset; **not** aliased to transport file count)

## Explicitly out

16K-D/E/F/G, OCR, semantic dedup, incremental indexing, new chunking/embedding,
distributed queue, Slice 17/18, 9G, main promotion, GPU HTTP-500 reopening.
Diagnostic GPU probe instrumentation is not a 16K-C dependency.
