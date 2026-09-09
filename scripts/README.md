# Scripts

Operational helpers for OfflineRAG.

## Slice 1

- `provision_docling.py` — explicit Docling artifact provisioning (network allowed here only)
- `generate_pdf_fixture.py` — regenerate the committed born-digital PDF test fixture (maintenance only; not used by pytest)

Later scripts may include:

- benchmark machine/environment summary
- prepare demo corpus
- export benchmark report
- verify offline runtime
- build/delete local Qdrant collection
- generate synthetic evaluation questions (clearly marked synthetic)
