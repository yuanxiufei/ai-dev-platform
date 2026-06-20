"""
Skills API — Markdown 技能指令管理 + 执行 (借鉴 Open WebUI Skills)

端点:
- POST   /skills/load          — 从 skills/ 目录加载所有技能
- GET    /skills               — 列出所有技能（可按 category 过滤）
- GET    /skills/categories    — 列出所有分类
- POST   /skills               — 创建/保存新技能
- GET    /skills/{name}        — 获取技能详情
- PUT    /skills/{name}        — 更新技能
- DELETE /skills/{name}        — 删除技能
- POST   /skills/apply         — 将技能注入为 system prompt
- POST   /skills/{name}/toggle — 启用/禁用技能
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.skills import (
    get_skills_registry,
    SkillsRegistry,
    Skill,
    parse_skill,
)

router = APIRouter(prefix="/skills", tags=["Skills"])


class SkillData(BaseModel):
    name: str = Field(..., description="技能名称（唯一标识）")
    description: str = Field(default="", description="技能描述")
    category: str = Field(default="general", description="分类")
    content: str = Field(..., description="Markdown 指令内容")
    author: str = Field(default="")
    version: str = Field(default="1.0")
    tags: list[str] = Field(default_factory=list)


class SkillApplyRequest(BaseModel):
    skills: list[str] = Field(..., description="要应用的技能名称列表")


class SkillMarkdownInput(BaseModel):
    markdown: str = Field(..., description="Markdown 格式的技能文本")


def _get_skill_or_404(registry: SkillsRegistry, name: str) -> Skill:
    skill = registry.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return skill


@router.post("/load")
async def load_skills() -> dict:
    """从 skills/ 目录重新加载所有技能"""
    registry = get_skills_registry()
    count = registry.load_all()
    return {"message": f"Loaded {count} skills", "count": count, "categories": registry.list_categories()}


@router.get("")
async def list_skills(category: str = Query(default=None, description="按分类过滤")) -> dict:
    registry = get_skills_registry()
    return {"skills": registry.list_all(category=category), "count": registry.count}


@router.get("/categories")
async def list_categories() -> dict:
    return {"categories": get_skills_registry().list_categories()}


@router.post("")
async def create_skill(data: SkillData) -> dict:
    registry = get_skills_registry()
    if registry.get(data.name):
        raise HTTPException(status_code=409, detail=f"Skill '{data.name}' already exists")
    skill = Skill(
        name=data.name,
        description=data.description,
        category=data.category,
        content=data.content,
        author=data.author,
        version=data.version,
        tags=data.tags,
    )
    path = registry.save_skill(skill)
    return {"skill": skill.to_dict(), "path": path}


@router.post("/parse-markdown")
async def parse_markdown(data: SkillMarkdownInput) -> dict:
    """预览解析 Markdown 文本为技能"""
    skill = parse_skill(data.markdown)
    if not skill:
        raise HTTPException(status_code=400, detail="Invalid skill markdown format")
    return {"skill": skill.to_dict()}


@router.get("/{name}")
async def get_skill(name: str) -> dict:
    registry = get_skills_registry()
    skill = _get_skill_or_404(registry, name)
    return {"skill": skill.to_dict()}


@router.put("/{name}")
async def update_skill(name: str, data: SkillData) -> dict:
    registry = get_skills_registry()
    _get_skill_or_404(registry, name)
    skill = Skill(
        name=data.name,
        description=data.description,
        category=data.category,
        content=data.content,
        author=data.author,
        version=data.version,
        tags=data.tags,
    )
    # 重命名时删除旧文件
    if data.name != name:
        registry.delete_skill(name)
    path = registry.save_skill(skill)
    return {"skill": skill.to_dict(), "path": path}


@router.delete("/{name}")
async def delete_skill(name: str) -> dict:
    registry = get_skills_registry()
    if not registry.delete_skill(name):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"message": f"Skill '{name}' deleted"}


@router.post("/{name}/toggle")
async def toggle_skill(name: str) -> dict:
    registry = get_skills_registry()
    skill = _get_skill_or_404(registry, name)
    skill.enabled = not skill.enabled
    registry.save_skill(skill)
    return {"name": name, "enabled": skill.enabled}


@router.post("/apply")
async def apply_skills(data: SkillApplyRequest) -> dict:
    """将多个技能组合为 system prompt"""
    registry = get_skills_registry()
    invalid = [n for n in data.skills if not registry.get(n)]
    if invalid:
        raise HTTPException(status_code=404, detail=f"Skills not found: {', '.join(invalid)}")
    prompt = registry.build_system_prompt(data.skills)
    # 更新使用计数
    for name in data.skills:
        skill = registry.get(name)
        if skill:
            skill.usage_count += 1
    return {"system_prompt": prompt, "skills_applied": len(data.skills)}
