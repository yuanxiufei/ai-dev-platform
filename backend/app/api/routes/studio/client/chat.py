"""
Studio — AI 对话 API

提供 AI 对话编程的核心能力：
  - SSE 流式对话（实时输出）
  - 历史消息查询
  - 支持截图→代码（Vision + Code Generation）

对话流程：
  1. 用户发送消息 → ModelRouter 自动选择最优模型
  2. 本地可用 → 本地推理（快速、免费）
  3. 本地不可用 → 第三方 API（OpenAI/Claude/DeepSeek/智谱）
  4. API 不可用 → 内置兜底模型
  5. 流式输出（SSE）→ 前端实时渲染
"""

import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models.studio_models import (
    ChatSession,
    ChatMessage,
    MessageRole,
)

router = APIRouter(prefix="/studio/chat", tags=["studio-chat"])


# ── 任务类型自动检测 ─────────────────────────────────────

def _detect_task_type(message: str) -> str:
    """根据用户消息自动识别子任务类型，用于模型路由精排。

    优先级规则：UI 关键词 > 后端关键词 > 通用
    """
    lower = message.lower()

    # UI / 前端关键词 — 匹配后返回 ui_design
    ui_kw = [
        "页面", "组件", "ui", "界面", "样式", "按钮", "表单", "布局",
        "前端", "vue", "react", "html", "css", "前端页面", "设计",
        "导航栏", "侧边栏", "卡片", "列表", "弹窗", "模态框", "对话框",
        "登录页", "注册页", "首页", "仪表盘", "dashboard", "landing",
        "响应式", "动画", "过渡", "tailwind", "bootstrap", "element",
        "antd", "arco", "vant", "naive", "tdesign",
    ]
    # 后端关键词
    backend_kw = [
        "api", "接口", "后端", "数据库", "sql", "后端代码",
        "服务端", "服务器", "fastapi", "express", "路由", "中间件",
        "orm", "migration", "迁移", "schema", "认证", "jwt",
        "oauth", "权限", "crud", "rest", "graphql", "微服务",
        "redis", "postgresql", "mysql", "mongodb", "docker",
    ]

    ui_score = sum(1 for kw in ui_kw if kw in lower)
    backend_score = sum(1 for kw in backend_kw if kw in lower)

    if ui_score > backend_score:
        return "ui_design"
    elif backend_score > ui_score:
        return "backend_code"
    return "general_code"


# ── Schemas ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    """发送消息请求"""
    session_id: uuid.UUID | None = None
    message: str = Field(..., min_length=1, max_length=10000)
    preferred_model: str | None = None
    project_id: uuid.UUID | None = None
    system_prompt: str | None = None
    images_base64: list[str] | None = None  # 截图→代码：base64 图片列表

class ChatResponse(BaseModel):
    """消息响应"""
    message_id: uuid.UUID
    session_id: uuid.UUID
    content: str
    role: str
    model_used: str | None = None
    provider: str | None = None
    is_fallback: bool = False
    latency_ms: int = 0


# ── 对话 ─────────────────────────────────────────────────

@router.post("")
async def chat(
    chat_in: ChatRequest,
    session: SessionDep,
    user: CurrentUser,
) -> ChatResponse:
    """
    发送对话消息（非流式）

    自动选择最优模型，记录会话历史
    """
    # 获取或创建会话
    chat_session = None
    if chat_in.session_id:
        chat_session = session.get(ChatSession, chat_in.session_id)
        if not chat_session or chat_session.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")

    if not chat_session:
        chat_session = ChatSession(
            title=chat_in.message[:50] + "..." if len(chat_in.message) > 50 else chat_in.message,
            project_id=chat_in.project_id,
            owner_id=user.id,
        )
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

    # 获取历史消息
    history = []
    if chat_in.session_id:
        messages = session.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at.asc())
            .limit(20)
        ).all()
        history = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

    # 保存用户消息
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.USER,
        content=chat_in.message,
    )
    session.add(user_msg)
    session.commit()

    # 通过 ModelRouter 调度
    from app.core.model_router import (
        ModelRequest,
        ModelCapability,
        ModelResponse,
    )

    # 判断是否有图片（截图→代码）
    capability = ModelCapability.CODE_GENERATION
    if chat_in.images_base64:
        capability = ModelCapability.VISION_LANGUAGE
        import base64
        images = [base64.b64decode(img) for img in chat_in.images_base64]
    else:
        images = None

    request = ModelRequest(
        capability=capability,
        prompt=chat_in.message,
        system_prompt=chat_in.system_prompt or "",
        preferred_model=chat_in.preferred_model,
        history=history,
        images=images,
        task_type=_detect_task_type(chat_in.message),
    )

    response: ModelResponse
    try:
        from app.core.model_router import get_model_router
        router = get_model_router()
        response = await router.generate(request)
    except Exception as e:
        # 如果路由器不可用，返回一条错误消息
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role=MessageRole.ASSISTANT,
            content=f"服务暂时不可用：{str(e)}",
        )
        session.add(assistant_msg)
        session.commit()
        session.refresh(assistant_msg)

        return ChatResponse(
            message_id=assistant_msg.id,
            session_id=chat_session.id,
            content=assistant_msg.content,
            role="assistant",
        )

    # 保存助手消息
    assistant_msg = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.ASSISTANT,
        content=response.content,
        metadata_={
            "model_used": response.model_used,
            "provider": response.provider,
            "tokens_used": response.tokens_used,
            "latency_ms": response.latency_ms,
            "is_fallback": response.is_fallback,
        },
    )
    session.add(assistant_msg)

    # 更新模型信息到会话
    chat_session.model_name = response.model_used
    session.add(chat_session)
    session.commit()
    session.refresh(assistant_msg)

    return ChatResponse(
        message_id=assistant_msg.id,
        session_id=chat_session.id,
        content=response.content,
        role="assistant",
        model_used=response.model_used,
        provider=response.provider,
        is_fallback=response.is_fallback,
        latency_ms=response.latency_ms,
    )


@router.post("/stream")
async def chat_stream(
    chat_in: ChatRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """
    SSE 流式对话

    实时推送生成内容，前端可逐字显示
    """
    # 获取或创建会话
    chat_session = None
    if chat_in.session_id:
        chat_session = session.get(ChatSession, chat_in.session_id)
        if not chat_session or chat_session.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Session not found")

    if not chat_session:
        chat_session = ChatSession(
            title=chat_in.message[:50] + "...",
            project_id=chat_in.project_id,
            owner_id=user.id,
        )
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

    # 保存用户消息
    user_msg = ChatMessage(
        session_id=chat_session.id,
        role=MessageRole.USER,
        content=chat_in.message,
    )
    session.add(user_msg)
    session.commit()

    async def event_stream():
        from app.core.model_router import (
            ModelRequest,
            ModelCapability,
            get_model_router,
        )

        request = ModelRequest(
            capability=ModelCapability.CODE_GENERATION,
            prompt=chat_in.message,
            system_prompt=chat_in.system_prompt or "",
            preferred_model=chat_in.preferred_model,
            task_type=_detect_task_type(chat_in.message),
        )

        try:
            router = get_model_router()
            response = await router.generate(request)

            # 流式输出内容
            for i in range(0, len(response.content), 10):
                chunk = response.content[i:i+10]
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            yield f"data: {json.dumps({'done': True, 'model_used': response.model_used, 'provider': response.provider, 'latency_ms': response.latency_ms})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/messages")
def get_history(
    session_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, le=200),
):
    """获取对话历史"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session or chat_session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    ).all()

    return {
        "session_id": str(session_id),
        "title": chat_session.title,
        "model_name": chat_session.model_name,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value,
                "content": m.content,
                "metadata": m.metadata_,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
