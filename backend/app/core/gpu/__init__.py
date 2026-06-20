"""
GPU Control Layer — GPU device detection, memory allocation, and real-time monitoring.

Borrows architectural patterns from GPUStack (gpustack/detectors, gpustack/scheduler).
Supports NVIDIA (CUDA), AMD (ROCm), Huawei Ascend (CANN), and CPU fallback.
"""

from app.core.gpu.schemas import (
    GPUDeviceInfo,
    GPUMemoryInfo,
    GPUUtilizationInfo,
    GPUVendor,
    GPUBackend,
    GPUAllocation,
    GPUAllocationStatus,
)
from app.core.gpu.detector import GPUDetector, detect_gpus, detect_system_gpus
from app.core.gpu.allocator import GPUAllocator, estimate_model_vram
from app.core.gpu.monitor import GPUMonitor, GPUAlert, AlertSeverity

# ── Global singletons ────────────────────────────
_gpu_detector: GPUDetector | None = None
_gpu_allocator: GPUAllocator | None = None
_gpu_monitor: GPUMonitor | None = None


def init_gpu_detector() -> GPUDetector:
    """Initialize the global GPU detector singleton."""
    global _gpu_detector
    if _gpu_detector is None:
        _gpu_detector = GPUDetector()
    return _gpu_detector


def get_gpu_detector() -> GPUDetector:
    """Get the global GPU detector singleton."""
    if _gpu_detector is None:
        return init_gpu_detector()
    return _gpu_detector


def init_gpu_allocator() -> GPUAllocator:
    """Initialize the global GPU allocator singleton."""
    global _gpu_allocator
    if _gpu_allocator is None:
        _gpu_allocator = GPUAllocator()
    return _gpu_allocator


def get_gpu_allocator() -> GPUAllocator:
    """Get the global GPU allocator singleton."""
    if _gpu_allocator is None:
        return init_gpu_allocator()
    return _gpu_allocator


def init_gpu_monitor(interval_seconds: float = 5.0) -> GPUMonitor:
    """Initialize the global GPU monitor singleton."""
    global _gpu_monitor
    if _gpu_monitor is None:
        _gpu_monitor = GPUMonitor(interval_seconds=interval_seconds)
    return _gpu_monitor


def get_gpu_monitor() -> GPUMonitor | None:
    """Get the global GPU monitor singleton (may be None if not initialized)."""
    return _gpu_monitor


__all__ = [
    # Schemas
    "GPUDeviceInfo",
    "GPUMemoryInfo",
    "GPUUtilizationInfo",
    "GPUVendor",
    "GPUBackend",
    "GPUAllocation",
    "GPUAllocationStatus",
    # Detector
    "GPUDetector",
    "detect_gpus",
    "detect_system_gpus",
    # Allocator
    "GPUAllocator",
    "estimate_model_vram",
    # Monitor
    "GPUMonitor",
    "GPUAlert",
    "AlertSeverity",
    # Singletons
    "init_gpu_detector",
    "get_gpu_detector",
    "init_gpu_allocator",
    "get_gpu_allocator",
    "init_gpu_monitor",
    "get_gpu_monitor",
]
