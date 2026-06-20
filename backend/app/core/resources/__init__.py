"""
Resources module — system resource monitoring (CPU, memory, disk, network, GPU).
"""

from app.core.resources.system_load import (
    CPULoad,
    MemoryLoad,
    DiskLoad,
    NetworkLoad,
    SystemLoad,
    collect_cpu_load,
    collect_memory_load,
    collect_disk_load,
    collect_network_load,
    collect_system_load,
)
from app.core.resources.hardware import (
    CPUInfo,
    MemoryInfo,
    SystemInfo,
    detect_system_info,
    detect_cpu,
    detect_memory,
)
from app.core.resources.collector import (
    ResourceSnapshot,
    ResourceCollector,
    init_resource_collector,
    get_resource_collector,
)

__all__ = [
    # System load
    "CPULoad",
    "MemoryLoad",
    "DiskLoad",
    "NetworkLoad",
    "SystemLoad",
    "collect_cpu_load",
    "collect_memory_load",
    "collect_disk_load",
    "collect_network_load",
    "collect_system_load",
    # Hardware
    "CPUInfo",
    "MemoryInfo",
    "SystemInfo",
    "detect_system_info",
    "detect_cpu",
    "detect_memory",
    # Collector
    "ResourceSnapshot",
    "ResourceCollector",
    "init_resource_collector",
    "get_resource_collector",
]
