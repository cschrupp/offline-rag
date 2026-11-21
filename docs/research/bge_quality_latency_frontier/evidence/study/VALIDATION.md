# Validation

- Research replay and canonical Slice 9 evaluation suite: 24 passed.
- Replay invariants: all 22 valid and quality-eligible, linked to exact
  GoldDataset/corpus/chunk-set identities. RRF and BGE candidate sets and
  BGE input order checked independently on every case.
- Research replay tests cover original prefix membership, incorrect source
  order, truncated output, duplicate/missing output, and padding arithmetic.
- Historical context: previous Torch 4/1 exact-logit failure remains a failure.
  Local pilot and ONNX used separate predefined floating-point tolerances.
- Deterministic replay rerun matched the recorded JSON byte for byte.
- Ruff lint and format checks, Python compilation, six figure renders, and git diff checks passed.
