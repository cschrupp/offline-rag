# Slice 14C authoritative quality-vs-cost report (perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca)

Evidence class: **AUTHORITATIVE**

Raw observations are authoritative. Aggregates/report are deterministic
derivations / presentation only. No winner, promotion, or portfolio claim
is authorized by this artifact alone.

- suite_id: `perfsuite_5248892df382995ac96ec2b09aea61bf27510673b93e0d816d6a255a2f4305ba`
- run_identity_hash: `perfrun_deb7a58e49d0f64496553a16c3edc3a5b517deec5ec1c9ddd76831fee79627ca`
- executing_sha: `affbd1127b1afc677e31c132da1c000c6cf246b5`
- machine_profile_id: `perfhost_02b2b88bece1b425e3572984aa3365d86f57d9eab41fb93cd5f2fc129b3173f4`
- scientific_config_id: `perfcfg_aae1ea9b048e414338f0a38b13cb31132505920c406293e1e9f8e35595faa42d`
- corpus_id: `corpus_040e49a1d261dba4e853939b36348dc40109551d6fdb49b38c7a9d896409eadb`
- execution_mode: `authoritative_14c_quality_vs_cost`
- run_status: `completed`
- benchmark_level: `B`
- case_count: `44`
- diagnostic_only: `False`
- authoritative: `True`
- suite_freeze_authority: `a662efc50d712bd6a986da05809dc864342139df`
- vram_availability: `unavailable`

## Overall measured accounting (total retrieval path)

- attempted_count: `440`
- valid_count: `440`
- failure_count: `0`
- instrumentation_exclusion_count: `0`
- warmup_count: `88`
- n: `440`
- min: `3.508741957019083`
- p50: `6.474126006476581`
- p95: `11.492776187800336`
- max: `70.4453759349417`

## By variant (total retrieval path)

- `hybrid`: n=220 p50=5.617130434024148 p95=8.311822108470368 failures=0
- `hybrid_rerank`: n=220 p50=7.412913789972663 p95=13.53324203192023 failures=0

## By semantic stage / path

- `fusion`: n=220 p50=0.00013805151684209704 p95=0.00029474627808667703
- `rerank`: n=220 p50=1.9139931004610844 p95=4.478658356377855

## Path latency rollups

- `baseline_hybrid_total_retrieval_path`: n=220 p50=5.617130434024148 p95=8.311822108470368
- `treatment_hybrid_component`: n=220 p50=5.5819768235087395 p95=9.578321079158922
- `treatment_reranker_latency`: n=220 p50=1.9139931004610844 p95=4.478658356377855
- `treatment_total_retrieval_path`: n=220 p50=7.412913789972663 p95=13.53324203192023

## Quality by variant (macro; frozen IR semantics)

- `hybrid` (eligible=22):
  - Recall@1/5/10: 0.341913 / 0.626741 / 0.807018
  - Precision@1/5/10: 0.772727 / 0.445455 / 0.322727
  - HitRate@1/5/10: 0.772727 / 1 / 1
  - MRR: 0.886364
  - nDCG@1/5/10: 0.742424 / 0.761166 / 0.790507
- `hybrid_rerank` (eligible=22):
  - Recall@1/5/10: 0.375625 / 0.685447 / 0.813577
  - Precision@1/5/10: 0.863636 / 0.490909 / 0.340909
  - HitRate@1/5/10: 0.863636 / 1 / 1
  - MRR: 0.931818
  - nDCG@1/5/10: 0.772727 / 0.825315 / 0.842218

## Resource summary (RAM)

- `hybrid`: RAM available samples=220 rss_min=2779291648 rss_p50=2850330071 rss_p95=2853190980 rss_max=3821805568
- `hybrid_rerank`: RAM available samples=220 rss_min=2864418816 rss_p50=2874134651 rss_p95=2875940512 rss_max=3819810816
- VRAM: `unavailable`
