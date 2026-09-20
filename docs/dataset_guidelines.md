# Evaluation Dataset Guidelines

## Question-writing rules

Good benchmark questions should resemble realistic user questions, not paraphrases mechanically copied from one sentence.

Include:

- exact lookup;
- terminology variants;
- synonyms;
- ambiguous acronyms resolved by corpus context;
- numeric constraints;
- table-derived facts;
- cross-document comparison;
- multi-evidence synthesis;
- unsupported questions.

## Relevance labeling

Prefer explicit supporting evidence over only a reference answer.

A question may have:

- one relevant chunk;
- multiple interchangeable chunks;
- multiple jointly necessary chunks.

GoldDataset v1 graded judgments (serialized positives only):

- `relevance = 2` — directly answer-bearing;
- `relevance = 1` — materially supporting but insufficient alone;
- `relevance = 0` — implicit / omitted (do not serialize).

Binary relevance for Recall/Precision/HitRate/MRR is `grade >= 1`. Use child `chunk_id` identity bound to `chunk_set_id`; do not gold-label EvidenceUnit IDs.

New datasets must write `judgments[]`. Legacy `relevant_chunk_ids[]` remains read-compatible and normalizes each positive to relevance `1`.

Optional opaque `category` (primary aggregation axis; missing → report bucket `uncategorized`) and `tags[]` (secondary slicing).

## Avoiding leakage

Do not create every gold question by asking the same generator model to turn each indexed chunk into a question. This creates synthetic bias.

## Versioning

`dataset_id` is derived from the canonical GoldDataset v1 semantic payload (not raw file bytes / paths / free-form metadata). If `meta.json` persists `dataset_id`, it must match recomputation or load fails closed.

Bind cases to a specific `chunk_set_id`. Changing child-chunk budgets or chunk config invalidates chunk-level relevance IDs; re-label or rebind before comparing runs.

See `eval/datasets/slice9_validation/` for the small harness fixture shape.

## Offline gold authoring (Milestone 4)

Private corpora should be labeled through the local authoring workflow (`offline-rag gold …`; Slices **9A**–**9E** implemented), not by uploading documents to cloud annotation or evaluation services. The local model may propose questions and pre-grades; **humans adjudicate** final GoldDataset v1 labels. Silver/authoring drafts are not evaluation gold.

Canonical plan: [`milestone4_offline_gold_authoring.md`](milestone4_offline_gold_authoring.md). Slices **9A**–**9E** done; **9F GO**; **9H-P COMPLETE / NON-PROMOTIONAL**; **9G** deferred; formal **9H** frozen — [`pilots/slice9f_ics_modules.md`](pilots/slice9f_ics_modules.md). Slice **10** design: [`slice10_generation_semantic_evaluation.md`](slice10_generation_semantic_evaluation.md).

## Review checklist

- Is the question understandable without seeing the target passage?
- Is the expected evidence actually present?
- Are multiple valid answers accounted for?
- Is the query category correct?
- Is the question answerable status correct?
- Does the reference answer include only corpus-supported facts?
