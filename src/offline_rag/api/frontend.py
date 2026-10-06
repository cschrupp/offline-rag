"""Same-origin SPA static delivery for the OfflineRAG UI (Slice 16C).

Serves compiled Vite assets from ``OFFLINE_RAG_UI_DIR`` (default ``/app/ui``)
without swallowing backend API, health, OpenAPI, or docs routes.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

_DEFAULT_UI_DIR = Path("/app/ui")
_RESERVED_ROOTS = frozenset({"v1", "health", "docs", "redoc", "openapi.json"})


def resolve_ui_dir(ui_dir: Path | str | None = None) -> Path | None:
    """Return a usable frontend directory, or ``None`` for API-only mode."""
    if ui_dir is not None:
        candidate = Path(ui_dir)
    else:
        env = os.environ.get("OFFLINE_RAG_UI_DIR", "").strip()
        candidate = Path(env) if env else _DEFAULT_UI_DIR
    if not candidate.is_dir():
        return None
    if not (candidate / "index.html").is_file():
        return None
    return candidate.resolve()


def _is_reserved_api_path(full_path: str) -> bool:
    normalized = full_path.lstrip("/")
    if not normalized:
        return False
    root = normalized.split("/", 1)[0]
    return root in _RESERVED_ROOTS


def _safe_file_under(root: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``root``; reject path traversal."""
    if not relative or relative.endswith("/"):
        return None
    cleaned = relative.replace("\\", "/").lstrip("/")
    if not cleaned or ".." in cleaned.split("/"):
        return None
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_file():
        return candidate
    return None


def mount_frontend(app: FastAPI, *, ui_dir: Path | str | None = None) -> None:
    """Attach SPA asset + HTML fallback routes when a frontend build is present."""
    root = resolve_ui_dir(ui_dir)
    if root is None:
        return

    assets_dir = root / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="offline_rag_ui_assets",
        )

    index_path = root / "index.html"

    @app.get("/")
    async def spa_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if _is_reserved_api_path(full_path):
            # Unknown API/docs paths must remain backend 404s, not SPA HTML.
            raise HTTPException(status_code=404, detail="Not Found")

        exact = _safe_file_under(root, full_path)
        if exact is not None:
            return FileResponse(exact)

        # Client-side routes (e.g. /workspaces/{id}) serve the SPA shell.
        return FileResponse(index_path)
