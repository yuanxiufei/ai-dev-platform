"""
Prompt Templates — 斜杠命令模板系统 (借鉴 Open WebUI Prompt Templates)

支持带类型化变量的斜杠命令模板，版本管理，一键插入聊天。

格式（JSON 存储）:
{
  "id": "gen-react-page",
  "command": "/gen-react-page",
  "title": "生成 React 页面",
  "prompt": "请帮我生成一个 {{component_name}} 组件的 React 页面...",
  "variables": {
    "component_name": {"type": "string", "default": "MyComponent", "description": "组件名称"},
    "use_typescript": {"type": "boolean", "default": true, "description": "是否使用 TypeScript"}
  },
  "category": "studio",
  "version": "1.0",
  "author": "",
  "tags": ["react", "frontend"],
  "is_public": true
}
"""

import json
import os
import time
import uuid
import re
from dataclasses import dataclass, field
from typing import Any, Optional


VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)\s*\}\}")


@dataclass
class TemplateVariable:
    name: str
    type: str = "string"  # string | number | boolean | select | multi_select
    default: Any = ""
    description: str = ""
    required: bool = False
    options: list[str] = field(default_factory=list)  # 用于 select/multi_select


@dataclass
class PromptTemplate:
    id: str
    command: str  # 斜杠命令，如 /gen-react-page
    title: str
    prompt: str  # 含 {{ variables }} 的模板文本
    variables: dict[str, TemplateVariable] = field(default_factory=dict)
    category: str = "general"
    version: str = "1.0"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    is_public: bool = True
    description: str = ""
    icon: str = ""  # emoji 图标
    created_at: str = ""
    updated_at: str = ""
    usage_count: int = 0

    def extract_variables(self) -> list[str]:
        """提取模板中所有变量名"""
        return list(set(VARIABLE_RE.findall(self.prompt)))

    def resolve(self, values: dict[str, Any]) -> str:
        """用实际值填充模板"""
        result = self.prompt
        for name, val in values.items():
            result = re.sub(
                r"\{\{\s*" + re.escape(name) + r"\s*\}\}",
                str(val),
                result,
            )
        return result

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "command": self.command,
            "title": self.title,
            "prompt": self.prompt,
            "variables": {
                k: {
                    "name": v.name,
                    "type": v.type,
                    "default": v.default,
                    "description": v.description,
                    "required": v.required,
                    "options": v.options,
                }
                for k, v in self.variables.items()
            },
            "category": self.category,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "is_public": self.is_public,
            "description": self.description,
            "icon": self.icon,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
        }


DEFAULT_TEMPLATES: list[dict] = [
    {
        "command": "/code-review",
        "title": "代码审查",
        "prompt": "请审查以下代码，关注安全漏洞、性能问题和代码规范。语言：{{ language }}，严格程度：{{ strictness }}",
        "variables": {
            "language": {"type": "select", "default": "python", "options": ["python", "javascript", "typescript", "go", "rust", "java"]},
            "strictness": {"type": "select", "default": "中等", "options": ["宽松", "中等", "严格"]},
        },
        "category": "studio",
        "icon": "🔍",
    },
    {
        "command": "/gen-api",
        "title": "生成 API 端点",
        "prompt": "请为 {{ entity }} 生成完整的 CRUD API 端点。框架：{{ framework }}，数据库：{{ database }}。包含请求验证、错误处理和分页。",
        "variables": {
            "entity": {"type": "string", "default": "User", "description": "实体名称"},
            "framework": {"type": "select", "default": "fastapi", "options": ["fastapi", "express", "flask", "django"]},
            "database": {"type": "select", "default": "postgresql", "options": ["postgresql", "mysql", "mongodb", "sqlite"]},
        },
        "category": "studio",
        "icon": "⚡",
    },
    {
        "command": "/gen-component",
        "title": "生成前端组件",
        "prompt": "请为 {{ component_name }} 生成一个 {{ framework }} 组件。样式方案：{{ style }}，需要 Props 类型定义。功能描述：{{ description }}",
        "variables": {
            "component_name": {"type": "string", "default": "UserCard", "description": "组件名称"},
            "framework": {"type": "select", "default": "vue", "options": ["vue", "react", "svelte"]},
            "style": {"type": "select", "default": "tailwind", "options": ["tailwind", "css", "scss", "styled-components"]},
            "description": {"type": "string", "default": "用户信息卡片，显示头像、姓名、邮箱和操作按钮"},
        },
        "category": "studio",
        "icon": "🧩",
    },
    {
        "command": "/gen-video",
        "title": "生成视频提示词",
        "prompt": "请为视频生成创作详细的视频描述。主题：{{ topic }}，风格：{{ style }}，时长：{{ duration }}秒。包含场景描述、运镜和转场效果。",
        "variables": {
            "topic": {"type": "string", "default": "科技产品展示", "description": "视频主题"},
            "style": {"type": "select", "default": "cinematic", "options": ["cinematic", "anime", "realistic", "abstract", "minimalist"]},
            "duration": {"type": "string", "default": "15", "description": "视频时长(秒)"},
        },
        "category": "video",
        "icon": "🎬",
    },
    {
        "command": "/debug-error",
        "title": "调试错误",
        "prompt": "以下代码报错，请分析原因并给出修复方案。错误信息：{{ error_message }}。语言：{{ language }}。环境：{{ environment }}。",
        "variables": {
            "error_message": {"type": "string", "default": "TypeError: Cannot read property 'map' of undefined", "description": "错误信息"},
            "language": {"type": "select", "default": "javascript", "options": ["python", "javascript", "typescript", "go", "rust", "java"]},
            "environment": {"type": "select", "default": "node", "options": ["node", "browser", "python3.12", "go1.22"]},
        },
        "category": "studio",
        "icon": "🐛",
    },
    {
        "command": "/optimize-sql",
        "title": "SQL 优化",
        "prompt": "请优化以下 SQL 查询。数据库：{{ database }}，关注：{{ focus }}。建议添加索引、重写查询并分析执行计划。",
        "variables": {
            "database": {"type": "select", "default": "postgresql", "options": ["postgresql", "mysql", "sqlite", "sqlserver"]},
            "focus": {"type": "select", "default": "性能", "options": ["性能", "可读性", "安全性", "全面优化"]},
        },
        "category": "studio",
        "icon": "📊",
    },
]


class TemplateRegistry:
    """模板注册中心"""

    def __init__(self, storage_path: str = "data/prompt_templates.json"):
        self.storage_path = storage_path
        self._templates: dict[str, PromptTemplate] = {}
        self._by_category: dict[str, list[str]] = {}
        self._load_storage()

    def _load_storage(self) -> None:
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if os.path.isfile(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    tpl = self._dict_to_template(item)
                    self._templates[tpl.id] = tpl
                    self._by_category.setdefault(tpl.category, []).append(tpl.id)
            except (json.JSONDecodeError, KeyError):
                pass
        # 如果没有模板，加载默认模板
        if not self._templates:
            self._load_defaults()

    def _load_defaults(self) -> None:
        for item in DEFAULT_TEMPLATES:
            tpl = self._dict_to_template({
                "id": item["command"].lstrip("/"),
                "command": item["command"],
                "title": item["title"],
                "prompt": item["prompt"],
                "variables": item.get("variables", {}),
                "category": item.get("category", "general"),
                "icon": item.get("icon", ""),
            })
            self._templates[tpl.id] = tpl
            self._by_category.setdefault(tpl.category, []).append(tpl.id)
        self._save_storage()

    def _save_storage(self) -> None:
        data = [t.to_dict() for t in self._templates.values()]
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _dict_to_template(self, d: dict) -> PromptTemplate:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        d.setdefault("id", str(uuid.uuid4())[:8])
        d.setdefault("version", "1.0")
        d.setdefault("category", "general")
        d.setdefault("is_public", True)
        d.setdefault("description", "")
        d.setdefault("icon", "")
        d.setdefault("created_at", now)
        d.setdefault("updated_at", now)

        variables: dict[str, TemplateVariable] = {}
        for name, v in d.get("variables", {}).items():
            variables[name] = TemplateVariable(
                name=name,
                type=v.get("type", "string"),
                default=v.get("default", ""),
                description=v.get("description", ""),
                required=v.get("required", False),
                options=v.get("options", []),
            )

        return PromptTemplate(
            id=d["id"],
            command=d.get("command", ""),
            title=d.get("title", ""),
            prompt=d.get("prompt", ""),
            variables=variables,
            category=d.get("category", "general"),
            version=d.get("version", "1.0"),
            author=d.get("author", ""),
            tags=d.get("tags", []),
            is_public=d.get("is_public", True),
            description=d.get("description", ""),
            icon=d.get("icon", ""),
            created_at=d.get("created_at", now),
            updated_at=d.get("updated_at", now),
            usage_count=d.get("usage_count", 0),
        )

    # ── CRUD ──

    def create(self, data: dict) -> PromptTemplate:
        tpl = self._dict_to_template(data)
        self._templates[tpl.id] = tpl
        self._by_category.setdefault(tpl.category, []).append(tpl.id)
        self._save_storage()
        return tpl

    def get(self, tpl_id: str) -> Optional[PromptTemplate]:
        return self._templates.get(tpl_id)

    def update(self, tpl_id: str, data: dict) -> Optional[PromptTemplate]:
        tpl = self._templates.get(tpl_id)
        if not tpl:
            return None
        # 合并更新
        for key in ("title", "prompt", "command", "category", "description", "icon", "is_public", "tags"):
            if key in data:
                setattr(tpl, key, data[key])
        if "variables" in data:
            variables: dict[str, TemplateVariable] = {}
            for name, v in data["variables"].items():
                variables[name] = TemplateVariable(
                    name=name,
                    type=v.get("type", "string"),
                    default=v.get("default", ""),
                    description=v.get("description", ""),
                    required=v.get("required", False),
                    options=v.get("options", []),
                )
            tpl.variables = variables
        tpl.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save_storage()
        return tpl

    def delete(self, tpl_id: str) -> bool:
        tpl = self._templates.pop(tpl_id, None)
        if tpl:
            cat_list = self._by_category.get(tpl.category, [])
            if tpl_id in cat_list:
                cat_list.remove(tpl_id)
            self._save_storage()
            return True
        return False

    def list_all(self, category: Optional[str] = None, search: Optional[str] = None) -> list[dict]:
        result: list[dict] = []
        for tpl in self._templates.values():
            if category and tpl.category != category:
                continue
            if search:
                q = search.lower()
                if not (q in tpl.title.lower() or q in tpl.command.lower() or q in tpl.prompt.lower()):
                    continue
            result.append(tpl.to_dict())
        result.sort(key=lambda t: t["title"])
        return result

    def list_categories(self) -> list[dict]:
        return [
            {"name": cat, "count": len(ids)}
            for cat, ids in sorted(self._by_category.items())
        ]

    def search_commands(self, query: str) -> list[dict]:
        """搜索匹配的斜杠命令 — 用于聊天输入自动补全"""
        q = query.lstrip("/").lower()
        results: list[dict] = []
        for tpl in self._templates.values():
            if q in tpl.command.lower() or q in tpl.title.lower():
                d = tpl.to_dict()
                d["variable_names"] = list(tpl.variables.keys())
                results.append(d)
        return sorted(results, key=lambda t: len(t["command"]))

    def resolve(self, tpl_id: str, values: dict[str, Any]) -> Optional[str]:
        """解析模板并返回填充后的 prompt"""
        tpl = self._templates.get(tpl_id)
        if not tpl:
            return None
        tpl.usage_count += 1
        self._save_storage()
        return tpl.resolve(values)

    @property
    def count(self) -> int:
        return len(self._templates)


# 全局单例
_registry: Optional[TemplateRegistry] = None


def get_template_registry() -> TemplateRegistry:
    global _registry
    if _registry is None:
        _registry = TemplateRegistry()
    return _registry


def init_template_registry(storage_path: str = "data/prompt_templates.json") -> TemplateRegistry:
    global _registry
    _registry = TemplateRegistry(storage_path=storage_path)
    return _registry
