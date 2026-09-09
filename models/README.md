# Local Retrieval Models

This directory is for **embedding and reranker assets only** and should remain ignored by Git except for documentation/manifests.

The generative LLM is intentionally managed outside OfflineRAG by Ollama or another local OpenAI-compatible inference runtime.

Suggested layout:

```text
models/
├── embeddings/
└── reranker/
```

Do not commit model weights.
