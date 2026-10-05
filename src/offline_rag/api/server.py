"""Project-owned ASGI server entrypoint (Slice 15G / D14).

Lifecycle ownership remains ApplicationRuntime via FastAPI lifespan.
This module only loads settings, enforces bind policy, and launches one worker.
"""

from __future__ import annotations

import sys

import uvicorn

from offline_rag.api.app import create_app
from offline_rag.api.bind_policy import BindPolicyError, enforce_bind_policy
from offline_rag.config import load_dotenv, load_settings


def main(argv: list[str] | None = None) -> int:
    """Load config, enforce D14, serve with exactly one Uvicorn worker."""
    del argv  # reserved for future CLI flags; unused in 15G
    load_dotenv()
    settings = load_settings()
    try:
        enforce_bind_policy(
            settings.api.http_host,
            allow_non_loopback=bool(settings.api.allow_non_loopback),
        )
    except BindPolicyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    app = create_app(settings=settings)
    uvicorn.run(
        app,
        host=str(settings.api.http_host),
        port=int(settings.api.http_port),
        workers=1,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
