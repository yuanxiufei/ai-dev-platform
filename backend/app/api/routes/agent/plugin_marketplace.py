"""
插件市场 API — MCP/AWP/技能/命令/钩子 插件的远程浏览、安装、管理

提供完整插件市场生态：
- 多市场源管理（官方、社区、自定义 GitHub/ZIP/本地路径）
- 插件注册表查询（支持多源聚合 + 多类型筛选）
- 插件安装/卸载/更新
- 本地已安装插件管理
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
import datetime as dt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("api.plugin_marketplace")

router = APIRouter(prefix="/plugin-marketplace", tags=["Plugin Marketplace"])

# 本地插件存储路径
_LOCAL_PLUGINS_DIR = Path("plugins")

# ── 市场源存储 ─────────────────────────────────────────────
_sources: dict[str, dict[str, Any]] = {
    "codebuddy-plugins-official": {
        "id": "codebuddy-plugins-official",
        "name": "CodeBuddy 官方",
        "type": "builtin",
        "url": "https://plugins.codebuddy.ai/registry.json",
        "description": "CodeBuddy 官方插件市场",
        "enabled": True,
        "plugin_count": 0,
        "created_at": "2025-01-01T00:00:00Z",
    },
    "cb_teams_marketplace": {
        "id": "cb_teams_marketplace",
        "name": "团队市场",
        "type": "builtin",
        "url": "https://teams.codebuddy.ai/marketplace/registry.json",
        "description": "团队共享插件市场",
        "enabled": False,
        "plugin_count": 0,
        "created_at": "2025-01-01T00:00:00Z",
    },
}

# ── 内置注册表（包含 MCP / AWP / Skill / Command / Hook 插件）──
_BUILTIN_REGISTRY: list[dict[str, Any]] = [
    # ═══ MCP 服务器 ═══
    {
        "name": "mcp-filesystem",
        "display_name": "MCP Filesystem",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Official MCP server for secure file system operations",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        "type": "mcp",
        "category": "filesystem",
        "tags": ["mcp", "filesystem", "file", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 15200,
        "rating": 4.8,
        "config_schema": {"allowed_directories": ["/workspace"]},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-github",
        "display_name": "MCP GitHub",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "GitHub API integration for repository management, issues, PRs",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/github",
        "type": "mcp",
        "category": "devops",
        "tags": ["mcp", "github", "git", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 12800,
        "rating": 4.7,
        "config_schema": {"github_token": ""},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-postgres",
        "display_name": "MCP PostgreSQL",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "PostgreSQL database access with read-only query capabilities",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        "type": "mcp",
        "category": "database",
        "tags": ["mcp", "postgres", "database", "sql", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 9800,
        "rating": 4.6,
        "config_schema": {"connection_string": ""},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-brave-search",
        "display_name": "MCP Brave Search",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Web search via Brave Search API",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
        "type": "mcp",
        "category": "search",
        "tags": ["mcp", "search", "web", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 7600,
        "rating": 4.5,
        "config_schema": {"brave_api_key": ""},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-puppeteer",
        "display_name": "MCP Puppeteer",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Browser automation via Puppeteer for web scraping and screenshots",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer",
        "type": "mcp",
        "category": "browser",
        "tags": ["mcp", "browser", "puppeteer", "screenshot", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 6500,
        "rating": 4.4,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-sqlite",
        "display_name": "MCP SQLite",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "SQLite database operations with full query support",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
        "type": "mcp",
        "category": "database",
        "tags": ["mcp", "sqlite", "database", "sql", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 5800,
        "rating": 4.3,
        "config_schema": {"database_path": ":memory:"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-memory",
        "display_name": "MCP Memory",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Knowledge graph-based memory system for persistent context across conversations",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
        "type": "mcp",
        "category": "ai",
        "tags": ["mcp", "memory", "knowledge-graph", "context", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 7200,
        "rating": 4.6,
        "config_schema": {"storage_path": "./memory"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-figma",
        "display_name": "MCP Figma",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Figma design tool integration — access design files, components, and styles",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/figma",
        "type": "mcp",
        "category": "design",
        "tags": ["mcp", "figma", "design", "ui", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 8900,
        "rating": 4.7,
        "config_schema": {"figma_token": ""},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-gitlab",
        "display_name": "MCP GitLab",
        "author": "community",
        "version": "0.9.0",
        "desc": "GitLab API integration for CI/CD, merge requests, and repository management",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/gitlab",
        "type": "mcp",
        "category": "devops",
        "tags": ["mcp", "gitlab", "ci-cd", "community"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 4300,
        "rating": 4.2,
        "config_schema": {"gitlab_token": "", "gitlab_host": "https://gitlab.com"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-slack",
        "display_name": "MCP Slack",
        "author": "community",
        "version": "0.8.0",
        "desc": "Slack workspace integration — send messages, read channels, manage users",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/slack",
        "type": "mcp",
        "category": "communication",
        "tags": ["mcp", "slack", "chat", "community"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 3400,
        "rating": 4.1,
        "config_schema": {"slack_bot_token": ""},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "mcp-sequential-thinking",
        "display_name": "MCP Sequential Thinking",
        "author": "anthropic",
        "version": "1.0.0",
        "desc": "Dynamic problem-solving through thought sequences for complex reasoning",
        "repo": "https://github.com/modelcontextprotocol/servers/tree/main/src/sequential-thinking",
        "type": "mcp",
        "category": "ai",
        "tags": ["mcp", "reasoning", "thinking", "problem-solving", "official"],
        "download_url": "https://github.com/modelcontextprotocol/servers/archive/refs/heads/main.zip",
        "installs": 6100,
        "rating": 4.5,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    # ═══ AWP 插件 ═══
    {
        "name": "awp-code-reviewer",
        "display_name": "Code Reviewer",
        "author": "ai-fullstack",
        "version": "0.2.0",
        "desc": "AI-powered code review plugin with static analysis and style checking",
        "repo": "https://github.com/ai-fullstack/awp-code-reviewer",
        "type": "awp",
        "category": "code-quality",
        "tags": ["awp", "code-review", "lint", "static-analysis"],
        "download_url": "https://github.com/ai-fullstack/awp-code-reviewer/archive/main.zip",
        "installs": 3200,
        "rating": 4.6,
        "config_schema": {"strict_mode": False, "max_issues": 50},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "awp-project-scaffold",
        "display_name": "Project Scaffolder",
        "author": "ai-fullstack",
        "version": "0.3.0",
        "desc": "Generate full-stack project scaffolds from natural language descriptions",
        "repo": "https://github.com/ai-fullstack/awp-project-scaffold",
        "type": "awp",
        "category": "generator",
        "tags": ["awp", "scaffold", "generator", "project"],
        "download_url": "https://github.com/ai-fullstack/awp-project-scaffold/archive/main.zip",
        "installs": 2100,
        "rating": 4.3,
        "config_schema": {"template_dir": "./templates", "default_framework": "react"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "awp-i18n-helper",
        "display_name": "i18n Helper",
        "author": "ai-fullstack",
        "version": "0.1.0",
        "desc": "Automatically extract and translate i18n strings in your project",
        "repo": "https://github.com/ai-fullstack/awp-i18n-helper",
        "type": "awp",
        "category": "translation",
        "tags": ["awp", "i18n", "translation", "locale"],
        "download_url": "https://github.com/ai-fullstack/awp-i18n-helper/archive/main.zip",
        "installs": 890,
        "rating": 4.1,
        "config_schema": {"source_lang": "en", "target_langs": ["zh-CN", "ja"]},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "awp-api-doc-gen",
        "display_name": "API Doc Generator",
        "author": "ai-fullstack",
        "version": "0.2.1",
        "desc": "Generate OpenAPI/Swagger docs from route definitions automatically",
        "repo": "https://github.com/ai-fullstack/awp-api-doc-gen",
        "type": "awp",
        "category": "documentation",
        "tags": ["awp", "api", "swagger", "openapi", "docs"],
        "download_url": "https://github.com/ai-fullstack/awp-api-doc-gen/archive/main.zip",
        "installs": 1500,
        "rating": 4.5,
        "config_schema": {"output_format": "yaml", "include_examples": True},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "awp-deploy-helper",
        "display_name": "Deploy Helper",
        "author": "ai-fullstack",
        "version": "0.1.0",
        "desc": "One-click deployment to CloudStudio / EdgeOne Pages / Lighthouse",
        "repo": "https://github.com/ai-fullstack/awp-deploy-helper",
        "type": "awp",
        "category": "devops",
        "tags": ["awp", "deploy", "cloud", "publish"],
        "download_url": "https://github.com/ai-fullstack/awp-deploy-helper/archive/main.zip",
        "installs": 670,
        "rating": 4.0,
        "config_schema": {"provider": "cloudstudio", "auto_build": True},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "awp-api-tester",
        "display_name": "API Tester",
        "author": "ai-fullstack",
        "version": "0.2.0",
        "desc": "Interactive API testing with request builder, environment variables, and assertions",
        "repo": "https://github.com/ai-fullstack/awp-api-tester",
        "type": "awp",
        "category": "devops",
        "tags": ["awp", "api", "testing", "http"],
        "download_url": "https://github.com/ai-fullstack/awp-api-tester/archive/main.zip",
        "installs": 1200,
        "rating": 4.4,
        "config_schema": {"collection_path": "./api-tests"},
        "source_id": "codebuddy-plugins-official",
    },
    # ═══ 技能包 (Skills) ═══
    {
        "name": "skill-find-skills",
        "display_name": "find-skills",
        "author": "codebuddy",
        "version": "1.2.0",
        "desc": "Helps discover and install agent skills from the marketplace",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/find-skills",
        "type": "skill",
        "category": "agent",
        "tags": ["skill", "skills", "discovery", "install", "agent"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 8700,
        "rating": 4.7,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-agent-browser",
        "display_name": "agent-browser",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Browser automation — open pages, take screenshots, extract content, click elements",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/agent-browser",
        "type": "skill",
        "category": "browser",
        "tags": ["skill", "skills", "browser", "automation", "screenshot"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 7500,
        "rating": 4.6,
        "config_schema": {"headless": True, "timeout": 30},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-docx",
        "display_name": "docx",
        "author": "codebuddy",
        "version": "1.1.0",
        "desc": "Create, read, edit Word documents (.docx) — formatting, TOC, headers, images",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/docx",
        "type": "skill",
        "category": "documentation",
        "tags": ["skill", "skills", "docx", "word", "document", "office"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 6800,
        "rating": 4.5,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-pdf",
        "display_name": "pdf",
        "author": "codebuddy",
        "version": "1.1.0",
        "desc": "Read, merge, split, rotate, watermark PDFs. OCR scanned documents to text.",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/pdf",
        "type": "skill",
        "category": "documentation",
        "tags": ["skill", "skills", "pdf", "ocr", "document"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 7200,
        "rating": 4.7,
        "config_schema": {"ocr_language": "eng+chi_sim"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-xlsx",
        "display_name": "xlsx",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Create and edit spreadsheets — formulas, charts, pivot tables, data cleaning",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/xlsx",
        "type": "skill",
        "category": "documentation",
        "tags": ["skill", "skills", "xlsx", "excel", "spreadsheet", "data"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 5900,
        "rating": 4.4,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-pptx",
        "display_name": "pptx",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Create PowerPoint presentations — slide decks, templates, speaker notes",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/pptx",
        "type": "skill",
        "category": "documentation",
        "tags": ["skill", "skills", "pptx", "powerpoint", "presentation"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 5400,
        "rating": 4.3,
        "config_schema": {"template_dir": "./templates"},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-playwright-cli",
        "display_name": "playwright-cli",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Web testing automation — fill forms, take screenshots, data extraction",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/playwright-cli",
        "type": "skill",
        "category": "browser",
        "tags": ["skill", "skills", "playwright", "testing", "browser", "automation"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 6200,
        "rating": 4.6,
        "config_schema": {"browser": "chromium", "headless": True},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-skill-creator",
        "display_name": "skill-creator",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Guide for creating effective agent skills with specialized knowledge",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/skill-creator",
        "type": "skill",
        "category": "agent",
        "tags": ["skill", "skills", "creator", "agent", "development"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 4100,
        "rating": 4.2,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
    # ═══ 命令/钩子插件 (Commands/Hooks) ═══
    {
        "name": "cmd-conventional-commit",
        "display_name": "Conventional Commit",
        "author": "community",
        "version": "0.5.0",
        "desc": "Enforce conventional commit message format with AI-assisted generation",
        "repo": "https://github.com/community-plugins/conventional-commit",
        "type": "command",
        "category": "devops",
        "tags": ["command", "commands", "git", "commit", "conventional"],
        "download_url": "https://github.com/community-plugins/conventional-commit/archive/main.zip",
        "installs": 3100,
        "rating": 4.3,
        "config_schema": {"types": ["feat", "fix", "docs", "chore", "refactor"], "scope_required": False},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "hook-pre-push-check",
        "display_name": "Pre-Push Check",
        "author": "community",
        "version": "0.4.0",
        "desc": "Run lint, test, and type-check before git push with AI analysis",
        "repo": "https://github.com/community-plugins/pre-push-check",
        "type": "hook",
        "category": "devops",
        "tags": ["hook", "hooks", "git", "pre-push", "lint", "test"],
        "download_url": "https://github.com/community-plugins/pre-push-check/archive/main.zip",
        "installs": 2600,
        "rating": 4.1,
        "config_schema": {"checks": ["lint", "test", "type-check"], "auto_fix": True},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "cmd-auto-changelog",
        "display_name": "Auto Changelog",
        "author": "community",
        "version": "0.6.0",
        "desc": "Auto-generate changelog from git history with AI categorization",
        "repo": "https://github.com/community-plugins/auto-changelog",
        "type": "command",
        "category": "documentation",
        "tags": ["command", "commands", "changelog", "release", "auto"],
        "download_url": "https://github.com/community-plugins/auto-changelog/archive/main.zip",
        "installs": 1900,
        "rating": 4.0,
        "config_schema": {"output": "CHANGELOG.md", "categories": ["Added", "Changed", "Fixed"]},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "hook-file-watcher",
        "display_name": "File Watcher",
        "author": "community",
        "version": "0.3.0",
        "desc": "Auto-trigger AI actions when files change — format, lint, regenerate",
        "repo": "https://github.com/community-plugins/file-watcher",
        "type": "hook",
        "category": "devops",
        "tags": ["hook", "hooks", "watch", "file", "auto"],
        "download_url": "https://github.com/community-plugins/file-watcher/archive/main.zip",
        "installs": 1500,
        "rating": 3.9,
        "config_schema": {"patterns": ["**/*.ts", "**/*.vue"], "debounce_ms": 500},
        "source_id": "codebuddy-plugins-official",
    },
    # ═══ 模型路由/代理 ═══
    {
        "name": "skill-model-router",
        "display_name": "model-router",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "Smart model routing proxy — automatic Ollama local + cloud API fallback on port 18888",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/model-router",
        "type": "skill",
        "category": "ai",
        "tags": ["skill", "skills", "router", "proxy", "ollama", "model"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 4800,
        "rating": 4.5,
        "config_schema": {"port": 18888, "prefer_local": True},
        "source_id": "codebuddy-plugins-official",
    },
    {
        "name": "skill-多模态内容生成",
        "display_name": "多模态内容生成",
        "author": "codebuddy",
        "version": "1.0.0",
        "desc": "多模态内容生成 — 文生视频、图生视频、文生图片、文生3D模型、特效",
        "repo": "https://github.com/codebuddy-ai/skills/tree/main/multimodal-gen",
        "type": "skill",
        "category": "generator",
        "tags": ["skill", "skills", "multimodal", "video", "image", "3d"],
        "download_url": "https://github.com/codebuddy-ai/skills/archive/refs/heads/main.zip",
        "installs": 3600,
        "rating": 4.4,
        "config_schema": {},
        "source_id": "codebuddy-plugins-official",
    },
]

# 模拟已安装插件（与本地 plugins/ 目录同步）
_installed_plugins: dict[str, dict[str, Any]] = {}


# ── Pydantic 模型 ──────────────────────────────────────────

class PluginInstallRequest(BaseModel):
    """插件安装请求"""
    name: str
    version: str = "latest"
    source: str = "registry"  # registry | url | local


class PluginConfigRequest(BaseModel):
    """插件配置更新请求"""
    config: dict[str, Any] = {}


class MarketplaceSourceCreate(BaseModel):
    """添加市场源请求"""
    name: str
    type: str = "github"        # github | zip | local
    url: str = ""
    description: str = ""


# ── 初始化 ─────────────────────────────────────────────────

def _sync_installed() -> None:
    """扫描本地插件目录，同步已安装状态"""
    global _installed_plugins
    _installed_plugins.clear()

    if not _LOCAL_PLUGINS_DIR.exists():
        return

    for entry in _LOCAL_PLUGINS_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        meta_file = entry / "plugin.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                _installed_plugins[entry.name] = {
                    "name": meta.get("name", entry.name),
                    "display_name": meta.get("display_name", entry.name),
                    "version": meta.get("version", "0.1.0"),
                    "author": meta.get("author", "unknown"),
                    "desc": meta.get("desc", ""),
                    "type": meta.get("type", "awp"),
                    "installed_at": meta.get("installed_at", ""),
                    "config": meta.get("config", {}),
                    "enabled": True,
                }
            except Exception:
                pass

    # 更新源的插件计数
    _update_source_counts()


def _update_source_counts() -> None:
    """更新每个市场源的插件数量"""
    counts: dict[str, int] = {}
    for p in _BUILTIN_REGISTRY:
        sid = p.get("source_id", "codebuddy-plugins-official")
        counts[sid] = counts.get(sid, 0) + 1
    for sid, s in _sources.items():
        s["plugin_count"] = counts.get(sid, 0)


# ── API 路由：市场源管理 ──────────────────────────────────


@router.get("/sources")
async def list_marketplace_sources() -> dict[str, Any]:
    """列出所有市场源"""
    _update_source_counts()
    sources_list = sorted(_sources.values(), key=lambda s: s["enabled"], reverse=True)
    return {
        "sources": sources_list,
        "total": len(sources_list),
        "enabled_count": sum(1 for s in sources_list if s["enabled"]),
    }


@router.post("/sources")
async def add_marketplace_source(req: MarketplaceSourceCreate) -> dict[str, Any]:
    """
    添加新的市场源

    支持三种类型：
    - github: GitHub仓库地址 (如 https://github.com/user/repo)
    - zip: ZIP包直链地址
    - local: 本地文件路径
    """
    source_id = f"custom-{uuid.uuid4().hex[:8]}"
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    source = {
        "id": source_id,
        "name": req.name,
        "type": req.type,
        "url": req.url,
        "description": req.description,
        "enabled": True,
        "plugin_count": 0,
        "created_at": now,
    }
    _sources[source_id] = source
    logger.info("Marketplace source added: %s (%s)", req.name, source_id)
    return {
        "success": True,
        "source": source,
        "message": f"市场源「{req.name}」已添加",
    }


@router.delete("/sources/{source_id}")
async def remove_marketplace_source(source_id: str) -> dict[str, Any]:
    """删除自定义市场源（内置源不可删除）"""
    if source_id not in _sources:
        raise HTTPException(status_code=404, detail="市场源不存在")
    source = _sources[source_id]
    if source.get("type") == "builtin":
        raise HTTPException(status_code=400, detail="内置市场源不可删除")
    del _sources[source_id]
    logger.info("Marketplace source removed: %s", source_id)
    return {"success": True, "message": f"市场源「{source['name']}」已删除"}


@router.post("/sources/{source_id}/toggle")
async def toggle_marketplace_source(source_id: str) -> dict[str, Any]:
    """启用/禁用市场源"""
    if source_id not in _sources:
        raise HTTPException(status_code=404, detail="市场源不存在")
    source = _sources[source_id]
    source["enabled"] = not source.get("enabled", True)
    return {
        "success": True,
        "source_id": source_id,
        "enabled": source["enabled"],
        "message": f"市场源已{'启用' if source['enabled'] else '禁用'}",
    }


# ── API 路由：插件注册表 ──────────────────────────────────


@router.get("/registry")
async def get_plugin_registry(
    search: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类筛选"),
    plugin_type: str = Query("", description="类型: mcp|awp|skill|command|hook"),
    source_id: str = Query("", description="市场源ID筛选"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """
    获取插件注册表（浏览/搜索插件市场）

    支持按关键词搜索、分类、类型、市场源筛选。
    返回分页的插件列表，每个插件包含安装状态。
    """
    results = list(_BUILTIN_REGISTRY)

    # 按市场源筛选
    if source_id:
        results = [p for p in results if p.get("source_id") == source_id]
    else:
        # 默认只显示启用的源
        enabled_ids = {sid for sid, s in _sources.items() if s.get("enabled", True)}
        results = [p for p in results if p.get("source_id", "") in enabled_ids]

    # 搜索
    if search:
        q = search.lower()
        results = [
            p for p in results
            if q in p.get("name", "").lower()
            or q in p.get("display_name", "").lower()
            or q in p.get("desc", "").lower()
            or any(q in t.lower() for t in p.get("tags", []))
        ]

    # 分类筛选
    if category:
        results = [p for p in results if p.get("category") == category]

    # 类型筛选
    if plugin_type:
        results = [p for p in results if p.get("type") == plugin_type]

    # 注入安装状态
    _sync_installed()
    for p in results:
        p["installed"] = p["name"] in _installed_plugins
        if p["installed"]:
            installed = _installed_plugins[p["name"]]
            p["installed_version"] = installed.get("version", "")
            p["installed_enabled"] = installed.get("enabled", True)
            p["installed_config"] = installed.get("config", {})
        else:
            p["installed_version"] = None
            p["installed_enabled"] = False
            p["installed_config"] = None

    total = len(results)
    start = (page - 1) * size
    paged = results[start:start + size]

    # 类别列表
    categories = sorted(set(p.get("category", "other") for p in results))
    types = sorted(set(p.get("type", "unknown") for p in results))

    return {
        "data": paged,
        "total": total,
        "page": page,
        "size": size,
        "categories": categories,
        "types": types,
    }


@router.get("/registry/categories")
async def get_categories() -> dict[str, Any]:
    """获取所有插件分类及计数"""
    categories: dict[str, int] = {}
    for p in _BUILTIN_REGISTRY:
        cat = p.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
    return {"categories": [{"name": k, "count": v} for k, v in sorted(categories.items())]}


@router.get("/registry/{name}")
async def get_plugin_detail(name: str) -> dict[str, Any]:
    """获取单个插件详细信息"""
    for p in _BUILTIN_REGISTRY:
        if p["name"] == name:
            _sync_installed()
            detail = dict(p)
            detail["installed"] = name in _installed_plugins
            if detail["installed"]:
                installed = _installed_plugins[name]
                detail["installed_version"] = installed.get("version", "")
                detail["installed_config"] = installed.get("config", {})
                detail["installed_enabled"] = installed.get("enabled", True)
            return detail
    raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found in registry")


# ── API 路由：安装/卸载 ──────────────────────────────────


@router.post("/install")
async def install_plugin(req: PluginInstallRequest) -> dict[str, Any]:
    """
    从注册表安装插件到本地

    流程：
    1. 查找注册表中的插件
    2. 下载插件包
    3. 解压到 plugins/ 目录
    4. 注册到 _installed_plugins
    """
    plugin_def = None
    for p in _BUILTIN_REGISTRY:
        if p["name"] == req.name:
            plugin_def = p
            break

    if plugin_def is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{req.name}' not found in registry")

    # 创建插件目录结构
    plugin_dir = _LOCAL_PLUGINS_DIR / req.name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # 写入 plugin.json 元数据
    meta = {
        "name": plugin_def["name"],
        "display_name": plugin_def["display_name"],
        "version": plugin_def["version"],
        "author": plugin_def["author"],
        "desc": plugin_def["desc"],
        "type": plugin_def["type"],
        "category": plugin_def.get("category", "general"),
        "tags": plugin_def.get("tags", []),
        "repo": plugin_def.get("repo", ""),
        "config": plugin_def.get("config_schema", {}),
        "installed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    (plugin_dir / "plugin.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写入占位 main.py
    (plugin_dir / "main.py").write_text(f'''"""
Plugin: {plugin_def["display_name"]}
Type: {plugin_def["type"]}
Version: {plugin_def["version"]}

Auto-generated by plugin marketplace installer.
"""
from app.core.plugins.base import Plugin

class {_to_class_name(req.name)}(Plugin):
    name = "{plugin_def['name']}"
    author = "{plugin_def['author']}"
    version = "{plugin_def['version']}"
    desc = "{plugin_def['desc']}"
    display_name = "{plugin_def['display_name']}"

    async def initialize(self) -> None:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"{{self.display_name}} loaded")

    async def terminate(self) -> None:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"{{self.display_name}} unloaded")
''', encoding="utf-8")

    # 更新已安装列表
    _installed_plugins[req.name] = {
        "name": req.name,
        "display_name": plugin_def["display_name"],
        "version": plugin_def["version"],
        "author": plugin_def["author"],
        "desc": plugin_def["desc"],
        "type": plugin_def["type"],
        "installed_at": meta["installed_at"],
        "config": plugin_def.get("config_schema", {}),
        "enabled": True,
    }

    logger.info("Plugin installed: %s v%s", req.name, plugin_def["version"])

    return {
        "success": True,
        "plugin": req.name,
        "version": plugin_def["version"],
        "path": str(plugin_dir),
        "message": f"Plugin '{req.name}' installed successfully",
    }


@router.delete("/install/{name}")
async def uninstall_plugin(name: str) -> dict[str, Any]:
    """卸载已安装的插件"""
    plugin_dir = _LOCAL_PLUGINS_DIR / name
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' is not installed")

    shutil.rmtree(str(plugin_dir))
    _installed_plugins.pop(name, None)

    logger.info("Plugin uninstalled: %s", name)

    return {
        "success": True,
        "plugin": name,
        "message": f"Plugin '{name}' uninstalled successfully",
    }


# ── API 路由：已安装管理 ──────────────────────────────────


@router.get("/installed")
async def list_installed_plugins() -> dict[str, Any]:
    """列出本地已安装的插件"""
    _sync_installed()
    installed_list = [
        {
            "name": k,
            **v,
            "registry_info": next(
                (p for p in _BUILTIN_REGISTRY if p["name"] == k), None
            ),
        }
        for k, v in _installed_plugins.items()
    ]
    return {"data": installed_list, "total": len(installed_list)}


@router.put("/installed/{name}/config")
async def update_plugin_config(name: str, req: PluginConfigRequest) -> dict[str, Any]:
    """更新插件配置"""
    plugin_dir = _LOCAL_PLUGINS_DIR / name
    if not plugin_dir.exists():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' is not installed")

    meta_file = plugin_dir / "plugin.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        meta["config"] = {**meta.get("config", {}), **req.config}
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if name in _installed_plugins:
        _installed_plugins[name]["config"] = {
            **_installed_plugins[name].get("config", {}),
            **req.config,
        }

    return {
        "success": True,
        "plugin": name,
        "config": _installed_plugins.get(name, {}).get("config", {}),
    }


@router.post("/installed/{name}/toggle")
async def toggle_plugin(name: str) -> dict[str, Any]:
    """切换插件的启用/禁用状态"""
    if name not in _installed_plugins:
        _sync_installed()
    if name not in _installed_plugins:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' is not installed")

    current = _installed_plugins[name].get("enabled", True)
    _installed_plugins[name]["enabled"] = not current

    return {
        "success": True,
        "plugin": name,
        "enabled": not current,
    }


@router.get("/stats")
async def get_marketplace_stats() -> dict[str, Any]:
    """获取插件市场统计数据"""
    _sync_installed()
    total_plugins = len(_BUILTIN_REGISTRY)
    total_installed = len(_installed_plugins)
    enabled_installed = sum(1 for p in _installed_plugins.values() if p.get("enabled", True))

    type_counts: dict[str, int] = {}
    for p in _BUILTIN_REGISTRY:
        t = p.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    category_counts: dict[str, int] = {}
    for p in _BUILTIN_REGISTRY:
        cat = p.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total_plugins": total_plugins,
        "total_installed": total_installed,
        "enabled_installed": enabled_installed,
        "type_counts": type_counts,
        "category_counts": category_counts,
        "sources_count": len(_sources),
        "enabled_sources_count": sum(1 for s in _sources.values() if s.get("enabled", True)),
    }


# ── 辅助函数 ──────────────────────────────────────────────

def _to_class_name(name: str) -> str:
    """将 kebab-case 转为 PascalCase"""
    return "".join(part.capitalize() for part in name.replace("-", " ").replace("_", " ").split())
