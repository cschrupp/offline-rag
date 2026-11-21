# Reproduce the Rich case study and matched prefixes

The branch starts at existing exact-incident research lineage
`cf6dab622be22305f96883fa2465619e77bbd835`. The deployed source and exact
image, snapshot, CPU, checkpoint, source and settings hashes are in
[the earlier stage report](../rich-stage/REPORT.md) and
[raw projections](../rich-stage/MEASUREMENTS.log). The imported report's
figure link was updated for the new location. Imported sample lines and
CSV line endings were normalized without changing any fields or values.
The original stage
authorization, implementation response, Bash runner and Python probe
are archived for provenance only. Running that experiment again would
require fresh authority.

From the research worktree root, use the repository Python environment,
the same authorized 9H-P historical artifact checkout and frozen Gold
dataset described in [the original instructions](../../REPRODUCIBILITY.md).
Only the five inputs needed for relevance replay are opened. They are
verified against the original digest manifest before replay. The output
uses opaque case ordinals and canonical judgments and metrics.

```bash
study=docs/research/bge_quality_latency_frontier
export PYTHONPATH="$PWD/src"
scratch=$(mktemp -d)
python "$study/scripts/small_pool.py" \
  "$AUTHORIZED_ARTIFACT_REPO" "$AUTHORIZED_GOLD_DATASET" > "$scratch/replay.json"
cmp "$scratch/replay.json" "$study/data/small-pool-replay.json"

cp "$study/evidence/rich-stage/"{MEASUREMENTS.log,SAMPLES.log,PHASE_TIMESTAMPS.log} "$scratch/"
python "$study/evidence/rich-stage/summarize.py" "$scratch" > "$scratch/summary.json"
cmp "$scratch/summary.json" "$study/evidence/rich-stage/SUMMARY.json"
cmp "$scratch/WATERFALL.csv" "$study/evidence/rich-stage/WATERFALL.csv"
Rscript "$study/evidence/rich-stage/waterfall.R" "$scratch/WATERFALL.csv" "$scratch/waterfall.png"
cmp "$scratch/waterfall.png" "$study/figures/08-rich-stage-waterfall.png"

python -m pytest -q "$study/scripts" tests/unit/test_slice9_evaluation.py tests/unit/test_hybrid_rerank.py
ruff check "$study/scripts"
ruff format --check "$study/scripts"
git diff --check
```

The new replay and the earlier replay use the same fixed Gold cases and
depth definitions. The comparison here takes the original RRF prefix as
the control for each BGE prefix. Missing raw logits are addressed by
filtering the verified full BGE permutation. Replay says nothing about
runtime logits under changed shape or about packed RRF-only context.
Figure rendering uses R 4.5.2 and ggplot2 4.0.2.

The Rich browser result was HTTP 200 and cited rendering, with two prior
turns, a resolver call, 46.095 seconds Firefox elapsed and 39.775 seconds
context stage. The [stage report](../rich-stage/REPORT.md) records the
hash mismatch against the no-history query without retaining prior-turn
or source content. The two workspaces' timing records remain separate.
