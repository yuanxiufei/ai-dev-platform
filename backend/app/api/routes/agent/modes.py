"""
Agent Modes API — Custom Modes 管理路由

提供:
- GET  /agent/modes              — 列出所有模式
- GET  /agent/modes/{slug}       — 获取单个模式
- POST /agent/modes              — 创建自定义模式
- PUT  /agent/modes/{slug}       — 更新模式
- DELETE /agent/modes/{slug}     — 删除自定义模式
- POST /agent/modes/load         — 从 .roomodes 文件加载
- POST /agent/modes/activate     — 激活模式（生成 AgentConfig）
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.agent.agent_modes import AgentMode, ModeManager, get_mode_manager

router = APIRouter(prefix="/agent/modes", tags=["Agent Modes"])


class ModeCreateRequest(BaseModel):
    slug: str
    name: str
    description: str = ""
    role_instructions: str = ""
    tools: list[str] = []
    tool_categories: list[str] = []
    preferred_model: str = ""
    temperature: float = 0.7
    max_turns: int = 10
    icon: str = "🤖"
    color: str = "#6366f1"


class ModeUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    role_instructions: str | None = None
    tools: list[str] | None = None
    tool_categories: list[str] | None = None
    preferred_model: str | None = None
    temperature: float | None = None
    max_turns: int | None = None
    icon: str | None = None
    color: str | None = None


class LoadFileRequest(BaseModel):
    filepath: str = ".roomodes"


class ActivateRequest(BaseModel):
    slug: str


def _get_mgr() -> ModeManager:
    return get_mode_manager()


@router.get("")
async def list_modes():
    """列出所有可用模式"""
    mgr = _get_mgr()
    return {"data": mgr.list_all(), "total": mgr.count}


@router.get("/{slug}")
async def get_mode(slug: str):
    """获取单个模式详情"""
    mgr = _get_mgr()
    mode = mgr.get(slug)
    if not mode:
        raise HTTPException(status_code=404, detail=f"Mode not found: {slug}")
    return mode.to_dict()


@router.post("")
async def create_mode(req: ModeCreateRequest):
    """创建自定义模式"""
    mgr = _get_mgr()
    if mgr.get(req.slug):
        raise HTTPException(status_code=409, detail=f"Mode already exists: {req.slug}")

    mode = AgentMode(
        slug=req.slug,
        name=req.name,
        description=req.description,
        role_instructions=req.role_instructions,
        tools=req.tools,
        tool_categories=req.tool_categories,
        preferred_model=req.preferred_model,
        temperature=req.temperature,
        max_turns=req.max_turns,
        icon=req.icon,
        color=req.color,
    )
    mgr.register(mode)
    return {"data": mode.to_dict(), "message": f"Mode created: {req.slug}"}


@router.put("/{slug}")
async def update_mode(slug: str, req: ModeUpdateRequest):
    """更新自定义模式"""
    mgr = _get_mgr()
    mode = mgr.get(slug)
    if not mode:
        raise HTTPException(status_code=404, detail=f"Mode not found: {slug}")

    if req.name is not None:
        mode.name = req.name
    if req.description is not None:
        mode.description = req.description
    if req.role_instructions is not None:
        mode.role_instructions = req.role_instructions
    if req.tools is not None:
        mode.tools = req.tools
    if req.tool_categories is not None:
        mode.tool_categories = req.tool_categories
    if req.preferred_model is not None:
        mode.preferred_model = req.preferred_model
    if req.temperature is not None:
        mode.temperature = req.temperature
    if req.max_turns is not None:
        mode.max_turns = req.max_turns
    if req.icon is not None:
        mode.icon = req.icon
    if req.color is not None:
        mode.color = req.color

    return {"data": mode.to_dict(), "message": f"Mode updated: {slug}"}


@router.delete("/{slug}")
async def delete_mode(slug: str):
    """删除自定义模式"""
    mgr = _get_mgr()
    # 不允许删除预设模式
    from app.core.agent.agent_modes import PRESET_MODES
    preset_slugs = {m.slug for m in PRESET_MODES}
    if slug in preset_slugs:
        raise HTTPException(status_code=403, detail=f"Cannot delete preset mode: {slug}")

    if not mgr.unregister(slug):
        raise HTTPException(status_code=404, detail=f"Mode not found: {slug}")
    return {"message": f"Mode deleted: {slug}"}


@router.post("/load")
async def load_modes_file(req: LoadFileRequest):
    """从 .roomodes 文件加载自定义模式"""
    mgr = _get_mgr()
    count = mgr.load_from_file(req.filepath)
    return {"data": {"loaded": count}, "message": f"Loaded {count} modes from {req.filepath}"}


@router.post("/activate")
async def activate_mode(req: ActivateRequest):
    """激活模式，返回对应的 AgentConfig"""
    mgr = _get_mgr()
    mode = mgr.get(req.slug)
    if not mode:
        raise HTTPException(status_code=404, detail=f"Mode not found: {req.slug}")

    config = mode.to_agent_config()
    return {
        "data": {
            "mode": mode.to_dict(),
            "config": {
                "name": config.name,
                "instructions": config.instructions,
                "tools": config.tools,
                "tool_categories": config.tool_categories,
                "preferred_model": config.preferred_model,
                "max_turns": config.max_turns,
            },
        },
        "message": f"Mode activated: {req.slug}",
    }
