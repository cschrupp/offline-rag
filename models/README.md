# Local Retrieval Models

This directory holds **embedding and (later) reranker assets** only. Weights are
gitignored except documentation / placeholders.

The generative LLM is managed outside OfflineRAG (Ollama or another local
OpenAI-compatible runtime).

## Layout

```text
models/
├── README.md
├── manifest.example.yaml
├── docling/                    # Slice 1 PDF artifacts (provision_docling.py)
├── tokenizers/tiktoken/        # Slice 2 budgeting tokenizer
├── embeddings/
│   └── qwen3-embedding-0.6b/   # Slice 3 dense model (provision embedding)
└── reranker/                   # future
```

## Provision

```bash
uv run python scripts/provision_docling.py
uv run python scripts/provision_tiktoken.py
uv run offline-rag provision embedding
```

Do not commit model weights.
