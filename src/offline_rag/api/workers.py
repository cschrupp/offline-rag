"""ASGI worker ownership helpers (Phase 15F / D18).

Cancellation of an await must not release capacity while a worker thread still
runs. Callers always wait for the future to complete before release.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Future

from starlette.requests import Request

from offline_rag.app.operations import CancelReason, OperationHandle


async def run_owned_worker[T](
    *,
    request: Request | None,
    operation: OperationHandle,
    worker: Callable[[], T],
    watch_disconnect: bool,
) -> T:
    """Run ``worker`` in a thread; optionally signal cancel on disconnect.

    Always waits for the worker to terminate before returning/raising, even if
    the surrounding task is cancelled. Does not release capacity.
    """
    loop = asyncio.get_running_loop()
    future: Future[T] = loop.run_in_executor(None, worker)
    stop_watch = asyncio.Event()

    async def _disconnect_watch() -> None:
        if request is None or not watch_disconnect:
            return
        while not stop_watch.is_set() and not future.done():
            try:
                disconnected = await request.is_disconnected()
            except (RuntimeError, AttributeError):
                return
            if disconnected:
                operation.signal_cancel(CancelReason.CLIENT_DISCONNECT)
                return
            try:
                await asyncio.wait_for(stop_watch.wait(), timeout=0.05)
            except TimeoutError:
                continue

    watcher = asyncio.create_task(_disconnect_watch())
    try:
        # Shield so HTTP-task cancellation cannot abandon the worker wait.
        return await asyncio.shield(asyncio.wrap_future(future))
    except asyncio.CancelledError:
        operation.signal_cancel(CancelReason.CLIENT_DISCONNECT)
        if not future.done():
            await asyncio.wrap_future(future)
        raise
    finally:
        stop_watch.set()
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        if not future.done():
            await asyncio.wrap_future(future)
