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

## 2. Embedding model (Slice 3 + 16K-D P3)

Canonical command:

```bash
offline-rag provision embedding
# or
uv run python scripts/provision_embedding.py
```

Representation selection (P3):

```bash
offline-rag provision embedding
                                 # torch_st_v1 (default)
offline-rag provision embedding --representation torch_st_v1
offline-rag provision embedding --representation onnx_fp32_v1 --onnx-source <DIR>
offline-rag provision embedding --representation all --onnx-source <DIR>
```

`--onnx-source` must point at a local directory containing the already-qualified
`onnx_fp32_v1` bytes (accepted historical tree SHA
`3e1b23a7293cf599bc34d1d9875e5c4ecde45bf12fcd300a6cb66794b5bc4345`).
The source path has no authority; package digests decide eligibility.
P3 never regenerates ONNX from Torch.

Default local layout (bundle-aware):

```text
models/embeddings/qwen3-embedding-0.6b/
├── offline-rag-embedding.json          # legacy torch root (may remain)
├── offline-rag-embedding-bundle.json   # selection pointers
└── representations/
    ├── torch_st_v1/<immutable-instance>/
    └── onnx_fp32_v1/<immutable-instance>/
        └── offline-rag-embedding-representation.json
```

Pinned upstream (Torch):

- model: `Qwen/Qwen3-Embedding-0.6B`
- revision: `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`
- dimension: 1024
- runtime: sentence-transformers

Provisioning is a durable same-filesystem transaction with one forward bundle
publication when selection changes. Successful provisioning does not mutate a
running process (`metadata.restart_required=true` when newly available).

Runtime (`index` / `retrieve` / `eval retrieve` / `doctor`) must never download weights.
Missing/invalid artifacts → actionable error (ABSENT / INVALID / READY).

CI uses `FakeEmbedder` (`indexing.embedding.implementation: fake`) without weights.

Design: `docs/slice16k_d_dual_backend_p3_provisioning_acquisition_design.md`.

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
