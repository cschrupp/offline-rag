"""HTTP adapter (FastAPI). Thin transport over offline_rag.app."""

from offline_rag.api.app import create_app

__all__ = ["create_app"]
