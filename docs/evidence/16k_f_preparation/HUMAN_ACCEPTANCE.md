# 16K-F Preparation and Replacement Baseline — Human Acceptance

## Decision

**ACCEPT** — preparation tooling and replacement baseline.

Accepted technical subject:

```text
52e740579259e82181fdbbb3c0335c7e0320e3ee
```

Independent review basis:

```text
S16K-F-PREP-IR-005 — ACCEPT
F001 — CLOSED
F002 — CLOSED
F003 — CLOSED
observed published source identity — CLOSED
```

The acceptance covers the preparation tooling, `CORPUS_BASELINE_AMENDMENT_001`,
and the exact private replacement manifest and query deck identified below.
It does not claim full-corpus execution, scientific qualification, or empirical
acceptance of ingestion results.

## Accepted replacement artifacts

```yaml
amendment: CORPUS_BASELINE_AMENDMENT_001
dataset:
  supported_paths: 52
  distinct_byte_identities: 44
  eligible_unique_sources: 38
manifest:
  canonical_sha256: 4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b
  file_sha256: 85770fc063287c4588c255ebd56947cd7ed3321a67d433883e3785a011ee1384
query_deck:
  file_sha256: f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a
```

The private artifacts remain outside Git. Acceptance binds only the exact
identities above; it does not publish corpus paths, source bytes, or query text.

## Remaining state

```yaml
preparation_tooling:
  HUMAN_ACCEPTED: true

replacement_baseline:
  HUMAN_ACCEPTED: true
  schema: 16k-f-replacement-acceptance-manifest-v1
  eligible_unique_sources: 38

execution_time_runtime_and_capacity_verification:
  NOT_RUN

real_corpus_execution:
  NOT_AUTHORIZED

promotion:
  NOT_AUTHORIZED
```

The proposed execution matrix still requires a separate bounded execution
authorization. At execution time, the dedicated runtime, capacity, disk, and
corpus-hash preflight must pass before any real source mutation.
