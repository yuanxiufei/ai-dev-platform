"""
Task Management — AI 任务列表与多步骤工作流 (借鉴 Open WebUI Tasks)

支持 AI 维护结构化任务列表，跟踪多步骤工作流进度。
每个任务有状态、优先级、子步骤、可分配给 Agent 执行。
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TaskStep:
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    order: int = 0
    result: str = ""  # AI 执行结果
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "order": self.order,
            "result": self.result,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    steps: list[TaskStep] = field(default_factory=list)
    assigned_model: str = ""  # 委派给哪个模型执行
    parent_id: str = ""  # 父任务 ID（层级关系）
    progress: float = 0.0  # 0-100
    result_summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    due_date: str = ""

    def recalc_progress(self) -> float:
        if not self.steps:
            return 100.0 if self.status == TaskStatus.COMPLETED else 0.0
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        self.progress = round(completed / len(self.steps) * 100, 1)
        return self.progress

    def next_step(self) -> Optional[TaskStep]:
        """获取下一个待执行的步骤"""
        for step in sorted(self.steps, key=lambda s: s.order):
            if step.status in (TaskStatus.TODO, TaskStatus.IN_PROGRESS):
                return step
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "category": self.category,
            "tags": self.tags,
            "steps": [s.to_dict() for s in sorted(self.steps, key=lambda x: x.order)],
            "assigned_model": self.assigned_model,
            "parent_id": self.parent_id,
            "progress": self.progress,
            "result_summary": self.result_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "due_date": self.due_date,
        }


class TaskManager:
    """任务管理器 — JSON 文件持久化"""

    def __init__(self, storage_path: str = "data/tasks.json"):
        self.storage_path = storage_path
        self._tasks: dict[str, Task] = {}
        self._load()

    def _load(self) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if os.path.isfile(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    task = self._dict_to_task(item)
                    self._tasks[task.id] = task
            except (json.JSONDecodeError, KeyError):
                pass

    def _save(self) -> None:
        data = [t.to_dict() for t in self._tasks.values()]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _dict_to_task(self, d: dict) -> Task:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        d.setdefault("id", str(uuid.uuid4())[:8])
        d.setdefault("created_at", now)
        d.setdefault("updated_at", now)

        steps: list[TaskStep] = []
        for s in d.get("steps", []):
            steps.append(TaskStep(
                id=s.get("id", str(uuid.uuid4())[:8]),
                title=s.get("title", ""),
                description=s.get("description", ""),
                status=TaskStatus(s.get("status", "todo")),
                order=s.get("order", 0),
                result=s.get("result", ""),
                started_at=s.get("started_at", ""),
                completed_at=s.get("completed_at", ""),
            ))

        return Task(
            id=d["id"],
            title=d.get("title", ""),
            description=d.get("description", ""),
            status=TaskStatus(d.get("status", "todo")),
            priority=TaskPriority(d.get("priority", "medium")),
            category=d.get("category", "general"),
            tags=d.get("tags", []),
            steps=steps,
            assigned_model=d.get("assigned_model", ""),
            parent_id=d.get("parent_id", ""),
            progress=d.get("progress", 0.0),
            result_summary=d.get("result_summary", ""),
            created_at=d.get("created_at", now),
            updated_at=d.get("updated_at", now),
            started_at=d.get("started_at", ""),
            completed_at=d.get("completed_at", ""),
            due_date=d.get("due_date", ""),
        )

    # ── CRUD ──

    def create(self, data: dict) -> Task:
        t = self._dict_to_task(data)
        self._tasks[t.id] = t
        self._save()
        return t

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, data: dict) -> Optional[Task]:
        t = self._tasks.get(task_id)
        if not t:
            return None
        for key in ("title", "description", "category", "tags", "assigned_model",
                     "parent_id", "result_summary", "due_date"):
            if key in data:
                setattr(t, key, data[key])
        if "status" in data:
            t.status = TaskStatus(data["status"])
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if t.status == TaskStatus.IN_PROGRESS and not t.started_at:
                t.started_at = now
            elif t.status == TaskStatus.COMPLETED:
                t.completed_at = now
                t.progress = 100.0
        if "priority" in data:
            t.priority = TaskPriority(data["priority"])
        if "steps" in data:
            steps: list[TaskStep] = []
            for s in data["steps"]:
                steps.append(TaskStep(
                    id=s.get("id", str(uuid.uuid4())[:8]),
                    title=s.get("title", ""),
                    description=s.get("description", ""),
                    status=TaskStatus(s.get("status", "todo")),
                    order=s.get("order", 0),
                    result=s.get("result", ""),
                    started_at=s.get("started_at", ""),
                    completed_at=s.get("completed_at", ""),
                ))
            t.steps = steps
        t.recalc_progress()
        t.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return t

    def update_step(self, task_id: str, step_id: str, data: dict) -> Optional[TaskStep]:
        t = self._tasks.get(task_id)
        if not t:
            return None
        for s in t.steps:
            if s.id == step_id:
                now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                for key in ("title", "description", "result"):
                    if key in data:
                        setattr(s, key, data[key])
                if "status" in data:
                    s.status = TaskStatus(data["status"])
                    if s.status == TaskStatus.IN_PROGRESS and not s.started_at:
                        s.started_at = now
                    elif s.status == TaskStatus.COMPLETED:
                        s.completed_at = now
                t.recalc_progress()
                t.updated_at = now
                self._save()
                return s
        return None

    def delete(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            # 同时删除子任务
            child_ids = [tid for tid, t in self._tasks.items() if t.parent_id == task_id]
            for cid in child_ids:
                del self._tasks[cid]
            self._save()
            return True
        return False

    def list_all(self, status: Optional[str] = None, category: Optional[str] = None,
                 priority: Optional[str] = None, parent_id: Optional[str] = None,
                 search: Optional[str] = None, page: int = 1, size: int = 20) -> tuple[list[dict], int]:
        result: list[Task] = []
        for t in self._tasks.values():
            if parent_id is not None and t.parent_id != parent_id:
                continue
            if status and t.status.value != status:
                continue
            if category and t.category != category:
                continue
            if priority and t.priority.value != priority:
                continue
            if search:
                q = search.lower()
                if not (q in t.title.lower() or q in t.description.lower()):
                    continue
            result.append(t)

        result.sort(key=lambda t: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(t.priority.value, 9),
            t.created_at,
        ), reverse=True)
        total = len(result)
        start = (page - 1) * size
        page_data = result[start:start + size]
        return [t.to_dict() for t in page_data], total

    def list_categories(self) -> list[dict]:
        cats: dict[str, int] = {}
        for t in self._tasks.values():
            cats[t.category] = cats.get(t.category, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(cats.items())]

    def get_tree(self, task_id: str) -> Optional[dict]:
        """获取任务树（含子任务）"""
        t = self._tasks.get(task_id)
        if not t:
            return None
        data = t.to_dict()
        children = [self.get_tree(cid) for cid, ct in self._tasks.items() if ct.parent_id == task_id]
        data["children"] = [c for c in children if c is not None]
        return data

    def auto_generate_steps(self, task_id: str, steps_data: list[dict]) -> Task:
        """AI 自动生成子步骤"""
        t = self._tasks.get(task_id)
        if not t:
            raise ValueError(f"Task {task_id} not found")
        steps: list[TaskStep] = []
        for i, s in enumerate(steps_data):
            steps.append(TaskStep(
                id=str(uuid.uuid4())[:8],
                title=s.get("title", f"Step {i+1}"),
                description=s.get("description", ""),
                order=i + 1,
            ))
        t.steps = steps
        t.recalc_progress()
        t.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save()
        return t

    @property
    def count(self) -> int:
        return len(self._tasks)


# 全局单例
_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager


def init_task_manager(storage_path: str = "data/tasks.json") -> TaskManager:
    global _manager
    _manager = TaskManager(storage_path=storage_path)
    return _manager
