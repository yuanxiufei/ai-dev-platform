"""
Session 58: External URI Opener — 对标 VSCode workbench/contrib/externalUriOpener

管理外部链接的打开策略:
  - 注册 URI opener (系统浏览器 / 内置浏览器 / 自定义)
  - 配置 URL 正则匹配规则
  - 优先级排序 + 已禁用回退

API:
  GET    /external-uri-openers          — 列出所有 opener 配置
  GET    /external-uri-openers/{id}     — 获取单个 opener
  POST   /external-uri-openers          — 注册/更新 opener
  DELETE /external-uri-openers/{id}     — 删除 opener
  POST   /external-uri-openers/match    — 测试 URL 匹配哪个 opener
"""

import json
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/external-uri-openers", tags=["external-uri-openers"])

# ── 持久化路径 ──
_STORE_DIR = Path("data")
_STORE_FILE = _STORE_DIR / "external_uri_openers.json"


# ── 数据模型 ──

class UriOpenerPattern(BaseModel):
    """URL 匹配模式"""
    regex: str = Field(..., description="正则表达式 (匹配完整 URL)")
    priority: int = Field(100, description="优先级 (数值越大越优先, 同 opener 下可有多条)")
    label: str = Field("", description="该模式的说明标签")


class UriOpenerConfig(BaseModel):
    """外部 URI 打开器配置"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8], description="唯一 ID")
    label: str = Field(..., description="显示名称 (如「系统浏览器」「内置浏览器」)")
    description: str = Field("", description="描述")
    action: str = Field("external", description="打开方式: external | internal | prompt")
    patterns: list[UriOpenerPattern] = Field(default_factory=list, description="URL 匹配模式列表")
    default_for_schemes: list[str] = Field(default_factory=list, description="默认处理的 URL scheme 列表")
    enabled: bool = Field(True, description="是否启用")
    is_builtin: bool = Field(False, description="是否为内置 opener (不可删除)")


class MatchRequest(BaseModel):
    url: str = Field(..., description="要测试的 URL")


class MatchResult(BaseModel):
    url: str
    matched: bool
    opener: Optional[UriOpenerConfig] = None
    pattern_index: int = -1
    all_candidates: list[dict] = Field(default_factory=list)


# ── 内置 Openers ──

BUILTIN_OPENERS: list[UriOpenerConfig] = [
    UriOpenerConfig(
        id="system-browser",
        label="系统浏览器",
        description="使用操作系统默认浏览器打开",
        action="external",
        default_for_schemes=["http", "https"],
        is_builtin=True,
        enabled=True,
    ),
    UriOpenerConfig(
        id="embedded-browser",
        label="内置浏览器",
        description="在 IDE 内嵌面板中打开",
        action="internal",
        patterns=[
            UriOpenerPattern(
                regex=r"^https?://localhost(:\d+)?(/.*)?$",
                priority=200,
                label="本地开发服务器",
            ),
            UriOpenerPattern(
                regex=r"^https?://127\.0\.0\.1(:\d+)?(/.*)?$",
                priority=200,
                label="本地开发服务器 (127.0.0.1)",
            ),
            UriOpenerPattern(
                regex=r"^https?://.*\.local(:\d+)?(/.*)?$",
                priority=150,
                label="本地域名 (.local)",
            ),
        ],
        is_builtin=True,
        enabled=True,
    ),
    UriOpenerConfig(
        id="always-prompt",
        label="每次询问",
        description="打开 URL 时总是弹出选择对话框",
        action="prompt",
        is_builtin=True,
        enabled=False,
    ),
]


# ── 加载/保存 ──

def _load_openers() -> list[UriOpenerConfig]:
    """从磁盘加载已保存的 opener 配置，合并内置配置"""
    user_openers: list[dict] = []
    if _STORE_FILE.exists():
        try:
            user_openers = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            user_openers = []

    # 合并: 用户配置覆盖内置
    result: dict[str, UriOpenerConfig] = {}
    
    # 先加载内置
    for o in BUILTIN_OPENERS:
        result[o.id] = o

    # 再加载用户配置 (覆盖内置同 id 的字段)
    user_ids = set()
    for data in user_openers:
        uid = data.get("id", "")
        user_ids.add(uid)
        if uid in result:
            # 更新已有内置配置
            existing = result[uid]
            existing.label = data.get("label", existing.label)
            existing.description = data.get("description", existing.description)
            existing.action = data.get("action", existing.action)
            existing.enabled = data.get("enabled", existing.enabled)
            if "patterns" in data:
                existing.patterns = [UriOpenerPattern(**p) for p in data["patterns"]]
            if "default_for_schemes" in data:
                existing.default_for_schemes = data["default_for_schemes"]
        else:
            # 新的自定义 opener
            result[uid] = UriOpenerConfig(
                id=uid,
                label=data.get("label", uid),
                description=data.get("description", ""),
                action=data.get("action", "external"),
                patterns=[UriOpenerPattern(**p) for p in data.get("patterns", [])],
                default_for_schemes=data.get("default_for_schemes", []),
                enabled=data.get("enabled", True),
                is_builtin=False,
            )

    return list(result.values())


def _save_openers(openers: list[UriOpenerConfig]) -> None:
    """保存配置到磁盘 (只保存自定义 opener，内置仅保存覆盖项)"""
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    data = []
    for o in openers:
        data.append({
            "id": o.id,
            "label": o.label,
            "description": o.description,
            "action": o.action,
            "patterns": [p.model_dump() for p in o.patterns],
            "default_for_schemes": o.default_for_schemes,
            "enabled": o.enabled,
        })
    _STORE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── 全局缓存 ──
_openers_cache: list[UriOpenerConfig] | None = None


def _get_openers() -> list[UriOpenerConfig]:
    global _openers_cache
    if _openers_cache is None:
        _openers_cache = _load_openers()
    return _openers_cache


def _refresh_cache() -> None:
    global _openers_cache
    _openers_cache = None


# ── API 路由 ──

@router.get("")
async def list_openers():
    """列出所有 URI opener 配置"""
    return {"data": [o.model_dump() for o in _get_openers()]}


@router.get("/{opener_id}")
async def get_opener(opener_id: str):
    """获取单个 opener 配置"""
    for o in _get_openers():
        if o.id == opener_id:
            return o.model_dump()
    raise HTTPException(404, f"Opener 不存在: {opener_id}")


@router.post("")
async def register_opener(config: UriOpenerConfig):
    """注册或更新 URI opener 配置"""
    openers = _get_openers()
    
    # 查找已有
    existing_idx = next((i for i, o in enumerate(openers) if o.id == config.id), -1)
    
    if existing_idx >= 0:
        existing = openers[existing_idx]
        if existing.is_builtin and config.action != existing.action:
            # 允许覆盖内置配置
            existing.label = config.label
            existing.description = config.description
            existing.action = config.action
            existing.patterns = config.patterns
            existing.default_for_schemes = config.default_for_schemes
            existing.enabled = config.enabled
        else:
            openers[existing_idx] = config
    else:
        config.is_builtin = False
        openers.append(config)

    _save_openers(openers)
    _refresh_cache()
    return {"success": True, "id": config.id}


@router.delete("/{opener_id}")
async def delete_opener(opener_id: str):
    """删除自定义 URI opener (内置不可删除)"""
    openers = _get_openers()
    
    target = next((o for o in openers if o.id == opener_id), None)
    if not target:
        raise HTTPException(404, f"Opener 不存在: {opener_id}")
    if target.is_builtin:
        raise HTTPException(400, f"内置 opener 不可删除，但可禁用")

    new_openers = [o for o in openers if o.id != opener_id]
    _save_openers(new_openers)
    _refresh_cache()
    return {"success": True, "deleted": opener_id}


@router.post("/match")
async def match_url(req: MatchRequest):
    """
    测试 URL 与哪个 opener 匹配。
    返回匹配结果及所有候选 opener列表。
    """
    openers = _get_openers()
    candidates: list[dict] = []

    for o_idx, opener in enumerate(openers):
        if not opener.enabled:
            continue
        
        matched_patterns: list[int] = []
        for p_idx, pattern in enumerate(opener.patterns):
            try:
                if re.search(pattern.regex, req.url, re.IGNORECASE):
                    matched_patterns.append(p_idx)
            except re.error:
                continue  # 跳过无效正则

        if matched_patterns:
            candidates.append({
                "opener_id": opener.id,
                "label": opener.label,
                "action": opener.action,
                "score": max(
                    (opener.patterns[p].priority for p in matched_patterns),
                    default=0,
                ),
                "matched_patterns": matched_patterns,
            })

    # 按分数排序 (高分优先)
    candidates.sort(key=lambda c: c["score"], reverse=True)

    best = candidates[0] if candidates else None
    best_opener = None
    if best:
        best_opener = next((o for o in openers if o.id == best["opener_id"]), None)

    return MatchResult(
        url=req.url,
        matched=best is not None,
        opener=best_opener.model_dump() if best_opener else None,
        pattern_index=best["matched_patterns"][0] if best else -1,
        all_candidates=candidates,
    ).model_dump()


@router.post("/resolve")
async def resolve_url(req: MatchRequest):
    """
    解析 URL 的最终 opener（含 scheme 回退）。
    返回推荐 action: external | internal | prompt
    """
    # 提取 scheme
    scheme_match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*):", req.url)
    scheme = scheme_match.group(1) if scheme_match else ""

    openers = _get_openers()

    # 1. 先按 pattern 匹配
    best_score = -1
    best_opener: UriOpenerConfig | None = None

    for opener in openers:
        if not opener.enabled:
            continue
        for pattern in opener.patterns:
            try:
                if re.search(pattern.regex, req.url, re.IGNORECASE):
                    if pattern.priority > best_score:
                        best_score = pattern.priority
                        best_opener = opener
                    break
            except re.error:
                continue

    # 2. scheme 回退
    if best_opener is None and scheme:
        for opener in openers:
            if opener.enabled and scheme in opener.default_for_schemes:
                best_opener = opener
                break

    # 3. 终极回退: 系统浏览器
    if best_opener is None:
        best_opener = next((o for o in openers if o.id == "system-browser"), None)

    result = {
        "url": req.url,
        "scheme": scheme,
        "action": best_opener.action if best_opener else "external",
        "opener_id": best_opener.id if best_opener else "system-browser",
        "opener_label": best_opener.label if best_opener else "系统浏览器",
        "matched_by": "pattern" if best_score >= 0 else ("scheme" if scheme else "fallback"),
    }

    return result
