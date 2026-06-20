"""
Webhook 管理 API — 注册/触发/测试/日志

借鉴 Open WebUI Webhooks
路径: /webhooks/*
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.webhooks import get_webhook_manager, WebhookEventType, WebhookRegistration, WebhookEvent, WebhookDelivery

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ── Request/Response Models ───────────────────────

class CreateWebhookRequest(BaseModel):
    """创建 webhook 请求"""
    url: str = Field(..., description="回调 URL")
    name: str = Field(..., description="显示名称")
    events: list[str] = Field(..., description="订阅事件类型列表")
    secret: str = Field(default="", description="HMAC 签名密钥（留空自动生成）")
    max_retries: int = Field(default=3, ge=1, le=10)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    headers: dict[str, str] = Field(default_factory=dict, description="自定义请求头")
    description: str = Field(default="")
    is_active: bool = Field(default=True)


class UpdateWebhookRequest(BaseModel):
    """更新 webhook 请求"""
    url: str | None = None
    name: str | None = None
    events: list[str] | None = None
    secret: str | None = None
    max_retries: int | None = None
    timeout_seconds: float | None = None
    headers: dict[str, str] | None = None
    description: str | None = None
    is_active: bool | None = None


class TriggerEventRequest(BaseModel):
    """手动触发事件请求"""
    event_type: str = Field(..., description="事件类型")
    payload: dict[str, Any] = Field(default_factory=dict, description="事件载荷")


class WebhookResponse(BaseModel):
    """Webhook 响应"""
    id: str
    url: str
    name: str
    events: list[str]
    is_active: bool
    max_retries: int
    timeout_seconds: float
    headers: dict[str, str]
    description: str
    created_at: str
    last_triggered_at: str
    success_count: int
    failure_count: int


class DeliveryLogResponse(BaseModel):
    """投递日志响应"""
    id: str
    webhook_id: str
    event_type: str
    url: str
    status: int
    success: bool
    error_message: str
    attempt: int
    sent_at: str
    latency_ms: float


# ── Helpers ───────────────────────────────────────

def _reg_to_response(r: WebhookRegistration) -> dict[str, Any]:
    return {
        "id": r.id,
        "url": r.url,
        "name": r.name,
        "events": [e.value for e in r.events],
        "is_active": r.is_active,
        "max_retries": r.max_retries,
        "timeout_seconds": r.timeout_seconds,
        "headers": r.headers,
        "description": r.description,
        "created_at": r.created_at,
        "last_triggered_at": r.last_triggered_at,
        "success_count": r.success_count,
        "failure_count": r.failure_count,
    }


def _delivery_to_response(d: WebhookDelivery) -> dict[str, Any]:
    return {
        "id": d.id,
        "webhook_id": d.webhook_id,
        "event_type": d.event_type,
        "url": d.url,
        "status": d.status,
        "success": d.success,
        "error_message": d.error_message,
        "attempt": d.attempt,
        "sent_at": d.sent_at,
        "latency_ms": d.latency_ms,
    }


# ── Routes ────────────────────────────────────────

@router.get("/event-types")
async def list_event_types() -> dict[str, Any]:
    """列出所有可用的事件类型"""
    types = [
        {"value": e.value, "name": e.name, "description": _describe_event(e)}
        for e in WebhookEventType
    ]
    return {"event_types": types}


def _describe_event(e: WebhookEventType) -> str:
    desc = {
        WebhookEventType.CHAT_COMPLETED: "对话完成时触发",
        WebhookEventType.CHAT_STARTED: "对话开始时触发",
        WebhookEventType.PROJECT_CREATED: "项目创建时触发",
        WebhookEventType.PROJECT_GENERATED: "项目生成完成时触发",
        WebhookEventType.PROJECT_DEPLOYED: "项目部署时触发",
        WebhookEventType.VIDEO_GENERATED: "视频生成完成时触发",
        WebhookEventType.VIDEO_FAILED: "视频生成失败时触发",
        WebhookEventType.TEMPLATE_INSTALLED: "模板安装时触发",
        WebhookEventType.MODEL_DOWNLOADED: "模型下载完成时触发",
        WebhookEventType.USER_REGISTERED: "用户注册时触发",
    }
    return desc.get(e, "")


@router.get("")
async def list_webhooks(
    event_type: str = Query(default="", description="按事件类型筛选"),
    active_only: bool = Query(default=True, description="仅活跃的"),
) -> dict[str, Any]:
    """列出所有 webhook"""
    mgr = get_webhook_manager()
    et = WebhookEventType(event_type) if event_type else None
    registrations = mgr.list_registrations(event_type=et, active_only=active_only)
    return {"webhooks": [_reg_to_response(r) for r in registrations], "total": len(registrations)}


@router.post("")
async def create_webhook(req: CreateWebhookRequest) -> dict[str, Any]:
    """创建新 webhook"""
    try:
        events = [WebhookEventType(e) for e in req.events]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的事件类型: {e}")

    reg = WebhookRegistration(
        url=req.url,
        name=req.name,
        events=events,
        secret=req.secret,
        max_retries=req.max_retries,
        timeout_seconds=req.timeout_seconds,
        headers=req.headers,
        description=req.description,
        is_active=req.is_active,
    )

    mgr = get_webhook_manager()
    webhook_id = mgr.register(reg)
    return {"id": webhook_id, **_reg_to_response(reg)}


@router.get("/{webhook_id}")
async def get_webhook(webhook_id: str) -> dict[str, Any]:
    """获取单个 webhook"""
    mgr = get_webhook_manager()
    reg = mgr.get(webhook_id)
    if not reg:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} 不存在")
    return _reg_to_response(reg)


@router.put("/{webhook_id}")
async def update_webhook(webhook_id: str, req: UpdateWebhookRequest) -> dict[str, Any]:
    """更新 webhook"""
    mgr = get_webhook_manager()
    reg = mgr.get(webhook_id)
    if not reg:
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} 不存在")

    if req.url is not None:
        reg.url = req.url
    if req.name is not None:
        reg.name = req.name
    if req.events is not None:
        try:
            reg.events = [WebhookEventType(e) for e in req.events]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效的事件类型: {e}")
    if req.secret is not None:
        reg.secret = req.secret
    if req.max_retries is not None:
        reg.max_retries = req.max_retries
    if req.timeout_seconds is not None:
        reg.timeout_seconds = req.timeout_seconds
    if req.headers is not None:
        reg.headers = req.headers
    if req.description is not None:
        reg.description = req.description
    if req.is_active is not None:
        reg.is_active = req.is_active

    return _reg_to_response(reg)


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str) -> dict[str, Any]:
    """删除 webhook"""
    mgr = get_webhook_manager()
    if not mgr.unregister(webhook_id):
        raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} 不存在")
    return {"message": "Webhook 已删除", "id": webhook_id}


@router.post("/{webhook_id}/test")
async def test_webhook(webhook_id: str) -> dict[str, Any]:
    """发送测试事件"""
    mgr = get_webhook_manager()
    try:
        delivery = await mgr.test_webhook(webhook_id)
        return {
            "success": delivery.success,
            "status": delivery.status,
            "error_message": delivery.error_message,
            "latency_ms": delivery.latency_ms,
            "delivery": _delivery_to_response(delivery),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/trigger")
async def trigger_event(req: TriggerEventRequest) -> dict[str, Any]:
    """手动触发事件（投递到所有匹配的 webhook）"""
    try:
        event_type = WebhookEventType(req.event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的事件类型: {req.event_type}")

    mgr = get_webhook_manager()
    event = WebhookEvent(type=event_type, payload=req.payload)
    deliveries = await mgr.trigger(event)

    return {
        "event_type": req.event_type,
        "delivered_to": len(deliveries),
        "deliveries": [_delivery_to_response(d) for d in deliveries],
    }


@router.get("/{webhook_id}/logs")
async def get_delivery_logs(
    webhook_id: str = "",
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """获取投递日志"""
    mgr = get_webhook_manager()
    if webhook_id:
        reg = mgr.get(webhook_id)
        if not reg:
            raise HTTPException(status_code=404, detail=f"Webhook {webhook_id} 不存在")
    logs = mgr.get_delivery_log(webhook_id=webhook_id, limit=limit)
    return {"logs": [_delivery_to_response(l) for l in logs], "total": len(logs)}
