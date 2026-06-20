"""
Hardware information detector — CPU, GPU, and system hardware profiling.

Borrows from GPUStack's Fastfetch detector pattern.
"""

import logging
import platform
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CPUInfo:
    model_name: str = ""
    physical_cores: int = 0
    logical_cores: int = 0
    max_frequency_mhz: float = 0.0
    architecture: str = ""
    vendor: str = ""
    cache_l1_kb: int = 0
    cache_l2_kb: int = 0
    cache_l3_kb: int = 0
    flags: list[str] = field(default_factory=list)


@dataclass
class MemoryInfo:
    total_mb: int = 0
    type: str = ""           # DDR4, DDR5, LPDDR5, etc.
    speed_mhz: int = 0
    form_factor: str = ""    # DIMM, SODIMM, etc.


@dataclass
class SystemInfo:
    hostname: str = ""
    os_name: str = ""
    os_version: str = ""
    kernel: str = ""
    architecture: str = ""
    cpu: CPUInfo = field(default_factory=CPUInfo)
    memory: list[MemoryInfo] = field(default_factory=list)
    gpu_count: int = 0
    python_version: str = ""
    is_virtualized: bool = False
    virtualization_type: str = ""


def detect_system_info() -> SystemInfo:
    """Detect full system hardware information."""
    info = SystemInfo(
        hostname=platform.node(),
        os_name=platform.system(),
        os_version=platform.release(),
        kernel=platform.version(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
    )
    info.cpu = detect_cpu()
    info.memory = detect_memory()
    info.is_virtualized = _detect_vm()
    return info


def detect_cpu() -> CPUInfo:
    """Detect CPU information."""
    cpu = CPUInfo(architecture=platform.machine())

    try:
        import psutil

        cpu.physical_cores = psutil.cpu_count(logical=False) or 0
        cpu.logical_cores = psutil.cpu_count(logical=True) or 0

        if platform.system() == "Linux":
            cpu = _detect_cpu_linux(cpu)
        elif platform.system() == "Darwin":
            cpu = _detect_cpu_macos(cpu)
        elif platform.system() == "Windows":
            cpu = _detect_cpu_windows(cpu)
    except ImportError:
        logger.debug("psutil not available for CPU detection")
    except Exception as e:
        logger.warning("CPU detection error: %s", e)

    return cpu


def detect_memory() -> list[MemoryInfo]:
    """Detect memory module information."""
    memories: list[MemoryInfo] = []
    try:
        import psutil

        total_mb = psutil.virtual_memory().total // (1024 * 1024)
        memories.append(MemoryInfo(total_mb=total_mb))
    except Exception:
        pass
    return memories


def _detect_cpu_linux(cpu: CPUInfo) -> CPUInfo:
    """Linux-specific CPU detection via /proc/cpuinfo."""
    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
        for line in content.split("\n"):
            line = line.strip()
            if "model name" in line:
                cpu.model_name = line.split(":", 1)[-1].strip()
            elif "vendor_id" in line:
                cpu.vendor = line.split(":", 1)[-1].strip()
            elif "cpu MHz" in line:
                mhz = _safe_float(line.split(":", 1)[-1].strip())
                if mhz > cpu.max_frequency_mhz:
                    cpu.max_frequency_mhz = mhz
            elif "cache size" in line:
                size_str = line.split(":", 1)[-1].strip()
                cpu.cache_l3_kb = _parse_cache_kb(size_str)
            elif "flags" in line:
                cpu.flags = line.split(":", 1)[-1].strip().split()
            # Only read once (first core is enough)
            if "power management" in line:
                break
    except Exception:
        pass
    return cpu


def _detect_cpu_macos(cpu: CPUInfo) -> CPUInfo:
    """macOS CPU detection via sysctl."""
    import subprocess
    queries = {
        "machdep.cpu.brand_string": "model_name",
        "machdep.cpu.vendor": "vendor",
        "hw.cpufrequency_max": "max_frequency_mhz",
        "hw.l1dcachesize": "cache_l1_kb",
        "hw.l2cachesize": "cache_l2_kb",
        "hw.l3cachesize": "cache_l3_kb",
    }
    for key, attr in queries.items():
        try:
            result = subprocess.run(
                ["sysctl", "-n", key], capture_output=True, text=True, timeout=3,
            )
            val = result.stdout.strip()
            if val:
                if "frequency" in attr or "cache" in attr:
                    val_int = _safe_int(val)
                    if "frequency" in attr:
                        val_int //= 1_000_000  # Hz → MHz
                    else:
                        val_int //= 1024       # B → KB
                    setattr(cpu, attr, val_int)
                else:
                    setattr(cpu, attr, val)
        except Exception:
            pass
    return cpu


def _detect_cpu_windows(cpu: CPUInfo) -> CPUInfo:
    """Windows CPU detection via WMI."""
    import subprocess

    try:
        result = subprocess.run(
            ["wmic", "cpu", "get", "Name,MaxClockSpeed,NumberOfCores,NumberOfLogicalProcessors",
             "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = [p.strip() for p in lines[1].split(",")]
            if len(parts) >= 2:
                cpu.model_name = parts[1]
            if len(parts) >= 3:
                cpu.max_frequency_mhz = _safe_float(parts[2])
    except Exception:
        pass
    return cpu


def _detect_vm() -> bool:
    """Detect if running inside a virtual machine."""
    if platform.system() == "Linux":
        try:
            import subprocess
            result = subprocess.run(
                ["systemd-detect-virt", "-q"],
                capture_output=True, timeout=3,
            )
            return result.returncode == 0
        except Exception:
            pass
        try:
            with open("/sys/class/dmi/id/product_name") as f:
                name = f.read().strip().lower()
                return any(x in name for x in ("kvm", "vmware", "virtualbox", "xen", "qemu"))
        except Exception:
            pass
    return False


# ── Helpers ───────────────────────────────────────
def _safe_int(val: str) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _safe_float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_cache_kb(size_str: str) -> int:
    """Parse cache size string like '8192 KB' → int KB."""
    import re
    match = re.search(r"(\d+)\s*(KB|MB|GB)?", size_str, re.IGNORECASE)
    if match:
        val, unit = int(match.group(1)), (match.group(2) or "KB").upper()
        if unit == "GB":
            return val * 1024 * 1024
        elif unit == "MB":
            return val * 1024
        return val
    return 0
