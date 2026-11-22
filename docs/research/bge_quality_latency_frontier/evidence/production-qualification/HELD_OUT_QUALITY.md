# BGE-15 held-out qualification population and adjudication

**Population specification only.** No queries selected, outcomes opened,
or judgments produced by this revision. Use the existing
[BGE-15 protocol](../bge15-cpu/PROTOCOL.md). Compare BGE-15 vs BGE-30
under the same approved batching, CPU profile, corpus/query, and source
scope. A sorted-eight release candidate must independently pass batching
parity at both depths. The 9H-P replay, Recipes and Rich incidents,
near duplicates and same-document-family paraphrases are development
evidence and excluded from held-out scoring.

## Sampling frame and evidence packet

Recruit independently cleared sources in at least four families:
technical manuals, procedures and incident/training guides, narrative
or reference documents, and mixed-layout/table-heavy documents.
Cross document family with query intent (direct answer, synthesis,
and technical terminology/disambiguation), language (English, Spanish,
and cross-lingual), and eligible pre-truncation pool size (1–5, 6–10,
11–29, and ≥30). Include short and long passage strata, with exact
token length definitions consistent with the execution plan. Declare
target population and report coverage, including unsupported intersections.
Sample by document/query family to prevent related questions from
inflating the sample. Long and multilingual strata need explicit counts.

Use a separately approved, development-only variance and feasibility
pilot of up to 32 questions to size adjudication and estimate paired
variance and cluster effects. Plan the held-out roster at up to 192
queries. Before any held-out scoring, document the selected sample size,
stratum counts, provenance, licenses/access permissions, query-family
grouping, scope/checkpoint/snapshot hashes, sampling seed and all
exclusions. Size against both frozen margins and the harm bound. If
the roster cannot provide the needed precision, require a new reviewed
authorization for a larger roster or report insufficient coverage.
Independent reviewers and access to rights-cleared corpora are actual
prerequisites.

The controlled runner retains both candidate orders, selected anchors,
ordered evidence units and packed contexts, with case and artifact
identities. Generate a blinded packet of the deduplicated candidate
union and a randomized context pair, hiding arm, rank, latency and model
scores. Include separately adjudicated eligible nonreturned passages
when needed for recall denominators. For naturally small pools aim for
exhaustive judgments of the eligible scope. Passage-level judgments
distinguish unrelated, partial support and direct support, using the
canonical relevance grades for scoring. Keep an explicit unjudged
state outside the canonical run envelope. Have two independent reviewers
label each case and resolve differences with a third adjudicator. Freeze
labels before calculating arm scores and document agreement and reasons.

Do not silently count unjudged candidates as irrelevant. Require agreed
coverage for the candidate union and scoped positive denominator before
assigning an eligible paired score. Report missing judgments by arm,
rank and stratum. Show sensitivity bounds for unresolved labels. A
required stratum lacking defensible denominators cannot pass. Apply the
canonical nDCG and Recall definitions with the same judgment set for both
arms. Context review separately asks whether the evidence is sufficient
to answer and whether direct support or necessary disambiguation was
lost. Candidate or context agreement with BGE-30 is diagnostic only.

## Frozen decision rules

Retain the existing non-inferiority margins: paired lower 95% bounds
for BGE-15 minus BGE-30 **strictly above −0.02 nDCG@10 and −0.05
Recall@10**. Use a predeclared query-family paired bootstrap plan
(10,000 resamples, fixed seed, lower endpoint of the 95% percentile
interval, both endpoints required). Report nDCG@5, Recall@5 and
HitRate@5 shifts within each required stratum with paired counts and
intervals. No lost sole directly supporting top-five passage, no
adjudicated material evidence-sufficiency regression, and no passage
of unsupported required strata. Retain the development Fire Safety
(−0.0676) and Construction Materials (−0.0636) losses.

Proposed query-level allowance for review **before** freezing or opening
the holdout: treat nDCG@10 loss >0.05 as a materially regressed query
and require the upper 95% family-bootstrap bound on the fraction of
such queries ≤10% overall, with per-stratum point fraction ≤10% and
no single nDCG@10 loss >0.20. Also report every downgrade and actual
count, including smaller deltas. These are proposed harm limits, not
changes to the existing non-inferiority margins. A separate review
must accept adequacy and freeze these limits (or specify revised
limits before data access). A safety-critical or sole-support loss
fails independently of numerical limits. Do not tune selection,
thresholds or models on held-out outcomes.

When a separately authorized paired generation study is feasible, use
the same frozen generator and prompt, keep trace-linked arm boundaries,
and independently judge answer correctness, direct support, citation
membership versus support, and abstention. Report latency separately.
If generator execution or independent labels are unavailable, qualify
retrieval/context only. Explicitly mark grounded-answer quality
unevaluated.

For rare harms, also precompute a conservative one-sided count bound
on the fraction of affected independent query families and require that
it support the stated harm assurance. A zero-event sample can produce
a degenerate bootstrap bound and does not by itself establish the
10% guarantee. Report insufficient precision where appropriate.
