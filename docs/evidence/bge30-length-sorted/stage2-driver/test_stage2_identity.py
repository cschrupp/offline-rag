import asyncio
import json

from stage2_identity import Stage2IdentityMiddleware


def test_identity_middleware_serves_json_before_spa_fallback():
    fallback_called = False
    messages = []

    async def app(_scope, _receive, _send):
        nonlocal fallback_called
        fallback_called = True

    async def send(message):
        messages.append(message)

    middleware = Stage2IdentityMiddleware(
        app,
        identity_provider=lambda: {"mode": "native", "runtime_ready": True},
    )
    asyncio.run(
        middleware(
            {"type": "http", "method": "GET", "path": "/__stage2/identity"},
            lambda: None,
            send,
        )
    )

    assert fallback_called is False
    assert messages[0]["status"] == 200
    assert dict(messages[0]["headers"])[b"content-type"] == b"application/json"
    assert json.loads(messages[1]["body"]) == {
        "mode": "native",
        "runtime_ready": True,
    }


def test_identity_middleware_passes_other_paths_through():
    called = False

    async def app(_scope, _receive, _send):
        nonlocal called
        called = True

    middleware = Stage2IdentityMiddleware(app, identity_provider=dict)
    asyncio.run(
        middleware(
            {"type": "http", "method": "GET", "path": "/health/ready"},
            lambda: None,
            lambda _message: None,
        )
    )
    assert called is True
