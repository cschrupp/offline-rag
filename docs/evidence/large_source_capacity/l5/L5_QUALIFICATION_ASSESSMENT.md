# L5 PDF qualification assessment

Campaign authority: `S16-K-LARGE-SOURCE-CAPACITY-L5-PDF-QUALIFICATION-EXECUTION-AUTH-001`

Campaign freeze subject: `70cea558bd0e8f35fb23057b9ee2c1a4ab89a450`

Accepted L4 subject: `4024ed04130681d757abcd4fb4abf6f302259db1`

Campaign terminal: `PROFILE_PARTIAL_QUALIFICATION`

## Disposition

The CPU lane is qualified through a confirmed Q100 class. Q25, Q100, and Q100-CONFIRM each used the exact frozen CPU profile, completed the full workspace `SOURCE_ADD` path, and passed identity, publication, parser, dense, lexical, and instrumentation gates.

Q250 was attempted with the exact frozen settings, but WSL terminated before the harness emitted a complete evidence record. Linux kernel, journal, and `/var/log` inspection after recovery found no conclusive OOM-killer record tied to the run. It is therefore classified as `INVALID_EVIDENCE / HOST_TERMINATED`, not as a measured resource failure. Partial Q250 logs are preserved under `partial_q250/` and are not used as capacity evidence.

Q512 was not run under the progressive stop rule.

The CUDA preflight failed closed before workload execution because CUDA was unavailable on the qualification host. CUDA is `PROFILE_NOT_EVALUABLE`; it does not invalidate the independent CPU result.

## CPU results

| Cell | Fixture | Disposition | Parser peak RSS | Parser time | Total wall time | Peak disk amplification | Chunks |
|---|---:|---|---:|---:|---:|---:|---:|
| Q25 | 22,430,312 bytes / 21.39 MiB | `VALID_PASS` | 4,025,581,568 bytes | 171.61 s | 930.01 s | 3.368× | 154 |
| Q100 | 96,152,520 bytes / 91.70 MiB | `VALID_PASS` | 6,593,409,024 bytes | 376.07 s | 1,536.39 s | 4.000× | 460 |
| Q100-CONFIRM | 96,152,520 bytes / 91.70 MiB | `VALID_PASS` | 6,600,499,200 bytes | 391.48 s | 1,744.96 s | 3.260× | 460 |
| Q250 | 284,502,054 bytes / 271.29 MiB | `INVALID_EVIDENCE / HOST_TERMINATED` | unavailable | unavailable | unavailable | unavailable | unavailable |
| Q512 | 569,005,126 bytes / 542.65 MiB | `NOT_RUN — progressive stop` | — | — | — | — | — |

The Q25 and Q100 source identities matched their frozen SHA-256 values, resolved as `cpu_onnx_fp32_v1`, and ended with one active published source. The full JSON records are in `cells/`.

## Duplicate identity

The qualified Q25 fixture was added once successfully. A second add using the same bytes under a different filename failed with `document_identity_conflict` before mutation. The final workspace retained one active source and no second publication. Evidence: `duplicate_identity_check.json`.

## Interpretation

The observed bottleneck is downstream PDF expansion and processing: Docling page/layout/table structures, decoded content, parsed artifacts, chunking, and qualified embedding execution. L1–L3 streaming and path contracts remain exercised and are not evidence of whole-file transport duplication.

The Q100 result supports a confirmed CPU qualification ceiling at the Q100 class for this representative technical-PDF family on this host. It does not establish a universal text-size limit or authorize a production limit change. Raw PDF bytes are only a proxy for parsed text capacity; images, tables, page count, fonts, and layout complexity materially affect memory.

## Unchanged scope

Production limits remain 25 MiB per file and 100 MiB per request. No parser, chunking, embedding-profile, API, UI, or full-replace behavior changed. L6 remains unauthorized.
