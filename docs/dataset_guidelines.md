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

If relevance is graded, document the scale.

## Avoiding leakage

Do not create every gold question by asking the same generator model to turn each indexed chunk into a question. This creates synthetic bias.

## Versioning

Store a dataset version and content hash. If chunking changes substantially, preserve page/semantic labels when possible so benchmark maintenance remains manageable.

For Slice 3 dense retrieval gold (`eval retrieve`), bind cases to a specific `chunk_set_id`. Changing child-chunk budgets or chunk config invalidates chunk-level relevance IDs; re-label or rebind before comparing runs.

## Review checklist

- Is the question understandable without seeing the target passage?
- Is the expected evidence actually present?
- Are multiple valid answers accounted for?
- Is the query category correct?
- Is the question answerable status correct?
- Does the reference answer include only corpus-supported facts?
