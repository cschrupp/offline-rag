# Known Limitations — Current

This file should evolve with measured project results.

## Implemented baseline (Slices 0–5)

- Dense retrieval quality depends on provisioning real Qwen3-Embedding-0.6B weights; FakeEmbedder is for CI/architecture only.
- Default PDF profile is born-digital / non-OCR; scanned/image-only PDFs may degrade or warn.
- Table splitting in the structure-aware chunker is intentionally modest (row packs + warn on pathological cases).
- Docling heading/outline fidelity is pragmatic, not a full outline engine.
- Dense gold labels are bound to a specific `chunk_set_id`; changing chunk budgets invalidates chunk-level relevance IDs.
- Published indexes and embedding artifacts are retained indefinitely; disk growth is intentional until GC exists.
- Qdrant Local assumes one OfflineRAG process owns a given storage directory.
- Hybrid retrieval is query-time RRF only (no hybrid index); both dense and lexical indexes must be CURRENT on the same chunk set or hybrid fails hard.
- Full rerank/generation quality claims are not yet available (Slices 6–8+; `query` deferred to Slice 8+).
- Lexical BM25 is corpus-global (full rebuild per `lexical_index_id`); no per-child lexical cache.
- Lexical indexes are retained indefinitely with dense indexes until GC exists.

## Expected later limitations

- table extraction/retrieval may require specialized handling;
- OCR quality can dominate downstream retrieval quality on scanned documents;
- exact numeric answers can fail even when semantically similar passages rank highly;
- hierarchical expansion may add excessive context if parent sections are large;
- local judge models may produce unstable semantic evaluation scores;
- quantized generators may vary in citation-format reliability;
- an offline system still requires an explicit initial model/dependency provisioning step;
- prompt-injection defenses reduce risk but do not constitute a formal security proof;
- benchmark results on one technical corpus do not imply universal ranking superiority.

## Deployment notes

- the flagship deployment is one OfflineRAG container plus a separately running local generator runtime (Ollama by default), not a literal single-process/single-container LLM stack;
- strict-offline correctness depends on deployment configuration and verification of the external local model runtime as well as the application container.

Public documentation should state measured limitations rather than hiding them.
