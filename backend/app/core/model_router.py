"""
模型调度路由器 — 统一的多模型协调入口

职责：
1. 接收统一的 ModelRequest，返回 ModelResponse
2. 根据 capability 筛选候选模型池
3. 按动态评分排序（本地优先 → API 回退 → 内置兜底）
4. 自动失败转移 + 使用统计记录
5. 对上层（API 路由）完全透明

数据流：
  POST /studio/chat
    → ModelRouter.generate(ModelRequest)
      → scheduler.rank(capability)
        → [LocalModel, ApiProxy, ...]
          → 依次尝试（fail-fast 30s）
            → 成功: record_usage() → return ModelResponse
            → 失败: continue
          → 全部失败: FallbackModel
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger("model_router")


# ── 能力类型 ──────────────────────────────────────────────

class ModelCapability(str, Enum):
    """模型能力分类 —— 不按厂商分类，按能力分类"""
    CODE_GENERATION = "code_gen"       # 代码生成（Studio 核心）
    VISION_LANGUAGE = "vision"          # 视觉理解（截图→布局）
    VIDEO_GENERATION = "video_gen"     # 视频生成（Video 核心）
    TEXT_GENERATION = "text_gen"        # 通用文本/对话
    EMBEDDING = "embedding"             # 文本嵌入
    TOOL_USE = "tool_use"              # 工具调用 / Function Calling（Agent 核心）


# ── 统一请求/响应契约 ─────────────────────────────────────

@dataclass
class ModelRequest:
    """统一模型请求 —— 所有调用方使用此结构"""
    capability: ModelCapability
    prompt: str
    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    extra_params: dict[str, Any] = field(default_factory=dict)
    preferred_model: str | None = None   # 用户指定模型（优先级最高）
    stream: bool = False
    images: list[bytes] | None = None    # 截图→代码 场景
    history: list[dict[str, Any]] | None = None  # 对话历史（含 tool role 消息）
    task_type: str = ""                  # 子任务类型（ui_design/frontend_code/backend_code/general_code）

    # ── 工具 / Function Calling 支持 ──
    tools: list[dict[str, Any]] = field(default_factory=list)
    """OpenAI Function Calling 格式的工具定义列表"""
    tool_choice: str | dict[str, Any] | None = None
    """工具选择策略: "auto" | "none" | {"type":"function", "function":{"name":"..."}}"""


@dataclass
class ModelResponse:
    """统一模型响应 —— 屏蔽底层差异"""
    content: str
    model_used: str
    provider: str  # local | openai | anthropic | replicate | fallback
    tokens_used: int | None = None
    latency_ms: int = 0
    finish_reason: str = "stop"  # stop | length | tool_calls | error
    is_fallback: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── 工具调用结果 ──
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """
    LLM 返回的工具调用请求，格式（OpenAI 兼容）：
    [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'}
        },
        ...
    ]
    当 finish_reason == "tool_calls" 时此字段有效。
    """


# ── 候选模型接口 ──────────────────────────────────────────

class ICandidateModel:
    """所有候选模型的统一接口"""

    def __init__(self, name: str, provider: str, priority: int = 50, strengths: list[str] | None = None):
        self.name = name
        self.provider = provider
        self.priority = priority
        self.strengths: list[str] = strengths or []
        self.dynamic_score: float = float(priority)
        self.is_available = True
        self.last_error: str | None = None

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """子类实现具体推理逻辑"""
        raise NotImplementedError

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """子类实现流式推理逻辑"""
        raise NotImplementedError

    def update_score(self, score: float):
        """外部调度器更新动态评分"""
        self.dynamic_score = score


# ── 回退链节点 ─────────────────────────────────────────────

class FallbackNode:
    """回退链中的一个备选节点"""

    def __init__(self, name: str, models: list[ICandidateModel]):
        self.name = name
        self.models = models

    async def try_generate(self, request: ModelRequest) -> ModelResponse | None:
        """依次尝试该节点的所有模型"""
        for model in self.models:
            if not model.is_available:
                continue
            try:
                start = time.perf_counter()
                response = await asyncio.wait_for(
                    model.generate(request),
                    timeout=30.0
                )
                response.latency_ms = int((time.perf_counter() - start) * 1000)
                return response
            except asyncio.TimeoutError:
                logger.warning(f"Model {model.name} timed out")
                model.last_error = "timeout"
            except Exception as e:
                logger.warning(f"Model {model.name} failed: {e}")
                model.last_error = str(e)
        return None


# ── ModelRouter 核心 ───────────────────────────────────────

class ModelRouter:
    """
    模型调度路由器

    回退链顺序（优先级从高到低）：
      1. 用户指定模型（preferred_model）
      2. 本地最优模型（按 DynamicScore 排序）
      3. 本地次优模型（降级尝试）
      4. 第三方 API（OpenAI → Claude → DeepSeek → ...）
      5. 内置轻量模型（永远可用的兜底）

    使用方式：
      router = ModelRouter(local_models, api_gateway, fallback_model)
      response = await router.generate(ModelRequest(
          capability=ModelCapability.CODE_GENERATION,
          prompt="用 Vue 3 写一个登录页面"
      ))
    """

    def __init__(
        self,
        local_models: list[ICandidateModel],
        api_gateway,  # ApiGateway 实例
        fallback_model: ICandidateModel,
        usage_recorder=None,  # 使用统计记录器
    ):
        self.local_models = local_models
        self.api_gateway = api_gateway
        self.fallback_model = fallback_model
        self.usage_recorder = usage_recorder

        # 构建回退链
        self._fallback_chain: list[FallbackNode] = []
        self._rebuild_chain()

    def _rebuild_chain(self):
        """根据当前状态重建回退链"""
        self._fallback_chain = [
            FallbackNode("local_primary", self._get_local_ranked()),
            FallbackNode("local_secondary", self._get_local_rest()),
            FallbackNode("api_gateway", self._get_api_candidates()),
            FallbackNode("fallback", [self.fallback_model]),
        ]

    def _get_local_ranked(self) -> list[ICandidateModel]:
        """获取本地模型并按优先级排序"""
        available = [m for m in self.local_models if m.is_available]
        available.sort(key=lambda m: m.dynamic_score, reverse=True)
        return available[:3]  # 取前3个

    def _get_local_rest(self) -> list[ICandidateModel]:
        """获取剩余本地模型作为备选"""
        ranked = self._get_local_ranked()
        ranked_names = {m.name for m in ranked}
        rest = [m for m in self.local_models if m.name not in ranked_names]
        rest.sort(key=lambda m: m.dynamic_score, reverse=True)
        return rest

    def _get_api_candidates(self) -> list[ICandidateModel]:
        """获取已配置的第三方 API 候选"""
        if self.api_gateway:
            return self.api_gateway.get_candidates()
        return []

    def _apply_task_boost(self, task_type: str):
        """根据子任务类型，给匹配的模型 dynamic_score 加成。

        匹配规则：如果模型的 strengths 包含 task_type，则 score × 1.5
        这样擅长 UI 的模型在 ui_design 任务时自动排到前面。
        """
        if not task_type:
            return
        boost_factor = 1.5
        all_candidates = self.local_models + self._get_api_candidates()
        for model in all_candidates:
            if task_type in (model.strengths or []):
                model.dynamic_score = float(model.priority) * boost_factor
                logger.debug(
                    "Task boost: %s [%s] score × %.1f → %.1f",
                    model.name, task_type, boost_factor, model.dynamic_score,
                )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """
        统一生成入口（v2 — 流水线架构）

        流程（通过 PipelineScheduler 编排）：
        1. InputValidationStage — 校验输入
        2. ContentSafetyCheckStage — 安全检查
        3. TaskBoostStage — 子任务模型加成
        4. ModelSelectionStage — 重建回退链
        5. ModelInferenceStage — 执行推理（含完整回退链）
        6. ResultDecorateStage — 结果后处理
        7. UsageRecordStage — 记录使用统计
        """
        from app.core.pipeline import PipelineContext, get_pipeline
        from app.core.pipeline_stages import (
            InputValidationStage,
            ContentSafetyCheckStage,
            TaskBoostStage,
            ModelSelectionStage,
            ModelInferenceStage,
            ResultDecorateStage,
            UsageRecordStage,
        )

        # 获取或创建流水线（单例缓存）
        pipeline = get_pipeline("model_generation")

        # 首次初始化时注册阶段（后续调用复用）
        if not pipeline.stages:
            pipeline.add_stage(InputValidationStage())
            pipeline.add_stage(ContentSafetyCheckStage())
            pipeline.add_stage(TaskBoostStage())
            pipeline.add_stage(ModelSelectionStage())
            pipeline.add_stage(ModelInferenceStage())
            pipeline.add_stage(ResultDecorateStage())
            pipeline.add_stage(UsageRecordStage())
            logger.info("Model generation pipeline initialized with %d stages", len(pipeline.stages))

        # 构建流水线上下文
        context = PipelineContext(
            metadata={
                "model_request": request,
                "model_router": self,
                "capability": request.capability.value,
            },
        )

        # 执行流水线
        context = await pipeline.execute(context)

        # 检查结果
        if context.final_output:
            return context.final_output

        # 如果流水线未产生输出，检查是否有阻止原因
        if context.metadata.get("content_blocked"):
            from app.core.model_router import ModelCapability
            reason = context.metadata.get("block_reason", "unknown")
            return ModelResponse(
                content=f"⚠️ 内容安全检查未通过：{reason}",
                model_used="safety_filter",
                provider="system",
                finish_reason="error",
                is_fallback=True,
            )

        # 回退到旧的直接生成逻辑（兼容性）
        return await self._generate_legacy(request)

    async def _do_generate(self, request: ModelRequest) -> ModelResponse:
        """
        实际执行模型推理（由 ModelInferenceStage 调用）

        包含完整的五层回退链：
        1. 用户指定模型
        2. 本地最优模型
        3. 本地次优模型
        4. 第三方 API
        5. 内置兜底模型
        """
        # 1. 用户指定模型优先
        if request.preferred_model:
            response = await self._try_specific_model(request.preferred_model, request)
            if response:
                return response
            logger.info(f"Preferred model '{request.preferred_model}' unavailable, falling back")

        # 2. 子任务类型加成
        self._apply_task_boost(request.task_type)

        # 3. 重建回退链
        self._rebuild_chain()

        # 4. 依次尝试回退链
        chain_errors: list[str] = []
        for node in self._fallback_chain:
            response = await node.try_generate(request)
            if response:
                response.is_fallback = (node.name != "local_primary")
                return response
            chain_errors.append(f"{node.name}: all models exhausted")

        # 5. 理论上不应该到这里（fallback_model 永远可用）
        raise ModelExhaustedError(
            f"All models exhausted. Chain: {' → '.join(chain_errors)}"
        )

    async def _generate_legacy(self, request: ModelRequest) -> ModelResponse:
        """
        旧版生成逻辑（兼容性回退）

        当流水线架构未能产生输出时使用。
        """
        return await self._do_generate(request)


    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式生成入口"""
        response = await self.generate(request)
        yield response.content

    async def _try_specific_model(
        self, model_name: str, request: ModelRequest
    ) -> ModelResponse | None:
        """尝试指定模型"""
        all_models = (
            self.local_models
            + (self.api_gateway.get_candidates() if self.api_gateway else [])
            + [self.fallback_model]
        )
        for model in all_models:
            if model.name == model_name:
                try:
                    return await model.generate(request)
                except Exception as e:
                    logger.warning(f"Specific model {model_name} failed: {e}")
        return None

    async def _record_usage(self, request: ModelRequest, response: ModelResponse):
        """记录使用统计（用于自动优化）"""
        if self.usage_recorder:
            try:
                self.usage_recorder(
                    model_name=response.model_used,
                    capability=request.capability.value,
                    success=(response.finish_reason == "stop"),
                    latency_ms=response.latency_ms,
                    tokens_used=response.tokens_used,
                    is_fallback=response.is_fallback,
                )
            except Exception as e:
                logger.error(f"Failed to record usage: {e}")


# ── 异常定义 ──────────────────────────────────────────────

class ModelExhaustedError(Exception):
    """所有模型尝试完毕仍失败"""
    pass


class ModelUnavailableError(Exception):
    """指定的模型不可用"""
    pass


# ── 全局路由器单例 ────────────────────────────────────────

_global_router: ModelRouter | None = None


def init_model_router(
    local_models: list[ICandidateModel],
    api_gateway=None,
    fallback_model: ICandidateModel | None = None,
    usage_recorder=None,
) -> ModelRouter:
    """初始化全局模型路由器"""
    global _global_router

    # 创建内置兜底模型（如果未提供）
    if fallback_model is None:
        fallback_model = _BuiltinFallbackModel()

    _global_router = ModelRouter(
        local_models=local_models,
        api_gateway=api_gateway,
        fallback_model=fallback_model,
        usage_recorder=usage_recorder,
    )
    logger.info("ModelRouter initialized with %d local models", len(local_models))
    return _global_router


def get_model_router() -> ModelRouter:
    """获取全局模型路由器"""
    if _global_router is None:
        raise RuntimeError(
            "ModelRouter not initialized. Call init_model_router() during app startup."
        )
    return _global_router


# ── 内置基础兜底模型 ──────────────────────────────────────

class _BuiltinFallbackModel(ICandidateModel):
    """
    内置基础模型 —— 确保永远有模型可用

    当所有本地模型和第三方 API 都不可用时，
    使用预设规则和模板提供基础能力。
    """

    def __init__(self):
        super().__init__(
            name="builtin-fallback",
            provider="fallback",
            priority=0,
        )
        self.is_available = True  # 永远可用

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """兜底生成逻辑"""
        if request.capability == ModelCapability.CODE_GENERATION:
            content = self._code_fallback(request.prompt)
        elif request.capability == ModelCapability.VIDEO_GENERATION:
            content = self._video_fallback(request.prompt)
        else:
            content = self._text_fallback(request.prompt)

        return ModelResponse(
            content=content,
            model_used="builtin-fallback",
            provider="fallback",
            finish_reason="stop",
            is_fallback=True,
        )

    def _code_fallback(self, prompt: str) -> str:
        """代码生成兜底"""
        return (
            "⚠️ 所有模型均不可用，请检查：\n"
            "1. 是否已下载本地模型？\n"
            "2. 是否已配置第三方 API 密钥？\n"
            "3. 网络连接是否正常？\n\n"
            f"你输入的提示：{prompt[:200]}"
        )

    def _video_fallback(self, prompt: str) -> str:
        """视频生成兜底"""
        return (
            "⚠️ 视频生成模型不可用。请：\n"
            "1. 下载本地视频模型 (cogvideox-5b)\n"
            "2. 配置 Replicate / Runway API 密钥\n\n"
            f"你输入的提示：{prompt[:200]}"
        )

    def _text_fallback(self, prompt: str) -> str:
        return (
            "⚠️ 当前无可用模型。请配置至少一个模型源。\n\n"
            f"你的消息：{prompt[:200]}"
        )
