# Codex — The 59-Second Retrieval: Independent Review Corrections

Repository: `cschrupp/offline-rag`

Branch: `research/bge-quality-latency-frontier`

Reviewed commit: `f2a1e145fb60a82581da559c36a939a8fdb6ca9f`

**Disposition:** `REVISE` — targeted research-quality improvements. The measured findings remain valid as exploratory observations. No production promotion is authorized.

## Task 1 — Add case-level quality analysis

Extend the candidate-depth analysis and research report to show the distribution of paired changes, not just macro averages.

Independently verify and document:

- BGE-15 versus BGE-30: 3 nDCG@10 improvements, 2 regressions, 11 ties among 16 human-reviewed queries.
- Fire Safety: approximately −0.0676 nDCG@10.
- Construction Materials: approximately −0.0636 nDCG@10.
- Full-pool judged-positive counts: 64 for BGE-15 and 79 for BGE-30.

Make the distinction between full-pool positive retention and Recall@10 explicit.

Add a seventh figure showing per-query nDCG@10 changes, including negative outcomes.

Clarify the depth-15 finding in the executive summary and figure captions: cohort-average retention is exploratory and does not establish query-level non-inferiority or production readiness.

## Task 2 — Strengthen reproducibility gates

Inspect `scripts/analyze.py` and `scripts/batch_pilot.py`.

Ensure:

- Pilot parity failures cause nonzero exit status.
- Numerical tolerances are explicit and checked.
- Candidate-score association and ranking mismatches fail closed.
- Historical input files are resolved unambiguously.
- Expected artifact SHA-256 values are verified before replay.
- Existing research metrics and frozen scientific contracts remain unchanged.

Add focused tests for the corrected behavior.

Do not alter or overwrite previously recorded observations. If reproduction reveals a mismatch, stop and report it rather than changing the evidence to make it pass.

## Task 3 — Refine research storytelling

Improve the narrative around three questions:

1. Why did conventional CPU optimization fail to solve the 59-second retrieval?
2. How much computation was wasted through padding, and what did the local experiment actually recover?
3. Why can depth 15 look equivalent on average while harming specific queries?

Preserve the negative PyTorch and ONNX results.

Clearly identify the difference between:

- Measured latency
- Theoretical workload reductions
- Replayed ranking quality
- Grounded-answer correctness

Keep the report labeled `INTERIM RESEARCH REPORT`.

## Task 4 — Independent-review package

Create a concise reviewer handoff documenting:

- Original research questions and preregistered tests.
- Commit and artifact identities.
- Exact reproduction instructions.
- Research evidence completed.
- Remaining limitations.
- Open questions for independent review.
- Explicitly unauthorized production changes.

Retain this authorization prompt and the full implementation response.

## Task 5 — Commit and push

Run the relevant tests, regenerate figures, verify Git diff and repository cleanliness.

Commit the changes to the existing research branch and push to origin.

Do not modify `main`, merge a PR, deploy anything, change retrieval defaults, or execute new VM experiments.

Return the new commit SHA, updated report link, test outcomes, and reviewer handoff.

**Stop after publishing the review revision.**
