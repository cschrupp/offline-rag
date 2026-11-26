# KM-02 workspace knowledge memory

KM-01 was merged through PR #7 at
`137591ea53774563160451955d05db326ef1a7a1`.
[Main CI passed](https://github.com/cschrupp/offline-rag/actions/runs/45712163348).
KM-02 starts from that merge under the Human implementation authorization.

Open **Knowledge** beside **Evidence**, then choose **Enable memory**.
Completed cited discussions are saved locally as a discussion, a concept
and a study excerpt. Add a learner note from an item. Use **Find a topic**
to bring related discussions together, and expand an item to inspect its
origin, links, source version, publication and corrections. Forgetting
removes a record, its revision history and its dependent records from the
memory store. It does not delete original sources or chat history. Pause
stops future capture and keeps saved items available.

Each workspace has a separate SQLite file under the application data root.
Capture deduplicates delivery by committed event ID. Note saves use the
client's idempotency key. Both operation markers survive forgetting without
retaining text, provenance, or a hash of the content. Topic association uses
normalized terms, explicit aliases and recognized question templates.
Uncertain topics keep separate keys. Search considers up to 24 indexed hits
per term, up to 12 terms, requires every query term and returns at most 24
records. Corrections replace indexed terms atomically, and learner notes
index their own text while retaining the relationship to the parent topic.
Cumulative summaries assemble short excerpts from the matched concepts
and retain their record identities. Edits preserve the original provenance
and mark the new text as learner-provided. SQLite transactions protect
compare-and-set revisions and cascading deletion. Forgetting does not erase
preexisting backups.

The canonical grounded query does not read memory. Scope and publication
binding determine the evidence and citations. Capture runs only after the
grounded result and conversation trace have committed. Storage failure is
isolated to memory and logged without note or answer text. Capture and
recall use zero additional inference.

## Demonstration

[Chromium screenshot](topic-recall.png) shows a fresh browser session
recalling two related discussions, with source provenance expanded.
Chromium used the running Seneca UI and real FastAPI routes with deterministic
inference fixtures. Three submitted questions caused three grounded
generation calls. The unrelated clustering discussion stayed outside the
topic view. The backend regression separately restarted the application
runtime against the same data directory, verified a second workspace
returned no records, and verified a newly selected source alone supplied
citations while a learner correction existed in memory.

## Local storage overhead

A local microbenchmark measured 200 serial captures and 200 lookups during
growth from zero to 600 records, using short synthetic text and a one-topic
index on this development host. Timings include SQLite open, transaction and
close. They exclude HTTP, ingestion, retrieval and generation.

| Operation | Median | p95 |
| --- | ---: | ---: |
| Capture three linked records | 15.842 ms | 21.229 ms |
| Recall up to 24 records | 1.015 ms | 1.676 ms |

The final SQLite file occupied 442,368 bytes. These measurements describe
the local fixture and do not establish latency under concurrent load or
large records.


## SOL corrective regression

The corrective covers shared topic keys for definition and tool questions,
the explicit SCBA alias, and distinct keys for ambiguous topics. It verifies
that a shared generic term alone is insufficient for recall. The storage
regression injects a SQLite failure during reindexing and checks that both
record and index roll back. It also verifies capture and save retries after
forgetting, and independent intentional saves. Existing databases seed
markers from still-retained discussion episodes when first opened.
