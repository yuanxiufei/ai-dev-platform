"""
Smart Auto-Approval Engine — RooCode + OpenInterpreter 风格自动审批

借鉴:
- RooCode auto-approval/ — 3级安全分级 + 自定义规则
- OpenInterpreter approval/ — Always Allow 记忆 + RiskLevel 判断

设计:
- 工具按 RiskLevel 分级 (SAFE / MODERATE / DANGEROUS)
- SAFE 工具自动批准 (Always Allow 记忆的也自动批)
- MODERATE 工具需要 confirm (有 Always Allow 则自动批)
- DANGEROUS 工具必须手动确认
- 用户可以对特定工具/文件设置 Always Allow 规则
"""

from __future__ import annotations

import enum
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.auto_approval")


# ── Risk Level ────────────────────────────────────────


class RiskLevel(str, enum.Enum):
    """工具风险级别"""
    SAFE = "safe"           # 只读操作，无任何副作用
    MODERATE = "moderate"   # 有副作用但风险可控
    DANGEROUS = "dangerous" # 高风险操作，必须手动确认


# ── 工具风险映射 ──────────────────────────────────────


TOOL_RISK_MAP: dict[str, RiskLevel] = {
    # 🟢 SAFE — 只读
    "read_file": RiskLevel.SAFE,
    "list_files": RiskLevel.SAFE,
    "list_dir": RiskLevel.SAFE,
    "search_content": RiskLevel.SAFE,
    "search_file": RiskLevel.SAFE,
    "search_graph": RiskLevel.SAFE,
    "trace_path": RiskLevel.SAFE,
    "get_symbol": RiskLevel.SAFE,
    "find_references": RiskLevel.SAFE,
    "get_file_info": RiskLevel.SAFE,
    "get_directory_tree": RiskLevel.SAFE,
    "code_analysis": RiskLevel.SAFE,
    "web_search": RiskLevel.SAFE,
    "web_fetch": RiskLevel.SAFE,
    
    # 🟡 MODERATE — 可逆副作用
    "write_file": RiskLevel.MODERATE,
    "edit_file": RiskLevel.MODERATE,
    "apply_diff": RiskLevel.MODERATE,
    "create_file": RiskLevel.MODERATE,
    "create_directory": RiskLevel.MODERATE,
    "generate_code": RiskLevel.MODERATE,
    "generate_image": RiskLevel.MODERATE,
    "git_add": RiskLevel.MODERATE,
    "git_commit": RiskLevel.MODERATE,
    "git_checkout": RiskLevel.MODERATE,
    
    # 🔴 DANGEROUS — 不可逆
    "delete_file": RiskLevel.DANGEROUS,
    "delete_directory": RiskLevel.DANGEROUS,
    "execute_command": RiskLevel.DANGEROUS,
    "execute_bash": RiskLevel.DANGEROUS,
    "git_push": RiskLevel.DANGEROUS,
    "git_reset_hard": RiskLevel.DANGEROUS,
    "npm_install": RiskLevel.DANGEROUS,
    "pip_install": RiskLevel.DANGEROUS,
    "system_command": RiskLevel.DANGEROUS,
    "sudo": RiskLevel.DANGEROUS,
}


# ── Data Models ───────────────────────────────────────


@dataclass
class ApprovalRule:
    """单条审批规则"""
    tool_name: str
    allowed: bool = True
    path_pattern: str = ""           # 可选：仅限特定路径
    param_conditions: dict[str, Any] = field(default_factory=dict)  # 可选：参数条件
    
    # 元数据
    created_by: str = "user"
    created_at: float = field(default_factory=time.time)
    usage_count: int = 0
    last_used: float = 0.0


@dataclass
class ApprovalRequest:
    """审批请求"""
    id: str
    tool_name: str
    tool_args: dict[str, Any]
    risk_level: RiskLevel
    agent_name: str = ""
    turn_number: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ApprovalDecision:
    """审批结果"""
    approved: bool
    reason: str = ""
    matched_rule: ApprovalRule | None = None
    needs_user_confirmation: bool = False


# ── Auto-Approval Engine ──────────────────────────────


class AutoApprovalEngine:
    """
    智能自动审批引擎
    
    用法:
        engine = AutoApprovalEngine()
        
        # 添加 Always Allow 规则
        engine.add_rule("read_file", allowed=True)
        engine.add_rule("write_file", allowed=True, path_pattern="src/*.py")
        
        # 检查是否需要审批
        decision = engine.check("write_file", {"path": "src/main.py"})
        if decision.needs_user_confirmation:
            # 显示审批 UI
            ...
    """
    
    DEFAULT_MODE = "safe-tools"  # safe-tools | custom | never | always
    
    def __init__(
        self,
        mode: str = "safe-tools",
        rules_file: str = "data/approval_rules.json",
    ):
        self._mode = mode
        self._rules: dict[str, list[ApprovalRule]] = {}  # tool_name → rules
        self._rules_file = Path(rules_file)
        self._load_rules()
    
    # ── 公共 API ────────────────────────────────────
    
    def check(
        self,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        agent_name: str = "",
        turn_number: int = 0,
    ) -> ApprovalDecision:
        """
        检查工具调用是否需要用户审批
        
        Returns:
            ApprovalDecision — approved=True则无需用户介入
        """
        args = tool_args or {}
        
        # 获取风险级别
        risk_level = self._get_risk_level(tool_name)
        
        # Mode: "always" → 全部自动批准
        if self._mode == "always":
            return ApprovalDecision(approved=True, reason="Mode: always auto-approve")
        
        # Mode: "never" → 一律需确认
        if self._mode == "never":
            return ApprovalDecision(
                approved=False,
                reason="Mode: always require confirmation",
                needs_user_confirmation=True,
            )
        
        # SAFE 工具直接批准
        if risk_level == RiskLevel.SAFE:
            return ApprovalDecision(approved=True, reason=f"SAFE tool: {tool_name}")
        
        # 检查 Always Allow 规则
        rule = self._match_rule(tool_name, args)
        if rule and rule.allowed:
            rule.usage_count += 1
            rule.last_used = time.time()
            logger.debug("Auto-approved %s via rule (used %d times)", tool_name, rule.usage_count)
            return ApprovalDecision(approved=True, reason=f"Rule: {rule.tool_name}", matched_rule=rule)
        
        # DANGEROUS 工具必定需要确认
        if risk_level == RiskLevel.DANGEROUS:
            return ApprovalDecision(
                approved=False,
                reason=f"DANGEROUS tool: {tool_name} requires manual confirmation",
                needs_user_confirmation=True,
            )
        
        # MODERATE 工具在 safe-tools 模式下需要确认
        if self._mode == "safe-tools":
            return ApprovalDecision(
                approved=False,
                reason=f"MODERATE tool: {tool_name} requires confirmation in safe-tools mode",
                needs_user_confirmation=True,
            )
        
        # 默认需要确认
        return ApprovalDecision(
            approved=False,
            reason=f"Tool '{tool_name}' needs confirmation",
            needs_user_confirmation=True,
        )
    
    def add_rule(
        self,
        tool_name: str,
        allowed: bool = True,
        path_pattern: str = "",
        param_conditions: dict[str, Any] | None = None,
    ) -> ApprovalRule:
        """
        添加审批规则 (Always Allow / Always Deny)
        
        Args:
            tool_name: 工具名
            allowed: True=Always Allow, False=Always Deny
            path_pattern: 可选的路径匹配模式 (glob)
            param_conditions: 可选的参数条件
        """
        rule = ApprovalRule(
            tool_name=tool_name,
            allowed=allowed,
            path_pattern=path_pattern,
            param_conditions=param_conditions or {},
            created_at=time.time(),
        )
        
        if tool_name not in self._rules:
            self._rules[tool_name] = []
        self._rules[tool_name].append(rule)
        self._save_rules()
        
        logger.info(
            "Added rule: %s %s (path=%s)",
            "ALLOW" if allowed else "DENY", tool_name, path_pattern or "*",
        )
        return rule
    
    def remove_rule(
        self,
        tool_name: str,
        path_pattern: str = "",
    ) -> bool:
        """移除审批规则"""
        if tool_name not in self._rules:
            return False
        
        before = len(self._rules[tool_name])
        self._rules[tool_name] = [
            r for r in self._rules[tool_name]
            if not (r.path_pattern == path_pattern)
        ]
        
        if not self._rules[tool_name]:
            del self._rules[tool_name]
        
        removed = before - len(self._rules.get(tool_name, []))
        if removed:
            self._save_rules()
            logger.info("Removed %d rules for %s", removed, tool_name)
        return removed > 0
    
    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有审批规则"""
        result = []
        for tool_name, rules in self._rules.items():
            for r in rules:
                result.append({
                    "tool_name": r.tool_name,
                    "allowed": r.allowed,
                    "path_pattern": r.path_pattern or "*",
                    "param_conditions": r.param_conditions,
                    "usage_count": r.usage_count,
                    "last_used": r.last_used,
                    "created_at": r.created_at,
                })
        result.sort(key=lambda x: x["usage_count"], reverse=True)
        return result
    
    def set_mode(self, mode: str) -> None:
        """设置审批模式: safe-tools | custom | never | always"""
        valid = {"safe-tools", "custom", "never", "always"}
        if mode not in valid:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid}")
        self._mode = mode
        logger.info("Approval mode set to: %s", mode)
    
    @property
    def mode(self) -> str:
        return self._mode
    
    @staticmethod
    def get_risk_level(tool_name: str) -> RiskLevel:
        """获取工具风险级别"""
        return TOOL_RISK_MAP.get(tool_name, RiskLevel.DANGEROUS)
    
    # ── 内部方法 ────────────────────────────────────
    
    def _get_risk_level(self, tool_name: str) -> RiskLevel:
        return TOOL_RISK_MAP.get(tool_name, RiskLevel.DANGEROUS)
    
    def _match_rule(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> ApprovalRule | None:
        """匹配 Always Allow 规则"""
        if tool_name not in self._rules:
            return None
        
        for rule in self._rules[tool_name]:
            if not rule.allowed:
                continue
            
            # 检查路径模式
            if rule.path_pattern:
                path = tool_args.get("path") or tool_args.get("file_path") or ""
                if not self._match_glob(path, rule.path_pattern):
                    continue
            
            # 检查参数条件
            if rule.param_conditions:
                if not self._match_params(tool_args, rule.param_conditions):
                    continue
            
            return rule
        
        return None
    
    @staticmethod
    def _match_glob(path: str, pattern: str) -> bool:
        """简单 glob 匹配"""
        import fnmatch
        return fnmatch.fnmatch(path, pattern)
    
    @staticmethod
    def _match_params(params: dict, conditions: dict) -> bool:
        """检查参数满足条件"""
        for key, value in conditions.items():
            if key not in params:
                return False
            if isinstance(value, str) and isinstance(params[key], str):
                import fnmatch
                if not fnmatch.fnmatch(params[key], value):
                    return False
            elif params[key] != value:
                return False
        return True
    
    def _load_rules(self) -> None:
        """从磁盘加载规则"""
        if self._rules_file.exists():
            try:
                data = json.loads(self._rules_file.read_text(encoding="utf-8"))
                for tool_name, rules_data in data.get("rules", {}).items():
                    self._rules[tool_name] = [
                        ApprovalRule(
                            tool_name=r["tool_name"],
                            allowed=r["allowed"],
                            path_pattern=r.get("path_pattern", ""),
                            param_conditions=r.get("param_conditions", {}),
                            usage_count=r.get("usage_count", 0),
                            last_used=r.get("last_used", 0.0),
                            created_at=r.get("created_at", time.time()),
                        )
                        for r in rules_data
                    ]
                self._mode = data.get("mode", self.DEFAULT_MODE)
                total_rules = sum(len(v) for v in self._rules.values())
                logger.info("Loaded %d approval rules (mode=%s)", total_rules, self._mode)
            except Exception as e:
                logger.warning("Failed to load approval rules: %s", e)
    
    def _save_rules(self) -> None:
        """保存规则到磁盘"""
        self._rules_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "mode": self._mode,
            "rules": {
                tool_name: [
                    {
                        "tool_name": r.tool_name,
                        "allowed": r.allowed,
                        "path_pattern": r.path_pattern,
                        "param_conditions": r.param_conditions,
                        "usage_count": r.usage_count,
                        "last_used": r.last_used,
                        "created_at": r.created_at,
                    }
                    for r in rules
                ]
                for tool_name, rules in self._rules.items()
            },
        }
        self._rules_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 全局单例 ──────────────────────────────────────────


_global_approval_engine: AutoApprovalEngine | None = None


def init_approval_engine(
    mode: str = "safe-tools",
    rules_file: str = "data/approval_rules.json",
) -> AutoApprovalEngine:
    global _global_approval_engine
    _global_approval_engine = AutoApprovalEngine(mode=mode, rules_file=rules_file)
    return _global_approval_engine


def get_approval_engine() -> AutoApprovalEngine:
    global _global_approval_engine
    if _global_approval_engine is None:
        return init_approval_engine()
    return _global_approval_engine
