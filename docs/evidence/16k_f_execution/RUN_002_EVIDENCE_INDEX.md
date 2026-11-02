# Seneca 16K-F run_002 evidence index

**Campaign disposition:** `HUMAN ACCEPTED — SCOPED BETA`\
**Evidence disposition:** `ACCEPTED DESCRIPTIVE REPLACEMENT-CORPUS RESULTS`\
**Closeout:** [`16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md`](16K_F_HUMAN_CAMPAIGN_CLOSEOUT.md)

This sanitized index records immutable evidence identities and summarized
results. Private source bytes, corpus paths, query text, and raw API payloads
remain outside Git. The historical `artifacts/16k_f_execution/run_002/` index
and all run evidence files are preserved unchanged.

## Frozen input identities

- Replacement manifest canonical SHA-256:
  `4d6d32c42d50e6753378d6f8dacc42b5fa0d3d18bdbdc4a9d4b4b3dfb000c92b`
- Approved query-deck file-byte SHA-256:
  `f10da5270a440004de8cac9db7d3e4836f46a87613f4f2d8124b58479d0f717a`
- Replacement population: 52 inventoried paths, 44 distinct byte identities,
  38 eligible deduplicated sources, 3 oversized PDFs, 3 OCR-required PDFs,
  and 8 duplicate paths.

## Primary campaign evidence

| Artifact | SHA-256 | Result |
|---|---|---|
| `robustness/robustness-matrix-summary.json` | `1c5ad895f1a5407f13bc68bc517dcd90272fbc43a78f0ddea241e1e3e50d30c6` | PASS; 17/17 cases; 3/3 mixed retries |
| `full_pair/38-cold.json` | `4bfa328238109aad2a3d5dbdc4d57f0792df3215cf5d7605f068fe942590e24e` | COMPLETE; 38 sources; 5/5 grounded queries |
| `full_pair/38-warm.json` | `6b28331d95c9ebbfb401bd529f2ee0771831e516fe7b274957fb4092109105ed` | COMPLETE; same 38 sources; 5/5 grounded queries |
| `full_pair/38-comparison.json` | `78ddddf263ffe6bc57c80cf2d371b1262f779a49b04b28eb03fec9fa9ae391fc` | Pair, hash, and source linkage recomputed and matched |

## Supplemental evidence

| Artifact | SHA-256 | Result |
|---|---|---|
| `proxy/1296-cold.json` | `31b9cbc911743508b1fea72c548c98d896af468bc504f1701b0e6687075d8425` | 1,296 children; 1,296 generated; 0 reused; single run |
| `largest/67m-cold-run3.json` | `8a80f32e8427e0fde88297c50d9513cb54ba0cda0d8edbfd34f2181a20ddf6d8` | 67,199,839-byte PDF; 374 children and embeddings; cited query passed |
| `markdown/markdown-api-smoke.json` | `85dba6b9f1ea6201f3282107b0b7bafbcac5690a0f62c6fe01190bb779335856` | Synthetic managed Markdown add and cited retrieval passed |

## Descriptive metrics and limits

- Cold operation `total_ms`: 3,759,581 ms across three sequential rebuilds.
- Warm operation `total_ms`: 56,615 ms for the same 38-source population and
  data root; reported aggregate operation-time reduction is 98.49%.
- Full-cell elapsed time, including setup, polling, and query checks: cold
  66.09 minutes; warm 5.14 minutes. These differ from operation-time sums.
- Cold aggregate embedding counters across rebuilds: 12,128 generated and
  13,669 reused. Warm: 0 generated and 25,797 reused. Counts are aggregate
  operation work, not unique-embedding totals.
- Warm dense-generation and dense-materialization timings are unavailable
  because no embeddings were generated and reuse was observed; no zero
  durations were fabricated.
- The replacement workload is not comparable to the historical
  curator-selected 39-primary workload. The 62m 40s operation-time sum is not
  the frozen dense-phase metric.

## Final governance state

```yaml
replacement_corpus_evidence: ACCEPTED_DESCRIPTIVE
robustness_matrix: PASS_17_OF_17
cold_warm_pair: ACCEPTED_DESCRIPTIVE
grounded_queries: PASS_5_OF_5_COLD_AND_WARM
proxy_single_run: ACCEPTED_DESCRIPTIVE
largest_eligible_pdf: ACCEPTED
managed_markdown_smoke: ACCEPTED
historical_39_primary_60_minute_benchmark:
  RETIRED_FOR_CURRENT_BETA / NOT_EVALUATED / HUMAN_APPROVED_EXCEPTION
historical_requirement: PRESERVED_UNCHANGED
human_campaign_closeout: ACCEPTED
promotion_to_main: NOT_AUTHORIZED
16K_G: NOT_AUTHORIZED
```

`run_001` remains historical and untouched. No product policy, capacity limit,
production code, or frozen scientific threshold was changed.
