"""Lightweight job queue notification layer.

The database remains the source of truth for job state. Redis Streams are used
as a fast notification channel so workers do not have to poll the database.
If Redis is unavailable, callers fall back to database polling automatically.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis

from backend.config import settings

logger = logging.getLogger("roadwatch.queue")
STREAM_KEY = "roadwatch:jobs"
GROUP = "workers"
_redis: "redis.Redis | None" = None


def get_redis():
    global _redis
    if _redis is not None:
        return _redis
    if not settings.redis_url:
        return None
    try:
        import redis
        client = redis.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        client.ping()
        try:
            client.xgroup_create(STREAM_KEY, GROUP, mkstream=True)
        except Exception:
            pass  # group may already exist
        _redis = client
        logger.info("Redis queue connected: %s", settings.redis_url)
        return client
    except Exception as exc:
        logger.warning("Redis unavailable, falling back to DB polling: %s", exc)
        _redis = False
        return None


def enqueue(job_id: str) -> None:
    """Notify workers that a new job is available. Never raises."""
    client = get_redis()
    if not client:
        return
    try:
        client.xadd(STREAM_KEY, {"job_id": job_id}, maxlen=10000)
    except Exception as exc:
        logger.warning("xadd failed: %s", exc)


def wait_for_job(timeout: int = 5) -> bool:
    """Block up to `timeout` seconds for a new job notification.

    Returns True if a notification arrived (the worker must still claim from
    the DB). Returns False on timeout or when Redis is unavailable.
    """
    client = get_redis()
    if not client:
        return False
    try:
        result = client.xreadgroup(
            GROUP, "worker", {STREAM_KEY: ">"}, count=1, block=timeout * 1000,
        )
        return bool(result)
    except Exception as exc:
        logger.warning("xreadgroup failed: %s", exc)
        return False
