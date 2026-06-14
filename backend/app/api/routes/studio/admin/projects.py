"""
Studio — 项目管理 API

提供 AI 编程项目的完整生命周期管理：
  - CRUD 操作
  - AI 生成项目（文本→全栈代码）
  - 项目构建与部署
  - 代码导出
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models.studio_models import (
    StudioProject,
    StudioTemplate,
    ProjectStatus,
)

router = APIRouter(prefix="/studio/projects", tags=["studio-projects"])


# ── Schemas ──────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = None
    framework: str = Field(default="vue", max_length=50)
    stack: str = Field(default="fastapi+vue", max_length=100)
    template_id: uuid.UUID | None = None

class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    framework: str | None = None
    stack: str | None = None
    generated_code: dict | None = None
    build_log: str | None = None
    deploy_url: str | None = None

class ProjectGenerate(BaseModel):
    """AI 生成项目请求"""
    description: str = Field(..., min_length=10, max_length=2000)
    framework: str = "vue"
    stack: str = "fastapi+vue"
    use_template: uuid.UUID | None = None
    preferred_model: str | None = None

class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    status: ProjectStatus
    framework: str | None
    stack: str | None
    template_id: uuid.UUID | None
    generated_code: Any | None
    build_log: str | None
    deploy_url: str | None
    owner_id: uuid.UUID
    created_at: Any
    updated_at: Any

class ProjectListResponse(BaseModel):
    data: list[ProjectResponse]
    total: int
    page: int
    size: int


# ── Helpers ──────────────────────────────────────────────

def _project_to_response(p: StudioProject) -> dict:
    code_str = p.generated_code
    parsed_code = None
    if code_str and isinstance(code_str, str):
        try:
            parsed_code = json.loads(code_str)
        except (json.JSONDecodeError, TypeError):
            parsed_code = code_str
    else:
        parsed_code = code_str

    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "status": p.status,
        "framework": p.framework,
        "stack": p.stack,
        "template_id": p.template_id,
        "generated_code": parsed_code,
        "build_log": p.build_log,
        "deploy_url": p.deploy_url,
        "owner_id": p.owner_id,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# ── CRUD ─────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
def list_projects(
    session: SessionDep,
    user: CurrentUser,
    page: int = 1,
    size: int = 20,
    status: ProjectStatus | None = None,
    framework: str | None = None,
):
    """获取项目列表（分页+筛选）"""
    stmt = select(StudioProject).where(
        StudioProject.owner_id == user.id
    )

    if status:
        stmt = stmt.where(StudioProject.status == status)
    if framework:
        stmt = stmt.where(StudioProject.framework == framework)

    total = len(session.exec(stmt).all())
    projects = session.exec(
        stmt.order_by(StudioProject.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [_project_to_response(p) for p in projects],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", response_model=dict, status_code=201)
def create_project(
    project_in: ProjectCreate,
    session: SessionDep,
    user: CurrentUser,
):
    """创建新项目"""
    project = StudioProject(
        name=project_in.name,
        description=project_in.description,
        framework=project_in.framework,
        stack=project_in.stack,
        owner_id=user.id,
    )

    # 如果指定了模板，关联模板
    if project_in.template_id:
        template = session.get(StudioTemplate, project_in.template_id)
        if template:
            project.template_id = template.id
            # 复制模板代码
            if template.template_data:
                project.generated_code = template.template_data
            template.usage_count += 1

    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)


@router.get("/{project_id}", response_model=dict)
def get_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """获取项目详情"""
    project = session.get(StudioProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    return _project_to_response(project)


@router.put("/{project_id}", response_model=dict)
def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
    session: SessionDep,
    user: CurrentUser,
):
    """更新项目"""
    project = session.get(StudioProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = project_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)

    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """删除项目"""
    project = session.get(StudioProject, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    session.delete(project)
    session.commit()


# ── AI 生成 ──────────────────────────────────────────────

@router.post("/generate", response_model=dict)
async def generate_project(
    gen_in: ProjectGenerate,
    session: SessionDep,
    user: CurrentUser,
):
    """
    AI 生成全栈项目（文本→代码）

    流程：
    1. 接收用户需求描述
    2. 通过 ModelRouter 自动选择最优模型（本地优先→API回退）
    3. 生成完整项目结构
    4. 返回代码和预览
    """
    from app.core.model_router import (
        ModelRequest,
        ModelCapability,
        get_model_router,
    )

    # 自动检测任务类型（UI / 后端 / 通用）
    _lower = gen_in.description.lower()
    _ui_score = sum(1 for kw in ["页面","ui","界面","样式","前端","vue","react","设计","组件","布局"] if kw in _lower)
    _be_score = sum(1 for kw in ["api","接口","后端","数据库","sql","服务端","fastapi","后端代码"] if kw in _lower)
    task_type = "ui_design" if _ui_score > _be_score else ("backend_code" if _be_score > _ui_score else "general_code")

    # 构建请求
    request = ModelRequest(
        capability=ModelCapability.CODE_GENERATION,
        prompt=gen_in.description,
        system_prompt=(
            f"你是一个全栈开发专家。请根据需求生成一个完整的 {gen_in.stack} 项目。"
            f"前端使用 {gen_in.framework}。"
            "请返回包含所有文件代码的 JSON 格式："
            '{"files": {"filepath": "code", ...}, "structure": "...", "readme": "..."}'
        ),
        preferred_model=gen_in.preferred_model,
        task_type=task_type,
    )

    try:
        router = get_model_router()
        response = await router.generate(request)

        # 创建项目记录
        project = StudioProject(
            name=f"AI Generated: {gen_in.description[:50]}",
            description=gen_in.description,
            framework=gen_in.framework,
            stack=gen_in.stack,
            status=ProjectStatus.DRAFT,
            generated_code=response.content,
            owner_id=user.id,
        )

        session.add(project)
        session.commit()
        session.refresh(project)

        return {
            "project": _project_to_response(project),
            "model_used": response.model_used,
            "provider": response.provider,
            "is_fallback": response.is_fallback,
            "latency_ms": response.latency_ms,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}",
        )


# ── 构建 / 部署 ──────────────────────────────────────────

@router.post("/{project_id}/build", response_model=dict)
async def build_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """构建项目"""
    project = session.get(StudioProject, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.generated_code:
        raise HTTPException(status_code=400, detail="No generated code to build")

    project.status = ProjectStatus.BUILDING
    session.add(project)
    session.commit()

    # TODO: 实际的构建流程（可接入 Docker 构建）
    project.status = ProjectStatus.RUNNING
    project.build_log = "Build completed successfully."
    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)


@router.post("/{project_id}/deploy", response_model=dict)
async def deploy_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """部署项目"""
    project = session.get(StudioProject, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Project must be built first")

    project.status = ProjectStatus.DEPLOYING
    session.add(project)
    session.commit()

    # TODO: 实际部署流程
    project.status = ProjectStatus.RUNNING
    project.deploy_url = f"https://{project.name.lower().replace(' ', '-')}.example.com"
    session.add(project)
    session.commit()
    session.refresh(project)

    return _project_to_response(project)
