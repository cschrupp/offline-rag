# Tiktoken tokenizer artifacts

Local cache for OfflineRAG Slice 2 token budgeting (`cl100k_base`).

Provision once (requires network):

```bash
uv run python scripts/provision_tiktoken.py
```

Runtime chunking uses `paths.tokenizer_artifacts` only and never downloads.
