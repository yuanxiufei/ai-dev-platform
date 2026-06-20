"""
Webhook 事件系统 — 事件注册、触发、重试

借鉴 Open WebUI 的 Webhooks：
- 注册 webhook 端点（对话完成/项目生成/视频完成等事件）
- 异步触发 + 自动重试（指数退避）
- 过滤器（按事件类型、模型、用户）
- Webhook 日志记录
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable

import httpx

from app.core.config import settings


# ── 数据模型 ─────────────────────────────────────

class WebhookEventType(str, Enum):
    """事件类型"""
    CHAT_COMPLETED = "chat.completed"        # 对话完成
    CHAT_STARTED = "chat.started"            # 对话开始
    PROJECT_CREATED = "project.created"      # 项目创建
    PROJECT_GENERATED = "project.generated"  # 项目生成完成
    PROJECT_DEPLOYED = "project.deployed"     # 项目部署
    VIDEO_GENERATED = "video.generated"       # 视频生成完成
    VIDEO_FAILED = "video.failed"            # 视频生成失败
    TEMPLATE_INSTALLED = "template.installed" # 模板安装
    MODEL_DOWNLOADED = "model.downloaded"     # 模型下载完成
    USER_REGISTERED = "user.registered"      # 用户注册


@dataclass
class WebhookRegistration:
    """Webhook 注册记录"""
    id: str = ""
    url: str = ""                          # 回调 URL
    name: str = ""                         # 显示名称
    secret: str = ""                       # HMAC 签名密钥
    events: list[WebhookEventType] = field(default_factory=list)  # 订阅事件
    is_active: bool = True
    max_retries: int = 3                   # 最大重试次数
    timeout_seconds: float = 10.0          # 超时 秒
    headers: dict[str, str] = field(default_factory=dict)  # 自定义请求头
    description: str = ""
    created_at: str = ""
    last_triggered_at: str = ""
    success_count: int = 0
    failure_count: int = 0


@dataclass
class WebhookEvent:
    """事件载荷"""
    type: WebhookEventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    event_id: str = ""


@dataclass
class WebhookDelivery:
    """单次投递记录"""
    id: str = ""
    webhook_id: str = ""
    event_type: str = ""
    url: str = ""
    status: int = 0                    # HTTP 状态码
    success: bool = False
    error_message: str = ""
    attempt: int = 1                   # 第几次尝试
    sent_at: str = ""
    latency_ms: float = 0.0
    request_body: str = ""             # JSON 字符串
    response_body: str = ""


# ── Webhook 管理器 ───────────────────────────────

class WebhookManager:
    """
    Webhook 事件管理器

    职责：
    1. 注册/注销 webhook 端点
    2. 接收事件并异步投递到所有注册端点
    3. 自动重试（指数退避）
    4. 事件过滤
    """

    def __init__(self):
        self._registrations: dict[str, WebhookRegistration] = {}
        self._delivery_log: list[WebhookDelivery] = []
        self._max_log_entries = 500
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    def register(self, reg: WebhookRegistration) -> str:
        """注册 webhook，返回 ID"""
        if not reg.id:
            reg.id = _generate_id()
        if not reg.created_at:
            reg.created_at = datetime.now(UTC).isoformat()
        if not reg.secret:
            reg.secret = _generate_secret()
        self._registrations[reg.id] = reg
        return reg.id

    def unregister(self, webhook_id: str) -> bool:
        """注销 webhook"""
        if webhook_id in self._registrations:
            del self._registrations[webhook_id]
            return True
        return False

    def get(self, webhook_id: str) -> WebhookRegistration | None:
        return self._registrations.get(webhook_id)

    def list_registrations(
        self,
        event_type: WebhookEventType | None = None,
        active_only: bool = True,
    ) -> list[WebhookRegistration]:
        """列出注册的 webhook"""
        result = list(self._registrations.values())
        if active_only:
            result = [r for r in result if r.is_active]
        if event_type:
            result = [r for r in result if event_type in r.events]
        return result

    async def trigger(
        self,
        event: WebhookEvent,
        filters: dict[str, Any] | None = None,
    ) -> list[WebhookDelivery]:
        """
        触发事件并投递到所有匹配的 webhook

        Args:
            event: 事件载荷
            filters: 额外过滤条件 {"model": "...", "user_id": "..."}

        Returns:
            所有投递记录
        """
        if not event.timestamp:
            event.timestamp = datetime.now(UTC).isoformat()
        if not event.event_id:
            event.event_id = _generate_id()

        # 查找匹配的 webhook
        matching = [
            r for r in self._registrations.values()
            if r.is_active and event.type in r.events
        ]

        if not matching:
            return []

        # 并发投递
        tasks = [self._deliver(reg, event, filters) for reg in matching]
        deliveries = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[WebhookDelivery] = []
        for d in deliveries:
            if isinstance(d, WebhookDelivery):
                results.append(d)
                self._log_delivery(d)

        return results

    async def _deliver(
        self,
        reg: WebhookRegistration,
        event: WebhookEvent,
        filters: dict[str, Any] | None,
    ) -> WebhookDelivery:
        """投递单次事件（含重试）"""
        body = json.dumps({
            "event_type": event.type.value,
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "payload": event.payload,
            "filters": filters or {},
        }, ensure_ascii=False)

        # 生成 HMAC 签名
        signature = _sign_body(body, reg.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": reg.id,
            "X-Webhook-Signature": signature,
            "X-Event-Type": event.type.value,
            "X-Event-ID": event.event_id,
            **reg.headers,
        }

        delivery = WebhookDelivery(
            id=_generate_id(),
            webhook_id=reg.id,
            event_type=event.type.value,
            url=reg.url,
            request_body=body,
        )

        last_error = ""
        for attempt in range(1, reg.max_retries + 1):
            delivery.attempt = attempt
            delivery.sent_at = datetime.now(UTC).isoformat()

            try:
                t0 = time.perf_counter()
                resp = await self.client.post(
                    reg.url,
                    content=body,
                    headers=headers,
                    timeout=reg.timeout_seconds,
                )
                delivery.latency_ms = (time.perf_counter() - t0) * 1000
                delivery.status = resp.status_code
                delivery.response_body = resp.text[:1000]

                if 200 <= resp.status_code < 300:
                    delivery.success = True
                    reg.success_count += 1
                    reg.last_triggered_at = delivery.sent_at
                    return delivery

                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except httpx.TimeoutException:
                last_error = "Timeout"
            except Exception as e:
                last_error = str(e)

            # 指数退避
            if attempt < reg.max_retries:
                delay = min(2 ** attempt, 30)
                await asyncio.sleep(delay)

        delivery.success = False
        delivery.error_message = last_error
        reg.failure_count += 1
        return delivery

    def _log_delivery(self, delivery: WebhookDelivery) -> None:
        self._delivery_log.append(delivery)
        if len(self._delivery_log) > self._max_log_entries:
            self._delivery_log = self._delivery_log[-self._max_log_entries:]

    def get_delivery_log(
        self,
        webhook_id: str = "",
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        """获取投递日志"""
        log = self._delivery_log
        if webhook_id:
            log = [d for d in log if d.webhook_id == webhook_id]
        return log[-limit:]

    async def test_webhook(self, webhook_id: str) -> WebhookDelivery:
        """发送测试事件"""
        reg = self._registrations.get(webhook_id)
        if not reg:
            raise ValueError(f"Webhook {webhook_id} 不存在")

        test_event = WebhookEvent(
            type=WebhookEventType.CHAT_COMPLETED,
            payload={"test": True, "message": "Webhook 测试事件"},
        )
        return await self._deliver(reg, test_event, None)

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── 辅助函数 ─────────────────────────────────────

def _generate_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _generate_secret() -> str:
    import secrets
    return secrets.token_hex(16)


def _sign_body(body: str, secret: str) -> str:
    """HMAC-SHA256 签名"""
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


# ── 全局单例 ─────────────────────────────────────

_webhook_manager: WebhookManager | None = None


def get_webhook_manager() -> WebhookManager:
    """获取全局 WebhookManager 单例"""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager
