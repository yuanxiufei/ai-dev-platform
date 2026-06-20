"""
System resource monitoring API — CPU, memory, disk, network status.
"""

from fastapi import APIRouter

from app.core.resources import get_resource_collector, collect_system_load, detect_system_info
from app.core.resources.system_load import SystemLoad
from app.core.resources.hardware import SystemInfo

router = APIRouter(prefix="/system/resources", tags=["Resources"])


@router.get("/current")
async def current_resources() -> dict:
    """Get current system resource utilization snapshot."""
    collector = get_resource_collector()
    if collector and collector.latest:
        snap = collector.latest
        system = snap.system
        gpus = [g.to_dict() for g in snap.gpus]
    else:
        system = collect_system_load()
        gpus = []

    return {
        "timestamp": collector.latest.timestamp if collector and collector.latest else None,
        "cpu": {
            "utilization_pct": system.cpu.utilization_pct if system else 0,
            "logical_cores": system.cpu.logical_cores if system else 0,
            "load_avg_1m": system.cpu.load_avg_1m if system else 0,
            "load_avg_5m": system.cpu.load_avg_5m if system else 0,
            "load_avg_15m": system.cpu.load_avg_15m if system else 0,
        },
        "memory": {
            "total_mb": system.memory.total_mb if system else 0,
            "used_mb": system.memory.used_mb if system else 0,
            "free_mb": system.memory.free_mb if system else 0,
            "utilization_pct": system.memory.utilization_pct if system else 0,
            "swap_total_mb": system.memory.swap_total_mb if system else 0,
            "swap_used_mb": system.memory.swap_used_mb if system else 0,
        },
        "disks": [
            {
                "mount": d.mount_point,
                "total_gb": d.total_gb,
                "used_gb": d.used_gb,
                "free_gb": d.free_gb,
                "utilization_pct": d.utilization_pct,
            }
            for d in (system.disks if system else [])
        ],
        "gpus": gpus,
        "hostname": system.hostname if system else "",
        "uptime_seconds": system.uptime_seconds if system else 0,
    }


@router.get("/hardware")
async def hardware_info() -> dict:
    """Get detailed hardware information."""
    info = detect_system_info()
    return {
        "hostname": info.hostname,
        "os": {
            "name": info.os_name,
            "version": info.os_version,
            "kernel": info.kernel,
            "architecture": info.architecture,
        },
        "cpu": {
            "model_name": info.cpu.model_name,
            "physical_cores": info.cpu.physical_cores,
            "logical_cores": info.cpu.logical_cores,
            "max_frequency_mhz": info.cpu.max_frequency_mhz,
            "vendor": info.cpu.vendor,
            "architecture": info.cpu.architecture,
        },
        "memory": [
            {
                "total_mb": m.total_mb,
                "type": m.type,
                "speed_mhz": m.speed_mhz,
            }
            for m in info.memory
        ],
        "gpu_count": info.gpu_count,
        "python_version": info.python_version,
        "is_virtualized": info.is_virtualized,
        "virtualization_type": info.virtualization_type,
    }


@router.get("/history")
async def resource_history(count: int = 60) -> dict:
    """Get recent resource snapshot history."""
    collector = get_resource_collector()
    if collector is None:
        return {"data": [], "total": 0}

    snapshots = collector.history(count=min(count, 360))
    return {
        "data": [
            {
                "timestamp": s.timestamp,
                "cpu_pct": s.system.cpu.utilization_pct if s.system else 0,
                "mem_pct": s.system.memory.utilization_pct if s.system else 0,
                "gpu_count": len(s.gpus),
            }
            for s in snapshots
        ],
        "total": len(snapshots),
    }
