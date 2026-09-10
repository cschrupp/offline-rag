# Scripts

Operational helpers for OfflineRAG.

## Provisioning (network allowed only here)

- `provision_docling.py` — Docling PDF model artifacts → `models/docling/`
- `provision_tiktoken.py` — tiktoken `cl100k_base` cache → `models/tokenizers/tiktoken/`
- `provision_embedding.py` — thin wrapper for `offline-rag provision embedding` (Qwen3-Embedding-0.6B → `models/embeddings/qwen3-embedding-0.6b/`)

## Fixtures / maintenance

- `generate_pdf_fixture.py` — regenerate the committed born-digital PDF test fixture (not used by pytest)

## Later (not implemented)

- benchmark machine/environment summary
- prepare demo corpus
- export benchmark report
- verify offline runtime
- reference-aware Qdrant/index GC
- generate synthetic evaluation questions (clearly marked synthetic)
