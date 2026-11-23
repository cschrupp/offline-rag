# One-shot browser-to-server request observation

**Observed outcome A — HTTP 200 and cited answer rendered. Fixed-request
qualification incomplete.** The recorded request contained two prior turns
and invoked the conversation resolver. The planned empty-history case
therefore remains untested in this window. The single observed request
was retained as evidence and was not repeated.

## Timeline (2026-11-21 UTC)

| Boundary | Observation |
|---|---|
| Firefox POST | HTTP 200, total 46.095 s, cited answer visible. Absolute browser UTC start, TTFB, and detailed phases unavailable in the screenshot |
| 19:29:31.674908 | Conversation admitted on revision 2, expected frozen snapshot, all-active one-document scope |
| 19:29:32.985834 | Grounded query trace created, 1.311 s after conversation admission. This interval includes the resolver and binding/setup |
| Grounded execution | 39.775 s context, 4.396 s generation, 44.171 s total |
| 19:30:17.160011 | Grounded trace written, answered with two citations |
| 19:30:17.172012 | Conversation trace written, answered |
| 19:30:17.182526 | Server HTTP 200 access entry, about 45.508 s after admission. Access entry marks response start, not last byte |
| 19:30:20–19:30:23 | Connection was established at first sample, then FIN-WAIT-2 after the response. No pre-response close observed |

Conversation trace: `trace_5c7bcd76773a49a7a5ede5e0a32a4d30`.
Query trace: `trace_4c701509255f474990998e3209ff620f`.
Snapshot: `snap_62fce56e749ccf0e7b3bad46f82c153c4d0ba032f500509a1da37755babc97ca`.

## Resources and interpretation

Verified the deployed image and original container, both health endpoints,
workspace identity, inactive managed operations, zero established connections
during preflight, and sufficient time before the 20:41:11 UTC VM STOP.
During the turn, 15 complete three-second samples saw at most one open
connection on the API port. This is a connection observation, not an active
application-request gauge. Uvicorn used about 1.55 CPU cores on average and
peaked at 1.99. Sampled host CPU peaked at 51%. Uvicorn RSS peaked near
4.07 GiB, host available RAM stayed above 12.2 GiB, and sampled swap free
was unchanged. No competing query was evident.

Context accounted for 90% of grounded execution. This request confirms
the browser can receive and render a cited response while substantial
isolated retrieval latency remains. It does not establish why earlier
requests were slower or whether overlap caused the timeouts. The durable
trace exposes aggregate context time only. Existing transient context
metadata can separate dense, lexical, fusion, reranking and packing times.
Projecting those fields and candidate counts for a separately authorized
diagnostic is the smallest next step for locating the isolated cost.

The [owned-worker design review](DESIGN_ANALYSIS.md) covers shared capacity,
cooperative disconnect and deadline behavior, snapshot binding, trace
compatibility, validation and rollback. This successful request does not
justify a proxy timeout change. The worker is a candidate for limiting
overlap and abandoned compute, not a remedy for one request's forward time.

No second turn, production code change, deployment, or settings change
was made. Evidence contains only timing, bounded resource observations
and trace metadata.
