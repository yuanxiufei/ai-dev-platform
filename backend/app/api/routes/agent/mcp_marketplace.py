"""
MCP 市场路由 — 预设 MCP 服务器集市 (Session 09: 数据库持久化)

端点:
  GET  /agent/mcp/marketplace       — MCP 市场列表（分类展示，含动态评分）
  POST /agent/mcp/marketplace/install — 安装/配置市场中的 MCP 服务器（记录统计）
  GET  /agent/mcp/marketplace/stats  — 市场统计（安装排行 + 分类统计）
  POST /agent/mcp/marketplace/seed   — 初始化种子数据
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import select, func

from app.api.deps import SessionDep, commit_or_rollback
from app.api.routes.agent.mcp_servers import get_mcp_manager, MCPAddServerRequest
from app.core.mcp import MCPServerConfig, MCPTransport
from app.models.mcp_models import McpMarketplaceEntry, McpInstalledServer

logger = logging.getLogger("api.agent.mcp_marketplace")

router = APIRouter(prefix="/agent/mcp/marketplace", tags=["agent"])


# ── Session 09: 动态评分 & 数据库辅助 ──────────────────────────

def _dynamic_score(base_stars: int, total_installs: int, recent_installs_30d: int) -> float:
    """综合动态评分 (0~5)。

    公式: score = min(5, log₂(1+installs)×0.6 + log₂(1+recent)×0.3 + log₂(1+stars)×0.1)
    """
    raw = (
        math.log2(1 + total_installs) * 0.6 +
        math.log2(1 + recent_installs_30d) * 0.3 +
        math.log2(1 + base_stars) * 0.1
    )
    return round(min(5.0, raw), 2)


def _recalc_dynamic_stats(session, entry: McpMarketplaceEntry) -> None:
    """根据安装记录重新计算 installs 和 score。"""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    total = session.exec(
        select(func.count()).where(McpInstalledServer.preset_id == entry.preset_id)
    ).one()
    recent = session.exec(
        select(func.count()).where(
            McpInstalledServer.preset_id == entry.preset_id,
            McpInstalledServer.installed_at >= thirty_days_ago,
        )
    ).one()
    entry.installs = total
    entry.score = _dynamic_score(entry.stars, total, recent)
    entry.updated_at = datetime.now(timezone.utc)


def _entry_to_item(entry: McpMarketplaceEntry) -> dict:
    """数据库模型 → API 响应字典。"""
    def _load(raw, default):
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return {
        "id": entry.preset_id,
        "name": entry.name,
        "description": entry.description or "",
        "icon": entry.icon,
        "category": entry.category,
        "features": _load(entry.features, []),
        "tags": _load(entry.tags, []),
        "author": entry.author,
        "version": entry.version,
        "stars": entry.stars,
        "installs": entry.installs,
        "score": entry.score,
        "transport": entry.transport,
        "url": entry.url,
        "command": entry.command,
        "args": _load(entry.args, []),
        "env_config": _load(entry.env_config, {}),
        "setup_guide": entry.setup_guide or "",
        "homepage": entry.homepage,
        "source_code": entry.source_code,
        "license": entry.license_name,
    }


_MCP_MARKETPLACE_MAX = 200

async def _get_db_entries(session) -> list[McpMarketplaceEntry]:
    """获取数据库中活跃的市场条目（自动种子化）。"""
    entries = session.exec(
        select(McpMarketplaceEntry).where(McpMarketplaceEntry.is_active == True)
        .order_by(McpMarketplaceEntry.score.desc())
        .limit(_MCP_MARKETPLACE_MAX)
    ).all()
    if not entries:
        # 自动种子化
        await _seed_marketplace(session)
        entries = session.exec(
            select(McpMarketplaceEntry).where(McpMarketplaceEntry.is_active == True)
            .order_by(McpMarketplaceEntry.score.desc())
            .limit(_MCP_MARKETPLACE_MAX)
        ).all()
    # 触发动态评分重算
    for e in entries:
        if e.installs > 0:
            _recalc_dynamic_stats(session, e)
    if entries:
        commit_or_rollback(session)
    return entries


# ── 种子数据 ────────────────────────────────────────────────

# 种子预设 ID 列表（已在旧版内存中定义，这里只存最小元数据用于自动填充）
_SEED_PRESET_IDS = [
    "cnb", "cloudbase", "tapd", "cos", "edgeone", "cloudstudio",
    "lighthouse", "tca", "tdesign", "coding-devops", "demoway",
    "gitlab", "github", "postgres", "sqlite", "filesystem",
    "brave-search", "puppeteer", "mem0", "sequential-thinking",
    "figma", "notion", "slack", "zhipu-mcp",
]


def _FIND_PRESET(preset_id: str) -> MCPPresetServer | None:
    """从旧版内存预设列表中查找条目。"""
    for s in MARKETPLACE_SERVERS:
        if s.id == preset_id:
            return s
    return None


async def _seed_marketplace(session) -> int:
    """Session 09: 从硬编码预设种子化数据库（幂等，已有则跳过）。"""
    seeded = 0
    for preset_id in _SEED_PRESET_IDS:
        exists = session.exec(
            select(McpMarketplaceEntry).where(McpMarketplaceEntry.preset_id == preset_id)
        ).first()
        if exists:
            continue
        # 从旧版 MARKETPLACE_SERVERS 查找详细数据
        preset = _FIND_PRESET(preset_id)
        if not preset:
            continue
        entry = McpMarketplaceEntry(
            preset_id=preset.id,
            name=preset.name,
            description=preset.description,
            icon=preset.icon,
            category=preset.category,
            features=json.dumps(preset.features) if preset.features else None,
            tags=json.dumps(preset.tags) if preset.tags else None,
            author=preset.author,
            version=preset.version,
            homepage=preset.homepage,
            source_code=preset.source_code,
            setup_guide=preset.setup_guide,
            transport=preset.transport,
            url=preset.url,
            command=preset.command,
            args=json.dumps(preset.args) if preset.args else None,
            env_config=json.dumps(preset.env_config) if preset.env_config else None,
            stars=preset.stars,
            installs=preset.installs,
            score=_dynamic_score(preset.stars, preset.installs, 0),
        )
        session.add(entry)
        seeded += 1
    if seeded:
        commit_or_rollback(session)
        logger.info("MCP marketplace seeded: %d entries", seeded)
    return seeded


# ── 市场预设数据（保留旧版兼容）───────────────────────────────

class MCPPresetServer(BaseModel):
    """市场中预设的 MCP 服务器"""
    id: str
    name: str
    description: str
    icon: str = ""           # emoji or icon name
    category: str = ""        # dev_tools, cloud, database, productivity, etc.
    features: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    author: str = ""
    version: str = "1.0.0"
    stars: int = 0
    installs: int = 0
    transport: str = "sse"    # sse | streamable_http | stdio
    url: str = ""             # 默认 URL
    command: str = ""         # stdio 命令
    args: list[str] = Field(default_factory=list)
    env_config: dict[str, str] = Field(default_factory=dict)
    setup_guide: str = ""     # 安装说明
    homepage: str = ""
    source_code: str = ""
    license: str = "MIT"


# ── 预设 MCP 服务器列表 ──────────────────────────────────────

MARKETPLACE_SERVERS: list[MCPPresetServer] = [
    MCPPresetServer(
        id="cnb",
        name="CNB MCP Server",
        description="连接腾讯工蜂 CNB 代码仓库，实现 AI 辅助代码审查、PR 管理等自动化操作。",
        icon="🐱",
        category="dev_tools",
        features=["代码审查", "PR 管理", "Branch 操作", "Issue 追踪", "代码搜索"],
        tags=["git", "codebase", "腾讯工蜂"],
        author="CNB Team",
        version="2.0.0",
        stars=320,
        installs=1280,
        transport="sse",
        url="https://cnb.tencent.com/api/mcp/sse",
        setup_guide="需要 CNB 账号并在设置中生成 MCP 令牌",
        homepage="https://cnb.tencent.com",
        source_code="https://git.woa.com/cnb/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="cloudbase",
        name="CloudBase AI ToolKit",
        description="腾讯云开发 CloudBase 一站式后端服务，支持数据库、云函数、存储、认证等。",
        icon="☁️",
        category="cloud",
        features=["云数据库", "云函数", "云存储", "用户认证", "静态托管"],
        tags=["baas", "serverless", "腾讯云"],
        author="Tencent CloudBase",
        version="1.5.0",
        stars=560,
        installs=3200,
        transport="sse",
        url="https://mcp.cloudbase.net/sse",
        env_config={"TCB_ENV_ID": "你的环境ID"},
        setup_guide="登录 CloudBase 控制台获取环境 ID 和 API 密钥",
        homepage="https://cloudbase.net",
        source_code="https://github.com/TencentCloudBase/cloudbase-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="tapd",
        name="TAPD MCP Server",
        description="连接 TAPD 敏捷开发平台，实现需求、缺陷、任务的 AI 自动化管理。",
        icon="📋",
        category="dev_tools",
        features=["需求管理", "缺陷追踪", "任务分配", "迭代计划", "看板同步"],
        tags=["pm", "agile", "tapd"],
        author="TAPD Team",
        version="1.3.0",
        stars=280,
        installs=1560,
        transport="sse",
        url="https://mcp.tapd.cn/sse",
        env_config={"TAPD_API_TOKEN": "你的API令牌"},
        setup_guide="TAPD 个人设置 → API 密钥 → 生成令牌",
        homepage="https://tapd.cn",
        source_code="https://github.com/tapd/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="cos",
        name="Tencent Cloud COS MCP Server",
        description="对象存储 COS 服务，AI 可直接上传、下载、管理云端文件。",
        icon="🪣",
        category="cloud",
        features=["文件上传/下载", "Bucket 管理", "CDN 加速", "生命周期管理", "图片处理"],
        tags=["storage", "cdn", "腾讯云"],
        author="Tencent Cloud",
        version="1.2.0",
        stars=210,
        installs=980,
        transport="sse",
        url="https://mcp.cos.tencent.com/sse",
        env_config={"COS_SECRET_ID": "", "COS_SECRET_KEY": ""},
        setup_guide="访问腾讯云控制台 → 访问密钥 → 创建 API 密钥",
        homepage="https://cloud.tencent.com/product/cos",
        source_code="https://github.com/tencentyun/cos-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="edgeone",
        name="EdgeOne Pages MCP Server",
        description="腾讯 EdgeOne Pages 边缘部署，快速将前端项目部署到全球 CDN。",
        icon="🌐",
        category="cloud",
        features=["自动部署", "全球 CDN", "SSL 证书", "域名绑定", "边缘函数"],
        tags=["deploy", "cdn", "edge"],
        author="Tencent EdgeOne",
        version="1.1.0",
        stars=180,
        installs=850,
        transport="sse",
        url="https://mcp.edgeone.ai/sse",
        env_config={"EDGEONE_API_TOKEN": ""},
        setup_guide="EdgeOne 控制台 → API Token → 创建密钥",
        homepage="https://edgeone.ai",
        source_code="https://github.com/TencentEdgeOne/eo-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="cloudstudio",
        name="Cloud Studio Sandbox",
        description="腾讯云开发环境 Cloud Studio，AI 可自动创建、配置开发容器。",
        icon="💻",
        category="dev_tools",
        features=["开发容器", "环境模板", "终端访问", "协作共享", "Web IDE"],
        tags=["ide", "sandbox", "cloud"],
        author="Cloud Studio Team",
        version="1.0.0",
        stars=150,
        installs=720,
        transport="sse",
        url="https://mcp.cloudstudio.net/sse",
        env_config={"CS_API_KEY": ""},
        setup_guide="CloudStudio 设置 → API 密钥 → 生成",
        homepage="https://cloudstudio.net",
        source_code="https://github.com/cloudstudio/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="lighthouse",
        name="Lighthouse MCP Server",
        description="腾讯轻量云服务器管理，AI 助手可直接管理云服务器实例。",
        icon="🏠",
        category="cloud",
        features=["实例管理", "防火墙配置", "快照备份", "监控告警", "远程登录"],
        tags=["vps", "server", "腾讯云"],
        author="Tencent Cloud",
        version="1.0.0",
        stars=130,
        installs=650,
        transport="sse",
        url="https://mcp.lighthouse.tencent.com/sse",
        env_config={"LH_SECRET_ID": "", "LH_SECRET_KEY": ""},
        setup_guide="腾讯云控制台 → 访问密钥 → 生成 API 密钥",
        homepage="https://cloud.tencent.com/product/lighthouse",
        source_code="https://github.com/tencentyun/lighthouse-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="tca",
        name="TCA MCP Server",
        description="腾讯云代码分析 TCA，AI 驱动的代码质量检测与安全扫描。",
        icon="🔍",
        category="dev_tools",
        features=["代码扫描", "质量分析", "安全审计", "规范检查", "报告生成"],
        tags=["lint", "security", "quality"],
        author="TCA Team",
        version="1.2.0",
        stars=170,
        installs=580,
        transport="sse",
        url="https://mcp.tca.tencent.com/sse",
        env_config={"TCA_TOKEN": ""},
        setup_guide="TCA 平台 → 个人设置 → 生成 Token",
        homepage="https://tca.tencent.com",
        source_code="https://github.com/TCATeam/tca-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="tdesign",
        name="TDesign MCP Server",
        description="TDesign 组件库助手，AI 生成代码时自动匹配 TDesign 组件与最佳实践。",
        icon="🎨",
        category="dev_tools",
        features=["组件查询", "代码生成", "设计规范", "主题定制", "图标搜索"],
        tags=["ui", "components", "design-system"],
        author="TDesign Team",
        version="1.3.0",
        stars=350,
        installs=2100,
        transport="sse",
        url="https://mcp.tdesign.tencent.com/sse",
        setup_guide="无需额外配置，即开即用",
        homepage="https://tdesign.tencent.com",
        source_code="https://github.com/TDesignOteam/tdesign-mcp",
        license="MIT",
    ),
    MCPPresetServer(
        id="coding-devops",
        name="CODING DevOps MCP Server",
        description="连接 CODING DevOps 平台，自动化 CI/CD、代码仓库与项目管理。",
        icon="🔄",
        category="dev_tools",
        features=["CI/CD 流水线", "代码仓库", "项目协同", "测试管理", "制品库"],
        tags=["devops", "ci-cd", "coding"],
        author="CODING Team",
        version="1.4.0",
        stars=240,
        installs=1100,
        transport="sse",
        url="https://mcp.coding.net/sse",
        env_config={"CODING_API_TOKEN": ""},
        setup_guide="CODING → 个人设置 → 访问令牌 → 生成",
        homepage="https://coding.net",
        source_code="https://github.com/Coding/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="demoway",
        name="DemoWay AI-Design",
        description="AI 驱动的 UI 设计与原型生成，描述想法即生成高保真设计稿。",
        icon="✨",
        category="productivity",
        features=["UI 生成", "原型设计", "组件导出", "响应式布局", "设计系统"],
        tags=["design", "ui", "prototype"],
        author="DemoWay",
        version="1.0.0",
        stars=420,
        installs=1850,
        transport="sse",
        url="https://mcp.demoway.com/sse",
        env_config={"DEMOWAY_API_KEY": ""},
        setup_guide="DemoWay 官网注册获取 API Key",
        homepage="https://demoway.com",
        source_code="https://github.com/demoway/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="gitlab",
        name="GitLab MCP Server",
        description="连接 GitLab 代码托管平台，管理仓库、MR、Issue 和 CI/CD 流水线。",
        icon="🦊",
        category="dev_tools",
        features=["仓库管理", "MR 操作", "Issue 追踪", "CI/CD 触发", "Wiki 编辑"],
        tags=["git", "codebase", "collaboration"],
        author="GitLab Community",
        version="2.1.0",
        stars=480,
        installs=2900,
        transport="sse",
        url="https://gitlab.com/api/mcp/sse",
        env_config={"GITLAB_API_TOKEN": ""},
        setup_guide="GitLab → Settings → Access Tokens → 创建",
        homepage="https://gitlab.com",
        source_code="https://gitlab.com/gitlab-org/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="github",
        name="GitHub MCP Server",
        description="连接 GitHub 平台，AI 融入仓库管理、PR 审查、Issue 操作等。",
        icon="🔷",
        category="dev_tools",
        features=["仓库管理", "PR 审查", "Issue 追踪", "Actions", "代码搜索"],
        tags=["git", "open-source", "github"],
        author="GitHub",
        version="2.2.0",
        stars=890,
        installs=5200,
        transport="sse",
        url="https://api.github.com/mcp",
        env_config={"GITHUB_TOKEN": ""},
        setup_guide="GitHub → Settings → Developer settings → Personal access tokens",
        homepage="https://github.com",
        source_code="https://github.com/github/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="postgres",
        name="PostgreSQL MCP Server",
        description="PostgreSQL 数据库 MCP 连接，AI 可查询表结构、执行 SQL、分析数据。",
        icon="🐘",
        category="database",
        features=["Schema 查询", "SQL 执行", "数据分析", "表结构导出", "查询优化"],
        tags=["database", "sql", "analytics"],
        author="MCP Community",
        version="1.4.0",
        stars=360,
        installs=2400,
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost:5432/db"],
        env_config={"DATABASE_URL": ""},
        setup_guide="配置 PostgreSQL 连接字符串后即可使用",
        homepage="https://www.postgresql.org",
        source_code="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        license="MIT",
    ),
    MCPPresetServer(
        id="sqlite",
        name="SQLite MCP Server",
        description="SQLite 数据库本地访问，无需网络，快速分析和操作数据库文件。",
        icon="🗄️",
        category="database",
        features=["数据库查询", "表操作", "数据导入导出", "Schema 分析", "离线使用"],
        tags=["database", "sql", "local"],
        author="MCP Community",
        version="1.0.0",
        stars=190,
        installs=1600,
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sqlite", "/path/to/database.db"],
        setup_guide="指定本地 .db 文件路径即可",
        homepage="https://www.sqlite.org",
        source_code="https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
        license="MIT",
    ),
    MCPPresetServer(
        id="filesystem",
        name="Filesystem MCP Server",
        description="文件系统访问，AI 可安全读写指定目录内的文件内容和结构。",
        icon="📁",
        category="productivity",
        features=["文件读写", "目录浏览", "文件搜索", "文本替换", "路径安全限制"],
        tags=["files", "io", "local"],
        author="Anthropic",
        version="1.1.0",
        stars=520,
        installs=4800,
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
        setup_guide="指定允许访问的目录路径，确保安全性",
        homepage="https://modelcontextprotocol.io",
        source_code="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        license="MIT",
    ),
    MCPPresetServer(
        id="brave-search",
        name="Brave Search MCP Server",
        description="通过 Brave Search API 实现 AI 联网搜索，获取实时互联网信息。",
        icon="🔎",
        category="productivity",
        features=["网页搜索", "新闻搜索", "实时信息", "结构化结果", "多语言支持"],
        tags=["search", "web", "information"],
        author="Brave",
        version="1.0.0",
        stars=340,
        installs=2100,
        transport="sse",
        url="https://mcp.search.brave.com/sse",
        env_config={"BRAVE_API_KEY": ""},
        setup_guide="Brave Search API 官网注册获取 API Key",
        homepage="https://brave.com/search/api",
        source_code="https://github.com/brave/brave-mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="puppeteer",
        name="Puppeteer MCP Server",
        description="无头浏览器自动化，截图、网页测试、内容抓取、表单填写。",
        icon="🧭",
        category="dev_tools",
        features=["网页截图", "内容抓取", "表单填写", "自动化测试", "性能分析"],
        tags=["browser", "testing", "automation"],
        author="MCP Community",
        version="1.2.0",
        stars=410,
        installs=3100,
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        setup_guide="需要 Node.js 环境，首次运行自动安装 Chromium",
        homepage="https://pptr.dev",
        source_code="https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer",
        license="MIT",
    ),
    MCPPresetServer(
        id="mem0",
        name="Mem0 Memory MCP Server",
        description="AI 记忆服务 Mem0，让 AI 记住用户偏好和历史对话，实现个性化交互。",
        icon="🧠",
        category="productivity",
        features=["用户记忆", "偏好学习", "对话历史", "语义搜索", "多轮对话"],
        tags=["memory", "personalization", "context"],
        author="Mem0",
        version="1.0.0",
        stars=260,
        installs=1400,
        transport="sse",
        url="https://mcp.mem0.ai/sse",
        env_config={"MEM0_API_KEY": ""},
        setup_guide="Mem0 官网注册获取 API Key",
        homepage="https://mem0.ai",
        source_code="https://github.com/mem0ai/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="sequential-thinking",
        name="Sequential Thinking MCP Server",
        description="动态、反思式问题解决思维链，支持思维修正、分支探索与假设验证。",
        icon="💭",
        category="productivity",
        features=["思维推导", "分支探索", "假设验证", "不确定性量化", "推理修正"],
        tags=["reasoning", "thinking", "problem-solving"],
        author="MCP Community",
        version="1.0.0",
        stars=380,
        installs=2600,
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        setup_guide="需要 Node.js 环境，即开即用",
        source_code="https://github.com/modelcontextprotocol/servers/tree/main/src/sequential-thinking",
        license="MIT",
    ),
    MCPPresetServer(
        id="figma",
        name="Figma MCP Server",
        description="连接 Figma 设计平台，AI 可获取设计稿组件、样式和布局信息。",
        icon="🎨",
        category="dev_tools",
        features=["设计稿获取", "组件提取", "样式导出", "设计 Token", "资源下载"],
        tags=["design", "ui", "figma"],
        author="Figma Community",
        version="1.0.0",
        stars=450,
        installs=2200,
        transport="sse",
        url="https://mcp.figma.com/sse",
        env_config={"FIGMA_API_TOKEN": ""},
        setup_guide="Figma → Settings → Account → Personal Access Tokens",
        homepage="https://figma.com",
        source_code="https://github.com/figma/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="notion",
        name="Notion MCP Server",
        description="连接 Notion 工作空间，AI 管理文档、数据库、页面和知识库。",
        icon="📝",
        category="productivity",
        features=["页面管理", "数据库操作", "块编辑", "搜索", "知识库同步"],
        tags=["docs", "knowledge", "productivity"],
        author="Notion Community",
        version="1.1.0",
        stars=290,
        installs=1800,
        transport="sse",
        url="https://mcp.notion.so/sse",
        env_config={"NOTION_API_TOKEN": ""},
        setup_guide="Notion Integrations → 创建集成 → 获取 Token",
        homepage="https://notion.so",
        source_code="https://github.com/notion/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="slack",
        name="Slack MCP Server",
        description="连接 Slack 工作空间，AI 助手可发送消息、管理频道和搜索对话。",
        icon="💬",
        category="productivity",
        features=["消息发送", "频道管理", "对话搜索", "文件分享", "用户查询"],
        tags=["messaging", "collaboration", "team"],
        author="Slack Community",
        version="1.0.0",
        stars=200,
        installs=1200,
        transport="sse",
        url="https://mcp.slack.com/sse",
        env_config={"SLACK_BOT_TOKEN": ""},
        setup_guide="Slack Apps → 创建 Bot → 获取 Token",
        homepage="https://slack.com",
        source_code="https://github.com/slack/mcp-server",
        license="MIT",
    ),
    MCPPresetServer(
        id="zhipu-mcp",
        name="智谱 AI MCP Server",
        description="智谱 GLM 大模型 MCP 服务，支持代码生成、视觉理解、工具调用。",
        icon="🤖",
        category="ai_model",
        features=["大模型调用", "代码生成", "视觉理解", "工具编排", "API 代理"],
        tags=["ai", "llm", "智谱", "zhipu"],
        author="智谱 AI",
        version="1.0.0",
        stars=160,
        installs=890,
        transport="sse",
        url="https://open.bigmodel.cn/api/mcp/sse",
        env_config={"ZHIPU_API_KEY": ""},
        setup_guide="智谱开放平台注册获取 API Key",
        homepage="https://open.bigmodel.cn",
        source_code="https://github.com/zhipuai/mcp-server",
        license="MIT",
    ),
]


# ── 响应模型 ──────────────────────────────────────────────────

class MCPMarketplaceResponse(BaseModel):
    """MCP 市场列表响应"""
    servers: list[MCPPresetServer]
    total: int
    categories: list[str]


class MCPInstallRequest(BaseModel):
    """安装 MCP 服务器请求"""
    preset_id: str = Field(..., description="市场的预设服务器 ID")
    transport: str = Field(default="sse")
    url: str = Field(default="")
    command: str = Field(default="")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout: float = Field(default=30.0)


# ── 路由 ──────────────────────────────────────────────────────

@router.get("")
async def get_marketplace(
    session: SessionDep,
    category: str = "",
    search: str = "",
):
    """获取 MCP 市场列表（DB 持久化），支持按分类筛选和搜索"""
    entries = await _get_db_entries(session)
    items = [_entry_to_item(e) for e in entries]

    # 筛选
    if category:
        items = [it for it in items if it["category"] == category]

    if search:
        q = search.lower()
        items = [
            it for it in items
            if q in it["name"].lower()
            or q in (it.get("description") or "").lower()
            or any(q in t.lower() for t in it.get("tags", []))
            or any(q in f.lower() for f in it.get("features", []))
        ]

    # 分类列表（从 DB 聚合）
    cat_rows = session.exec(
        select(McpMarketplaceEntry.category, func.count(McpMarketplaceEntry.id))
        .where(McpMarketplaceEntry.is_active == True)
        .group_by(McpMarketplaceEntry.category)
    ).all()
    categories = sorted([cat for cat, _ in cat_rows if cat])

    return {
        "servers": items,
        "total": len(items),
        "categories": categories,
    }


@router.get("/categories")
async def get_categories(session: SessionDep) -> dict:
    """获取 MCP 市场所有分类（DB 聚合）"""
    rows = session.exec(
        select(McpMarketplaceEntry.category, func.count(McpMarketplaceEntry.id))
        .where(McpMarketplaceEntry.is_active == True)
        .group_by(McpMarketplaceEntry.category)
        .order_by(McpMarketplaceEntry.category)
    ).all()

    return {
        "categories": [
            {"id": cat, "name": CATEGORY_LABELS.get(cat, cat), "count": count}
            for cat, count in rows if cat
        ],
    }


@router.get("/{preset_id}")
async def get_preset_detail(session: SessionDep, preset_id: str):
    """获取某个 MCP 服务器的详细信息（DB）"""
    from fastapi import HTTPException
    entry = session.exec(
        select(McpMarketplaceEntry).where(
            McpMarketplaceEntry.preset_id == preset_id,
            McpMarketplaceEntry.is_active == True,
        )
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")
    # 动态重算评分
    _recalc_dynamic_stats(session, entry)
    commit_or_rollback(session)
    return _entry_to_item(entry)


@router.post("/install")
async def install_from_marketplace(session: SessionDep, payload: MCPInstallRequest) -> dict:
    """从市场安装 MCP 服务器（DB 持久化安装记录 + 统计更新）"""
    from fastapi import HTTPException

    # 查找数据库条目（优先 DB，回退内存预设）
    entry = session.exec(
        select(McpMarketplaceEntry).where(
            McpMarketplaceEntry.preset_id == payload.preset_id,
            McpMarketplaceEntry.is_active == True,
        )
    ).first()

    if not entry:
        preset = _FIND_PRESET(payload.preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail=f"Preset '{payload.preset_id}' not found")
        name = preset.name
        transport_val = payload.transport or preset.transport
        url = payload.url or preset.url
        command = payload.command or preset.command
        args = payload.args or preset.args
        env_vars = payload.env or preset.env_config
    else:
        name = entry.name
        transport_val = payload.transport or entry.transport
        url = payload.url or (entry.url or "")
        command = payload.command or entry.command
        args = payload.args or (json.loads(entry.args) if entry.args else [])
        env_vars = payload.env or (json.loads(entry.env_config) if entry.env_config else {})

    # 构建 MCP 服务器配置
    transport_map = {
        "sse": MCPTransport.SSE,
        "streamable_http": MCPTransport.STREAMABLE_HTTP,
        "stdio": MCPTransport.STDIO,
    }

    config = MCPServerConfig(
        name=name,
        transport=transport_map.get(transport_val, MCPTransport.SSE),
        url=url,
        command=command,
        args=args,
        env=env_vars,
        tool_prefix=payload.preset_id,
        auto_discover=True,
        timeout_seconds=payload.timeout,
    )

    manager = get_mcp_manager()
    manager.add_server(config)

    import time
    t0 = time.perf_counter()
    result = await manager.connect_all()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    tools_count = 0
    tools_names = []
    if result.success:
        tools = await manager.discover_all_tools()
        tools_count = len(tools)
        tools_names = [t.name for t in tools]

    # ── Session 09: 写入安装记录 + 更新市场统计 ──
    install_record = McpInstalledServer(
        preset_id=payload.preset_id,
        user_id=None,  # TODO: 从 auth 上下文获取
        server_name=name,
        status="connected" if result.success else "failed",
        error_message="; ".join(result.errors) if result.errors else None,
        tools_discovered=tools_count,
        install_duration_ms=round(elapsed_ms, 1),
        installed_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc) if result.success else None,
    )
    session.add(install_record)

    # 更新市场条目统计
    if entry:
        _recalc_dynamic_stats(session, entry)
        entry.last_installed_at = datetime.now(timezone.utc)

    commit_or_rollback(session)

    return {
        "success": result.success,
        "message": f"已安装 '{name}'" if result.success else f"连接失败: {name}",
        "preset": payload.preset_id,
        "tools_discovered": tools_count,
        "tools": tools_names,
        "errors": result.errors,
    }


@router.get("/stats")
async def get_marketplace_stats(session: SessionDep) -> dict:
    """Session 09: 市场统计 — 总安装数、热门排行、分类分布"""
    # 总安装数
    total_installs = session.exec(
        select(func.count()).select_from(McpInstalledServer)
        .where(McpInstalledServer.status == "connected")
    ).one()

    # Top 5 安装排行
    top_installed = session.exec(
        select(McpMarketplaceEntry.preset_id, McpMarketplaceEntry.name,
               McpMarketplaceEntry.installs, McpMarketplaceEntry.score)
        .where(McpMarketplaceEntry.is_active == True)
        .order_by(McpMarketplaceEntry.installs.desc())
        .limit(5)
    ).all()

    # Top 5 评分排行
    top_rated = session.exec(
        select(McpMarketplaceEntry.preset_id, McpMarketplaceEntry.name,
               McpMarketplaceEntry.installs, McpMarketplaceEntry.score)
        .where(McpMarketplaceEntry.is_active == True)
        .order_by(McpMarketplaceEntry.score.desc())
        .limit(5)
    ).all()

    # 分类安装分布
    cat_dist = session.exec(
        select(McpMarketplaceEntry.category, func.sum(McpMarketplaceEntry.installs))
        .where(McpMarketplaceEntry.is_active == True)
        .group_by(McpMarketplaceEntry.category)
        .order_by(McpMarketplaceEntry.category)
    ).all()

    # 活跃服务器数
    active_count = session.exec(
        select(func.count()).select_from(McpMarketplaceEntry)
        .where(McpMarketplaceEntry.is_active == True)
    ).one()

    return {
        "total_installs": total_installs,
        "active_servers": active_count,
        "top_installed": [
            {"id": pid, "name": name, "installs": inst, "score": score}
            for pid, name, inst, score in top_installed
        ],
        "top_rated": [
            {"id": pid, "name": name, "installs": inst, "score": score}
            for pid, name, inst, score in top_rated
        ],
        "category_distribution": [
            {"category": cat, "label": CATEGORY_LABELS.get(cat, cat), "installs": int(inst or 0)}
            for cat, inst in cat_dist if cat
        ],
    }


@router.post("/seed")
async def seed_marketplace(session: SessionDep) -> dict:
    """Session 09: 手动触发种子数据初始化（幂等）"""
    count = await _seed_marketplace(session)
    return {"seeded": count, "message": f"种子数据已初始化: {count} 条"}


# ── Session 09: 安装追踪 & 动态评分独立 API ──────────────────

@router.get("/installed")
async def get_installed_history(
    session: SessionDep,
    preset_id: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """获取安装历史记录（支持按 preset_id 筛选）"""
    stmt = select(McpInstalledServer).order_by(McpInstalledServer.installed_at.desc())
    count_stmt = select(func.count()).select_from(McpInstalledServer)

    if preset_id:
        stmt = stmt.where(McpInstalledServer.preset_id == preset_id)
        count_stmt = count_stmt.where(McpInstalledServer.preset_id == preset_id)

    total = session.exec(count_stmt).one()
    records = session.exec(stmt.offset(offset).limit(limit)).all()

    return {
        "data": [
            {
                "id": str(r.id),
                "preset_id": r.preset_id,
                "server_name": r.server_name,
                "status": r.status,
                "tools_discovered": r.tools_discovered,
                "install_duration_ms": r.install_duration_ms,
                "installed_at": r.installed_at.isoformat() if r.installed_at else None,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "error_message": r.error_message,
            }
            for r in records
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/{preset_id}/uninstall")
async def uninstall_preset(session: SessionDep, preset_id: str) -> dict:
    """卸载追踪：标记最近一次安装为已卸载"""
    from fastapi import HTTPException

    # 查找最近的 connected 安装记录
    record = session.exec(
        select(McpInstalledServer).where(
            McpInstalledServer.preset_id == preset_id,
            McpInstalledServer.status == "connected",
        ).order_by(McpInstalledServer.installed_at.desc())
    ).first()

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No active install found for '{preset_id}'",
        )

    record.status = "uninstalled"
    record.uninstalled_at = datetime.now(timezone.utc)

    # 降级市场 installs 计数
    entry = session.exec(
        select(McpMarketplaceEntry).where(
            McpMarketplaceEntry.preset_id == preset_id,
            McpMarketplaceEntry.is_active == True,
        )
    ).first()
    if entry and entry.installs > 0:
        entry.installs -= 1
        _recalc_dynamic_stats(session, entry)

    commit_or_rollback(session)
    return {
        "success": True,
        "message": f"已卸载 '{preset_id}'",
        "uninstalled_at": record.uninstalled_at.isoformat(),
    }


@router.post("/recalc")
async def recalc_all_scores(session: SessionDep) -> dict:
    """手动触发所有活跃市场条目的动态评分重算"""
    entries = session.exec(
        select(McpMarketplaceEntry).where(McpMarketplaceEntry.is_active == True)
    ).all()

    updated = 0
    for e in entries:
        old_score = e.score
        _recalc_dynamic_stats(session, e)
        if e.score != old_score:
            updated += 1

    if updated:
        commit_or_rollback(session)

    return {
        "message": f"评分重算完成: {updated}/{len(entries)} 条记录已更新",
        "total_entries": len(entries),
        "updated": updated,
    }


# ── 分类标签映射 ──────────────────────────────────────────────

CATEGORY_LABELS: dict[str, str] = {
    "dev_tools": "开发工具",
    "cloud": "云服务",
    "database": "数据库",
    "productivity": "效率工具",
    "ai_model": "AI 模型",
}
