"""
System resource monitoring — CPU, memory, disk, network load collection.

Borrows patterns from GPUStack's server/system_load.py and worker/collector.py.
"""

import logging
import os
import platform
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CPULoad:
    """CPU load information."""
    physical_cores: int = 0
    logical_cores: int = 0
    utilization_pct: float = 0.0    # Overall CPU usage %
    per_core_pct: list[float] = field(default_factory=list)
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0
    model_name: str = ""


@dataclass
class MemoryLoad:
    """Memory usage information (all in MB)."""
    total_mb: int = 0
    available_mb: int = 0
    used_mb: int = 0
    free_mb: int = 0
    utilization_pct: float = 0.0
    swap_total_mb: int = 0
    swap_used_mb: int = 0
    swap_free_mb: int = 0


@dataclass
class DiskLoad:
    """Disk usage per mount point."""
    mount_point: str = ""
    device: str = ""
    fstype: str = ""
    total_gb: float = 0.0
    used_gb: float = 0.0
    free_gb: float = 0.0
    utilization_pct: float = 0.0


@dataclass
class NetworkLoad:
    """Network I/O stats."""
    interface: str = ""
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    errors_in: int = 0
    errors_out: int = 0


@dataclass
class SystemLoad:
    """Complete system resource snapshot."""
    cpu: CPULoad = field(default_factory=CPULoad)
    memory: MemoryLoad = field(default_factory=MemoryLoad)
    disks: list[DiskLoad] = field(default_factory=list)
    networks: list[NetworkLoad] = field(default_factory=list)
    uptime_seconds: float = 0.0
    hostname: str = ""
    os_name: str = ""
    kernel_version: str = ""


# ── Collectors ────────────────────────────────────

def collect_cpu_load() -> CPULoad:
    """Collect CPU load information."""
    load = CPULoad()
    try:
        import psutil

        load.physical_cores = psutil.cpu_count(logical=False) or 0
        load.logical_cores = psutil.cpu_count(logical=True) or 0
        load.utilization_pct = psutil.cpu_percent(interval=0.1)
        load.per_core_pct = psutil.cpu_percent(interval=0.1, percpu=True) or []

        # Load averages
        if hasattr(os, "getloadavg"):
            avg = os.getloadavg()
            load.load_avg_1m, load.load_avg_5m, load.load_avg_15m = avg

        # CPU model name
        if platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            load.model_name = line.split(":", 1)[-1].strip()
                            break
            except Exception:
                pass
        elif platform.system() == "Darwin":
            import subprocess
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=3,
                )
                load.model_name = result.stdout.strip()
            except Exception:
                pass
    except ImportError:
        logger.debug("psutil not available — CPU stats limited")
    except Exception as e:
        logger.warning("CPU load collection error: %s", e)
    return load


def collect_memory_load() -> MemoryLoad:
    """Collect memory usage."""
    load = MemoryLoad()
    try:
        import psutil

        mem = psutil.virtual_memory()
        load.total_mb = mem.total // (1024 * 1024)
        load.available_mb = mem.available // (1024 * 1024)
        load.used_mb = mem.used // (1024 * 1024)
        load.free_mb = mem.free // (1024 * 1024)
        load.utilization_pct = mem.percent

        swap = psutil.swap_memory()
        load.swap_total_mb = swap.total // (1024 * 1024)
        load.swap_used_mb = swap.used // (1024 * 1024)
        load.swap_free_mb = swap.free // (1024 * 1024)
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Memory load collection error: %s", e)
    return load


def collect_disk_load(mount_points: Optional[list[str]] = None) -> list[DiskLoad]:
    """Collect disk usage for specified or common mount points."""
    disks: list[DiskLoad] = []
    try:
        import psutil

        for part in psutil.disk_partitions():
            if mount_points and part.mountpoint not in mount_points:
                continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(DiskLoad(
                    mount_point=part.mountpoint,
                    device=part.device,
                    fstype=part.fstype,
                    total_gb=round(usage.total / (1024**3), 1),
                    used_gb=round(usage.used / (1024**3), 1),
                    free_gb=round(usage.free / (1024**3), 1),
                    utilization_pct=usage.percent,
                ))
            except PermissionError:
                continue
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Disk load collection error: %s", e)
    return disks


def collect_network_load() -> list[NetworkLoad]:
    """Collect network I/O statistics."""
    networks: list[NetworkLoad] = []
    try:
        import psutil

        counters = psutil.net_io_counters(pernic=True)
        for iface, stats in counters.items():
            if iface == "lo":
                continue
            networks.append(NetworkLoad(
                interface=iface,
                bytes_sent=stats.bytes_sent,
                bytes_recv=stats.bytes_recv,
                packets_sent=stats.packets_sent,
                packets_recv=stats.packets_recv,
                errors_in=stats.errin,
                errors_out=stats.errout,
            ))
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Network load collection error: %s", e)
    return networks


def collect_system_load() -> SystemLoad:
    """Collect full system resource snapshot."""
    import time

    return SystemLoad(
        cpu=collect_cpu_load(),
        memory=collect_memory_load(),
        disks=collect_disk_load(),
        networks=collect_network_load(),
        uptime_seconds=time.time() - _boot_time() if _boot_time() else 0.0,
        hostname=platform.node(),
        os_name=f"{platform.system()} {platform.release()}",
        kernel_version=platform.version(),
    )


def _boot_time() -> float:
    """Get system boot time as epoch."""
    try:
        import psutil
        return psutil.boot_time()
    except Exception:
        return 0.0
