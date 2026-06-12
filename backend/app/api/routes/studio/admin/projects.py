"""
项目管理 API - 专供 studio-admin 管理端 (Vue)
项目的创建、编辑、删除、构建、部署
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/studio/projects", tags=["studio-admin"])


@router.get("/")
def list_projects(session: SessionDep, current_user: CurrentUser):
    """项目列表 - 待实现"""
    return {"message": "projects list ready", "projects": []}


@router.post("/")
def create_project(session: SessionDep, current_user: CurrentUser):
    """创建新项目 - 待实现"""
    return {"message": "project created"}


@router.get("/{project_id}")
def get_project(project_id: str, session: SessionDep, current_user: CurrentUser):
    """项目详情 - 待实现"""
    return {"message": "project detail", "project_id": project_id}


@router.put("/{project_id}")
def update_project(project_id: str, session: SessionDep, current_user: CurrentUser):
    """更新项目 - 待实现"""
    return {"message": "project updated", "project_id": project_id}


@router.delete("/{project_id}")
def delete_project(project_id: str, session: SessionDep, current_user: CurrentUser):
    """删除项目 - 待实现"""
    return {"message": "project deleted", "project_id": project_id}


@router.post("/{project_id}/build")
def build_project(project_id: str, session: SessionDep, current_user: CurrentUser):
    """构建项目 - 待实现"""
    return {"message": "build started", "project_id": project_id}


@router.post("/{project_id}/deploy")
def deploy_project(project_id: str, session: SessionDep, current_user: CurrentUser):
    """部署项目 - 待实现"""
    return {"message": "deploy started", "project_id": project_id}
