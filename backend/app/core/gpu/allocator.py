"""
GPU Memory Allocator — allocate GPU VRAM for model loading.

Borrows from GPUStack scheduler/scheduler.py resource-fit selection patterns:
- CPUComputeSelector
- GPUComputeSelector
- ResourceFitSelector (GGUF/VLLM)

Supports multiple allocation strategies: first-fit, best-fit, and pinned.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from app.core.gpu.detector import GPUDetector
from app.core.gpu.schemas import (
    GPUDeviceInfo,
    GPUAllocation,
    GPUAllocationStatus,
    GPUVendor,
)

logger = logging.getLogger(__name__)


@dataclass
class _Slot:
    """Internal allocation slot tracking."""
    gpu_index: int
    gpu_uuid: str
    offset_mb: int
    size_mb: int
    allocation_id: str


class GPUAllocator:
    """Manages GPU memory allocation across detected devices."""

    def __init__(self):
        self._detector = GPUDetector()
        self._allocations: dict[str, GPUAllocation] = {}
        self._gpu_slots: dict[int, list[_Slot]] = {}  # gpu_index → allocated slots
        self._gpu_devices: list[GPUDeviceInfo] = []

    def refresh_devices(self) -> list[GPUDeviceInfo]:
        """Re-detect GPUs and refresh internal state."""
        self._gpu_devices = self._detector.detect_all()
        return self._gpu_devices

    @property
    def devices(self) -> list[GPUDeviceInfo]:
        if not self._gpu_devices:
            self.refresh_devices()
        return self._gpu_devices

    @property
    def total_gpu_count(self) -> int:
        return len(self.devices)

    @property
    def total_vram_mb(self) -> int:
        return sum(d.memory.total_mb for d in self.devices)

    @property
    def free_vram_mb(self) -> int:
        return sum(d.memory.free_mb for d in self.devices)

    # ── Allocation strategies ─────────────────────
    def allocate_first_fit(self, model_name: str, required_mb: int) -> Optional[GPUAllocation]:
        """Allocate on the first GPU with enough free memory (first-fit)."""
        for device in self.devices:
            if not device.is_available:
                continue
            if device.can_fit_model(required_mb):
                return self._allocate_on_gpu(device, model_name, required_mb)
        return None

    def allocate_best_fit(self, model_name: str, required_mb: int) -> Optional[GPUAllocation]:
        """Allocate on the GPU with the smallest sufficient free memory (best-fit)."""
        best: Optional[GPUDeviceInfo] = None
        best_free = float("inf")
        for device in self.devices:
            if not device.is_available:
                continue
            free = device.memory.free_mb
            if free >= required_mb + 512 and free < best_free:
                best = device
                best_free = free
        if best:
            return self._allocate_on_gpu(best, model_name, required_mb)
        # Fallback to first-fit
        return self.allocate_first_fit(model_name, required_mb)

    def allocate_multi_gpu(self, model_name: str, total_mb: int, max_gpus: int = 4) -> Optional[list[GPUAllocation]]:
        """Split a model across multiple GPUs (e.g., for tensor parallelism)."""
        available = [d for d in self.devices if d.is_available]
        if len(available) < 1:
            return None
        allocations: list[GPUAllocation] = []
        remaining = total_mb
        gpu_count = min(max_gpus, len(available))

        per_gpu_mb = total_mb // gpu_count
        for i in range(gpu_count):
            device = available[i]
            alloc_mb = min(per_gpu_mb if i < gpu_count - 1 else remaining, device.memory.free_mb - 512)
            if alloc_mb <= 0:
                self._release_list(allocations)
                return None
            alloc = self._allocate_on_gpu(device, f"{model_name}_shard{i}", alloc_mb)
            if alloc is None:
                self._release_list(allocations)
                return None
            allocations.append(alloc)
            remaining -= alloc_mb
        return allocations

    def allocate_cpu_fallback(self, model_name: str, required_mb: int) -> GPUAllocation:
        """Create a CPU-only allocation (always succeeds)."""
        import time
        alloc_id = f"cpu-{uuid.uuid4().hex[:8]}"
        alloc = GPUAllocation(
            allocation_id=alloc_id,
            gpu_uuid="cpu-fallback",
            gpu_index=-1,
            model_name=model_name,
            requested_mb=required_mb,
            allocated_mb=0,
            status=GPUAllocationStatus.ALLOCATED,
            created_at=time.time(),
        )
        self._allocations[alloc_id] = alloc
        logger.info("CPU fallback allocation: %s (%d MB)", model_name, required_mb)
        return alloc

    def release(self, allocation_id: str) -> bool:
        """Release a GPU allocation."""
        import time
        alloc = self._allocations.get(allocation_id)
        if not alloc:
            return False
        alloc.status = GPUAllocationStatus.RELEASED
        alloc.released_at = time.time()
        # Clear slot tracking
        for idx, slots in self._gpu_slots.items():
            self._gpu_slots[idx] = [s for s in slots if s.allocation_id != allocation_id]
        logger.info("Released GPU allocation: %s (GPU %d, %d MB)",
                     allocation_id, alloc.gpu_index, alloc.allocated_mb)
        return True

    def get_allocation(self, allocation_id: str) -> Optional[GPUAllocation]:
        return self._allocations.get(allocation_id)

    def list_allocations(self) -> list[GPUAllocation]:
        return list(self._allocations.values())

    def list_active_allocations(self) -> list[GPUAllocation]:
        return [a for a in self._allocations.values() if a.status == GPUAllocationStatus.ALLOCATED]

    # ── Internal ──────────────────────────────────
    def _allocate_on_gpu(self, device: GPUDeviceInfo, model_name: str, required_mb: int) -> Optional[GPUAllocation]:
        import time
        alloc_id = f"gpu{uuid.uuid4().hex[:8]}"
        alloc = GPUAllocation(
            allocation_id=alloc_id,
            gpu_uuid=device.uuid,
            gpu_index=device.index,
            model_name=model_name,
            requested_mb=required_mb,
            allocated_mb=required_mb,
            status=GPUAllocationStatus.ALLOCATED,
            created_at=time.time(),
        )
        self._allocations[alloc_id] = alloc
        if device.index not in self._gpu_slots:
            self._gpu_slots[device.index] = []
        self._gpu_slots[device.index].append(_Slot(
            gpu_index=device.index,
            gpu_uuid=device.uuid,
            offset_mb=0,
            size_mb=required_mb,
            allocation_id=alloc_id,
        ))
        logger.info("GPU allocation: %s → GPU %d (%s), %d MB",
                     model_name, device.index, device.name, required_mb)
        return alloc

    def _release_list(self, allocations: list[GPUAllocation]) -> None:
        for a in allocations:
            self.release(a.allocation_id)


# ── Model VRAM estimation ─────────────────────────
# Rough estimates: 1B parameters ≈ 2GB in FP16, 4GB in FP32
_ESTIMATES = {
    "fp16": 2.0,    # GB per billion params
    "fp32": 4.0,
    "int8": 1.0,
    "int4": 0.5,
    "gguf_q4": 0.55,
    "gguf_q8": 0.95,
}


def estimate_model_vram(
    param_count_billions: float,
    precision: str = "fp16",
    context_length: int = 4096,
    overhead_pct: float = 0.20,  # 20% KV cache + framework overhead
) -> int:
    """Estimate VRAM required for a model in MB.

    Args:
        param_count_billions: Model parameter count in billions (e.g., 7 for 7B).
        precision: Quantization precision (fp16/fp32/int8/int4/gguf_q4/gguf_q8).
        context_length: Max context length for KV cache estimation.
        overhead_pct: Overhead factor for framework + activations.

    Returns:
        Estimated VRAM in MB.
    """
    gb_per_b = _ESTIMATES.get(precision, 2.0)
    param_vram_gb = param_count_billions * gb_per_b
    # KV cache: ~2 bytes per param per token for attention
    kv_cache_gb = (param_count_billions * 2 * context_length) / (1024**3) * 0.1
    total_gb = (param_vram_gb + kv_cache_gb) * (1 + overhead_pct)
    return int(total_gb * 1024)
