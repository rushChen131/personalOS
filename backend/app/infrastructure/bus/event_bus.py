from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import logger

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """In-process event bus.

    Local dev uses the in-memory implementation so no Redis is required.
    Production keeps the same publish/subscribe API and swaps the transport
    (see ``RedisEventBus``) without touching services.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, event_type: str, handler: Handler) -> None:
        async with self._lock:
            self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: Handler) -> None:
        async with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.info("bus.publish", event_type=event_type, payload_keys=list(payload.keys()))
        await self._dispatch(event_type, payload)

    async def _dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            handlers = list(self._handlers.get(event_type, []))
        for handler in handlers:
            try:
                await handler(payload)
            except Exception as exc:  # a failing handler must not break the publisher
                logger.error("bus.handler.failed", event_type=event_type, error=str(exc))

    def subscriber_count(self, event_type: str) -> int:
        return len(self._handlers.get(event_type, []))


class RedisEventBus(EventBus):
    """Redis pub/sub transport for multi-process deployments.

    Falls back to in-process dispatch when Redis is unreachable so the API keeps
    working during local development. The subscriber loop reconnects with
    exponential backoff: a transient Redis restart must never permanently
    silence event delivery for the process.
    """

    #: Backoff bounds for the subscriber reconnect loop (seconds).
    RECONNECT_MIN_DELAY = 0.5
    RECONNECT_MAX_DELAY = 30.0

    def __init__(self, redis_url: str, channel: str = "personalos.events") -> None:
        super().__init__()
        self.redis_url = redis_url
        self.channel = channel
        self._redis: Any = None
        self._pubsub_task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._pubsub_task is not None:
            return
        self._stopping = False
        if not await self._connect():
            # Redis unavailable at boot: keep serving via in-process dispatch.
            return
        self._pubsub_task = asyncio.create_task(self._listen_forever())

    async def _connect(self) -> bool:
        try:
            import redis.asyncio as aioredis
        except ImportError:  # pragma: no cover - redis is an optional extra
            logger.warning("bus.redis.unavailable", reason="redis package missing")
            return False
        try:
            client = aioredis.from_url(self.redis_url, decode_responses=True)
            await client.ping()
        except Exception as exc:  # pragma: no cover - depends on a live server
            logger.warning("bus.redis.unavailable", error=str(exc))
            return False
        self._redis = client
        return True

    async def _listen_forever(self) -> None:  # pragma: no cover - requires Redis
        """Keep a subscription alive, reconnecting with backoff on failure."""
        delay = self.RECONNECT_MIN_DELAY
        while not self._stopping:
            try:
                await self._listen()
                # A clean return means the stream ended; loop to resubscribe.
                delay = self.RECONNECT_MIN_DELAY
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stopping:
                    return
                logger.warning("bus.redis.listen_failed", error=str(exc), retry_in=delay)
                await asyncio.sleep(delay)
                delay = min(self.RECONNECT_MAX_DELAY, delay * 2)
                # Drop the dead client so _connect() rebuilds it.
                await self._drop_client()
                if not await self._connect():
                    continue

    async def _drop_client(self) -> None:
        client, self._redis = self._redis, None
        if client is not None:
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001 - closing a broken client is best-effort
                pass

    async def _listen(self) -> None:  # pragma: no cover - requires Redis
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    envelope = json.loads(message["data"])
                except (TypeError, json.JSONDecodeError):
                    continue
                await self._dispatch(envelope.get("event_type", ""), envelope.get("payload", {}))
        finally:
            try:
                await pubsub.unsubscribe(self.channel)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.info("bus.publish", event_type=event_type, payload_keys=list(payload.keys()))
        if self._redis is not None:
            try:
                await self._redis.publish(
                    self.channel, json.dumps({"event_type": event_type, "payload": payload})
                )
                return
            except Exception as exc:  # pragma: no cover - transient Redis failure
                logger.warning("bus.redis.publish_failed", error=str(exc))
        await self._dispatch(event_type, payload)

    async def stop(self) -> None:
        self._stopping = True
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._pubsub_task = None
        await self._drop_client()


event_bus = EventBus()
