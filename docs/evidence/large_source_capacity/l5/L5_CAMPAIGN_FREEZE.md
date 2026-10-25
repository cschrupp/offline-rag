# L5 PDF qualification campaign freeze

Authority: `S16-K-LARGE-SOURCE-CAPACITY-L5-PDF-QUALIFICATION-EXECUTION-AUTH-001`

Accepted L4 subject: `4024ed04130681d757abcd4fb4abf6f302259db1`

Campaign freeze subject: `32107a1b5c96b1435e50a23ca61078e9d6939af4`

Execution branch: `qualification/16k-large-source-capacity-l5-pdf`

Fixture manifest: `docs/evidence/large_source_capacity/l5/l5_fixture_manifest.json`

## Frozen campaign

- Evidence contract: `large-source-capacity-evidence-v1`.
- Qualification profiles: `cpu_onnx_fp32_v1`, then `cuda_fp16_v1`.
- Progressive cell order per evaluable profile: Q25, Q100, Q250, Q512.
- Stop a profile at its first valid failure; do not run larger cells after failure.
- Repeat only the largest passing cell once as confirmation.
- Maximum: four screen cells plus one confirmation per profile.
- Per-cell wall-time ceiling: 6 hours, classified as `VALID_RESOURCE_FAIL` with reason `campaign_wall_timeout` if reached.
- Sampling intervals: RSS 0.2 s, disk 1.0 s, GPU 1.0 s.
- Each cell uses a fresh temporary Seneca data tree and the accepted L4 workspace `SOURCE_ADD` path.
- Product defaults remain 25 MiB per file and 100 MiB per request; qualification uses only isolated harness overrides with a one MiB margin above each fixture.
- No large PDF binary is committed to Git; the manifest records metadata and provenance only.

## Profile preflight

Before the first capacity cell, each profile receives one small born-digital PDF `SOURCE_ADD` preflight through `--mode qualification`. A profile that cannot resolve its exact representation/device prerequisites is `PROFILE_NOT_EVALUABLE`; its capacity lane is not run and the other profile remains independent.

## Correctness and evidence gates

Each attempted cell must prove exact requested/resolved profile identity, managed-operation success, workspace readiness, one active source, fixture identity, parsing, chunking, dense indexing, lexical indexing, publication, observed RSS/CPU/disk instrumentation, and parser samples for Q100/Q250/Q512. Missing required evidence is `INVALID_EVIDENCE`, not a capacity failure.

## Duplicate check

After the smallest successful cell, perform one bounded duplicate-identity check against an already-active source and record it separately from the size matrix.

## Scope lock

This campaign does not change production limits, parser behavior, chunking, embedding profiles, APIs, or full-replace semantics. L6 remains unauthorized.
