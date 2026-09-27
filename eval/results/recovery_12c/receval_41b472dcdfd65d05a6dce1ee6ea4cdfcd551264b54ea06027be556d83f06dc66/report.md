# Slice 12C-2 authoritative recovery measure-once report

- run_status: `stopped_not_evaluable`
- stage_b_executed: `false`
- authority_baseline_sha: `47656d17b1e907f5965a60b0fe988a83942855ca`
- accepted_harness_sha: `c4f8734d57f45d3aa111997abf2bc8890322ff33`
- gold_dataset_id: `gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172`
- cohort_map_identity_hash: `receval_e4e25402b92db2243bec2d361e96976f805efceda02844f2a70e49c44e384ca4`
- rrwcfg_: `rrwcfg_7ffb94fc3db815124596c5d4910378d2bc09be23d3cf4c916cfd88794ee9ac1d`
- receval_: `receval_41b472dcdfd65d05a6dce1ee6ea4cdfcd551264b54ea06027be556d83f06dc66`
- conclusion: `insufficient_evidence_for_recovery_efficacy`

## Trigger census (Stage A)

- T_H (human): **0** `[]`
- T_A (assistant): **0** `[]`
- not_evaluable: `True`
- stop_reason: `not_evaluable_no_human_recovery_opportunities`

## Census-stop aggregate

- human_reviewed_count: 16
- assistant_only_count: 6
- human_stage_a_trigger_count: 0
- assistant_stage_a_trigger_count: 0
- measured_recovery_case_count: 0
- rewrite_call_count: 0
- recovery_retrieval_attempt_count: 0

## Policy / method notes

- `retrieval_recovery.enabled=false` remains the product default in `config/base.yaml`; this evaluation-only overlay does not promote recovery.
- No generation / LLM judge was used as promotion truth.
- No LangGraph was used.
- Scientific limitation: the current Gold set has no authoritative genuinely-unanswerable negative population, so 12C does not estimate the false-recovery rate on unanswerable questions.
