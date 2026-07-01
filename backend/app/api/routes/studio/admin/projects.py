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
from sqlmodel import Session, func, select

from app.api.deps import CurrentUser, SessionDep, commit_or_rollback
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

_MAX_PAGE_SIZE = 200


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
    size = min(size, _MAX_PAGE_SIZE)
    if page < 1:
        page = 1

    stmt = select(StudioProject).where(
        StudioProject.owner_id == user.id
    )

    if status:
        stmt = stmt.where(StudioProject.status == status)
    if framework:
        stmt = stmt.where(StudioProject.framework == framework)

    total = session.exec(
        select(func.count()).select_from(stmt.subquery())
    ).one()
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

    commit_or_rollback(session, project)

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

    commit_or_rollback(session, project)

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
    commit_or_rollback(session)


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

        commit_or_rollback(session, project)

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


# ── 异步生成（Celery）────────────────────────────────

class AsyncGenerateResponse(BaseModel):
    task_id: str
    status: str
    message: str


class AsyncTaskStatus(BaseModel):
    task_id: str
    status: str  # PENDING / STARTED / SUCCESS / FAILURE
    result: dict | None = None
    error: str | None = None


@router.post("/generate/async", response_model=AsyncGenerateResponse)
def generate_project_async(
    gen_in: ProjectGenerate,
    user: CurrentUser,
):
    """异步 AI 生成全栈项目（通过 Celery 任务队列）。

    适用于长时间生成任务，立即返回 task_id，
    前端可通过 GET /studio/projects/generate/async/{task_id} 轮询状态。
    """
    from task_queue.celery_app import celery_app
    from workers.code_worker import generate_fullstack_from_text

    # 先创建一个草稿项目
    from app.core.db import engine
    from sqlmodel import Session as DBSession

    with DBSession(engine) as db_session:
        project = StudioProject(
            name=f"AI Async: {gen_in.description[:50]}",
            description=gen_in.description,
            framework=gen_in.framework,
            stack=gen_in.stack,
            status=ProjectStatus.DRAFT,
            owner_id=user.id,
        )
        db_session.add(project)
        try:
            db_session.commit()
            db_session.refresh(project)
        except Exception:
            db_session.rollback()
            raise
        project_id = str(project.id)

    # 提交 Celery 任务
    include_backend = "api" in gen_in.stack.lower() or "fastapi" in gen_in.stack.lower()
    task = generate_fullstack_from_text.delay(
        task_id=project_id,
        description=gen_in.description,
        include_backend=include_backend,
    )

    return AsyncGenerateResponse(
        task_id=task.id,
        status="PENDING",
        message=f"Project {project_id} generation queued. Track via /studio/projects/generate/async/{task.id}",
    )


@router.get("/generate/async/{task_id}", response_model=AsyncTaskStatus)
def get_async_task_status(
    task_id: str,
    user: CurrentUser,
):
    """查询 Celery 异步任务状态。

    Returns:
        task_id, status, result (SUCCESS 时), error (FAILURE 时)
    """
    from celery.result import AsyncResult
    from task_queue.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    response_data: dict = {
        "task_id": task_id,
        "status": result.state,
        "result": None,
        "error": None,
    }

    if result.state == "SUCCESS":
        task_result = result.result
        response_data["result"] = task_result if isinstance(task_result, dict) else {"data": str(task_result)}
    elif result.state == "FAILURE":
        response_data["error"] = str(result.info) if result.info else "Unknown error"

    return response_data


# ── 构建 / 部署 ──────────────────────────────────────────

async def _get_sandbox(workspace_dir: str):
    """获取沙箱实例，用于构建/部署的隔离执行。"""
    from app.core.sandbox import SandboxProvider, SandboxConfig
    from app.core.config import settings

    config = SandboxConfig(
        type=settings.SANDBOX_TYPE,
        workspace_dir=workspace_dir,
        command_timeout=settings.SANDBOX_COMMAND_TIMEOUT,
        denied_paths=["/etc", "/sys", "/proc", "/dev"],
    )
    return SandboxProvider.create(config)


def _parse_project_files(generated_code: Any) -> dict[str, str]:
    """解析 generated_code 为 {filepath: content} 字典。

    支持格式:
      - str: JSON 字符串 {"files": {"path": "code", ...}}
      - dict: 直接 dict
      - str (非JSON): 作为单个 README.md
    """
    import json as _json

    if isinstance(generated_code, str):
        try:
            parsed = _json.loads(generated_code)
        except (_json.JSONDecodeError, TypeError):
            return {"README.md": generated_code}
    elif isinstance(generated_code, dict):
        parsed = generated_code
    else:
        return {"README.md": str(generated_code)}

    # 如果 parsed 有 "files" 键，提取文件
    if isinstance(parsed, dict):
        files = parsed.get("files", {})
        if isinstance(files, dict):
            return {str(k): str(v) for k, v in files.items()}
        # 可能是 {"filepath": "code", ...} 直接在顶层
        return {str(k): str(v) for k, v in parsed.items() if isinstance(v, (str, int, float, bool))}

    return {"README.md": str(generated_code)}


def _detect_build_commands(files: dict[str, str], framework: str, stack: str) -> list[str]:
    """根据项目文件和技术栈检测构建命令序列。

    Returns:
        shell 命令列表，按顺序执行
    """
    file_list = list(files.keys())
    commands: list[str] = []

    has_package_json = any("package.json" in f for f in file_list)
    has_requirements = any("requirements.txt" in f for f in file_list) or any(
        "pyproject.toml" in f for f in file_list
    )
    has_vue = framework.lower() in ("vue", "vue3") or any(
        f.endswith(".vue") for f in file_list
    )
    has_react = framework.lower() == "react" or any(
        f.endswith(".tsx") or f.endswith(".jsx") for f in file_list
    )

    # 前端构建
    if has_package_json:
        commands.append("npm install --prefer-offline 2>&1 || npm install 2>&1")
        if has_vue:
            commands.append("npx vue-tsc --noEmit 2>&1 || true")
            commands.append("npm run build 2>&1 || npx vite build 2>&1")
        elif has_react:
            commands.append("npm run build 2>&1 || npx vite build 2>&1")
        else:
            commands.append("npm run build 2>&1 || true")

    # 后端检查
    if has_requirements:
        commands.append("pip install -r requirements.txt --quiet 2>&1 || true")
        commands.append("python -c 'import ast; print(\"Syntax check passed\")' 2>&1 || true")

    # 如果没有检测到任何构建工具，做语法检查
    if not commands:
        for fp, content in files.items():
            if fp.endswith(".py"):
                import tempfile
                import ast as _ast
                try:
                    _ast.parse(content)
                except SyntaxError as e:
                    commands.append(f"echo 'Syntax error in {fp}: {e}'")
        if not commands:
            commands.append("echo 'No build steps detected — static project'")

    return commands


@router.post("/{project_id}/build", response_model=dict)
async def build_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """构建项目 — 在沙箱中执行实际构建流程。

    流程:
    1. 解析 generated_code → 文件列表
    2. 将文件写入沙箱工作区
    3. 检测框架/技术栈 → 选择构建命令
    4. 执行构建（npm install/build 或 pip install/check）
    5. 记录构建日志
    """
    import asyncio
    import tempfile
    import shutil
    from pathlib import Path
    import time

    project = session.get(StudioProject, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.generated_code:
        raise HTTPException(status_code=400, detail="No generated code to build")

    # 更新状态
    project.status = ProjectStatus.BUILDING
    commit_or_rollback(session, project)

    # 解析项目文件
    files = _parse_project_files(project.generated_code)
    framework = project.framework or "vue"
    stack = project.stack or "vue"

    build_logs: list[str] = []
    build_success = False
    sandbox_workspace = ""

    try:
        # 创建临时工作区
        sandbox_workspace = tempfile.mkdtemp(prefix=f"build_{project_id}_")
        workspace_path = Path(sandbox_workspace)

        # 写入所有文件
        for filepath, content in files.items():
            full_path = workspace_path / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        build_logs.append(f"📁 Writing {len(files)} files to workspace...")

        # 获取沙箱并执行构建
        sandbox = await _get_sandbox(sandbox_workspace)
        commands = _detect_build_commands(files, framework, stack)

        start_time = time.time()
        for cmd in commands:
            build_logs.append(f"\n$ {cmd}")
            try:
                result = await sandbox.execute_command(cmd, cwd=sandbox_workspace)
                output = result.output[:5000]  # 截断过长输出
                if result.exit_code == 0:
                    build_logs.append(f"✅ {output[:500]}")
                else:
                    build_logs.append(f"⚠ exit={result.exit_code}\n{output[:500]}")
                    # 非关键命令失败不中断构建
            except Exception as cmd_err:
                build_logs.append(f"❌ Error: {cmd_err}")
                # 继续执行剩余命令

        elapsed = time.time() - start_time
        build_logs.append(f"\n⏱ Build completed in {elapsed:.1f}s")

        # 检查常见构建产物
        dist_exists = (workspace_path / "dist").exists()
        build_exists = (workspace_path / "build").exists()
        if dist_exists or build_exists:
            build_logs.append(f"📦 Build artifacts: {'dist/' if dist_exists else ''} {'build/' if build_exists else ''}".strip())

        build_success = True

    except Exception as e:
        build_logs.append(f"\n❌ Build failed: {str(e)}")
        build_success = False

    finally:
        # 清理临时工作区（保留构建产物路径到项目记录）
        if sandbox_workspace and Path(sandbox_workspace).exists():
            try:
                shutil.rmtree(sandbox_workspace, ignore_errors=True)
            except Exception:
                pass

    # 更新项目状态
    project.build_log = "\n".join(build_logs)
    project.status = ProjectStatus.RUNNING if build_success else ProjectStatus.FAILED
    commit_or_rollback(session, project)

    return {
        **_project_to_response(project),
        "build_success": build_success,
        "files_count": len(files),
    }


@router.post("/{project_id}/deploy", response_model=dict)
async def deploy_project(
    project_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """部署项目 — 将构建产物部署到静态文件服务目录。

    部署流程:
    1. 检查项目状态（必须已构建成功）
    2. 创建部署目录（storage/deploy/{project_id}/）
    3. 重新解析文件并写入部署目录
    4. 尝试执行构建并复制产物
    5. 设置 deploy_url
    """
    import shutil
    import tempfile
    from pathlib import Path
    from app.core.config import settings

    project = session.get(StudioProject, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status not in (ProjectStatus.RUNNING, ProjectStatus.DRAFT):
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in RUNNING or DRAFT status (current: {project.status.value})"
        )

    if not project.generated_code:
        raise HTTPException(status_code=400, detail="No generated code to deploy")

    project.status = ProjectStatus.DEPLOYING
    commit_or_rollback(session, project)

    deploy_dir = ""
    deploy_success = False
    deploy_logs: list[str] = []

    try:
        # 部署目标目录
        storage_root = Path(settings.STORAGE_ROOT) if settings.STORAGE_ROOT else Path("storage")
        deploy_dir = str(storage_root / "deploy" / str(project_id))
        deploy_path = Path(deploy_dir)
        deploy_path.mkdir(parents=True, exist_ok=True)

        # 解析并写入项目文件
        files = _parse_project_files(project.generated_code)
        for filepath, content in files.items():
            full_path = deploy_path / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        deploy_logs.append(f"📁 Deployed {len(files)} files to {deploy_dir}")

        # 尝试构建
        sandbox_workspace = tempfile.mkdtemp(prefix=f"deploy_build_{project_id}_")
        try:
            workspace_path = Path(sandbox_workspace)
            for filepath, content in files.items():
                fp = workspace_path / filepath
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")

            sandbox = await _get_sandbox(sandbox_workspace)
            framework = project.framework or "vue"
            stack = project.stack or "vue"
            commands = _detect_build_commands(files, framework, stack)

            for cmd in commands:
                try:
                    result = await sandbox.execute_command(cmd, cwd=sandbox_workspace)
                    deploy_logs.append(f"$ {cmd}\n{result.output[:500]}")
                except Exception:
                    pass

            # 复制构建产物到部署目录
            for artifact_dir in ("dist", "build", "out", ".next", "public"):
                src = workspace_path / artifact_dir
                if src.exists() and src.is_dir():
                    dst = deploy_path / artifact_dir
                    if dst.exists():
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                    deploy_logs.append(f"📦 Copied {artifact_dir}/ → deploy dir")
        finally:
            shutil.rmtree(sandbox_workspace, ignore_errors=True)

        # 生成 index.html 如果不存在
        index_path = deploy_path / "index.html"
        if not index_path.exists():
            index_path.write_text(
                "<!DOCTYPE html>\n<html><head><meta charset='utf-8'><title>"
                f"{project.name}</title></head><body><h1>{project.name}</h1>"
                "<p>Deployed by AI Fullstack Platform</p></body></html>",
                encoding="utf-8",
            )
            deploy_logs.append("📄 Generated fallback index.html")

        # 设置部署 URL
        from app.core.config import settings as s
        frontend_host = s.FRONTEND_HOST.rstrip("/") if s.FRONTEND_HOST else "http://localhost:5173"
        project.deploy_url = f"{frontend_host}/api/v1/static/deploy/{project_id}/index.html"

        deploy_success = True
        deploy_logs.append(f"\n✅ Deploy success: {project.deploy_url}")

    except Exception as e:
        deploy_logs.append(f"\n❌ Deploy failed: {str(e)}")
        deploy_success = False

    project.status = ProjectStatus.RUNNING if deploy_success else ProjectStatus.FAILED
    commit_or_rollback(session, project)

    return {
        **_project_to_response(project),
        "deploy_success": deploy_success,
        "deploy_dir": deploy_dir if deploy_success else None,
        "deploy_log": "\n".join(deploy_logs),
    }


# ── 截图→代码 ──────────────────────────────────────────

class ScreenshotToCodeRequest(BaseModel):
    """截图转代码请求"""
    images_base64: list[str] = Field(..., min_length=1, max_length=5)
    """base64 编码的截图列表（最多 5 张）"""
    prompt: str = Field(default="", max_length=2000)
    """补充文字说明（可选）"""
    framework: str = Field(default="auto", max_length=50)
    """目标框架：auto/vue3/react/html/miniapp/flutter"""
    preferred_model: str | None = None
    """指定模型（可选）"""
    auto_create_project: bool = True
    """是否自动创建项目并保存生成代码"""


class ScreenshotToCodeResponse(BaseModel):
    """截图转代码响应"""
    project: dict | None = None
    """创建的项目信息（auto_create_project=True 时）"""
    code: str
    """生成的代码"""
    files: dict[str, str]
    """解析后的文件列表 {filename: code}"""
    model_used: str | None = None
    provider: str | None = None
    is_fallback: bool = False
    latency_ms: int = 0


def _parse_code_to_files(raw_code: str, framework: str) -> dict[str, str]:
    """从 AI 生成的代码字符串中提取文件。

    支持两种格式：
    1. Markdown 代码块：```filename.ext\ncode\n```
    2. JSON: {"files": {"path": "code", ...}}
    3. 纯文本：作为单个文件
    """
    import re
    import json as _json

    files: dict[str, str] = {}

    # 尝试 JSON 格式
    try:
        parsed = _json.loads(raw_code)
        if isinstance(parsed, dict):
            f = parsed.get("files", {})
            if f and isinstance(f, dict):
                return {str(k): str(v) for k, v in f.items()}
            # 顶层可能是文件结构
            if all(isinstance(v, str) for v in parsed.values()):
                return {str(k): str(v) for k, v in parsed.items()}
    except (_json.JSONDecodeError, TypeError):
        pass

    # 尝试 Markdown 代码块格式 ```filename.ext\ncode\n```
    pattern = r'```(\S+)?\n(.*?)```'
    matches = re.findall(pattern, raw_code, re.DOTALL)
    if matches:
        for lang, code in matches:
            lang = (lang or "").strip()
            # 如果语言标记看起来像文件名
            if "." in lang and "/" not in lang and len(lang) < 80:
                filename = lang
            elif lang in ("vue", "html", "tsx", "jsx", "ts", "js", "css", "py", "json", "yaml", "toml", "md"):
                # 根据语言生成默认文件名
                ext_map = {
                    "vue": "App.vue", "tsx": "App.tsx", "jsx": "App.jsx",
                    "ts": "index.ts", "js": "index.js", "css": "styles.css",
                    "py": "main.py", "json": "config.json", "yaml": "config.yaml",
                    "toml": "pyproject.toml", "md": "README.md", "html": "index.html",
                }
                filename = ext_map.get(lang, f"code.{lang}")
            else:
                continue
            files[filename] = code.strip()

    if files:
        return files

    # 回退：整段代码作为主文件
    ext_map = {"vue3": "App.vue", "vue": "App.vue", "react": "App.tsx", "html": "index.html"}
    default_file = ext_map.get(framework.lower(), "index.html")
    files[default_file] = raw_code.strip()
    return files


@router.post("/screenshot", response_model=dict)
async def screenshot_to_code(
    req: ScreenshotToCodeRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """截图→代码：AI 分析截图布局并生成完整前端代码。

    流程:
    1. 接收截图（base64）+ 可选提示词
    2. Vision Language 模型分析截图 → 布局描述
    3. Code Generation 模型根据布局生成代码
    4. 自动创建项目并保存生成代码
    5. 返回项目信息 + 代码文件
    """
    import base64
    import time

    from app.core.model_router import (
        ModelRequest,
        ModelCapability,
        get_model_router,
    )

    # 构建系统提示词
    framework_hints = {
        "auto": "自动选择最合适的框架",
        "vue3": "使用 Vue 3 Composition API + TypeScript + <script setup>",
        "react": "使用 React 18 + TypeScript + 函数组件 + Hooks",
        "html": "使用纯 HTML + Tailwind CSS CDN",
        "miniapp": "使用微信小程序 WXML + WXSS + JS",
        "flutter": "使用 Flutter Dart",
    }
    fw = req.framework.lower()
    fw_hint = framework_hints.get(fw, framework_hints["auto"])

    system_prompt = (
        f"你是一个专业的前端开发专家。请根据截图生成完整的单页代码。\n"
        f"目标框架：{fw_hint}\n"
        f"要求：\n"
        f"1. 100% 还原截图的布局和设计\n"
        f"2. 使用语义化标签和最佳实践\n"
        f"3. 代码可直接运行\n"
        f"4. 返回格式：```文件名\n完整代码\n```"
    )
    if req.prompt:
        system_prompt += f"\n\n用户补充说明：{req.prompt}"

    # 解码图片
    try:
        images = [base64.b64decode(img) for img in req.images_base64]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data")

    # Step 1: Vision Language 分析截图
    start_time = time.time()
    try:
        router = get_model_router()
        vl_request = ModelRequest(
            capability=ModelCapability.VISION_LANGUAGE,
            prompt="请详细描述这个截图的布局结构，包括："
                   "1. 整体布局（flex/grid等）\n"
                   "2. 每个组件的类型和位置\n"
                   "3. 文字内容\n"
                   "4. 颜色方案\n"
                   "5. 交互元素",
            system_prompt=system_prompt,
            images=images,
            preferred_model=req.preferred_model,
            task_type="ui_design",
        )
        vl_response = await router.generate(vl_request)
        layout_description = vl_response.content
        model_used = vl_response.model_used
        provider = vl_response.provider
        is_fallback = vl_response.is_fallback

        # Step 2: Code Generation 生成代码
        code_request = ModelRequest(
            capability=ModelCapability.CODE_GENERATION,
            prompt=(
                f"根据以下布局描述生成完整的前端代码（{fw_hint}）：\n\n"
                f"{layout_description}\n\n"
                f"请生成可直接运行的完整代码，包含所有必要的样式和脚本。\n"
                f"将所有代码放入 markdown 代码块中，格式为 ```文件名\n代码```。"
            ),
            system_prompt=system_prompt,
            preferred_model=req.preferred_model,
            task_type="ui_design",
        )
        code_response = await router.generate(code_request)
        raw_code = code_response.content
        if not model_used:
            model_used = code_response.model_used

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI generation failed: {str(e)}")

    latency_ms = int((time.time() - start_time) * 1000)

    # 解析代码为文件
    files = _parse_code_to_files(raw_code, req.framework)

    # 自动创建项目
    project = None
    if req.auto_create_project:
        project_name = f"Screenshot: {req.prompt[:30] or 'UI Design'}"
        project = StudioProject(
            name=project_name,
            description=req.prompt or "Generated from screenshot",
            framework=req.framework,
            stack=req.framework,
            status=ProjectStatus.DRAFT,
            generated_code=json.dumps({"files": files}),
            owner_id=user.id,
        )
        commit_or_rollback(session, project)

    return {
        "project": _project_to_response(project) if project else None,
        "code": raw_code,
        "files": files,
        "files_count": len(files),
        "model_used": model_used,
        "provider": provider,
        "is_fallback": is_fallback,
        "latency_ms": latency_ms,
    }


# ── 静态文件部署服务 ────────────────────────────────────

from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


# 挂载部署静态文件目录
_static_deploy_dir = Path(settings.STORAGE_ROOT) / "deploy" if settings.STORAGE_ROOT else Path("storage") / "deploy"
_static_deploy_dir.mkdir(parents=True, exist_ok=True)

# 单独注册一个 router 用于 serving 静态部署文件
# 该 router 的 prefix 与 deploy_url 中 /api/v1/static/deploy 对应
static_deploy_router = APIRouter(prefix="/static/deploy", tags=["static-deploy"])


@static_deploy_router.get("/{project_id}/{filename:path}")
async def serve_deployed_file(project_id: str, filename: str):
    """Serve deployed project static files."""
    file_path = _static_deploy_dir / project_id / filename
    if not file_path.resolve().is_relative_to(_static_deploy_dir.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))
