"""WebSocket hub for real-time event notifications."""
from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("roadwatch.ws")
_clients: set[asyncio.Queue] = set()
_lock = asyncio.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop):
    global _loop
    _loop = loop


async def subscribe(queue: asyncio.Queue):
    async with _lock:
        _clients.add(queue)


async def unsubscribe(queue: asyncio.Queue):
    async with _lock:
        _clients.discard(queue)


async def broadcast(event: dict):
    """Push a serializable event to all connected clients."""
    if not _clients:
        return
    payload = json.dumps(event, ensure_ascii=False)
    async with _lock:
        dead = []
        for queue in list(_clients):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            _clients.discard(queue)


def broadcast_event(event: dict):
    """Synchronous entry point for non-async code (e.g. add_event)."""
    if _loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(broadcast(event), _loop)
    except Exception as exc:
        logger.warning("ws broadcast failed: %s", exc)
