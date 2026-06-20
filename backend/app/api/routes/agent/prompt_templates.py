"""
Prompt Templates API — 斜杠命令模板管理 (借鉴 Open WebUI Prompt Templates)

端点:
- GET    /prompt-templates            — 列出所有模板
- GET    /prompt-templates/categories — 列出分类
- POST   /prompt-templates            — 创建模板
- GET    /prompt-templates/{id}       — 获取模板
- PUT    /prompt-templates/{id}       — 更新模板
- DELETE /prompt-templates/{id}       — 删除模板
- POST   /prompt-templates/{id}/resolve  — 解析模板（填充变量）
- GET    /prompt-templates/search?q=   — 搜索斜杠命令（用于自动补全）
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.prompt_templates import get_template_registry, TemplateRegistry

router = APIRouter(prefix="/prompt-templates", tags=["Prompt Templates"])


class TemplateVariableDef(BaseModel):
    type: str = "string"
    default: str | int | float | bool = ""
    description: str = ""
    required: bool = False
    options: list[str] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    command: str = Field(..., description="斜杠命令，如 /gen-api")
    title: str = Field(..., description="模板标题")
    prompt: str = Field(..., description="模板文本，使用 {{ variable }} 格式")
    variables: dict[str, TemplateVariableDef] = Field(default_factory=dict)
    category: str = "general"
    description: str = ""
    icon: str = ""
    tags: list[str] = Field(default_factory=list)
    is_public: bool = True


class TemplateUpdate(BaseModel):
    command: str | None = None
    title: str | None = None
    prompt: str | None = None
    variables: dict[str, TemplateVariableDef] | None = None
    category: str | None = None
    description: str | None = None
    icon: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None


class TemplateResolve(BaseModel):
    values: dict[str, str | int | float | bool] = Field(default_factory=dict)


def _get_or_404(registry: TemplateRegistry, tpl_id: str):
    tpl = registry.get(tpl_id)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"Template '{tpl_id}' not found")
    return tpl


@router.get("")
async def list_templates(
    category: str = Query(default=None),
    search: str = Query(default=None),
) -> dict:
    registry = get_template_registry()
    return {"templates": registry.list_all(category=category, search=search), "count": registry.count}


@router.get("/categories")
async def list_categories() -> dict:
    return {"categories": get_template_registry().list_categories()}


@router.get("/search")
async def search_commands(q: str = Query(default="", description="搜索查询")) -> dict:
    registry = get_template_registry()
    return {"commands": registry.search_commands(q)}


@router.post("")
async def create_template(data: TemplateCreate) -> dict:
    registry = get_template_registry()
    tpl = registry.create(data.model_dump())
    return {"template": tpl.to_dict()}


@router.get("/{tpl_id}")
async def get_template(tpl_id: str) -> dict:
    tpl = _get_or_404(get_template_registry(), tpl_id)
    return {"template": tpl.to_dict(), "variable_names": list(tpl.variables.keys())}


@router.put("/{tpl_id}")
async def update_template(tpl_id: str, data: TemplateUpdate) -> dict:
    registry = get_template_registry()
    _get_or_404(registry, tpl_id)
    tpl = registry.update(tpl_id, data.model_dump(exclude_none=True))
    return {"template": tpl.to_dict()}


@router.delete("/{tpl_id}")
async def delete_template(tpl_id: str) -> dict:
    registry = get_template_registry()
    if not registry.delete(tpl_id):
        raise HTTPException(status_code=404, detail=f"Template '{tpl_id}' not found")
    return {"message": f"Template '{tpl_id}' deleted"}


@router.post("/{tpl_id}/resolve")
async def resolve_template(tpl_id: str, data: TemplateResolve) -> dict:
    registry = get_template_registry()
    tpl = _get_or_404(registry, tpl_id)
    resolved = registry.resolve(tpl_id, data.values)
    return {
        "template_id": tpl_id,
        "command": tpl.command,
        "resolved_prompt": resolved,
        "variables_used": list(data.values.keys()),
    }
