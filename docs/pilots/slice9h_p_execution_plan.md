# Slice 9H-P — Execution Plan

**Status:** `PLAN LOCKED / EXECUTION NOT YET AUTHORIZED`

Companion contract: [`slice9h_p_pilot_contract.md`](slice9h_p_pilot_contract.md).

This document freezes **how** 9H-P will be executed when separately authorized.
It does **not** authorize running retrieval now.

```text
PILOT / NON-PROMOTIONAL
6 retrieval executions total (NOT 12)
human-16 = post-hoc cohort from the same full-22 result artifacts
```

---

## 1. Execution model

Lock:

```text
6 retrieval executions total
```

Each of the six arms executes **exactly once** against the frozen **full-22**
GoldDataset.

The `human-16` cohort is derived deterministically afterward from the `cases[]`
already present in each `offline-rag-retrieval-eval-result-v1` artifact.

Do **not** rerun retrieval for human-16.

Reason:

```text
same retrieval output
same run
same latency observation
same semantic provenance
only population aggregation changes
```

This makes the 22-vs-16 sensitivity analysis strictly paired.

---

## 2. Frozen identities

Dataset directory:

```text
data/corpora/ics_modules/gold_authoring/gold/
  authorrun_b28d88f64054491a837cb4a144cbe056/
```

Expected:

```text
gold_dataset_id:
  gold_d3fc157c7b3206f6983abee766e7ce7b939244a7dea04f0be256f3a533a46172

chunk_set_id:
  chunkset_6d4925ea8d66e7dc599a884e96bc5f6b094e4288d565372d15e6002086c41da2

corpus:
  ics_modules

authoring_run_id (lineage / Silver):
  authorrun_b28d88f64054491a837cb4a144cbe056
```

Execution must **fail closed** if any identity differs after load / in result
envelopes.

GoldDataset and chunkset must remain byte/identity stable throughout 9H-P.

---

## 3. Exact six arms

### A — dense-baseline

```text
method: dense
config: config/base.yaml
dense query: raw-query-v1
dense searchable units: all-children-v1
index: historical baseline dense (CURRENT during A/B/C/E/F)
```

### B — lexical-baseline

```text
method: lexical
config: config/base.yaml
index: historical plain lexical
```

### C — dense-model-query-prompt

```text
method: dense
configs (in order):
  config/base.yaml
  config/experiments/dense_query_prompt.yaml
query: model-query-prompt-v1
searchable units: all-children-v1 (unchanged from baseline)
index: SAME historical baseline passage index as A
```

Only query-side encoding changes. No index rebuild caused by the query
contract is allowed (`preflight_pooling_artifacts` already asserts query-prompt
index identity equals baseline).

### D — dense-arm-h

```text
method: dense
configs (in order):
  config/base.yaml
  config/experiments/dense_no_heading_peers.yaml
contracts:
  model-query-prompt-v1
  +
  exclude-heading-only-v1
index: historical Arm H dense
```

### E — hybrid-rrf

```text
method: hybrid
config: config/base.yaml
inputs:
  baseline / raw-query dense
  plain lexical
  rrf-v1
```

Do **not** accidentally compose Arm H / query-prompt into hybrid.

### F — hybrid-rerank

```text
method: hybrid-rerank
config: config/base.yaml
inputs: same baseline hybrid inputs as E + existing reranker contract
```

Do **not** compose Arm H / query-prompt into F.

**Repo note (not a deviation):** `config/experiments/dense_baseline.yaml` and
`hybrid_*.yaml` exist as named experiment overlays; 9H-P deliberately uses
`config/base.yaml` (± the two dense overlays above) so hybrid/reranker defaults
are not disabled by those experiment stubs.

---

## 4. Retrieval depth

All six evaluations run with:

```text
--top-k 30
```

This is an evaluation-depth decision, not parameter tuning. It is required so
Slice 9 emits conditional **HitRate@30**.

```text
For A/B/C/D/E: request 30 ranked candidates.
For F:
  reranker.input_k remains 30 (unchanged YAML)
  reranker model/config unchanged
  fusion inputs unchanged
  --top-k 30 retains all 30 reranked candidates (no output truncation at 10)
```

Therefore:

```text
@1/@5/@10 metrics = ordinary ranking-quality evaluation
HitRate@30 = diagnostic over the complete reranker input / ranked pool
```

Do **not** modify `reranker.output_k` in YAML.

---

## 5. Historical-index preflight

Before execution, use the existing 9C historical artifact resolver:

```text
offline_rag.gold_authoring.pool_preflight.preflight_pooling_artifacts(...)
```

Load the frozen Silver authoring run for this lineage (read-only) and resolve:

```text
baseline dense index_id
Arm H dense index_id
lexical index_id
chunk_set_id
corpus_id
```

Both dense manifests and the lexical manifest must already exist and bind to
the frozen chunkset.

If any required historical artifact is missing:

```text
HARD STOP
```

Do not silently create a new experimental index and call it the historical arm.

---

## 6. CURRENT index handling

Public `eval retrieve` uses the active CURRENT dense index and checks config
compatibility.

Therefore execution may deliberately activate existing **immutable** historical
indexes, but must **not** manually edit state JSON.

Before any activation:

```text
record original:
  current_index_id
  current_index_manifest
  full index state
```

Preferred execution order:

```text
baseline CURRENT
  A dense-baseline
  B lexical-baseline
  C dense-model-query-prompt
  E hybrid-rrf
  F hybrid-rerank

Arm H CURRENT
  D dense-arm-h

restore original CURRENT state/config
```

Use ordinary existing `offline-rag index` behavior/configuration to activate
the required immutable artifact (no state-file surgery).

After every activation, verify:

```text
CURRENT index_id == expected historical index_id
source_chunk_set_id == frozen chunk_set_id
```

If activation computes or publishes a different index identity:

```text
HARD STOP
```

At the end, restore the exact pre-9H-P operational CURRENT configuration and
verify it.

---

## 7. Raw result paths

Directory (gitignored locally under `eval/results/*`):

```text
eval/results/9h_p/
```

Results:

```text
A_dense_baseline_full22.json
B_lexical_baseline_full22.json
C_dense_query_prompt_full22.json
D_dense_arm_h_full22.json
E_hybrid_rrf_full22.json
F_hybrid_rerank_full22.json
```

Every raw result must validate as:

```text
offline-rag-retrieval-eval-result-v1
```

and contain:

```text
population.total_cases = 22
gold_dataset_id = frozen ID
chunk_set_id = frozen ID
requested depth = 30
22 case results
```

Also verify semantic provenance for each arm matches its intended
contracts/index IDs.

---

## 8. Exact future CLI shapes

**Documented only — DO NOT execute in this planning step.**

### A

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method dense \
  --top-k 30 \
  --output eval/results/9h_p/A_dense_baseline_full22.json
```

### B

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method lexical \
  --top-k 30 \
  --output eval/results/9h_p/B_lexical_baseline_full22.json
```

### C

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --config config/experiments/dense_query_prompt.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method dense \
  --top-k 30 \
  --output eval/results/9h_p/C_dense_query_prompt_full22.json
```

### D

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --config config/experiments/dense_no_heading_peers.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method dense \
  --top-k 30 \
  --output eval/results/9h_p/D_dense_arm_h_full22.json
```

### E

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method hybrid \
  --top-k 30 \
  --output eval/results/9h_p/E_hybrid_rrf_full22.json
```

### F

```bash
offline-rag eval retrieve \
  --config config/base.yaml \
  --dataset data/corpora/ics_modules/gold_authoring/gold/authorrun_b28d88f64054491a837cb4a144cbe056 \
  --corpus ics_modules \
  --method hybrid-rerank \
  --top-k 30 \
  --output eval/results/9h_p/F_hybrid_rerank_full22.json
```

---

## 9. `eval compare` boundary

Existing `eval compare` requires:

```text
same gold_dataset_id
same chunk_set_id
same method
same case set
```

Valid for dense-arm comparisons on the full-22 artifacts:

```text
A vs C
A vs D
C vs D
```

Future commands (not executed now):

```bash
offline-rag eval compare \
  --a eval/results/9h_p/A_dense_baseline_full22.json \
  --b eval/results/9h_p/C_dense_query_prompt_full22.json \
  --json \
  > eval/results/9h_p/compare_A_C_dense_full22.json
```

Likewise:

```text
compare_A_D_dense_full22.json
compare_C_D_dense_full22.json
```

Do **not** force `eval compare` across:

```text
dense vs lexical
dense vs hybrid
hybrid vs hybrid-rerank
```

Cross-method analysis belongs in the deterministic pilot postprocessor.

---

## 10. human-16 derivation

Do not create a second GoldDataset.
Do not run retrieval again.

After the six raw result artifacts exist, a temporary/local deterministic
analysis step selects the exact human-reviewed cases from each result's
`cases[]`.

### Locked ordinals

```text
1, 3, 8, 9, 11, 13, 15, 17,
19, 20, 21, 23, 29, 31, 33, 34
```

### Resolved `draft_case_id` map (authoritative lineage order)

Resolved from the frozen Silver / consolidation ordinal order and verified
present in the GoldDataset (`cases.jsonl`):

```text
 1: draft_54115e36a58442e0a1574bc8017248c9
 3: draft_4c185aa9607b42688627ef26323f3367
 8: draft_08f83eaef198495d92ff557eda974bf4
 9: draft_127ac342012d47fc9720a0c13a577550
11: draft_94722ca912bd46ada6b9689f388d1b17
13: draft_aad45b4a4bd940459793788e716aa580
15: draft_7cb38254d8ab4c2084bb9e328da73b1e
17: draft_5cc85e4fade84aab9369d0a129f913c4
19: draft_bc0aa8c3e7e44e20bae3af071f3eab68
20: draft_7df2ca731edf4daaa794ee20507205ca
21: draft_29389bdab2f84345b596e45fcf2e2bcc
23: draft_85741ff7269e40bb8ce8992f24a6f3c7
29: draft_a597e472c3e141c3bf4a5539d2bcb5dd
31: draft_cc9a054620e040a5adee66a1f4dc3540
33: draft_296be0251d6f4ad2baadedfb506eba4b
34: draft_53be6e34cbb745c18d11ed233897fcb3
```

Assistant-only finalized cases **excluded** from human-16 (still in full-22):

```text
 2: draft_559331559a1a4a3eaf6f667db0727850
22: draft_ac3bfbaa86b4458ea1137742dc3829de
26: draft_e8bd3467bc52419e95d19a19dde839e2
27: draft_2083433ad52e4e00ad4214d3fec27464
30: draft_b88e163517ec47e29240171af181566d
32: draft_959387c7d1fc48f0a7ac4b38166d1fb1
```

Fail closed if:

```text
any ordinal maps to zero IDs
any ordinal maps to >1 ID
any selected ID is absent from the GoldDataset
selected count != 16
any selected ID is absent from a raw result cases[]
```

For human-16, recompute from existing per-case result data:

```text
aggregate metrics
category aggregates
latency summary
paired wins/losses/ties
```

Use existing Slice 9 metric semantics/helpers where possible.
Do **not** alter the six raw evaluation artifacts.

---

## 11. Module/document analysis

Raw Slice 9 results contain case ID / category / tags but not source module.

For module/document breakdown, resolve read-only:

```text
GoldCase id (= draft_case_id)
  → frozen Silver case
  → source_seed.document_id / document_title
```

Do not add module metadata to GoldDataset.

---

## 12. Pilot analysis outputs

Later execution may create local artifacts:

```text
eval/results/9h_p/9hp_analysis.json
eval/results/9h_p/compare_A_C_dense_full22.json
eval/results/9h_p/compare_A_D_dense_full22.json
eval/results/9h_p/compare_C_D_dense_full22.json
```

`9hp_analysis.json` should contain:

```text
full-22 aggregates for all six arms
human-16 aggregates for all six arms
per-case paired deltas
module/document aggregates
category aggregates
latency
22-vs-16 sensitivity findings
exact artifact/run IDs used
exact case-ID cohort mapping
```

No composite winner score.

---

## 13. Report

Future execution produces:

```text
docs/pilots/slice9h_p_results.md
```

Prominently:

```text
PILOT / NON-PROMOTIONAL
```

The report must distinguish:

```text
observed metric facts
sensitivity findings
hypotheses
limitations
```

No production/default recommendation.
No automatic start of 9G, formal 9H promotion, or Slice 10.

---

## 14. Private artifact policy

Raw GoldDataset / result artifacts remain local (`eval/results/*` gitignored).

Do not commit private candidate lists, retrieved text, or proprietary labels
merely to make the pilot reproducible publicly.

The tracked report should contain only the minimum aggregate/provenance
information already permitted by the existing pilot documentation policy.

---

## 15. Pre-execution checklist (when later authorized)

```text
[ ] preflight_pooling_artifacts succeeds for frozen Silver lineage
[ ] record original CURRENT dense index state
[ ] activate baseline historical dense; verify IDs
[ ] run A, B, C, E, F with --top-k 30 to planned paths
[ ] activate Arm H historical dense; verify IDs
[ ] run D with --top-k 30
[ ] restore original CURRENT; verify
[ ] validate six offline-rag-retrieval-eval-result-v1 envelopes
[ ] eval compare A-C, A-D, C-D only
[ ] postprocess human-16 + module + sensitivity into 9hp_analysis.json
[ ] write docs/pilots/slice9h_p_results.md (PILOT / NON-PROMOTIONAL)
[ ] HARD STOP
```

---

## Repo validation notes (planning pass)

Verified against the repo at plan-authoring time:

```text
config/base.yaml — present
config/experiments/dense_query_prompt.yaml — present (model-query-prompt-v1)
config/experiments/dense_no_heading_peers.yaml — present (Arm H composition)
preflight_pooling_artifacts — present in gold_authoring.pool_preflight
eval/results/* — gitignored (local results OK)
human-16 ordinal→draft_case_id map — 16/16 present in frozen GoldDataset
GoldDataset id / chunk_set_id — match contract
```

**Execution-plan deviations found:** none relative to the authorized planning
brief. Intentional non-use of `config/experiments/dense_baseline.yaml` /
`hybrid_*.yaml` experiment stubs is recorded in §3.
