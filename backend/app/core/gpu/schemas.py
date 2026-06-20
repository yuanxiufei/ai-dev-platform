"""
GPU data schemas — device info, memory, utilization, and allocation records.

Mirrors GPUStack's gpustack/schemas/workers.py GPU device model.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GPUVendor(str, Enum):
    """GPU manufacturer."""
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    HUAWEI_ASCEND = "ascend"
    HYGON = "hygon"
    MOORE_THREADS = "moore_threads"
    UNKNOWN = "unknown"


class GPUBackend(str, Enum):
    """GPU runtime backend."""
    CUDA = "cuda"
    ROCM = "rocm"
    CANN = "cann"
    ONEAPI = "oneapi"
    METAL = "metal"
    VULKAN = "vulkan"
    OPENCL = "opencl"
    CPU = "cpu"
    UNKNOWN = "unknown"

    @classmethod
    def from_vendor(cls, vendor: GPUVendor) -> "GPUBackend":
        """Map vendor to its primary backend."""
        mapping = {
            GPUVendor.NVIDIA: cls.CUDA,
            GPUVendor.AMD: cls.ROCM,
            GPUVendor.INTEL: cls.ONEAPI,
            GPUVendor.APPLE: cls.METAL,
            GPUVendor.HUAWEI_ASCEND: cls.CANN,
            GPUVendor.HYGON: cls.ROCM,
            GPUVendor.MOORE_THREADS: cls.CUDA,
        }
        return mapping.get(vendor, cls.UNKNOWN)


class GPUAllocationStatus(str, Enum):
    """Status of a GPU memory allocation."""
    PENDING = "pending"
    ALLOCATED = "allocated"
    FAILED = "failed"
    RELEASED = "released"


@dataclass
class GPUMemoryInfo:
    """GPU memory information (bytes)."""
    total_mb: int = 0
    used_mb: int = 0
    free_mb: int = 0
    is_unified_memory: bool = False  # Apple M-series unified memory

    @property
    def total_bytes(self) -> int:
        return self.total_mb * 1024 * 1024

    @property
    def used_bytes(self) -> int:
        return self.used_mb * 1024 * 1024

    @property
    def free_bytes(self) -> int:
        return self.free_mb * 1024 * 1024

    @property
    def utilization_pct(self) -> float:
        if self.total_mb == 0:
            return 0.0
        return round(self.used_mb / self.total_mb * 100, 1)


@dataclass
class GPUUtilizationInfo:
    """GPU core utilization."""
    gpu_util_pct: float = 0.0   # GPU core utilization %
    memory_util_pct: float = 0.0  # Memory bandwidth utilization %
    temperature_c: float = 0.0   # Temperature in Celsius
    power_w: float = 0.0        # Power draw in Watts
    power_limit_w: float = 0.0  # Power limit in Watts


@dataclass
class GPUDeviceInfo:
    """Complete GPU device information.

    Mirrors GPUStack's GPUDeviceInfo in schemas/workers.py.
    """
    index: int = 0
    name: str = ""
    uuid: str = ""
    vendor: GPUVendor = GPUVendor.UNKNOWN
    backend: GPUBackend = GPUBackend.UNKNOWN
    driver_version: str = ""
    runtime_version: str = ""         # e.g., "CUDA 12.4"
    compute_capability: str = ""      # e.g., "8.0" for Ampere
    architecture: str = ""           # e.g., "Ampere", "RDNA3"
    memory: GPUMemoryInfo = field(default_factory=GPUMemoryInfo)
    utilization: GPUUtilizationInfo = field(default_factory=GPUUtilizationInfo)
    is_available: bool = True
    pci_bus_id: str = ""
    numa_node: int = -1

    @property
    def can_fit_model(self, model_size_mb: int, safety_margin_mb: int = 512) -> bool:
        """Check if this GPU has enough free memory for a model."""
        return self.memory.free_mb >= (model_size_mb + safety_margin_mb)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "uuid": self.uuid,
            "vendor": self.vendor.value,
            "backend": self.backend.value,
            "driver_version": self.driver_version,
            "runtime_version": self.runtime_version,
            "compute_capability": self.compute_capability,
            "architecture": self.architecture,
            "memory_total_mb": self.memory.total_mb,
            "memory_used_mb": self.memory.used_mb,
            "memory_free_mb": self.memory.free_mb,
            "memory_utilization_pct": self.memory.utilization_pct,
            "gpu_utilization_pct": self.utilization.gpu_util_pct,
            "temperature_c": self.utilization.temperature_c,
            "power_w": self.utilization.power_w,
            "is_available": self.is_available,
            "pci_bus_id": self.pci_bus_id,
            "numa_node": self.numa_node,
        }


@dataclass
class GPUAllocation:
    """Record of a GPU memory allocation for a model instance."""
    allocation_id: str
    gpu_uuid: str
    gpu_index: int
    model_name: str
    requested_mb: int
    allocated_mb: int
    status: GPUAllocationStatus = GPUAllocationStatus.PENDING
    created_at: float = 0.0
    released_at: float | None = None
