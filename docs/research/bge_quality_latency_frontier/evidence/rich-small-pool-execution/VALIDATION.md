# Validation

- 44 focused tests passed (4.35 s) in the existing repository Python
  environment. Invocation from the repository root:

  ```bash
  study=docs/research/bge_quality_latency_frontier
  evidence="$study/evidence/rich-small-pool-execution"
  PYTHONPATH=src python -m pytest -q "$study/scripts" "$evidence/test_summary.py" \
    tests/unit/test_slice9_evaluation.py tests/unit/test_hybrid_rerank.py
  ```

- Ruff lint and formatting passed for the analysis and gate tests.
  The staged runner and sampler passed Bash syntax validation, and the
  probe and summary scripts passed Python compilation.
- Reproduce the results and plot without executing inference:

  ```bash
  scratch=$(mktemp -d)
  python "$evidence/summarize.py" "$evidence/MEASUREMENTS.log" "$evidence/SAMPLES.log" "$scratch"
  cmp "$evidence/SUMMARY.json" "$scratch/SUMMARY.json"
  cmp "$evidence/PAIRED.csv" "$scratch/PAIRED.csv"
  Rscript "$evidence/figure.R" "$scratch/PAIRED.csv" "$scratch/figure.png"
  cmp "$study/figures/09-rich-small-pool-paired.png" "$scratch/figure.png"
  ```

- The JSON, paired CSV and figure reproduced byte for byte. Git diff
  checks passed. The branch changes only the appended report and new
  experiment evidence.
