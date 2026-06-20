"""
Resource Collector — periodic system + GPU resource collection with history.

Borrows from GPUStack's worker/collector.py WorkerStatusCollector pattern.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.core.resources.system_load import SystemLoad, collect_system_load
from app.core.gpu.schemas import GPUDeviceInfo

logger = logging.getLogger(__name__)


@dataclass
class ResourceSnapshot:
    """A point-in-time snapshot of all system resources."""
    timestamp: float = field(default_factory=time.time)
    system: Optional[SystemLoad] = None
    gpus: list[GPUDeviceInfo] = field(default_factory=list)


class ResourceCollector:
    """Periodically collects system + GPU resource snapshots.

    Maintains a rolling window of history for trend analysis and alerting.
    """

    def __init__(self, interval_seconds: float = 10.0, max_history: int = 360):
        """
        Args:
            interval_seconds: Collection interval in seconds (default 10s).
            max_history: Max snapshots to retain (360 × 10s = 1 hour).
        """
        self.interval_seconds = interval_seconds
        self.max_history = max_history
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._snapshots: list[ResourceSnapshot] = []

    # ── Lifecycle ─────────────────────────────────
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._collect_loop())
        logger.info("ResourceCollector started (interval=%ss, max_history=%d)",
                     self.interval_seconds, self.max_history)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ResourceCollector stopped")

    # ── Snapshot access ───────────────────────────
    @property
    def latest(self) -> Optional[ResourceSnapshot]:
        return self._snapshots[-1] if self._snapshots else None

    def history(self, count: int = 60) -> list[ResourceSnapshot]:
        return self._snapshots[-count:] if self._snapshots else []

    def history_since(self, since_ts: float) -> list[ResourceSnapshot]:
        return [s for s in self._snapshots if s.timestamp >= since_ts]

    # ── Internal ──────────────────────────────────
    async def _collect_loop(self) -> None:
        while self._running:
            try:
                snapshot = await self._collect()
                self._snapshots.append(snapshot)
                if len(self._snapshots) > self.max_history:
                    self._snapshots = self._snapshots[-self.max_history:]
            except Exception as e:
                logger.error("ResourceCollector error: %s", e)
            await asyncio.sleep(self.interval_seconds)

    async def _collect(self) -> ResourceSnapshot:
        loop = asyncio.get_event_loop()
        system = await loop.run_in_executor(None, collect_system_load)

        gpus: list[GPUDeviceInfo] = []
        try:
            from app.core.gpu.detector import GPUDetector
            detector = GPUDetector()
            gpus = await loop.run_in_executor(None, detector.detect_all)
        except Exception as e:
            logger.debug("GPU detection in collector: %s", e)

        return ResourceSnapshot(system=system, gpus=gpus)


# ── Global singleton ──────────────────────────────
_resource_collector: Optional[ResourceCollector] = None


def init_resource_collector(interval_seconds: float = 10.0) -> ResourceCollector:
    global _resource_collector
    if _resource_collector is None:
        _resource_collector = ResourceCollector(interval_seconds=interval_seconds)
    return _resource_collector


def get_resource_collector() -> Optional[ResourceCollector]:
    return _resource_collector
