# Reproduce the interim study

Branch `research/bge-quality-latency-frontier` starts at
`9c92e706c4b9e9d9ac0816a655bdf131cc63fca1`. Protocol freeze `830879ed`
preceded both new analyses. The exact source commits executed are in
[replay-commit.txt](executed/replay-commit.txt) and
[pilot-commit.txt](executed/pilot-commit.txt). The benchmark ran in the
research worktree, using the existing local Python 3.14.5 environment
without changes to the release dependency graph.

## Frozen inputs

The artifact SHA-256 values and run IDs are recorded in
[observations.json](executed/observations.json). Use an existing authorized
local workspace containing the original Slice 9H-P E/F full-22 result
artifacts under `eval/results/9h_p/` and the exact GoldDataset v1 directory.
These local historical inputs may contain source-derived text and are not
copied into this publication draft. Verify their SHA-256 against the manifest
before running. The repo contains the cohort membership and corrected Slice
14C aggregate. The scalar VM log is included with this study. It is a retained
observation, not a new VM run.

```bash
study=docs/research/bge_quality_latency_frontier
export PYTHONPATH="$PWD/src"
python "$study/exploratory/analyze.py" \
  "$AUTHORIZED_ARTIFACT_REPO" "$AUTHORIZED_GOLD_DATASET" \
  "$study/executed/seneca-four-results.log" /tmp/seneca-replay.json
cmp /tmp/seneca-replay.json "$study/executed/observations.json"
```

The replay code validates corpus, chunk set, Gold identity, dense/lexical
indexes, fusion settings, original fused order, complete BGE permutation,
label eligibility and matching question identity. Per-case output contains
an opaque case ordinal, category, cohort, label counts, and metrics.
The published summary cannot reconstruct any source passage or query.

## Offline pilot

The benchmark requires the already provisioned BAAI/bge-reranker-v2-m3
checkpoint revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` and its
tokenizer. Their exact digests are recorded in the pilot JSONL. The input
generator produces synthetic sequences with the 30 measured incident token
lengths. It checks equal unpadded IDs across arms and records observed
batch shapes. It does not use original incident documents or a vector store.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  python "$study/exploratory/batch_pilot.py" "$LOCAL_BGE_MODEL" > /tmp/seneca-pilot.jsonl
```

The timed interval is model forward only. Scorer wall, process CPU time and
cumulative RSS are also retained. The runtime uses the existing reranker
load contract with Torch 2.14.0+cpu and Transformers 4.57.6, CPU FP32, on an
Intel i9-10885H with 16 visible logical CPUs and measured intra/inter 2/2.
Synthetic logit and rank parity do not establish evidence-unit parity.
Timing will vary by host, workload and operating conditions.

## Figures and checks

```bash
Rscript "$study/exploratory/figures.R" "$study"
python -m pytest -q "$study/exploratory/test_analyze.py" tests/unit/test_slice9_evaluation.py
ruff check "$study/exploratory"
ruff format --check "$study/exploratory"
git diff --check
```

Figures were rendered with R 4.5.2, ggplot2 4.0.2 and jsonlite 2.0.0. The
research plots use frozen JSON/JSONL and require no model runtime.

## Historical provenance anchors

| Evidence | Source identity |
|---|---|
| Corrected Slice 14C | Execution `affbd1127b1afc677e31c132da1c000c6cf246b5`, evidence `153376b28545017c6134f9858d330548a7d8c6c7` |
| Slice 14C earlier terminal runs | `perfrun_87771f72…` failed, `perfrun_f5ed426a…` audit unaccepted. Both preserved and excluded |
| Level-C | Execution `30b5abb627e16e50b2b848b44676b89b2372c3d6`, run `perfrun_211ebf1f9bcdef93d1f14421b754ef5ff387e2e091dc7f603f455dd083fdbf39` |
| Recipes incident snapshot | `snap_89eb8d5cfc93c444b970ee8da72b177967009d22ba059f12e318efb45a422196`, workspace revision 4, single-document scope |
| BGE VM forward diagnostic | Code `c3b72ac7d6f81220779e1370f43d33fe2c065ec4`, evidence `f9f3f35a` |
| BGE VM thread experiment | Evidence `9066e62fb1c07ab915e4e8360742b66f469afe1e` |
| Local ONNX feasibility | `f196e5ff98f1a8d47fd442f212fc45d8ce086e75` |
| Four-vCPU ONNX qualification | `1d1f9aec`, included scalar execution log |
