"""
GPU Detector — auto-discover GPU devices across multiple vendors.

Borrows heavily from GPUStack detectors/detector_factory.py and runtime.py patterns.
Supports NVIDIA (nvidia-smi), AMD (rocm-smi), Apple Silicon (system_profiler),
Huawei Ascend (npu-smi), and CPU-only fallback.
"""

import logging
import os
import platform
import re
import shutil
import subprocess
from typing import Optional

from app.core.gpu.schemas import (
    GPUDeviceInfo,
    GPUMemoryInfo,
    GPUUtilizationInfo,
    GPUVendor,
    GPUBackend,
)

logger = logging.getLogger(__name__)


class GPUDetector:
    """Detect GPU devices across multiple vendors via CLI tools."""

    # ── Tool discovery ────────────────────────────
    NVIDIA_SMI = "nvidia-smi"
    ROCM_SMI = "rocm-smi"
    NPU_SMI = "npu-smi"           # Huawei Ascend
    INTEL_GPU_TOP = "intel_gpu_top"
    SYSTEM_PROFILER = "system_profiler"  # macOS

    @classmethod
    def _find_tool(cls, name: str) -> Optional[str]:
        """Locate a CLI tool in PATH."""
        return shutil.which(name)

    @classmethod
    def has_nvidia_gpu(cls) -> bool:
        return cls._find_tool(cls.NVIDIA_SMI) is not None

    @classmethod
    def has_amd_gpu(cls) -> bool:
        return cls._find_tool(cls.ROCM_SMI) is not None

    @classmethod
    def has_ascend_gpu(cls) -> bool:
        return cls._find_tool(cls.NPU_SMI) is not None

    @classmethod
    def has_apple_gpu(cls) -> bool:
        return platform.system() == "Darwin" and platform.processor() == "arm"

    # ── Detection ─────────────────────────────────
    def detect_all(self) -> list[GPUDeviceInfo]:
        """Detect all available GPUs, preferring the first available backend."""
        devices: list[GPUDeviceInfo] = []
        detectors = [
            (self.has_nvidia_gpu, self._detect_nvidia),
            (self.has_amd_gpu, self._detect_amd),
            (self.has_ascend_gpu, self._detect_ascend),
            (self.has_apple_gpu, self._detect_apple),
        ]
        for has_fn, detect_fn in detectors:
            try:
                if has_fn():
                    found = detect_fn()
                    if found:
                        devices.extend(found)
                        break  # First valid backend wins
            except Exception as e:
                logger.debug("GPU detection (%s) failed: %s", detect_fn.__name__, e)

        if not devices:
            logger.info("No discrete GPU detected; using CPU fallback.")
        return devices

    # ── NVIDIA via nvidia-smi ─────────────────────
    def _detect_nvidia(self) -> list[GPUDeviceInfo]:
        """Detect NVIDIA GPUs via nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    self.NVIDIA_SMI,
                    "--query-gpu=index,name,uuid,memory.total,memory.used,memory.free,"
                    "utilization.gpu,temperature.gpu,power.draw,power.limit,"
                    "driver_version,cuda_version,pci.bus_id,compute_cap",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []

            devices: list[GPUDeviceInfo] = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 13:
                    continue
                (
                    idx, name, uuid, mem_total, mem_used, mem_free,
                    gpu_util, temp, power, power_limit,
                    driver_ver, cuda_ver, pci_bus, comp_cap,
                ) = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], \
                    parts[6], parts[7], parts[8], parts[9], parts[10], parts[11], \
                    parts[12], parts[13] if len(parts) > 13 else ""

                devices.append(GPUDeviceInfo(
                    index=int(idx),
                    name=name,
                    uuid=uuid,
                    vendor=GPUVendor.NVIDIA,
                    backend=GPUBackend.CUDA,
                    driver_version=driver_ver,
                    runtime_version=f"CUDA {cuda_ver}" if cuda_ver else "",
                    compute_capability=comp_cap,
                    memory=GPUMemoryInfo(
                        total_mb=_safe_int(mem_total),
                        used_mb=_safe_int(mem_used),
                        free_mb=_safe_int(mem_free),
                    ),
                    utilization=GPUUtilizationInfo(
                        gpu_util_pct=_safe_float(gpu_util),
                        temperature_c=_safe_float(temp),
                        power_w=_safe_float(power),
                        power_limit_w=_safe_float(power_limit),
                    ),
                    pci_bus_id=pci_bus,
                ))
            logger.info("Detected %d NVIDIA GPU(s)", len(devices))
            return devices
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning("NVIDIA GPU detection error: %s", e)
            return []

    # ── AMD via rocm-smi ─────────────────────────
    def _detect_amd(self) -> list[GPUDeviceInfo]:
        """Detect AMD GPUs via rocm-smi."""
        try:
            result = subprocess.run(
                [self.ROCM_SMI, "--showid", "--showproductname", "--showmeminfo",
                 "vram", "--showuse", "--showtemp", "--csv"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []

            devices: list[GPUDeviceInfo] = []
            lines = result.stdout.strip().split("\n")
            if len(lines) < 2:
                return []
            for line in lines[1:]:  # Skip header
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 5:
                    continue
                idx = _safe_int(parts[0])
                devices.append(GPUDeviceInfo(
                    index=idx,
                    name=parts[1] if len(parts) > 1 else f"AMD GPU {idx}",
                    uuid=parts[1] if len(parts) > 1 else "",
                    vendor=GPUVendor.AMD,
                    backend=GPUBackend.ROCM,
                    memory=GPUMemoryInfo(
                        total_mb=_safe_int(parts[2]) if len(parts) > 2 else 0,
                        used_mb=_safe_int(parts[3]) if len(parts) > 3 else 0,
                        free_mb=0,
                    ),
                    utilization=GPUUtilizationInfo(
                        temperature_c=_safe_float(parts[4]) if len(parts) > 4 else 0.0,
                    ),
                ))
            logger.info("Detected %d AMD GPU(s)", len(devices))
            return devices
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning("AMD GPU detection error: %s", e)
            return []

    # ── Huawei Ascend via npu-smi ────────────────
    def _detect_ascend(self) -> list[GPUDeviceInfo]:
        """Detect Huawei Ascend NPUs via npu-smi."""
        try:
            result = subprocess.run(
                [self.NPU_SMI, "info", "-m"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                return []
            devices = self._parse_ascend_output(result.stdout)
            logger.info("Detected %d Ascend NPU(s)", len(devices))
            return devices
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning("Ascend NPU detection error: %s", e)
            return []

    def _parse_ascend_output(self, output: str) -> list[GPUDeviceInfo]:
        """Parse npu-smi output for Ascend devices."""
        devices: list[GPUDeviceInfo] = []
        idx = 0
        for line in output.split("\n"):
            line = line.strip()
            if "Name" in line or "Chip" in line:
                name = line.split(":", 1)[-1].strip() if ":" in line else line
                mem_match = re.search(r"Memory.*?(\d+)", output)
                total_mem = int(mem_match.group(1)) if mem_match else 0
                devices.append(GPUDeviceInfo(
                    index=idx,
                    name=name,
                    uuid=f"ascend-{idx}",
                    vendor=GPUVendor.HUAWEI_ASCEND,
                    backend=GPUBackend.CANN,
                    memory=GPUMemoryInfo(total_mb=total_mem),
                ))
                idx += 1
        return devices

    # ── Apple Silicon via system_profiler ─────────
    def _detect_apple(self) -> list[GPUDeviceInfo]:
        """Detect Apple Silicon GPU via system_profiler."""
        try:
            result = subprocess.run(
                [self.SYSTEM_PROFILER, "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=10,
            )
            cores_match = re.search(r"Total Number of Cores:\s*(\d+)", result.stdout)
            cores = int(cores_match.group(1)) if cores_match else 0

            # Get unified memory
            mem_result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            total_mem_bytes = int(mem_result.stdout.strip()) if mem_result.stdout.strip() else 0
            total_mem_mb = total_mem_bytes // (1024 * 1024)

            return [GPUDeviceInfo(
                index=0,
                name=f"Apple M-series ({cores} GPU cores)",
                uuid="apple-unified",
                vendor=GPUVendor.APPLE,
                backend=GPUBackend.METAL,
                memory=GPUMemoryInfo(
                    total_mb=total_mem_mb,
                    is_unified_memory=True,
                ),
            )]
        except Exception as e:
            logger.warning("Apple GPU detection error: %s", e)
            return []

    # ── Refresh utilization ───────────────────────
    def refresh_utilization(self, device: GPUDeviceInfo) -> GPUDeviceInfo:
        """Refresh real-time utilization for a single GPU."""
        if device.vendor == GPUVendor.NVIDIA:
            return self._refresh_nvidia(device)
        elif device.vendor == GPUVendor.AMD:
            return self._refresh_amd(device)
        # Other vendors: utilization stays as-is
        return device

    def _refresh_nvidia(self, device: GPUDeviceInfo) -> GPUDeviceInfo:
        try:
            result = subprocess.run(
                [self.NVIDIA_SMI, "-i", str(device.index),
                 "--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                device.memory.used_mb = _safe_int(parts[0])
                device.memory.free_mb = _safe_int(parts[1])
                device.utilization.gpu_util_pct = _safe_float(parts[2])
                device.utilization.temperature_c = _safe_float(parts[3])
                device.utilization.power_w = _safe_float(parts[4])
        except Exception:
            pass
        return device

    def _refresh_amd(self, device: GPUDeviceInfo) -> GPUDeviceInfo:
        try:
            result = subprocess.run(
                [self.ROCM_SMI, "-i", "--showuse", "--showmemuse", "--showtemp", "--csv"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= device.index + 2:
                parts = [p.strip() for p in lines[device.index + 1].split(",")]
                if len(parts) >= 2:
                    device.utilization.gpu_util_pct = _safe_float(parts[1])
                if len(parts) >= 3:
                    device.utilization.temperature_c = _safe_float(parts[2])
        except Exception:
            pass
        return device


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


# ── Convenience functions ─────────────────────────
def detect_gpus() -> list[GPUDeviceInfo]:
    """Quick detection — returns cached or fresh result."""
    detector = GPUDetector()
    return detector.detect_all()


def detect_system_gpus() -> list[dict]:
    """Detect GPUs and return as dicts (for API responses)."""
    devices = detect_gpus()
    return [d.to_dict() for d in devices]
