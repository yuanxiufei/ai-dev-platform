"""
特性开关/实验分组 API — Session 52
对标 VSCode assignment (TAS): A/B实验/百分比发布/布尔开关，SHA256 hash确定性分组
路由: GET / | GET /{name} | POST / | DELETE /{name} | POST /{name}/evaluate
"""
import hashlib, json, logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/feature-flags", tags=["system-feature-flags"])


class FlagType(str, Enum):
    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    EXPERIMENT = "experiment"


class FeatureFlag(BaseModel):
    name: str = Field(..., description="唯一标识")
    description: str = ""
    flag_type: FlagType = FlagType.BOOLEAN
    enabled: bool = True
    rollout_percent: int = Field(default=100, ge=0, le=100)
    variants: list[dict] = Field(default_factory=list)
    target_user_ids: list[str] = Field(default_factory=list)
    target_groups: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class EvalResult(BaseModel):
    flag_name: str
    flag_type: str
    active: bool
    variant: str = "default"
    config: dict = Field(default_factory=dict)
    bucket: Optional[int] = None


# ── 预置 & 存储 ──
_DEFAULTS = {
    "new-dashboard": FeatureFlag(name="new-dashboard", description="新版Dashboard", flag_type=FlagType.PERCENTAGE, rollout_percent=20),
    "dark-mode-v2": FeatureFlag(name="dark-mode-v2", description="新版深色主题", enabled=False),
    "ai-autocomplete": FeatureFlag(name="ai-autocomplete", description="AI代码补全", flag_type=FlagType.PERCENTAGE, rollout_percent=50),
    "button-color-test": FeatureFlag(name="button-color-test", description="按钮A/B测试", flag_type=FlagType.EXPERIMENT,
        variants=[{"name":"control","weight":50,"config":{"color":"blue"}},
                  {"name":"treatment-a","weight":25,"config":{"color":"green"}},
                  {"name":"treatment-b","weight":25,"config":{"color":"purple"}}]),
    "inline-chat": FeatureFlag(name="inline-chat", description="内联AI对话", enabled=True),
    "notebook-v2": FeatureFlag(name="notebook-v2", description="新版Notebook", flag_type=FlagType.PERCENTAGE, rollout_percent=10),
}
_flags: dict[str, FeatureFlag] = {k: v.model_copy() for k, v in _DEFAULTS.items()}


def _hash_user(user_id: str, flag_name: str) -> int:
    h = hashlib.sha256(f"{user_id}:{flag_name}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 10000


def evaluate(user_id: str, flag_name: str) -> Optional[dict]:
    """核心评估函数"""
    flag = _flags.get(flag_name)
    if not flag: return None

    bucket = _hash_user(user_id, flag_name)
    result = {"flag_name": flag_name, "flag_type": flag.flag_type.value}

    if flag.flag_type == FlagType.BOOLEAN:
        active = flag.enabled if user_id not in flag.target_user_ids else not flag.enabled
        result.update(active=active, variant="default" if active else "off")
    elif flag.flag_type == FlagType.PERCENTAGE:
        active = bucket < flag.rollout_percent * 100 or user_id in flag.target_user_ids
        result.update(active=active, variant="default" if active else "off", bucket=bucket)
    elif flag.flag_type == FlagType.EXPERIMENT:
        cum = 0
        matched = None
        for v in flag.variants:
            cum += v.get("weight", 0) * 100
            if bucket < cum:
                matched = v; break
        matched = matched or (flag.variants[-1] if flag.variants else None)
        if matched:
            result.update(active=True, variant=matched["name"], config=matched.get("config", {}), bucket=bucket)
        else:
            result.update(active=False, variant="off", bucket=bucket)
    return result


# ═══════════════ 路由 ═══════════════

@router.get("", response_model=list[FeatureFlag])
async def list_flags() -> list[FeatureFlag]:
    return list(_flags.values())

@router.get("/{name}", response_model=FeatureFlag)
async def get_flag(name: str) -> FeatureFlag:
    if name not in _flags: raise HTTPException(404, f"Flag '{name}' not found")
    return _flags[name]

@router.post("", response_model=FeatureFlag)
async def create_or_update(msg: FeatureFlag) -> FeatureFlag:
    now = datetime.now(timezone.utc).isoformat()
    if msg.name in _flags:
        existing = _flags[msg.name]
        existing.description = msg.description or existing.description
        existing.flag_type = msg.flag_type
        existing.enabled = msg.enabled
        existing.rollout_percent = msg.rollout_percent
        existing.variants = msg.variants or existing.variants
        existing.target_user_ids = msg.target_user_ids or existing.target_user_ids
        existing.target_groups = msg.target_groups or existing.target_groups
        existing.updated_at = now
        return existing
    msg.created_at = now
    msg.updated_at = now
    _flags[msg.name] = msg
    return msg

@router.delete("/{name}")
async def delete_flag(name: str) -> dict:
    if name in _DEFAULTS: raise HTTPException(400, f"Cannot delete built-in flag '{name}'")
    _flags.pop(name, None)
    return {"status": "ok", "deleted": name}

@router.post("/{name}/evaluate", response_model=EvalResult)
async def evaluate_flag(name: str, user_id: str = "default") -> EvalResult:
    result = evaluate(user_id, name)
    if not result: raise HTTPException(404, f"Flag '{name}' not found")
    return EvalResult(**result)
