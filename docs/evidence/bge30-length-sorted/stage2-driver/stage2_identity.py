"""Expose diagnostic identity before the packaged SPA fallback route."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class Stage2IdentityMiddleware:
    """Serve the private diagnostic identity path ahead of app routes."""

    def __init__(self, app, *, identity_provider: Callable[[], dict[str, Any]]):
        self.app = app
        self.identity_provider = identity_provider

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/__stage2/identity":
            body = json.dumps(
                self.identity_provider(), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
