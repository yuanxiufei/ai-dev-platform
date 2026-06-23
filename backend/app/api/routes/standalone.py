"""
Standalone 管理 API 路由

提供独立运行方案的控制接口：
- GET  /standalone/status      — 系统状态
- GET  /standalone/features    — 列出功能开关
- POST /standalone/features/{key}/toggle  — 切换开关
- POST /standalone/features/{key}         — 设置开关
- GET  /standalone/keys        — 列出 API Keys
- POST /standalone/keys        — 创建 API Key
- DELETE /standalone/keys/{hash} — 撤销 API Key
- POST /standalone/sleep       — 手动休眠
- POST /standalone/wake        — 手动唤醒
- GET  /standalone/watchdog    — 看门狗状态
"""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("standalone.routes")

router = APIRouter(prefix="/standalone", tags=["standalone"])


class FeatureToggleRequest(BaseModel):
    """功能开关切换请求"""
    enabled: bool = Field(..., description="目标状态: true=启用, false=禁用")


class CreateApiKeyRequest(BaseModel):
    """创建 API Key 请求"""
    tenant: str = Field(default="default", description="租户标识")
    name: str = Field(default="", description="密钥名称")
    roles: list[str] | None = Field(default=None, description="角色列表")


class ApiKeyResponse(BaseModel):
    """API Key 响应"""
    full_key: str
    access_key_prefix: str
    tenant: str
    name: str
    roles: list[str]
    created_at: float | None = None


class StatusResponse(BaseModel):
    """系统状态响应"""
    version: str
    started: bool
    timestamp: float
    features: list[dict]
    subsystems: dict


# ── 辅助函数 ────────────────────────────────────────


def _get_manager():
    """获取 StandaloneManager 实例"""
    from app.core.standalone.manager import get_standalone_manager
    manager = get_standalone_manager()
    if manager is None:
        raise HTTPException(status_code=503, detail="StandaloneManager not initialized")
    return manager


# ── 系统状态 ────────────────────────────────────────


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """获取独立运行系统的完整状态"""
    manager = _get_manager()
    return manager.get_status()


@router.get("/ping")
async def ping():
    """简单连通性检查"""
    return {"status": "ok", "service": "standalone"}


# ── 功能开关 ────────────────────────────────────────


@router.get("/features")
async def list_features():
    """列出所有功能开关及其当前状态"""
    manager = _get_manager()
    from app.core.standalone.state_switch import list_feature_states
    return {"features": list_feature_states()}


@router.get("/features/{key}")
async def get_feature(key: str):
    """获取单个功能开关状态"""
    manager = _get_manager()
    from app.core.standalone.state_switch import get_feature_state
    state = get_feature_state(key)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {key}")
    return {"key": key, "enabled": state}


@router.post("/features/{key}/toggle")
async def toggle_feature(key: str):
    """翻转功能开关状态"""
    manager = _get_manager()
    new_state = await manager.toggle_feature(key)
    if new_state is None:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {key}")
    return {"key": key, "enabled": new_state, "message": f"Feature '{key}' toggled to {new_state}"}


@router.post("/features/{key}")
async def set_feature(key: str, body: FeatureToggleRequest):
    """设置功能开关状态"""
    manager = _get_manager()
    success = await manager.set_feature(key, body.enabled)
    if not success:
        raise HTTPException(status_code=400, detail=f"Cannot update feature: {key}")
    return {"key": key, "enabled": body.enabled, "message": f"Feature '{key}' set to {body.enabled}"}


# ── 智能休眠控制 ────────────────────────────────────


@router.post("/sleep")
async def force_sleep():
    """强制立即进入休眠状态"""
    manager = _get_manager()
    result = await manager.force_sleep()
    if not result:
        raise HTTPException(status_code=409, detail="Cannot enter sleep (active requests or disabled)")
    return {"status": "sleeping", "message": "System entered sleep mode"}


@router.post("/wake")
async def force_wake():
    """强制立即唤醒"""
    manager = _get_manager()
    result = await manager.force_wake()
    return {"status": "awake", "message": "System woke up"}


# ── 守护进程状态 ────────────────────────────────────


@router.get("/watchdog")
async def watchdog_status():
    """获取守护进程状态"""
    manager = _get_manager()
    status = manager.get_status()
    wd = status.get("subsystems", {}).get("watchdog", {})
    return {"watchdog": wd}


# ── OS 级休眠控制 ──────────────────────────────────


@router.post("/os-sleep")
async def trigger_os_sleep():
    """立即触发操作系统睡眠/休眠（不可逆，需 Wake-on-LAN 恢复）"""
    manager = _get_manager()
    result = await manager.trigger_os_sleep()
    if not result:
        raise HTTPException(status_code=400, detail="OS sleep not supported on this platform")
    return {"status": "os_sleeping", "message": "OS sleep triggered — system will become unresponsive"}


@router.post("/os-sleep/cancel")
async def cancel_os_sleep():
    """取消已安排的 OS 休眠倒计时"""
    manager = _get_manager()
    result = await manager.cancel_os_sleep()
    return result


@router.get("/os-sleep/status")
async def get_os_sleep_status():
    """获取 OS 休眠计划状态"""
    manager = _get_manager()
    return manager.get_os_sleep_status()


# ── API Key 管理 ────────────────────────────────────


@router.get("/keys")
async def list_api_keys():
    """列出所有 API Key（不含完整密钥）"""
    manager = _get_manager()
    keys = manager.list_api_keys()
    return {"keys": keys, "count": len(keys)}


@router.post("/keys", response_model=ApiKeyResponse)
async def create_api_key(body: CreateApiKeyRequest):
    """创建一个新的 API Key"""
    manager = _get_manager()
    try:
        result = manager.create_api_key(
            tenant=body.tenant,
            name=body.name,
            roles=body.roles,
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/keys/{hashed_key}")
async def revoke_api_key(hashed_key: str):
    """撤销一个 API Key"""
    manager = _get_manager()
    success = await manager.revoke_api_key(hashed_key)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"message": "API key revoked", "hashed_key": hashed_key}


# ── Wake-on-LAN 远程唤醒 ──────────────────────────────


class WOLSendRequest(BaseModel):
    """WOL 发送请求"""
    mac_address: str = Field(default="", description="目标 MAC 地址（留空则唤醒本机）")
    broadcast: str = Field(default="", description="广播地址（留空则使用配置值）")
    port: int = Field(default=0, description="UDP 端口（0 则使用配置值 9）")


class WOLConfigureRequest(BaseModel):
    """WOL 配置请求"""
    target_mac: str = Field(default="", description="本机 MAC 地址")
    broadcast_address: str = Field(default="", description="子网广播地址")
    port: int = Field(default=0, description="UDP 端口")


@router.get("/wol/info")
async def get_wol_info():
    """获取 Wake-on-LAN 配置信息（MAC 地址、广播地址、接口列表）"""
    manager = _get_manager()
    return manager.get_wol_info() if hasattr(manager, 'get_wol_info') else {"error": "WOL not available"}


@router.post("/wol/send")
async def send_wol_packet(body: WOLSendRequest):
    """发送 WOL 魔术包——唤醒另一台电脑或测试本机 WOL。

    可以通过另一台机器调用此 API，也可以直接调用本机 API 唤醒本机（自测）。

    使用场景：
    - curl -X POST .../wol/send -d '{"mac_address":"AA:BB:CC:DD:EE:FF","broadcast":"192.168.1.255"}'
      → 从当前运行的服务器发魔术包，唤醒目标主机
    """
    manager = _get_manager()
    result = await manager.send_wol(body.mac_address, body.broadcast, body.port)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "WOL send failed"))
    return result


@router.post("/wol/configure")
async def configure_wol(body: WOLConfigureRequest):
    """配置 WOL 参数（手动指定本机 MAC 或广播地址）"""
    manager = _get_manager()
    result = await manager.configure_wol(body.target_mac, body.broadcast_address, body.port)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.post("/wol/redetect")
async def redetect_wol():
    """重新检测本机网络接口（刷新 MAC/IP/广播地址）"""
    manager = _get_manager()
    result = await manager.redetect_wol()
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result
