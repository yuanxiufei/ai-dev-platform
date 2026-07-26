"""
Extensions API — 扩展市场与管理

参考: VSCode platform/extensionManagement
端点:
  GET    /extensions/search       — 搜索扩展
  GET    /extensions/installed    — 列出已安装扩展
  GET    /extensions/{id}         — 扩展详情
  POST   /extensions/install      — 安装扩展
  POST   /extensions/{id}/uninstall — 卸载扩展
  POST   /extensions/{id}/enable   — 启用扩展
  POST   /extensions/{id}/disable  — 禁用扩展
  GET    /extensions/gallery      — 扩展市场列表

持久化: SQLite + JSON 配置
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/extensions", tags=["Extensions"])

_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))
_DB_DIR = os.path.join(_ROOT, ".data", "extensions")
_DB_PATH = os.path.join(_DB_DIR, "extensions.db")
_GALLERY_DIR = os.path.join(_DB_DIR, "gallery")
_EXTENSIONS_DIR = os.path.join(_ROOT, ".data", "extensions", "installed")

for d in [_DB_DIR, _GALLERY_DIR, _EXTENSIONS_DIR]:
    os.makedirs(d, exist_ok=True)


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS extensions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '0.0.1',
                publisher TEXT NOT NULL DEFAULT '',
                publisher_display_name TEXT DEFAULT '',
                categories TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_builtin INTEGER NOT NULL DEFAULT 0,
                icon_url TEXT DEFAULT '',
                installed_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        db.commit()


_init_db()


# ── 模型 ──

class ExtensionInfo(BaseModel):
    id: str
    name: str
    display_name: str = ""
    description: str = ""
    version: str = "0.0.1"
    publisher: str = ""
    publisher_display_name: str = ""
    categories: list[str] = []
    tags: list[str] = []
    is_active: bool = True
    is_builtin: bool = False
    icon_url: str = ""
    installed_at: float = 0
    updated_at: float = 0
    install_count: int = 0
    rating: float = 0
    rating_count: int = 0


class SearchResult(BaseModel):
    total: int
    items: list[ExtensionInfo]


# ── 内置扩展目录 ──

_BUILTIN_EXTENSIONS: list[ExtensionInfo] = [
    ExtensionInfo(
        id="builtin.theme-default",
        name="theme-default",
        display_name="Default Theme",
        description="Default light and dark themes",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Themes"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.git",
        name="git",
        display_name="Git Integration",
        description="Git source control integration",
        version="1.0.0",
        publisher="ai-platform",
        categories=["SCM Providers"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.markdown-preview",
        name="markdown-preview",
        display_name="Markdown Preview",
        description="Preview Markdown files",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.emmet",
        name="emmet",
        display_name="Emmet",
        description="Emmet abbreviation support for HTML/CSS",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.json-language",
        name="json-language",
        display_name="JSON Language Features",
        description="JSON language support with validation and formatting",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.css-language",
        name="css-language",
        display_name="CSS Language Features",
        description="CSS/SCSS/Less language support",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.typescript-language",
        name="typescript-language",
        display_name="TypeScript Language Features",
        description="TypeScript/JavaScript language support",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.python-language",
        name="python-language",
        display_name="Python Language Features",
        description="Python language support with IntelliSense",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Languages"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.debugger",
        name="debugger",
        display_name="Debugger",
        description="Integrated debugger support",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Debuggers"],
        is_builtin=True,
    ),
    ExtensionInfo(
        id="builtin.search",
        name="search",
        display_name="Search",
        description="Search across files with ripgrep",
        version="1.0.0",
        publisher="ai-platform",
        categories=["Other"],
        is_builtin=True,
    ),
]

# 选中内置扩展到本地
for builtin in _BUILTIN_EXTENSIONS:
    with _get_db() as db:
        existing = db.execute("SELECT id FROM extensions WHERE id = ?", (builtin.id,)).fetchone()
        if not existing:
            now = time.time()
            db.execute(
                """INSERT INTO extensions (id, name, display_name, description, version,
                   publisher, publisher_display_name, categories, tags, is_active, is_builtin,
                   icon_url, installed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?)""",
                (builtin.id, builtin.name, builtin.display_name, builtin.description,
                 builtin.version, builtin.publisher, builtin.publisher_display_name,
                 json.dumps(builtin.categories), json.dumps(builtin.tags),
                 builtin.icon_url, now, now),
            )
        db.commit()


def _row_to_extension(row: sqlite3.Row) -> ExtensionInfo:
    try:
        categories = json.loads(row["categories"] or "[]")
    except json.JSONDecodeError:
        categories = []
    try:
        tags = json.loads(row["tags"] or "[]")
    except json.JSONDecodeError:
        tags = []

    return ExtensionInfo(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"],
        description=row["description"],
        version=row["version"],
        publisher=row["publisher"],
        publisher_display_name=row["publisher_display_name"] or "",
        categories=categories,
        tags=tags,
        is_active=bool(row["is_active"]),
        is_builtin=bool(row["is_builtin"]),
        icon_url=row["icon_url"] or "",
        installed_at=row["installed_at"],
        updated_at=row["updated_at"],
    )


# ── 端点 ──


@router.get("/search", response_model=SearchResult)
async def search_extensions(
    q: str = Query("", max_length=200),
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> SearchResult:
    """搜索扩展 (本地 + 模拟市场)"""
    all_items: list[ExtensionInfo] = []

    # 1. 从本地数据库搜索
    with _get_db() as db:
        query = "SELECT * FROM extensions WHERE 1=1"
        params: list[Any] = []
        if q:
            query += " AND (name LIKE ? OR display_name LIKE ? OR description LIKE ?)"
            like_q = f"%{q}%"
            params.extend([like_q, like_q, like_q])
        if category:
            query += " AND categories LIKE ?"
            params.append(f"%{category}%")

        rows = db.execute(query, params).fetchall()
        for row in rows:
            all_items.append(_row_to_extension(row))

    # 2. 模拟市场扩展 (如果本地没有)
    market_base = [
        ExtensionInfo(
            id="market.eslint",
            name="eslint",
            display_name="ESLint",
            description="Integrates ESLint JavaScript linter into the editor",
            version="2.4.0",
            publisher="dbaeumer",
            publisher_display_name="Dirk Baeumer",
            categories=["Linters"],
            tags=["javascript", "typescript", "linting"],
            install_count=45000000,
            rating=4.8,
            rating_count=32000,
        ),
        ExtensionInfo(
            id="market.prettier",
            name="prettier",
            display_name="Prettier - Code formatter",
            description="Code formatter using prettier",
            version="10.1.0",
            publisher="esbenp",
            publisher_display_name="Esben Petersen",
            categories=["Formatters"],
            tags=["javascript", "typescript", "css", "html", "json"],
            install_count=38000000,
            rating=4.7,
            rating_count=28000,
        ),
        ExtensionInfo(
            id="market.python",
            name="python",
            display_name="Python",
            description="IntelliSense, linting, debugging, formatting for Python",
            version="2024.8.0",
            publisher="ms-python",
            publisher_display_name="Microsoft",
            categories=["Programming Languages"],
            tags=["python", "debugging", "linting", "intellisense"],
            install_count=90000000,
            rating=4.6,
            rating_count=41000,
        ),
        ExtensionInfo(
            id="market.vue",
            name="volar",
            display_name="Vue - Official",
            description="Language support for Vue 3",
            version="2.0.28",
            publisher="vue",
            publisher_display_name="Vue",
            categories=["Programming Languages"],
            tags=["vue", "typescript", "javascript"],
            install_count=12000000,
            rating=4.8,
            rating_count=8900,
        ),
        ExtensionInfo(
            id="market.rust-analyzer",
            name="rust-analyzer",
            display_name="rust-analyzer",
            description="Rust language support",
            version="0.3.2000",
            publisher="rust-lang",
            publisher_display_name="Rust Language",
            categories=["Programming Languages"],
            tags=["rust", "cargo"],
            install_count=8000000,
            rating=4.9,
            rating_count=6200,
        ),
        ExtensionInfo(
            id="market.docker",
            name="docker",
            display_name="Docker",
            description="Dockerfile and docker-compose support",
            version="1.29.0",
            publisher="ms-azuretools",
            publisher_display_name="Microsoft",
            categories=["Other"],
            tags=["docker", "dockerfile", "container"],
            install_count=25000000,
            rating=4.5,
            rating_count=15000,
        ),
        ExtensionInfo(
            id="market.gitlens",
            name="gitlens",
            display_name="GitLens — Git supercharged",
            description="Git blame, code lens, and rich Git integrations",
            version="15.0.0",
            publisher="eamodio",
            publisher_display_name="Eric Amodio",
            categories=["Other"],
            tags=["git", "blame", "history", "compare"],
            install_count=32000000,
            rating=4.9,
            rating_count=29000,
        ),
        ExtensionInfo(
            id="market.theme-one-dark",
            name="one-dark-pro",
            display_name="One Dark Pro",
            description="Atom's iconic One Dark theme for VS Code",
            version="3.18.0",
            publisher="zhuangtongfa",
            categories=["Themes"],
            tags=["theme", "dark"],
            install_count=11000000,
            rating=4.8,
            rating_count=18000,
        ),
    ]

    for m in market_base:
        if any(e.id == m.id for e in all_items):
            continue
        searchable = f"{m.name} {m.display_name} {m.description} {m.publisher_display_name}".lower()
        if q and q.lower() not in searchable:
            continue
        if category and category not in m.categories:
            continue
        all_items.append(m)

    total = len(all_items)
    start = (page - 1) * size
    items = all_items[start:start + size]

    return SearchResult(total=total, items=items)


@router.get("/installed", response_model=list[ExtensionInfo])
async def list_installed() -> list[ExtensionInfo]:
    """列出已安装的扩展"""
    with _get_db() as db:
        rows = db.execute("SELECT * FROM extensions ORDER BY is_builtin DESC, display_name ASC").fetchall()
        return [_row_to_extension(r) for r in rows]


@router.get("/{extension_id}", response_model=ExtensionInfo)
async def get_extension(extension_id: str) -> ExtensionInfo:
    """获取扩展详情"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if row:
            return _row_to_extension(row)

    # 搜索市场
    search = await search_extensions(q=extension_id)
    for item in search.items:
        if item.id == extension_id:
            return item

    raise HTTPException(404, f"Extension '{extension_id}' not found")


@router.post("/install", response_model=ExtensionInfo)
async def install_extension(
    extension_id: str = Query(..., max_length=256),
    version: str = Query("latest", max_length=64),
) -> ExtensionInfo:
    """安装扩展 (模拟)"""
    # 检查是否已安装
    with _get_db() as db:
        existing = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if existing and bool(existing["is_active"]):
            return _row_to_extension(existing)

    # 搜索市场
    search = await search_extensions(q=extension_id)
    ext = next((e for e in search.items if e.id == extension_id), None)
    if not ext:
        raise HTTPException(404, f"Extension '{extension_id}' not found in marketplace")

    now = time.time()
    with _get_db() as db:
        existing = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if existing:
            db.execute(
                "UPDATE extensions SET version = ?, is_active = 1, updated_at = ? WHERE id = ?",
                (version if version != "latest" else ext.version, now, extension_id),
            )
        else:
            db.execute(
                """INSERT INTO extensions (id, name, display_name, description, version,
                   publisher, publisher_display_name, categories, tags, is_active, is_builtin,
                   icon_url, installed_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?)""",
                (extension_id, ext.name, ext.display_name, ext.description,
                 version if version != "latest" else ext.version,
                 ext.publisher, ext.publisher_display_name,
                 json.dumps(ext.categories), json.dumps(ext.tags),
                 ext.icon_url, now, now),
            )
        db.commit()

    return ext


@router.post("/{extension_id}/uninstall")
async def uninstall_extension(extension_id: str) -> dict:
    """卸载扩展"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Extension not found")
        if bool(row["is_builtin"]):
            raise HTTPException(400, "Cannot uninstall built-in extension")

        db.execute("DELETE FROM extensions WHERE id = ?", (extension_id,))
        db.commit()

    return {"ok": True}


@router.post("/{extension_id}/enable")
async def enable_extension(extension_id: str) -> dict:
    """启用扩展"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Extension not found")

        db.execute("UPDATE extensions SET is_active = 1 WHERE id = ?", (extension_id,))
        db.commit()

    return {"ok": True, "is_active": True}


@router.post("/{extension_id}/disable")
async def disable_extension(extension_id: str) -> dict:
    """禁用扩展"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM extensions WHERE id = ?", (extension_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Extension not found")
        if bool(row["is_builtin"]):
            raise HTTPException(400, "Cannot disable built-in extension")

        db.execute("UPDATE extensions SET is_active = 0 WHERE id = ?", (extension_id,))
        db.commit()

    return {"ok": True, "is_active": False}


@router.get("/gallery/list", response_model=list[ExtensionInfo])
async def gallery_list(
    category: str | None = Query(None),
    sort_by: str = Query("popular", pattern="^(popular|name|recent|rating)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> list[ExtensionInfo]:
    """获取扩展市场列表"""
    search = await search_extensions(q="", category=category, page=page, size=size)

    items = search.items
    if sort_by == "name":
        items.sort(key=lambda e: e.display_name)
    elif sort_by == "rating":
        items.sort(key=lambda e: e.rating, reverse=True)
    elif sort_by == "recent":
        items.sort(key=lambda e: e.updated_at, reverse=True)
    else:  # popular
        items.sort(key=lambda e: e.install_count, reverse=True)

    return items
