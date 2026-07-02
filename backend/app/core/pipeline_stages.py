"""
内置流水线阶段 — 模型请求处理的标准化阶段

借鉴 AstrBot 的流水线阶段设计：
- InputValidationStage — 输入校验
- RateLimitStage — Fixed Window 限流（per-session）
- ContentSafetyCheckStage — 内容安全检查（策略链双向检查）
- RequestAuthenticateStage — 请求认证与唤醒检查
- AccessControlStage — 访问控制（白名单/黑名单）
- SessionCheckStage — 会话状态检查
- TaskBoostStage — 任务类型加成
- ModelSelectionStage — 模型选择
- ModelInferenceStage — 模型推理（洋葱模型）
- ResultDecorateStage — 结果装饰与格式化（分段/TTS/t2i/合并）
- UsageRecordStage — 使用记录
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from app.core.metrics import record_model_call
from app.core.pipeline import (
    PipelineContext, PipelineStage, OnionPipelineStage,
    StageDecision, StageResult,
)

logger = logging.getLogger("pipeline.stages")


class InputValidationStage(PipelineStage):
    """输入校验阶段 —— 验证请求参数是否合法"""

    stage_name = "input_validation"
    priority = 10

    async def execute(self, context: PipelineContext) -> StageResult:
        request = context.metadata.get("model_request")
        if not request:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="no ModelRequest in context",
            )

        # 校验 prompt 非空
        if not request.prompt or not request.prompt.strip():
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="empty prompt",
            )

        # 校验 capability
        from app.core.model_router import ModelCapability
        if request.capability not in ModelCapability:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error=f"invalid capability: {request.capability}",
            )

        logger.debug("[%s] Input validation passed", self.stage_name)
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


# ── 限流策略枚举 ──────────────────────────────────────────


class RateLimitStrategy(str, Enum):
    """限流策略"""
    STALL = "stall"       # 暂停等待窗口刷新
    DISCARD = "discard"   # 直接丢弃请求


class RateLimitStage(PipelineStage):
    """Fixed Window 限流阶段 — per-session 请求限流

    借鉴 AstrBot RateLimitStage 的 Fixed Window 算法：
    - 每个 session 独立 deque 追踪时间戳
    - asyncio.Lock 防止并发竞态
    - STALL: 触发限流后暂停 pipeline，等待窗口刷新自动恢复
    - DISCARD: 触发限流后直接短路丢弃

    配置（通过 context.metadata 传入或使用默认值）:
        rate_limit_count: 窗口内最大请求数（默认 10）
        rate_limit_time: 时间窗口秒数（默认 60）
        rate_limit_strategy: "stall" 或 "discard"（默认 "stall"）
    """

    stage_name = "rate_limit"
    priority = 12

    def __init__(self) -> None:
        self.event_timestamps: defaultdict[str, deque[datetime]] = defaultdict(deque)
        self.locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def execute(self, context: PipelineContext) -> StageResult:
        session_id = context.metadata.get("session_id", "default")
        count = context.metadata.get("rate_limit_count", 10)
        window = timedelta(seconds=context.metadata.get("rate_limit_time", 60))
        strategy = RateLimitStrategy(
            context.metadata.get("rate_limit_strategy", "stall"),
        )

        now = datetime.now()

        async with self.locks[session_id]:
            while True:
                timestamps = self.event_timestamps[session_id]
                self._remove_expired(timestamps, now, window)

                if count <= 0:
                    break
                if len(timestamps) < count:
                    timestamps.append(now)
                    break

                next_window = timestamps[0] + window
                stall_duration = (next_window - now).total_seconds() + 0.3

                if strategy == RateLimitStrategy.STALL:
                    logger.info(
                        "[%s] Session '%s' rate-limited, stalling %.1fs",
                        self.stage_name, session_id, stall_duration,
                    )
                    await asyncio.sleep(stall_duration)
                    now = datetime.now()
                else:
                    logger.info(
                        "[%s] Session '%s' rate-limited, request discarded",
                        self.stage_name, session_id,
                    )
                    context.metadata["rate_limited"] = True
                    return StageResult(
                        stage_name=self.stage_name,
                        decision=StageDecision.SHORT_CIRCUIT,
                        error=f"Rate limit exceeded for session '{session_id}'",
                    )

        logger.debug("[%s] Rate check passed: session='%s' count=%d", self.stage_name, session_id, len(timestamps))
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

    @staticmethod
    def _remove_expired(
        timestamps: deque[datetime],
        now: datetime,
        window: timedelta,
    ) -> None:
        """移除时间窗口外的时间戳"""
        expiry = now - window
        while timestamps and timestamps[0] < expiry:
            timestamps.popleft()


class ContentSafetyCheckStage(PipelineStage):
    """内容安全检查阶段 —— 策略链双向检查

    v2.0: 升级为可插拔策略链模式，支持：
    - KeywordsStrategy: 正则关键词匹配
    - LLMJudgeStrategy: LLM 安全裁判
    - StrategySelector: 配置驱动策略组装
    - 双向检查：用户输入 + LLM 输出

    配置（通过 context.metadata 传入）:
        content_safety_config: {"keywords_enable": True, "extra_keywords": [...], "llm_judge_enable": False}
    """

    stage_name = "content_safety_check"
    priority = 20
    enabled = True

    async def execute(self, context: PipelineContext) -> StageResult:
        from app.core.security.content_safety import StrategySelector

        request = context.metadata.get("model_request")
        if not request:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        config = context.metadata.get("content_safety_config", {})
        selector = StrategySelector(config)

        ok, reason = await selector.check(request.prompt)
        if not ok:
            logger.warning("[%s] Content blocked: %s", self.stage_name, reason)
            context.metadata["content_blocked"] = True
            context.metadata["block_reason"] = reason
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error=reason,
            )

        logger.debug("[%s] Content safety check passed", self.stage_name)
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

    async def on_error(self, context: PipelineContext, error: Exception) -> StageResult:
        """安全检查出错时放行（避免误拦）"""
        logger.warning("[%s] Check error, allowing: %s", self.stage_name, error)
        return StageResult(
            stage_name=self.stage_name,
            decision=StageDecision.CONTINUE,
            error=f"check error (allowed): {error}",
        )


class TaskBoostStage(PipelineStage):
    """任务类型加成阶段 —— 根据 task_type 提升匹配模型的优先级"""

    stage_name = "task_boost"
    priority = 30

    async def execute(self, context: PipelineContext) -> StageResult:
        request = context.metadata.get("model_request")
        router = context.metadata.get("model_router")
        if not request or not router:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        task_type = getattr(request, "task_type", "")
        if not task_type:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        boost_factor = 1.5
        all_candidates = router.local_models + (
            router.api_gateway.get_candidates() if router.api_gateway else []
        )

        boosted = 0
        for model in all_candidates:
            if task_type in (model.strengths or []):
                model.dynamic_score = float(model.priority) * boost_factor
                boosted += 1

        if boosted > 0:
            logger.info(
                "[%s] Task boost applied: %d models boosted for task_type='%s'",
                self.stage_name, boosted, task_type,
            )

        context.metadata["boosted_models"] = boosted
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


class ModelSelectionStage(PipelineStage):
    """模型选择阶段 —— 确定使用哪个模型"""

    stage_name = "model_selection"
    priority = 40

    async def execute(self, context: PipelineContext) -> StageResult:
        request = context.metadata.get("model_request")
        router = context.metadata.get("model_router")

        if not router:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="No ModelRouter in context",
            )

        # 重建回退链确保评分最新
        router._rebuild_chain()

        chain_info = router._fallback_chain
        available_layers = sum(1 for node in chain_info if node.models)

        if available_layers == 0:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="No available models in any layer",
            )

        logger.info(
            "[%s] Rebuilt fallback chain: %d layers, %d available",
            self.stage_name, len(chain_info), available_layers,
        )

        context.metadata["available_layers"] = available_layers
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


class ModelInferenceStage(PipelineStage):
    """模型推理阶段 —— 执行实际的模型调用（含完整回退链）"""

    stage_name = "model_inference"
    priority = 50

    async def execute(self, context: PipelineContext) -> StageResult:
        request = context.metadata.get("model_request")
        router = context.metadata.get("model_router")

        if not request or not router:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="Missing request or router",
            )

        try:
            response = await router._do_generate(request)
            context.set_output(response)
            context.metadata["model_used"] = response.model_used
            context.metadata["provider"] = response.provider
            context.metadata["is_fallback"] = response.is_fallback
            context.metadata["latency_ms"] = response.latency_ms

            logger.info(
                "[%s] Inference succeeded: model=%s provider=%s latency=%dms",
                self.stage_name,
                response.model_used,
                response.provider,
                response.latency_ms,
            )

            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.CONTINUE,
                data={
                    "model": response.model_used,
                    "provider": response.provider,
                    "latency_ms": response.latency_ms,
                    "is_fallback": response.is_fallback,
                },
            )
        except Exception as e:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.ERROR,
                error=f"Inference failed: {str(e)[:200]}",
            )


class ResultDecorateStage(PipelineStage):
    """结果装饰阶段 —— 对模型输出进行后处理和格式化"""

    stage_name = "result_decorate"
    priority = 60

    async def execute(self, context: PipelineContext) -> StageResult:
        output = context.final_output
        if not output:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        request = context.metadata.get("model_request")

        # 为代码生成添加元数据标记
        if request and hasattr(output, "content"):
            from app.core.model_router import ModelCapability

            if request.capability == ModelCapability.CODE_GENERATION:
                # 清理可能的 Markdown 代码块包裹
                content = output.content

                # 如果内容是纯代码但没被标记，添加代码语言标记
                if content.strip() and not content.strip().startswith("```"):
                    # 自动检测并注入生成元数据
                    output.metadata["generated_by"] = "ai-fullstack-platform"
                    output.metadata["pipeline_version"] = "2.0"

        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


class UsageRecordStage(PipelineStage):
    """使用记录阶段 —— 记录模型使用统计"""

    stage_name = "usage_record"
    priority = 90

    async def execute(self, context: PipelineContext) -> StageResult:
        request = context.metadata.get("model_request")
        output = context.final_output

        if not request or not output:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        router = context.metadata.get("model_router")
        if router and router.usage_recorder:
            try:
                router.usage_recorder(
                    model_name=getattr(output, "model_used", "unknown"),
                    capability=request.capability.value,
                    success=getattr(output, "finish_reason", "stop") == "stop",
                    latency_ms=getattr(output, "latency_ms", 0),
                    tokens_used=getattr(output, "tokens_used", None),
                    is_fallback=getattr(output, "is_fallback", False),
                )
                logger.debug("[%s] Usage recorded: model=%s", self.stage_name, getattr(output, "model_used", "?"))
            except Exception as e:
                logger.error("[%s] Failed to record usage: %s", self.stage_name, e)

        # 记录 Prometheus 模型调用指标
        try:
            model_name = getattr(output, "model_used", "unknown")
            provider = getattr(output, "provider", "unknown")
            capability = request.capability.value if request else "unknown"
            latency_ms = getattr(output, "latency_ms", 0)
            finish_reason = getattr(output, "finish_reason", "stop")
            is_error = finish_reason not in ("stop", "length")
            record_model_call(
                provider=provider,
                model_name=model_name,
                capability=capability,
                duration=latency_ms / 1000.0,
                error=is_error,
            )
        except Exception:
            pass

        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


# ── 洋葱模型阶段（v2.0） ──────────────────────────────────


class PreProcessOnionStage(OnionPipelineStage):
    """
    前置/后置处理阶段（洋葱模型）

    前置：记录请求开始
    后置：清理临时数据、计算总延迟

    用法（OnionPipelineScheduler）:
        scheduler.add_stage(PreProcessOnionStage())    # priority=5
        scheduler.add_stage(InputValidationStage())     # priority=10
        scheduler.add_stage(ModelInferenceStage())      # priority=50
        # 执行顺序：PreProcess.pre → InputValidation → Inference → PreProcess.post
    """

    stage_name = "pre_process_onion"
    priority = 5

    async def process_async(self, context):
        from collections.abc import AsyncGenerator
        import time

        # ── 前置：请求预处理 ──
        context.metadata["pipeline_start"] = time.perf_counter()

        request = context.metadata.get("model_request")
        if request:
            logger.info(
                "[%s] Starting request: capability=%s prompt_len=%d",
                self.stage_name,
                getattr(request, "capability", "unknown"),
                len(request.prompt) if request.prompt else 0,
            )

        yield  # ← 暂停点：后续阶段在此执行

        # ── 后置：后处理 ──
        start = context.metadata.get("pipeline_start", time.perf_counter())
        total_ms = (time.perf_counter() - start) * 1000
        context.metadata["pipeline_total_ms"] = total_ms

        output = context.final_output
        if output:
            logger.info(
                "[%s] Completed: total=%dms model=%s",
                self.stage_name,
                int(total_ms),
                context.metadata.get("model_used", "unknown"),
            )


class ResultPostProcessOnionStage(OnionPipelineStage):
    """
    结果后处理（洋葱模型）

    在所有处理完成后，对输出进行最终验证和元数据补充。

    洋葱关键：在 Inference 完成后才执行后置处理。
    """

    stage_name = "result_post_process"
    priority = 85

    async def process_async(self, context):
        # ── 前置 ──
        pass

        yield  # ← 暂停点

        # ── 后置：元数据注入 ──
        output = context.final_output
        if not output:
            return

        if hasattr(output, "metadata"):
            output.metadata["generated_by"] = "ai-fullstack-platform"
            output.metadata["pipeline_version"] = "3.0-onion"
            output.metadata["pipeline_latency_ms"] = context.metadata.get(
                "pipeline_total_ms", 0,
            )

        logger.debug("[%s] Post-processing complete", self.stage_name)


# ── v3.0 新增阶段：借鉴 AstrBot 高级流水线 ──────────────────


class RequestAuthenticateStage(PipelineStage):
    """请求认证与唤醒检查阶段

    借鉴 AstrBot WakingCheckStage:
    - 验证 API key / token 有效性
    - 检查请求来源（admin / client / system）
    - 设置请求优先级和上下文角色
    - 根据配置决定是否短路未授权请求
    """

    stage_name = "request_authenticate"
    priority = 14

    # 允许的来源类型
    ALLOWED_SOURCES: set[str] = {"admin", "client", "system", "internal"}

    async def execute(self, context: PipelineContext) -> StageResult:
        # 获取认证信息
        api_key = context.metadata.get("api_key")
        source = context.metadata.get("source", "client")
        require_auth = context.metadata.get("require_auth", False)

        # 内部调用或 system 来源免检
        if source == "system" or source == "internal":
            logger.debug("[%s] Internal/system request, auth bypassed", self.stage_name)
            context.metadata["authenticated"] = True
            context.metadata["auth_role"] = "system"
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        # 来源验证
        if source not in self.ALLOWED_SOURCES:
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error=f"Unknown request source: {source}",
            )

        # API key 验证
        if require_auth and not api_key:
            logger.warning("[%s] Authentication required but no API key provided", self.stage_name)
            return StageResult(
                stage_name=self.stage_name,
                decision=StageDecision.SHORT_CIRCUIT,
                error="Authentication required",
            )

        if api_key:
            valid = await self._validate_api_key(api_key, context)
            if not valid:
                return StageResult(
                    stage_name=self.stage_name,
                    decision=StageDecision.SHORT_CIRCUIT,
                    error="Invalid API key",
                )
            context.metadata["authenticated"] = True
            context.metadata["auth_role"] = context.metadata.get("api_key_role", "user")

        logger.debug("[%s] Authentication passed: source=%s", self.stage_name, source)
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

    async def _validate_api_key(self, api_key: str, context: PipelineContext) -> bool:
        """验证 API key 有效性"""
        # 简单的环境变量对比（生产环境应接入数据库）
        import os
        valid_keys = os.getenv("PLATFORM_API_KEYS", "").split(",")
        valid_keys = [k.strip() for k in valid_keys if k.strip()]

        if not valid_keys:
            # 未配置则放行（开发模式）
            return True

        if api_key in valid_keys:
            return True

        # 从 credential 表校验
        try:
            from app.core.api_gateway import get_api_gateway
            gateway = get_api_gateway()
            if gateway and hasattr(gateway, "_validate_key"):
                return gateway._validate_key(api_key)
        except Exception:
            pass

        return False


class AccessControlStage(PipelineStage):
    """访问控制阶段 — 白名单/黑名单检查

    借鉴 AstrBot WhitelistCheckStage:
    - IP 白名单/黑名单过滤
    - 用户/组织级白名单
    - admin 角色豁免
    - 可配置启用/禁用
    """

    stage_name = "access_control"
    priority = 15
    enabled = False  # 默认关闭，通过 context 配置启用

    async def execute(self, context: PipelineContext) -> StageResult:
        # 读取配置
        enable_whitelist = context.metadata.get("enable_id_white_list", False)
        enable_blacklist = context.metadata.get("enable_ip_blacklist", False)

        if not enable_whitelist and not enable_blacklist:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        # admin 豁免
        auth_role = context.metadata.get("auth_role", "")
        ignore_admin = context.metadata.get("wl_ignore_admin", True)
        if ignore_admin and auth_role in ("admin", "system"):
            logger.debug("[%s] Admin user, access control bypassed", self.stage_name)
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        # IP 黑名单
        if enable_blacklist:
            client_ip = context.metadata.get("client_ip", "")
            ip_blacklist = context.metadata.get("ip_blacklist", [])
            if client_ip and ip_blacklist and self._ip_matched(client_ip, ip_blacklist):
                logger.warning("[%s] IP blacklisted: %s", self.stage_name, client_ip)
                return StageResult(
                    stage_name=self.stage_name,
                    decision=StageDecision.SHORT_CIRCUIT,
                    error=f"IP {client_ip} is blacklisted",
                )

        # 用户/组织白名单
        if enable_whitelist:
            user_id = context.metadata.get("user_id", "")
            org_id = context.metadata.get("org_id", "")
            whitelist = context.metadata.get("id_whitelist", [])

            if whitelist and user_id and user_id not in whitelist:
                if org_id and org_id in whitelist:
                    pass  # 组织在白名单
                else:
                    logger.warning("[%s] User not in whitelist: %s", self.stage_name, user_id)
                    return StageResult(
                        stage_name=self.stage_name,
                        decision=StageDecision.SHORT_CIRCUIT,
                        error=f"User {user_id} is not authorized",
                    )

        logger.debug("[%s] Access control passed", self.stage_name)
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

    @staticmethod
    def _ip_matched(ip: str, patterns: list[str]) -> bool:
        """检查 IP 是否匹配（支持子网掩码）"""
        for pattern in patterns:
            if pattern == ip:
                return True
            if "/" in pattern:
                # 简化的子网匹配
                try:
                    prefix = pattern.split("/")[0]
                    if ip.startswith(prefix.rsplit(".", 1)[0]):
                        return True
                except (IndexError, ValueError):
                    pass
        return False


class SessionCheckStage(PipelineStage):
    """会话状态检查阶段

    借鉴 AstrBot SessionStatusCheckStage:
    - 检查会话是否有效且启用
    - 支持会话过期检测
    - 支持会话级禁用/启用
    """

    stage_name = "session_check"
    priority = 16
    enabled = False  # 默认关闭

    async def execute(self, context: PipelineContext) -> StageResult:
        session_id = context.metadata.get("session_id", "")
        if not session_id:
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        # 从数据库检查会话状态
        try:
            from app.models.studio_models import ChatSession
            from app.core.db import get_db
            db = get_db()
            session = await db.get(ChatSession, session_id)
            if session:
                # 检查是否过期
                if hasattr(session, "expires_at") and session.expires_at:
                    from datetime import datetime, timezone
                    if session.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
                        logger.info("[%s] Session expired: %s", self.stage_name, session_id)
                        return StageResult(
                            stage_name=self.stage_name,
                            decision=StageDecision.SHORT_CIRCUIT,
                            error=f"Session {session_id} has expired",
                        )

                # 检查是否被禁用
                if hasattr(session, "disabled") and session.disabled:
                    logger.info("[%s] Session disabled: %s", self.stage_name, session_id)
                    return StageResult(
                        stage_name=self.stage_name,
                        decision=StageDecision.SHORT_CIRCUIT,
                        error=f"Session {session_id} is disabled",
                    )
        except Exception as e:
            logger.debug("[%s] Session check skipped (DB unavailable): %s", self.stage_name, e)

        logger.debug("[%s] Session check passed: %s", self.stage_name, session_id)
        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)


class AdvancedResultDecorateStage(PipelineStage):
    """高级结果装饰阶段 — TTS / t2i / 分段 / 合并转发

    借鉴 AstrBot ResultDecorateStage:
    - 输出内容安全检查（双向）
    - 分段回复控制（按字数/正则/关键字）
    - TTS 文本转语音（概率触发）
    - 文本转图片（超长文本自动渲染）
    - 推理内容展示（reasoning_content）
    - 合并转发阈值控制
    """

    stage_name = "advanced_result_decorate"
    priority = 65
    enabled = False  # 默认关闭

    async def execute(self, context: PipelineContext) -> StageResult:
        output = context.final_output
        if not output or not hasattr(output, "content"):
            return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

        config = context.metadata.get("result_config", {})

        # 1. 内容安全检查（输出端）
        if config.get("output_safety", False):
            from app.core.security.content_safety import StrategySelector
            selector = StrategySelector(config)
            ok, reason = await selector.check(output.content)
            if not ok:
                context.metadata["content_blocked"] = True
                output.content = f"[Content blocked: {reason}]"

        # 2. 分段控制
        split_mode = config.get("split_mode")
        if split_mode and output.content:
            max_chars = config.get("max_chars_per_segment", 2000)
            segments = self._split_content(output.content, split_mode, max_chars)
            context.metadata["segments"] = segments
            context.metadata["segment_count"] = len(segments)

        # 3. TTS 配置标记
        tts_config = config.get("tts")
        if tts_config:
            trigger_prob = tts_config.get("trigger_probability", 0)
            if trigger_prob > 0:
                import random
                if random.random() < trigger_prob:
                    context.metadata["tts_triggered"] = True
                    context.metadata["tts_config"] = tts_config

        # 4. t2i 配置
        t2i_config = config.get("t2i")
        if t2i_config:
            threshold = t2i_config.get("threshold", 500)
            if len(output.content) > threshold:
                context.metadata["t2i_triggered"] = True

        return StageResult(stage_name=self.stage_name, decision=StageDecision.CONTINUE)

    @staticmethod
    def _split_content(content: str, mode: str, max_chars: int) -> list[str]:
        """按模式分割内容"""
        import re
        if mode == "sentence":
            # 按句子分割
            sentences = re.split(r"(?<=[。！？.!?\n])\s*", content)
        elif mode == "paragraph":
            # 按段落分割
            sentences = content.split("\n\n")
        elif mode == "words":
            # 按关键字分割
            sentences = re.split(r"\n(?=#{1,6}\s|\d+\.\s|[-*]\s)", content)
        else:
            # 按字数分割
            sentences = []
            for i in range(0, len(content), max_chars):
                sentences.append(content[i:i + max_chars])
            return sentences

        # 合并长度不足的段
        segments = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= max_chars:
                current += s
            else:
                if current:
                    segments.append(current)
                current = s
        if current:
            segments.append(current)

        return segments if segments else [content]
