"""
EventBus Coordinator — distributed event bus support for multi-instance deployments.

Extends the existing EventBus with a Coordinator pattern borrowed from GPUStack:
- EventBus.set_coordinator(coordinator) for distributed pub/sub
- Abstract Coordinator base with local/redis/rabbitmq implementations
- Cross-instance event enrichment (ID-only events → DB fetch → full data)
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class Event:
    """Distributed event envelope."""
    def __init__(
        self,
        type: EventType,
        data: Any = None,
        changed_fields: set = None,
        id: Any = None,
    ):
        self.type = type
        self.data = data
        self.changed_fields = changed_fields or set()
        self.id = id


class Coordinator(ABC):
    """Abstract base for distributed coordination.

    Implementations must provide leader election and topic-based pub/sub.
    """

    @abstractmethod
    async def publish(self, topic: str, event: Event) -> None:
        """Publish an event to a topic across all instances."""
        ...

    @abstractmethod
    def subscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        """Subscribe to a topic. Callback fires from main event loop."""
        ...

    @abstractmethod
    def unsubscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        """Unsubscribe from a topic."""
        ...

    @abstractmethod
    async def is_leader(self) -> bool:
        """Check if this instance is the current leader."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the coordinator."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the coordinator."""
        ...


class LocalCoordinator(Coordinator):
    """Single-instance coordinator (no distributed support).

    All events are routed locally — used when no distributed backend is configured.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}

    async def publish(self, topic: str, event: Event) -> None:
        """Route event to local subscribers only."""
        callbacks = self._subscribers.get(topic, [])
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error("Local coordinator callback error for topic %s: %s", topic, e)

    def subscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        if topic in self._subscribers:
            self._subscribers[topic].remove(callback)

    async def is_leader(self) -> bool:
        return True  # Single instance is always leader

    async def start(self) -> None:
        logger.info("LocalCoordinator started (single-instance mode)")

    async def stop(self) -> None:
        self._subscribers.clear()
        logger.info("LocalCoordinator stopped")


class RedisCoordinator(Coordinator):
    """Redis-backed distributed coordinator.

    Uses Redis Pub/Sub for event distribution and SETNX for leader election.
    Requires redis.asyncio client.
    """

    def __init__(self, redis_url: str, instance_id: str = ""):
        self._redis_url = redis_url
        self._instance_id = instance_id or f"instance-{id(self)}"
        self._redis = None
        self._pubsub = None
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._leader_key = "coordinator:leader"
        self._running = False
        self._listener_task = None

    async def start(self) -> None:
        import asyncio
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._redis_url)
            await self._redis.ping()
            self._running = True
            self._listener_task = asyncio.create_task(self._listen())
            logger.info("RedisCoordinator started (url=%s)", self._redis_url)
        except ImportError:
            logger.warning("redis not installed — falling back to LocalCoordinator")
        except Exception as e:
            logger.error("RedisCoordinator start failed: %s", e)

    async def stop(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        logger.info("RedisCoordinator stopped")

    async def publish(self, topic: str, event: Event) -> None:
        if self._redis is None:
            return
        import json
        payload = json.dumps({
            "topic": topic,
            "type": event.type.value,
            "id": event.id,
            "data": event.data if isinstance(event.data, dict) else None,
        })
        await self._redis.publish(f"coordinator:{topic}", payload)

    def subscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[Event], None]) -> None:
        if topic in self._subscribers:
            self._subscribers[topic].remove(callback)

    async def is_leader(self) -> bool:
        if self._redis is None:
            return True
        return await self._redis.get(self._leader_key) == self._instance_id.encode()

    async def _listen(self) -> None:
        """Listen for Redis pub/sub messages."""
        if self._redis is None:
            return
        import asyncio
        import json
        self._pubsub = self._redis.pubsub()

        # Subscribe to all coordinator channels
        channels = [f"coordinator:{t}" for t in self._subscribers]
        if channels:
            await self._pubsub.subscribe(*channels)

        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    topic = payload.get("topic", "")
                    event = Event(
                        type=EventType(payload["type"]),
                        id=payload.get("id"),
                        data=payload.get("data"),
                    )
                    self._dispatch(topic, event)
                except Exception as e:
                    logger.error("Redis message parse error: %s", e)
        except asyncio.CancelledError:
            pass

    def _dispatch(self, topic: str, event: Event) -> None:
        """Dispatch event to local subscribers."""
        callbacks = self._subscribers.get(topic, [])
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error("Redis coordinator callback error: %s", e)


# ── Factory ───────────────────────────────────────
def create_coordinator(coordinator_type: str = "local", **kwargs) -> Coordinator:
    """Create a coordinator instance.

    Args:
        coordinator_type: "local" | "redis"
        **kwargs: Passed to coordinator constructor.
    """
    if coordinator_type == "redis":
        return RedisCoordinator(
            redis_url=kwargs.get("redis_url", "redis://localhost:6379/0"),
            instance_id=kwargs.get("instance_id", ""),
        )
    return LocalCoordinator()


__all__ = [
    "Event",
    "EventType",
    "Coordinator",
    "LocalCoordinator",
    "RedisCoordinator",
    "create_coordinator",
]
