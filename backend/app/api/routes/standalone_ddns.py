"""
Standalone DDNS API 路由 — 动态域名解析管理

提供 RESTful 接口管理阿里云 DDNS：
- GET  /ddns/status          — 获取当前 DDNS 状态
- POST /ddns/test            — 测试连接和配置
- POST /ddns/update          — 手动触发一次更新
- GET  /ddns/config          — 获取当前配置
- POST /ddns/config          — 更新配置
- POST /ddns/daemon/start    — 启动守护进程
- POST /ddns/daemon/stop     — 停止守护进程
- GET  /ddns/history         — 更新历史记录
- GET  /ddns/dns-resolve     — DNS 解析验证

扩展性设计：
- 当前仅支持阿里云 DNS，接口抽象为通用模式
- 未来可接入 Cloudflare API / 腾讯云 DNSPod / Google Cloud DNS 等
- 通过 provider 字段区分不同 DNS 服务商
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("standalone.ddns.routes")

router = APIRouter(prefix="/standalone/ddns", tags=["standalone-ddns"])


# ── 请求模型 ────────────────────────────────────────


class DDNSConfigUpdateRequest(BaseModel):
    """DDNS 配置更新请求"""
    access_key_id: str | None = Field(None, description="阿里云 AccessKey ID")
    access_key_secret: str | None = Field(None, description="阿里云 AccessKey Secret")
    domain: str | None = Field(None, description="主域名 (如 reginyuan.com)")
    subdomain: str | None = Field(None, description="子域名 (如 wake)")
    record_type: str | None = Field(None, description="记录类型: A 或 AAAA")
    ttl: int | None = Field(None, description="DNS TTL 秒数")
    interval: int | None = Field(None, description="检测间隔秒数")


class DDNSForceUpdateRequest(BaseModel):
    """强制更新请求"""
    force: bool = Field(default=True, description="强制更新（不比较旧IP）")


# ── 辅助函数 ────────────────────────────────────────


def _get_ddns():
    """获取 DDNSManager 单例"""
    from app.core.standalone.ddns_manager import get_ddns_manager
    mgr = get_ddns_manager()
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail="DDNSManager not initialized. Ensure standalone-tools/ddns/aliddns_config.json exists.",
        )
    return mgr


# ── 状态查询 ────────────────────────────────────────


@router.get("/status")
async def ddns_status():
    """
    获取 DDNS 当前完整状态。

    返回：域名、IP、DNS解析状态、守护进程状态、配置信息等。
    前端用此接口渲染 DDNS 管理卡片。
    """
    mgr = _get_ddns()
    return mgr.get_status()


@router.get("/config")
async def ddns_get_config():
    """获取当前 DDNS 配置（不含敏感密钥的完整信息）。"""
    mgr = _get_ddns()
    cfg = mgr.config
    return {
        "domain": cfg.domain,
        "subdomain": cfg.subdomain,
        "record_type": cfg.record_type,
        "ttl": cfg.ttl,
        "interval": cfg.interval,
        "full_domain": mgr.full_domain,
        "has_credentials": bool(cfg.access_key_id and cfg.access_key_secret),
        # 密钥只返回前4位用于确认已配置（脱敏）
        "key_preview": cfg.access_key_id[:4] + "****" if cfg.access_key_id else "",
        "config_path": str(mgr._config_file),
        "config_exists": mgr._config_file.exists(),
    }


@router.post("/config")
async def ddns_update_config(body: DDNSConfigUpdateRequest):
    """更新 DDNS 配置参数。"""
    mgr = _get_ddns()
    result = mgr.update_config(
        access_key_id=body.access_key_id,
        access_key_secret=body.access_key_secret,
        domain=body.domain,
        subdomain=body.subdomain,
        record_type=body.record_type,
        ttl=body.ttl,
        interval=body.interval,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail="Failed to save config")

    return {
        "message": "配置已更新",
        "full_domain": mgr.full_domain,
        **result,
    }


# ── 操作接口 ────────────────────────────────────────


@router.post("/test")
async def ddns_test_connection():
    """
    测试 DDNS 全链路连通性：

    Step 1: 检测公网 IP 是否可获取（网络是否通）
    Step 2: 测试阿里云 API 凭证是否有效
    返回每步的详细结果。
    """
    mgr = _get_ddns()
    return await mgr.test_connection()


@router.post("/update")
async def ddns_force_update(body: DDNSForceUpdateRequest = DDNSForceUpdateRequest()):
    """
    手动触发一次 DDNS IP 检测与更新。

    默认 force=True，即使 IP 未变也会调 API 刷新。
    前端「立即更新」按钮调用此接口。
    """
    mgr = _get_ddns()
    result = await mgr.check_update(force=body.force)
    return result


@router.get("/dns-resolve")
async def ddns_dns_resolve():
    """对当前域名执行 DNS 解析，返回实际解析结果。"""
    mgr = _get_ddns()

    if not mgr.full_domain or mgr.full_domain == "(未配置)":
        raise HTTPException(status_code=400, detail="DDNS domain not configured")

    import socket
    try:
        socket.setdefaulttimeout(5)
        resolved_ip = socket.gethostbyname(mgr.full_domain)
        return {
            "domain": mgr.full_domain,
            "resolved_ip": resolved_ip,
            "matches_current": resolved_ip == mgr.config.last_ip if mgr.config.last_ip else None,
            "current_recorded_ip": mgr.config.last_ip or None,
        }
    except socket.gaierror as e:
        return {
            "domain": mgr.full_domain,
            "resolved_ip": None,
            "error": f"DNS 解析失败: {e}",
            "current_recorded_ip": mgr.config.last_ip or None,
        }


# ── 守护进程控制 ────────────────────────────────────


@router.post("/daemon/start")
async def ddns_start_daemon():
    """启动 DDNS 后台守护进程。"""
    mgr = _get_ddns()
    return await mgr.start_daemon()


@router.post("/daemon/stop")
async def ddns_stop_daemon():
    """停止 DDNS 后台守护进程。"""
    mgr = _get_ddns()
    return await mgr.stop_daemon()


@router.get("/daemon/status")
async def ddns_daemon_status():
    """获取守护进程运行状态。"""
    mgr = _get_ddns()
    return {
        "running": mgr.config.daemon_running,
        "started_at": mgr.config.daemon_started_at,
        "check_count": mgr.config.daemon_check_count,
        "update_count": mgr.config.daemon_update_count,
        "last_error": mgr.config.daemon_last_error,
        "uptime_seconds": (
            time.time() - mgr.config.daemon_started_at
            if mgr.config.daemon_running else 0
        ),
    }


# ── 历史 ────────────────────────────────────────────


@router.get("/history")
async def ddns_history(limit: int = 20):
    """获取最近 N 条 DDNS 更新历史记录。"""
    import time as _time
    mgr = _get_ddns()
    history = mgr.get_history(limit=min(limit, 50))
    return {
        "records": history,
        "total": len(mgr.config.history),
        "returned": len(history),
    }


# ── 远程唤醒辅助 ────────────────────────────────────


@router.get("/wake-info")
async def ddns_wake_info():
    """
    获取远程唤醒所需的信息。

    将 DDNS 域名、WOL MAC 等信息聚合，
    方便前端一键展示「从外面唤醒」所需的所有参数。
    """
    mgr = _get_ddns()

    # 同时获取 WOL 信息
    wol_info = {}
    try:
        from app.core.standalone.ddns_manager import get_wol_manager
        wol_mgr = get_wol_manager()
        if wol_mgr:
            wol_info = wol_mgr.get_info()
    except Exception:
        pass

    return {
        "domain": mgr.full_domain,
        "ip": mgr.config.last_ip,
        "configured": bool(mgr.domain and mgr.config.last_ip),
        **wol_info,
    }
