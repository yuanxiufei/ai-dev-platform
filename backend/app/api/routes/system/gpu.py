"""
GPU management API — device listing, allocation, and monitoring.
"""

from fastapi import APIRouter, HTTPException

from app.core.gpu import get_gpu_detector, get_gpu_allocator, get_gpu_monitor

router = APIRouter(prefix="/system/gpu", tags=["GPU"])


@router.get("/devices")
async def list_gpu_devices() -> dict:
    """List all detected GPU devices with current utilization."""
    detector = get_gpu_detector()
    devices = detector.detect_all()
    return {"data": [d.to_dict() for d in devices], "total": len(devices)}


@router.get("/allocations")
async def list_allocations() -> dict:
    """List all GPU memory allocations."""
    allocator = get_gpu_allocator()
    active = allocator.list_active_allocations()
    all_allocs = allocator.list_allocations()
    return {
        "active": [
            {
                "allocation_id": a.allocation_id,
                "gpu_index": a.gpu_index,
                "model_name": a.model_name,
                "requested_mb": a.requested_mb,
                "allocated_mb": a.allocated_mb,
                "status": a.status.value,
                "created_at": a.created_at,
            }
            for a in active
        ],
        "total_allocations": len(all_allocs),
    }


@router.get("/status")
async def gpu_status() -> dict:
    """Get overall GPU status summary."""
    allocator = get_gpu_allocator()
    allocator.refresh_devices()
    monitor = get_gpu_monitor()
    snapshot = monitor.latest_snapshot if monitor else None
    return {
        "gpu_count": allocator.total_gpu_count,
        "total_vram_mb": allocator.total_vram_mb,
        "free_vram_mb": allocator.free_vram_mb,
        "active_allocations": len(allocator.list_active_allocations()),
        "last_snapshot_ts": snapshot.timestamp if snapshot else None,
    }


@router.post("/allocations/{allocation_id}/release")
async def release_allocation(allocation_id: str) -> dict:
    """Release a GPU memory allocation."""
    allocator = get_gpu_allocator()
    success = allocator.release(allocation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Allocation not found")
    return {"message": f"Allocation {allocation_id} released"}
