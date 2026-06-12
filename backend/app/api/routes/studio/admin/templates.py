"""
模板管理 API - 专供 studio-admin 管理端 (Vue)
项目模板的浏览、使用、收藏
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/studio/templates", tags=["studio-admin"])


@router.get("/")
def list_templates(session: SessionDep, current_user: CurrentUser):
    """模板列表 - 待实现"""
    return {"message": "templates list ready", "templates": []}


@router.get("/{template_id}")
def get_template(template_id: str, session: SessionDep, current_user: CurrentUser):
    """模板详情 - 待实现"""
    return {"message": "template detail", "template_id": template_id}


@router.post("/{template_id}/use")
def use_template(template_id: str, session: SessionDep, current_user: CurrentUser):
    """使用模板创建项目 - 待实现"""
    return {"message": "creating project from template", "template_id": template_id}
