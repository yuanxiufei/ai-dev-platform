"""
Task Management API — AI 任务列表与多步骤工作流 (借鉴 Open WebUI Tasks)

端点:
- GET    /tasks                  — 列出任务（支持筛选+分页）
- GET    /tasks/categories       — 列出分类
- POST   /tasks                  — 创建任务
- POST   /tasks/auto-generate    — AI 自动生成子步骤
- GET    /tasks/{id}             — 获取任务详情
- GET    /tasks/{id}/tree        — 获取任务树（含子任务）
- PUT    /tasks/{id}             — 更新任务
- DELETE /tasks/{id}             — 删除任务
- PUT    /tasks/{id}/steps/{sid} — 更新子步骤
- POST   /tasks/{id}/start       — 执行任务（标记为进行中，返回下一步）
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.tasks import (
    get_task_manager,
    TaskManager,
    TaskStatus,
    TaskPriority,
)

router = APIRouter(prefix="/tasks", tags=["Task Management"])


class TaskStepData(BaseModel):
    id: str | None = None
    title: str
    description: str = ""
    status: str = "todo"
    order: int = 0
    result: str = ""


class TaskCreate(BaseModel):
    title: str = Field(..., description="任务标题")
    description: str = ""
    priority: str = "medium"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    steps: list[TaskStepData] = Field(default_factory=list)
    assigned_model: str = ""
    parent_id: str = ""
    due_date: str = ""


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    steps: list[TaskStepData] | None = None
    assigned_model: str | None = None
    result_summary: str | None = None
    due_date: str | None = None


class StepUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    result: str | None = None
    order: int | None = None


class AutoGenerateSteps(BaseModel):
    title: str
    description: str = ""
    category: str = "general"
    step_count: int = Field(default=3, ge=1, le=10, description="期望生成的步骤数")


def _get_or_404(mgr: TaskManager, task_id: str):
    t = mgr.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return t


def _validate_enum(value: str, enum_cls, field_name: str) -> str:
    try:
        enum_cls(value)
        return value
    except ValueError:
        valid = ", ".join(e.value for e in enum_cls)
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: '{value}'. Valid: {valid}")


@router.get("")
async def list_tasks(
    status: str = Query(default=None),
    category: str = Query(default=None),
    priority: str = Query(default=None),
    parent_id: str = Query(default=None),
    search: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
) -> dict:
    mgr = get_task_manager()
    data, total = mgr.list_all(
        status=status, category=category, priority=priority,
        parent_id=parent_id, search=search, page=page, size=size,
    )
    return {"data": data, "total": total, "page": page, "size": size}


@router.get("/categories")
async def list_categories() -> dict:
    return {"categories": get_task_manager().list_categories()}


@router.post("")
async def create_task(data: TaskCreate) -> dict:
    mgr = get_task_manager()
    if data.priority:
        _validate_enum(data.priority, TaskPriority, "priority")
    task = mgr.create(data.model_dump())
    return {"task": task.to_dict()}


@router.post("/auto-generate")
async def auto_generate_steps(data: AutoGenerateSteps) -> dict:
    """基于标题和描述，由 AI 自动生成任务步骤"""
    mgr = get_task_manager()
    # 先创建任务
    task = mgr.create({"title": data.title, "description": data.description, "category": data.category})
    # 基于 AI 生成步骤（这里使用 rule-based 作为回退，实际可接 ModelRouter）
    # 在实际部署中，这里可以调用 get_model_router().generate() 来生成步骤
    steps_data = [
        {"title": f"步骤 {i+1}: 分析与规划", "description": f"分析「{data.title}」的需求并制定执行计划"}
        if i == 0 else
        {"title": f"步骤 {i+1}: 执行核心逻辑", "description": f"执行「{data.title}」的核心实现"}
        if i == 1 else
        {"title": f"步骤 {i+1}: 验证与总结", "description": f"验证执行结果并生成总结报告"}
        for i in range(min(data.step_count, 10))
    ]
    task = mgr.auto_generate_steps(task.id, steps_data)
    return {"task": task.to_dict(), "steps_generated": len(steps_data)}


@router.get("/{task_id}")
async def get_task(task_id: str) -> dict:
    t = _get_or_404(get_task_manager(), task_id)
    return {"task": t.to_dict()}


@router.get("/{task_id}/tree")
async def get_task_tree(task_id: str) -> dict:
    mgr = get_task_manager()
    _get_or_404(mgr, task_id)
    tree = mgr.get_tree(task_id)
    return {"task": tree}


@router.put("/{task_id}")
async def update_task(task_id: str, data: TaskUpdate) -> dict:
    mgr = get_task_manager()
    _get_or_404(mgr, task_id)
    payload = data.model_dump(exclude_none=True)
    if "status" in payload:
        _validate_enum(payload["status"], TaskStatus, "status")
    if "priority" in payload:
        _validate_enum(payload["priority"], TaskPriority, "priority")
    task = mgr.update(task_id, payload)
    return {"task": task.to_dict()}


@router.delete("/{task_id}")
async def delete_task(task_id: str) -> dict:
    mgr = get_task_manager()
    if not mgr.delete(task_id):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"message": f"Task '{task_id}' deleted"}


@router.put("/{task_id}/steps/{step_id}")
async def update_step(task_id: str, step_id: str, data: StepUpdate) -> dict:
    mgr = get_task_manager()
    _get_or_404(mgr, task_id)
    payload = data.model_dump(exclude_none=True)
    if "status" in payload:
        _validate_enum(payload["status"], TaskStatus, "status")
    step = mgr.update_step(task_id, step_id, payload)
    if not step:
        raise HTTPException(status_code=404, detail=f"Step '{step_id}' not found in task '{task_id}'")
    return {"step": step.to_dict(), "task_progress": mgr.get(task_id).progress}


@router.post("/{task_id}/start")
async def start_task(task_id: str) -> dict:
    """标记任务为进行中，并返回下一步骤信息"""
    mgr = get_task_manager()
    t = _get_or_404(mgr, task_id)
    t = mgr.update(task_id, {"status": "in_progress"})
    next_step = t.next_step()
    return {
        "task": t.to_dict(),
        "next_step": next_step.to_dict() if next_step else None,
        "message": "Task started" if next_step else "All steps completed",
    }
