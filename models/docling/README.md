# Docling artifacts

Provision local Docling model artifacts here for offline PDF parsing:

```bash
uv run python scripts/provision_docling.py --output models/docling
```

This directory is ignored by git except this README and `.gitkeep`.
Runtime parsing never downloads artifacts.
