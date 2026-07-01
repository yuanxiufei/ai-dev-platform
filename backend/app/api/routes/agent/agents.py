"""
Agent Management API — Agent 完整配置管理 CRUD

端点:
- GET    /agents              — 列出所有 Agent（支持 scope/mode 筛选）
- GET    /agents/{id}         — 获取单个 Agent
- POST   /agents              — 创建 Agent
- PUT    /agents/{id}         — 更新 Agent
- DELETE /agents/{id}         — 删除 Agent
- POST   /agents/{id}/toggle  — 启用/禁用
- POST   /agents/{id}/clone   — 克隆 Agent
- GET    /agents/tools-metadata — 获取工具分类元数据（含 categories 和 MCP 状态）
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db, commit_or_rollback
from app.models.system_models import AgentConfig

router = APIRouter(prefix="/agents", tags=["Agent Management"])


# ── Schemas ──────────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    mode: str = Field(default="craft", pattern="^(craft|ask|plan)$")
    agentic_mode: str = Field(default="agentic", pattern="^(agentic|manual)$")
    model: str = Field(default="auto", max_length=100)
    system_prompt: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)
    tool_categories: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    auto_run: bool = True
    enabled: bool = True
    sort_order: int = 0
    scope: str = Field(default="user", pattern="^(user|project)$")
    project_id: uuid.UUID | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    mode: str | None = Field(default=None, pattern="^(craft|ask|plan)$")
    agentic_mode: str | None = Field(default=None, pattern="^(agentic|manual)$")
    model: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = None
    tools: list[str] | None = None
    tool_categories: list[str] | None = None
    mcp_servers: list[str] | None = None
    auto_run: bool | None = None
    enabled: bool | None = None
    sort_order: int | None = None
    scope: str | None = None
    project_id: uuid.UUID | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    mode: str
    agentic_mode: str
    model: str
    system_prompt: str | None
    tools: list[str] | None
    tool_categories: list[str] | None
    mcp_servers: list[str] | None
    auto_run: bool
    enabled: bool
    sort_order: int
    scope: str
    project_id: uuid.UUID | None
    created_at: str | None
    updated_at: str | None


def _safe_json_load(val: Any) -> list | None:
    """安全解析 JSON 字段"""
    if val is None:
        return None
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return None


def _agent_to_response(a: AgentConfig) -> AgentResponse:
    return AgentResponse(
        id=a.id,
        name=a.name,
        description=a.description,
        mode=a.mode,
        agentic_mode=getattr(a, "agentic_mode", None) or "agentic",
        model=a.model or "auto",
        system_prompt=a.system_prompt,
        tools=_safe_json_load(a.tools),
        tool_categories=_safe_json_load(getattr(a, "tool_categories", None)),
        mcp_servers=_safe_json_load(getattr(a, "mcp_servers", None)),
        auto_run=getattr(a, "auto_run", True),
        enabled=a.enabled,
        sort_order=a.sort_order,
        scope=getattr(a, "scope", None) or "user",
        project_id=getattr(a, "project_id", None),
        created_at=a.created_at.isoformat() if a.created_at else None,
        updated_at=a.updated_at.isoformat() if a.updated_at else None,
    )


# ── Tools Metadata ───────────────────────────────────────

# 内置工具元数据：按 category 分组，附带 id / name / description / enabled 标记
_BUILTIN_TOOL_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "read",
        "name": "Read",
        "label": "读取",
        "icon": "FileText",
        "description": "读取文件和搜索代码库",
        "tools": [
            {"id": "filesystem-read", "name": "FileSystem Read", "description": "读取项目文件内容，支持多种编码格式", "enabled": True},
            {"id": "code-search", "name": "Code Search", "description": "在代码库中搜索符号、引用和定义", "enabled": True},
            {"id": "find", "name": "Find", "description": "通过 glob 模式匹配查找文件", "enabled": True},
            {"id": "list-dir", "name": "List Directory", "description": "列出目录中的文件和子目录", "enabled": True},
        ],
    },
    {
        "id": "edit",
        "name": "Edit",
        "label": "编辑",
        "icon": "Edit3",
        "description": "修改和写入文件",
        "tools": [
            {"id": "filesystem-write", "name": "FileSystem Write", "description": "创建或覆盖文件内容", "enabled": True},
            {"id": "replace-in-file", "name": "Replace In File", "description": "在文件中精确替换文本内容", "enabled": True},
            {"id": "delete-file", "name": "Delete File", "description": "删除指定路径的文件", "enabled": True},
        ],
    },
    {
        "id": "execute",
        "name": "Execute",
        "label": "执行",
        "icon": "Terminal",
        "description": "运行命令和脚本",
        "tools": [
            {"id": "bash", "name": "Bash Shell", "description": "在终端中执行 shell 命令", "enabled": True},
            {"id": "git", "name": "Git", "description": "Git 版本控制操作（commit/push/branch 等）", "enabled": True},
            {"id": "task", "name": "Sub Agent", "description": "启动子 Agent 处理复杂多步骤任务", "enabled": True},
        ],
    },
    {
        "id": "web",
        "name": "Web",
        "label": "网页",
        "icon": "Globe",
        "description": "网络访问与搜索",
        "tools": [
            {"id": "web-fetch", "name": "Web Fetch", "description": "获取并解析远程网页内容", "enabled": True},
            {"id": "web-search", "name": "Web Search", "description": "在线搜索最新信息", "enabled": True},
            {"id": "preview-url", "name": "Preview URL", "description": "在 IDE 内置浏览器中预览网页", "enabled": False},
        ],
    },
    {
        "id": "skills",
        "name": "Skills",
        "label": "技能",
        "icon": "Sparkles",
        "description": "领域专用技能扩展",
        "tools": [
            {"id": "pdf", "name": "PDF 处理", "description": "读取、合并、拆分、加水印 PDF 文件", "enabled": False},
            {"id": "xlsx", "name": "Excel 处理", "description": "创建、编辑、分析 Excel 电子表格", "enabled": False},
            {"id": "docx", "name": "Word 处理", "description": "创建和编辑 Word 文档", "enabled": False},
            {"id": "pptx", "name": "PPT 处理", "description": "创建演示文稿幻灯片", "enabled": False},
            {"id": "image-gen", "name": "图像生成", "description": "通过 AI 生成图片", "enabled": False},
            {"id": "agent-browser", "name": "浏览器自动化", "description": "自动打开网页、截图、提取内容", "enabled": False},
            {"id": "model-router", "name": "模型路由", "description": "智能模型调度与回退代理", "enabled": False},
            {"id": "find-skills", "name": "技能发现", "description": "搜索和安装可用技能扩展", "enabled": False},
        ],
    },
    {
        "id": "others",
        "name": "Others",
        "label": "其他",
        "icon": "Wrench",
        "description": "其他辅助工具",
        "tools": [
            {"id": "rag-retrieval", "name": "知识库检索", "description": "从 RAG 知识库中检索相关文档", "enabled": False},
            {"id": "voice", "name": "语音", "description": "文字转语音 / 语音转文字", "enabled": False},
            {"id": "deploy", "name": "部署", "description": "部署项目到云端服务", "enabled": False},
            {"id": "integrations", "name": "集成服务", "description": "连接数据库/存储等第三方服务", "enabled": False},
        ],
    },
]


# ── Endpoints ────────────────────────────────────────────

_AGENTS_MAX_LIST = 200

@router.get("")
async def list_agents(
    mode: str | None = Query(None),
    scope: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """列出所有 Agent，支持按 mode / scope 筛选"""
    stmt = select(AgentConfig).where(AgentConfig.user_id == current_user.id)
    if mode:
        stmt = stmt.where(AgentConfig.mode == mode)
    if scope:
        stmt = stmt.where(AgentConfig.scope == scope)
    items = db.exec(
        stmt.order_by(AgentConfig.sort_order, AgentConfig.created_at.desc())
        .limit(_AGENTS_MAX_LIST)
    ).all()
    return {"data": [_agent_to_response(a).model_dump() for a in items], "total": len(items)}


@router.get("/tools-metadata")
async def get_tools_metadata(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    返回工具分类元数据 — 所有内置工具按 category 分组（Read/Edit/Execute/Web/Skills/Others）。

    同时查询当前用户的 MCP 服务器连接状态和已注册工具。
    """
    categories = _BUILTIN_TOOL_CATEGORIES

    # MCP 状态 — 尝试从 MCP 管理器获取
    mcp_servers: list[dict[str, Any]] = []
    mcp_tools: list[dict[str, Any]] = []
    mcp_connected = False
    try:
        from app.core.mcp import MCPManager
        # 尝试获取已初始化的管理器
        from app.api.routes.agent.mcp_servers import get_mcp_manager
        mgr = get_mcp_manager()
        mcp_connected = mgr.is_connected
        mcp_servers = [
            {
                "name": s.name,
                "transport": s.transport.value if hasattr(s.transport, "value") else str(s.transport),
                "url": s.url if hasattr(s, "url") else "",
                "connected": True,
            }
            for s in mgr.servers
        ]
        mcp_tools = [
            {"name": t.name, "description": t.description, "server": getattr(t, "server_name", "")}
            for t in mgr.tools
        ]
    except Exception:
        pass

    return {
        "categories": categories,
        "mcp": {
            "connected": mcp_connected,
            "servers": mcp_servers,
            "tools": mcp_tools,
        },
    }


@router.get("/{agent_id}")
async def get_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """获取单个 Agent"""
    agent = db.get(AgentConfig, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    return {"data": _agent_to_response(agent).model_dump()}


@router.post("")
async def create_agent(
    body: AgentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """创建 Agent"""
    agent = AgentConfig(
        name=body.name,
        description=body.description,
        mode=body.mode,
        agentic_mode=body.agentic_mode,
        model=body.model,
        system_prompt=body.system_prompt,
        tools=json.dumps(body.tools) if body.tools else None,
        tool_categories=json.dumps(body.tool_categories) if body.tool_categories else None,
        mcp_servers=json.dumps(body.mcp_servers) if body.mcp_servers else None,
        auto_run=body.auto_run,
        enabled=body.enabled,
        sort_order=body.sort_order,
        scope=body.scope,
        project_id=body.project_id,
        user_id=current_user.id,
    )
    db.add(agent)
    commit_or_rollback(db)
    db.refresh(agent)
    return {"data": _agent_to_response(agent).model_dump(), "message": "Agent 已创建"}


@router.put("/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """更新 Agent"""
    agent = db.get(AgentConfig, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    for field_name in (
        "name", "description", "mode", "agentic_mode", "model",
        "system_prompt", "auto_run", "enabled", "sort_order", "scope",
    ):
        val = getattr(body, field_name, None)
        if val is not None and hasattr(agent, field_name):
            setattr(agent, field_name, val)

    if body.tools is not None:
        agent.tools = json.dumps(body.tools)
    if body.tool_categories is not None:
        agent.tool_categories = json.dumps(body.tool_categories)
    if body.mcp_servers is not None:
        agent.mcp_servers = json.dumps(body.mcp_servers)
    if body.project_id is not None:
        agent.project_id = body.project_id

    agent.updated_at = datetime.now(timezone.utc)
    db.add(agent)
    commit_or_rollback(db)
    db.refresh(agent)
    return {"data": _agent_to_response(agent).model_dump(), "message": "Agent 已更新"}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """删除 Agent"""
    agent = db.get(AgentConfig, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    db.delete(agent)
    commit_or_rollback(db)
    return {"message": "Agent 已删除", "ok": True}


@router.post("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """启用/禁用 Agent"""
    agent = db.get(AgentConfig, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent 不存在")
    agent.enabled = not agent.enabled
    agent.updated_at = datetime.now(timezone.utc)
    db.add(agent)
    commit_or_rollback(db)
    db.refresh(agent)
    return {"name": agent.name, "enabled": agent.enabled}


@router.post("/{agent_id}/clone")
async def clone_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """克隆 Agent"""
    agent = db.get(AgentConfig, agent_id)
    if not agent or agent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Agent 不存在")

    clone = AgentConfig(
        name=f"{agent.name} (副本)",
        description=agent.description,
        mode=agent.mode,
        agentic_mode=getattr(agent, "agentic_mode", "agentic"),
        model=agent.model,
        system_prompt=agent.system_prompt,
        tools=agent.tools,
        tool_categories=getattr(agent, "tool_categories", None),
        mcp_servers=getattr(agent, "mcp_servers", None),
        auto_run=getattr(agent, "auto_run", True),
        enabled=False,
        sort_order=agent.sort_order + 1,
        scope=getattr(agent, "scope", "user"),
        project_id=getattr(agent, "project_id", None),
        user_id=current_user.id,
    )
    db.add(clone)
    commit_or_rollback(db)
    db.refresh(clone)
    return {"data": _agent_to_response(clone).model_dump(), "message": "Agent 已克隆"}
