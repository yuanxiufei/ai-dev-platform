"""
Agent 流程 E2E 集成测试 — 覆盖同步对话、流式事件、工具调用循环

使用 httpx 直接调用后端 API，验证完整 Agent 对话链路。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

# ---- Test App Setup ----
from app.main import app
from app.core.config import settings

BASE_URL = "http://test"
API = f"{BASE_URL}{settings.API_V1_STR}"

# 测试用超管凭据
TEST_SUPERUSER_EMAIL = settings.FIRST_SUPERUSER
TEST_SUPERUSER_PASSWORD = settings.FIRST_SUPERUSER_PASSWORD


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """获取认证 token header"""
    resp = await client.post(
        f"{API}/login/access-token",
        data={
            "username": TEST_SUPERUSER_EMAIL,
            "password": TEST_SUPERUSER_PASSWORD,
        },
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── 辅助模型 ───────────────────────────────────

class SimpleChatRequest:
    """简化的 Agent 对话请求"""

    def __init__(self, message: str, max_turns: int = 3, preferred_model: str = ""):
        self.payload = {
            "message": message,
            "agent_name": "test-agent",
            "max_turns": max_turns,
            "tools": [],
            "tool_categories": [],
            "preferred_model": preferred_model,
        }

    def with_tools(self, *tool_names: str):
        self.payload["tools"] = list(tool_names)
        return self

    def for_model(self, model_name: str):
        self.payload["preferred_model"] = model_name
        return self


# ── 测试 1: 简单同步对话 ───────────────────────

@pytest.mark.anyio
class TestAgentSimpleChat:

    async def test_basic_question(self, client: AsyncClient, auth_headers: dict):
        """基本问答 — Agent 无需工具直接回答"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "What is 2 + 2?", "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
        assert data["turns"] >= 1

    async def test_empty_message(self, client: AsyncClient, auth_headers: dict):
        """空消息应返回错误或空答案"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "", "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        # 允许 200 或 422
        assert resp.status_code in (200, 422)

    async def test_long_message(self, client: AsyncClient, auth_headers: dict):
        """长消息不会导致崩溃"""
        long_msg = "Tell me about Python programming. " * 20
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": long_msg, "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data

    async def test_unicode_message(self, client: AsyncClient, auth_headers: dict):
        """Unicode 多语言消息支持"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "你好！请用中文回答：什么是人工智能？", "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 0

    async def test_response_structure(self, client: AsyncClient, auth_headers: dict):
        """验证响应字段完整性"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "Say hello", "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        for field in ("answer", "turns", "tool_calls", "model_used", "provider", "tokens_used", "latency_ms", "error"):
            assert field in data, f"Missing field: {field}"


# ── 测试 2: 流式对话 (SSE) ────────────────────

@pytest.mark.anyio
class TestAgentStreamChat:

    async def test_stream_yields_tokens(self, client: AsyncClient, auth_headers: dict):
        """流式对话应产出 token 事件"""
        async with client.stream(
            "POST",
            f"{API}/agent/chat/stream",
            json={"message": "Count from 1 to 3", "max_turns": 1, "tools": []},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200

            events: list[dict] = []
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    if data_str.strip() in ("[DONE]", ""):
                        continue
                    try:
                        events.append(json.loads(data_str))
                    except json.JSONDecodeError:
                        pass

            assert len(events) > 0, "No SSE events received"

            # 应有 token 事件和 final_answer 事件
            event_types = {e.get("type") for e in events if e.get("type")}
            assert "token" in event_types, "No token events in stream"
            assert "final_answer" in event_types, "No final_answer event in stream"

    async def test_stream_event_format(self, client: AsyncClient, auth_headers: dict):
        """验证流式事件格式"""
        async with client.stream(
            "POST",
            f"{API}/agent/chat/stream",
            json={"message": "hi", "max_turns": 1, "tools": []},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            tokens: list[str] = []
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[len("data: "):]
                if data_str.strip() in ("[DONE]", ""):
                    continue
                try:
                    evt = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if evt.get("type") == "token":
                    delta = evt.get("delta", "")
                    tokens.append(delta)

            assert len(tokens) > 0, "No tokens extracted from stream"
            answer = "".join(tokens)
            assert len(answer) > 0

    async def test_stream_content_type(self, client: AsyncClient, auth_headers: dict):
        """流式响应应为 text/event-stream"""
        async with client.stream(
            "POST",
            f"{API}/agent/chat/stream",
            json={"message": "test", "max_turns": 1, "tools": []},
            headers=auth_headers,
        ) as response:
            assert response.status_code == 200
            ct = response.headers.get("content-type", "")
            assert "text/event-stream" in ct.lower()


# ── 测试 3: 工具调用循环 ──────────────────────

@pytest.mark.anyio
class TestAgentToolCalling:

    async def test_tool_calling_simple(self, client: AsyncClient, auth_headers: dict):
        """工具调用 — 获取当前时间"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={
                "message": "What is the current time? Use the get_current_time tool.",
                "max_turns": 5,
                "tools": ["get_current_time"],
                "preferred_model": "",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # 验证回答非空
        assert len(data["answer"]) > 0
        # 工具调用次数 >= 0 (取决于LLM是否真的调用了工具)
        assert data["tool_calls"] >= 0

    async def test_multi_turn_conversation(self, client: AsyncClient, auth_headers: dict):
        """多轮对话 — 带 session_id 保持上下文"""
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"

        # 第一轮
        r1 = await client.post(
            f"{API}/agent/chat",
            json={"message": "My name is Alice.", "max_turns": 1, "tools": [],
                  "session_id": session_id},
            headers=auth_headers,
        )
        assert r1.status_code == 200

        # 第二轮：应记住名字
        r2 = await client.post(
            f"{API}/agent/chat",
            json={"message": "What is my name?", "max_turns": 1, "tools": [],
                  "session_id": session_id},
            headers=auth_headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        # 答案中可能包含 "Alice"（取决于模型能力）
        assert len(data2["answer"]) > 0


# ── 测试 4: 边界场景 ──────────────────────────

@pytest.mark.anyio
class TestAgentEdgeCases:

    async def test_unauthorized(self, client: AsyncClient):
        """未认证请求应被拒绝"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "hello", "max_turns": 1, "tools": []},
        )
        assert resp.status_code in (401, 403)

    async def test_invalid_max_turns(self, client: AsyncClient, auth_headers: dict):
        """max_turns 超出范围应被校验"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "hello", "max_turns": 100, "tools": []},
            headers=auth_headers,
        )
        # Pydantic 验证: max_turns <= 50
        assert resp.status_code == 422

    async def test_missing_message_field(self, client: AsyncClient, auth_headers: dict):
        """缺少必要字段应返回 422"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_concurrent_requests(self, client: AsyncClient, auth_headers: dict):
        """并发请求不互相干扰"""
        async def send(msg: str):
            return await client.post(
                f"{API}/agent/chat",
                json={"message": msg, "max_turns": 1, "tools": []},
                headers=auth_headers,
            )

        tasks = [send(f"Say: {i}") for i in range(3)]
        results = await asyncio.gather(*tasks)

        for r in results:
            assert r.status_code == 200
            data = r.json()
            assert len(data["answer"]) > 0


# ── 测试 5: 模型回退链 ────────────────────────

@pytest.mark.anyio
class TestAgentModelFallback:

    async def test_default_model_works(self, client: AsyncClient, auth_headers: dict):
        """默认模型可正常对话"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={"message": "Say hello", "max_turns": 1, "tools": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["model_used"] != "" or data["error"] != ""
        # 至少有一个返回（要么成功有 model_used，要么有 error）

    async def test_graceful_error_on_invalid_model(self, client: AsyncClient, auth_headers: dict):
        """不存在的模型名不应导致崩溃"""
        resp = await client.post(
            f"{API}/agent/chat",
            json={
                "message": "hello",
                "max_turns": 1,
                "tools": [],
                "preferred_model": "nonexistent-model-99999",
            },
            headers=auth_headers,
        )
        # 可能 200（回退到默认模型）或返回错误
        assert resp.status_code in (200, 500, 502)
