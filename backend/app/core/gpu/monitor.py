"""
GPU Monitor — real-time GPU health, utilization tracking, and alerting.

Borrows patterns from GPUStack server/system_load.py and metrics_collector.py.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from app.core.gpu.detector import GPUDetector
from app.core.gpu.schemas import GPUDeviceInfo

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class GPUAlert:
    severity: AlertSeverity
    gpu_index: int
    gpu_name: str
    message: str
    metric: str
    value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class GPUSnapshot:
    """A point-in-time GPU state snapshot."""
    devices: list[GPUDeviceInfo]
    timestamp: float = field(default_factory=time.time)


class GPUMonitor:
    """Periodic GPU monitoring with configurable alert thresholds."""

    def __init__(
        self,
        interval_seconds: float = 5.0,
        temp_warning_c: float = 80.0,
        temp_critical_c: float = 90.0,
        mem_warning_pct: float = 85.0,
        mem_critical_pct: float = 95.0,
        gpu_util_idle_pct: float = 5.0,
    ):
        self.interval_seconds = interval_seconds
        self.temp_warning_c = temp_warning_c
        self.temp_critical_c = temp_critical_c
        self.mem_warning_pct = mem_warning_pct
        self.mem_critical_pct = mem_critical_pct
        self.gpu_util_idle_pct = gpu_util_idle_pct

        self._detector = GPUDetector()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._snapshots: list[GPUSnapshot] = []
        self._alert_callbacks: list[Callable[[GPUAlert], None]] = []
        self._max_snapshots = 120  # Keep 10 minutes at 5s interval

    # ── Lifecycle ─────────────────────────────────
    async def start(self) -> None:
        """Start the periodic monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("GPU Monitor started (interval=%ss)", self.interval_seconds)

    async def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("GPU Monitor stopped")

    def on_alert(self, callback: Callable[[GPUAlert], None]) -> None:
        """Register an alert callback."""
        self._alert_callbacks.append(callback)

    # ── Snapshot access ───────────────────────────
    @property
    def latest_snapshot(self) -> Optional[GPUSnapshot]:
        return self._snapshots[-1] if self._snapshots else None

    @property
    def devices(self) -> list[GPUDeviceInfo]:
        snap = self.latest_snapshot
        return snap.devices if snap else []

    def get_history(self, count: int = 20) -> list[GPUSnapshot]:
        return self._snapshots[-count:] if self._snapshots else []

    # ── Internal loop ─────────────────────────────
    async def _monitor_loop(self) -> None:
        while self._running:
            try:
                snapshot = await self._collect()
                self._snapshots.append(snapshot)
                if len(self._snapshots) > self._max_snapshots:
                    self._snapshots = self._snapshots[-self._max_snapshots:]
                self._check_alerts(snapshot)
            except Exception as e:
                logger.error("GPU monitor collect error: %s", e)
            await asyncio.sleep(self.interval_seconds)

    async def _collect(self) -> GPUSnapshot:
        """Collect current GPU state (non-blocking)."""
        loop = asyncio.get_event_loop()
        devices = await loop.run_in_executor(None, self._detector.detect_all)
        # Refresh utilization
        refreshed = await loop.run_in_executor(
            None, lambda: [self._detector.refresh_utilization(d) for d in devices]
        )
        return GPUSnapshot(devices=refreshed)

    def _check_alerts(self, snapshot: GPUSnapshot) -> None:
        """Check all devices against alert thresholds."""
        for device in snapshot.devices:
            alerts: list[GPUAlert] = []

            # Temperature
            if device.utilization.temperature_c >= self.temp_critical_c:
                alerts.append(GPUAlert(
                    severity=AlertSeverity.CRITICAL,
                    gpu_index=device.index,
                    gpu_name=device.name,
                    message=f"GPU temperature critical: {device.utilization.temperature_c}°C",
                    metric="temperature",
                    value=device.utilization.temperature_c,
                    threshold=self.temp_critical_c,
                ))
            elif device.utilization.temperature_c >= self.temp_warning_c:
                alerts.append(GPUAlert(
                    severity=AlertSeverity.WARNING,
                    gpu_index=device.index,
                    gpu_name=device.name,
                    message=f"GPU temperature high: {device.utilization.temperature_c}°C",
                    metric="temperature",
                    value=device.utilization.temperature_c,
                    threshold=self.temp_warning_c,
                ))

            # Memory
            if device.memory.utilization_pct >= self.mem_critical_pct:
                alerts.append(GPUAlert(
                    severity=AlertSeverity.CRITICAL,
                    gpu_index=device.index,
                    gpu_name=device.name,
                    message=f"GPU memory critical: {device.memory.utilization_pct}%",
                    metric="memory",
                    value=device.memory.utilization_pct,
                    threshold=self.mem_critical_pct,
                ))
            elif device.memory.utilization_pct >= self.mem_warning_pct:
                alerts.append(GPUAlert(
                    severity=AlertSeverity.WARNING,
                    gpu_index=device.index,
                    gpu_name=device.name,
                    message=f"GPU memory high: {device.memory.utilization_pct}%",
                    metric="memory",
                    value=device.memory.utilization_pct,
                    threshold=self.mem_warning_pct,
                ))

            # Dispatch alerts
            for alert in alerts:
                log_fn = logger.warning if alert.severity == AlertSeverity.WARNING else logger.error
                log_fn("[GPU %d] %s", alert.gpu_index, alert.message)
                for cb in self._alert_callbacks:
                    try:
                        cb(alert)
                    except Exception as e:
                        logger.error("Alert callback error: %s", e)
