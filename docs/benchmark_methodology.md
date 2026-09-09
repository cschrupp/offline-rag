# Benchmark Methodology

## Goal

Provide a reproducible basis for comparing retrieval and generation configurations without cherry-picked questions.

## Corpus

Document the public demo corpus with:

- file list;
- source/license notes;
- content hashes;
- page count;
- ingestion/parser configuration;
- chunking configuration;
- corpus manifest hash.

## Benchmark sets

### Gold

Human-authored and verified.

### Negative

Questions intentionally unsupported by the corpus.

### Adversarial

Questions/documents designed to test prompt injection, fake citations, and evidence manipulation.

### Synthetic

Optional local-model-generated expansion, reported separately.

## Run protocol

For every published experiment:

1. freeze corpus manifest;
2. freeze evaluation dataset;
3. record git commit;
4. record config;
5. clear/identify relevant caches;
6. run retrieval metrics;
7. run generation metrics if enabled;
8. record stage timing/resources;
9. save per-query results;
10. generate aggregate and category reports.

## Statistical caution

A small portfolio benchmark can be informative but may not justify broad generalization. Report the number of questions and avoid claiming universal superiority from one corpus.

Where useful, bootstrap confidence intervals can be added later over per-query metric contributions.

## Reporting

Always show:

- dataset size;
- corpus version;
- hardware;
- relevant configuration;
- overall metrics;
- category metrics;
- at least representative failures;
- latency/resources.
