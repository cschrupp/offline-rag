# Model Provisioning

Model provisioning is intentionally separate from normal OfflineRAG runtime.

## 1. Generator

The generative model is managed by an external local inference runtime. Ollama is the default deployment target.

OfflineRAG stores only:

- the configured endpoint;
- the configured model identifier;
- an approved local-model manifest/list;
- generation parameters used for reproducibility.

It does not store generator weights in the application image or `/models`.

## 2. Embedding model (Slice 3)

Canonical command:

```bash
offline-rag provision embedding
# or
uv run python scripts/provision_embedding.py
```

Default local layout:

```text
models/embeddings/qwen3-embedding-0.6b/
├── ... Sentence Transformers / model files ...
└── offline-rag-embedding.json
```

Pinned upstream:

- model: `Qwen/Qwen3-Embedding-0.6B`
- revision: `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- dimension: 1024
- runtime: sentence-transformers

Runtime (`index` / `retrieve` / `eval retrieve` / `doctor`) must never download weights.
Missing/invalid artifacts → actionable error (ABSENT / INVALID / READY).

CI uses `FakeEmbedder` (`indexing.embedding.implementation: fake`) without weights.

## 3. Tokenizer (Slice 2)

```bash
uv run python scripts/provision_tiktoken.py
```

Installs under `models/tokenizers/tiktoken/` with `offline-rag-tokenizer.json`.

## 4. Docling (Slice 1)

```bash
uv run python scripts/provision_docling.py
```

Installs under `models/docling/` with `offline-rag-artifacts.json`.

## 5. Reranker

Not provisioned yet. Future weights belong under:

```text
models/reranker/<model>/
```

## 6. Manifest

Use `models/manifest.example.yaml` as the schema seed for approved retrieval assets and generator identifiers.
