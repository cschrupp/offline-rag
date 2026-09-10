# Slice 1 — Document Parsing and Ingestion

Slice 1 turns source files into durable normalized parser output.

**Status:** implemented.

## Flow

```text
source files
    ↓
parser dispatch (TXT / Markdown / Docling PDF)
    ↓
ParsedDocument JSON          (content-addressed cache)
    ↓
CorpusManifest               (immutable snapshot)
    +
CorpusState                  (mutable active library)
    +
IngestionReport              (one execution)
```

## Configuration additions

- `paths.docling_artifacts` (default `models/docling`)
- `paths.corpora` (default `data/corpora`)
- `paths.manifests` / `paths.processed`
- `parsing.pdf.ocr_enabled` (default `false`)
- env: `OFFLINE_RAG_DOCLING_ARTIFACTS_PATH`, `OFFLINE_RAG_CORPORA`, `OFFLINE_RAG_PDF_OCR_ENABLED`

## Docling artifacts

Python package dependency: Docling is required.

Runtime model dependency: artifacts must be provisioned explicitly:

```bash
uv run python scripts/provision_docling.py
```

Parsing never downloads artifacts. Missing/incomplete local artifacts raise
`DoclingArtifactsUnavailableError`.

## CLI

```bash
offline-rag ingest <path> [<path> ...]
  --recursive
  --root <path>
  --corpus <name>          # default: default
  --json
  --config <yaml>          # repeatable
```

`ingest` is additive/update-oriented. Sources not included in an invocation
remain in the active corpus. Authoritative synchronization/removal is deferred.

## Identities

| Identity | Deterministic? | Meaning |
|---|---|---|
| `document_id` | Yes | Source bytes |
| `parsed_artifact_id` | Yes | Source + parse config/contract |
| `corpus_id` | Yes | Full active corpus snapshot |
| `run_id` | No | One ingestion execution |

## PDF profile

Slice 1 targets born-digital PDFs with OCR disabled by default. Image-only /
scanned PDFs may require OCR and are outside the default parser profile.

## Deferred beyond Slice 1

(Now implemented in later slices where noted.)

- retrieval `Chunk` creation / parent-child chunking → **Slice 2**
- embeddings, Qdrant, dense retrieve → **Slice 3**
- BM25 (Slice 4), hybrid/RRF (Slice 5), reranking (Slice 6), context expansion (Slice 7), generation (Slice 8+)
- authoritative `--sync` / deletion
- OCR-focused fixture suite
