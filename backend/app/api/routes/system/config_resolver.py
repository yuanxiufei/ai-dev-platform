"""
Configuration Resolver API — 配置变量解析

POST /api/v1/system/config-resolver/resolve — 解析文本中的 ${variable}
POST /api/v1/system/config-resolver/resolve-all — 递归解析 dict
GET  /api/v1/system/config-resolver/variables — 列出支持的所有变量
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Optional

from app.core.config_resolver import ConfigurationResolver

router = APIRouter(prefix="/system/config-resolver", tags=["Config Resolver"])


class ResolveRequest(BaseModel):
    text: str
    workspace_root: str = ""
    file: str = ""
    file_basename: str = ""
    file_extname: str = ""
    file_dirname: str = ""
    relative_file: str = ""
    line_number: str = ""
    selected_text: str = ""
    config_overrides: dict[str, Any] = {}
    env_overrides: dict[str, str] = {}


class ResolveAllRequest(BaseModel):
    data: dict[str, Any]
    workspace_root: str = ""
    file: str = ""
    config_overrides: dict[str, Any] = {}
    env_overrides: dict[str, str] = {}


SUPPORTED_VARIABLES = [
    {"name": "${workspaceFolder}", "description": "工作区根目录路径"},
    {"name": "${workspaceFolderBasename}", "description": "工作区文件夹名"},
    {"name": "${file}", "description": "当前打开文件的完整路径"},
    {"name": "${fileBasename}", "description": "当前文件名 (含扩展名)"},
    {"name": "${fileExtname}", "description": "当前文件扩展名"},
    {"name": "${fileDirname}", "description": "当前文件所在目录路径"},
    {"name": "${fileWorkspaceFolder}", "description": "文件所在工作区路径"},
    {"name": "${relativeFile}", "description": "文件相对于工作区的路径"},
    {"name": "${relativeFileDirname}", "description": "文件目录相对于工作区的路径"},
    {"name": "${lineNumber}", "description": "当前光标行号"},
    {"name": "${selectedText}", "description": "当前选中文本"},
    {"name": "${cwd}", "description": "当前工作目录"},
    {"name": "${userHome}", "description": "用户主目录"},
    {"name": "${pathSeparator}", "description": "平台路径分隔符 (\\\\ 或 /)"},
    {"name": "${/}", "description": "路径分隔符简写"},
    {"name": "${config:section.key}", "description": "引用 settings 配置值"},
    {"name": "${env:VAR_NAME}", "description": "引用环境变量"},
    {"name": "${command:commandID}", "description": "引用命令执行结果"},
]


@router.post("/resolve")
def resolve_variables(req: ResolveRequest):
    """解析文本中的 ${variable} 引用"""
    import os
    resolver = ConfigurationResolver(
        workspace_root=req.workspace_root,
        config_getter=req.config_overrides.get if req.config_overrides else None,
        env_getter=lambda k: req.env_overrides.get(k, os.environ.get(k)),
    )
    resolver.set_context(
        file=req.file,
        fileBasename=req.file_basename,
        fileExtname=req.file_extname,
        fileDirname=req.file_dirname,
        relativeFile=req.relative_file,
        lineNumber=req.line_number,
        selectedText=req.selected_text,
    )
    result = resolver.resolve(req.text)
    return {"original": req.text, "resolved": result}


@router.post("/resolve-all")
def resolve_all_variables(req: ResolveAllRequest):
    """递归解析 dict 中所有值里的 ${variable} 引用"""
    import os
    resolver = ConfigurationResolver(
        workspace_root=req.workspace_root,
        config_getter=req.config_overrides.get if req.config_overrides else None,
        env_getter=lambda k: req.env_overrides.get(k, os.environ.get(k)),
    )
    if req.file:
        resolver.set_context(file=req.file)
    result = resolver.resolve_all(req.data)
    return {"original": req.data, "resolved": result}


@router.get("/variables")
def list_variables():
    """列出支持的所有配置变量"""
    return {"variables": SUPPORTED_VARIABLES}
