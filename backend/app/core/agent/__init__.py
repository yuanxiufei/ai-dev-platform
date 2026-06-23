"""
Agent 系统 — Function Calling + Tool Loop 运行器

借鉴 AstrBot agent/ 架构：
- ToolExecutor: 工具执行引擎（解析 tool_calls → 调用工具 → 收集结果）
- AgentRunner: 多轮工具调用循环（LLM → tool_call → execute → result → LLM）
- AgentConfig: Agent 定义（名称、指令、工具集、钩子）
- Handoff: 子 Agent 委派机制
- ContextCompressor: 对话上下文压缩（LLM 摘要 + 轮次截断）
- AgentHooks: Agent 生命周期钩子（EventBus 桥接 + 组合模式）
- TrajectoryRecorder: Agent 轨迹记录（增量持久化）
- MiddlewarePipeline: Agent 中间件管道（Guardrail/LoopDetection/Summarization/ErrorHandling）
- AgentReflector: LLM 自省/反思（reflect_on_result, SelfCritique, ReflectionManager）
- AgentModes: Custom Modes 系统（architect/code/debug/test/review/docs）
- LakeviewSummarizer: LLM 步骤摘要（人类可读 + 上下文压缩）
- WorktreeManager: Git Worktree 并行开发环境（多分支并行任务）
- DiffEngine: 文件变更差异生成器（unified diff → 前端 diff-viewer）
"""

from app.core.agent.tool_executor import ToolExecutor, get_tool_executor  # noqa: F401
from app.core.agent.agent_runner import (  # noqa: F401
    AgentRunner, AgentRunResult, StreamingAgentRunner,
)
from app.core.agent.agent_config import AgentConfig, AgentHook  # noqa: F401
from app.core.agent.handoff import (  # noqa: F401
    HandoffTool, SubAgentConfig, SubAgentOrchestrator,
    HandoffResult, init_orchestrator, get_orchestrator,
)
from app.core.agent.context_compressor import (  # noqa: F401
    ContextConfig, ContextCompressor,
    ContextTruncator, EstimateTokenCounter,
    TruncateByTurnsCompressor, LLMSummaryCompressor,
    create_compressors, split_into_rounds,
)
from app.core.agent.hooks import (  # noqa: F401
    AgentHooks, HookContext, EventBusAgentHooks, CompositeAgentHooks,
)
from app.core.agent.trajectory_recorder import (  # noqa: F401
    TrajectoryRecorder, TrajectoryStep, TrajectorySummary,
)
from app.core.agent.middlewares import (  # noqa: F401
    AgentMiddleware, MiddlewarePipeline, MiddlewareContext,
    LoopDetectionMiddleware, SummarizationMiddleware,
    ErrorHandlingMiddleware, GuardrailMiddleware,
    create_default_pipeline,
)
from app.core.agent.agent_modes import (  # noqa: F401
    AgentMode, ModeManager, PRESET_MODES,
    CKGMode, init_mode_manager, get_mode_manager,
)
from app.core.agent.lakeview import (  # noqa: F401
    LakeviewSummarizer, StepSummary, RunSummary,
    get_lakeview_summarizer,
)
from app.core.agent.worktree import (  # noqa: F401
    WorktreeManager, WorktreeConfig, WorktreeInfo, WorktreeResult,
    WorktreeTask, WorktreeStatus,
    get_worktree_manager, init_worktree_manager,
)
from app.core.agent.reflection import (  # noqa: F401
    AgentReflector, ReflectionResult, ReflectionPrompt,
    ReflectionConfig, SelfCritique, ReflectionManager,
    get_reflection_manager, init_reflection_manager,
)
from app.core.diff import DiffEngine, FileDiff  # noqa: F401
