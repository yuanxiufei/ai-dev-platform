import os
import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = secrets.token_urlsafe(32)
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            self.FRONTEND_HOST
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    # ── AI 模型相关配置 ──────────────────────────────
    MODELS_DIR: str = "models"               # 本地模型存放目录
    DEFAULT_MODEL: str = "gemma-31b"         # 默认使用的模型
    MODEL_PREFER_LOCAL: bool = True          # 是否优先使用本地模型

    # 第三方 API 密钥（可通过环境变量注入）
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    REPLICATE_API_KEY: str = ""
    ZHIPU_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    OLLAMA_API_KEY: str = "ollama-local"  # Ollama 本地运行无需密钥，使用占位值

    # 模型调度配置
    MODEL_REQUEST_TIMEOUT: int = 30          # 单次请求超时（秒）
    MODEL_MAX_RETRIES: int = 2               # 最大重试次数
    MODEL_FALLBACK_ENABLED: bool = True      # 是否启用回退链

    # 自动优化配置
    AUTO_OPTIMIZE_ENABLED: bool = True       # 是否启用自动优化
    AUTO_OPTIMIZE_INTERVAL_HOURS: int = 24   # 优化间隔（小时）

    # ── Agent / MCP 配置 ─────────────────────────────
    AGENT_ENABLED: bool = True               # 是否启用 Agent 系统
    AGENT_DEFAULT_MAX_TURNS: int = 10        # Agent 默认最大循环轮次
    AGENT_TOOL_TIMEOUT: int = 30             # 单次工具调用超时（秒）
    AGENT_MAX_CONTEXT_TOKENS: int = 64000    # Agent 最大上下文 token
    AGENT_AUTO_DISCOVERY: bool = True        # 是否自动发现工具模块

    # ── 限流配置 ────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True          # 是否启用 Fixed Window 限流
    RATE_LIMIT_COUNT: int = 10               # 时间窗口内最大请求数
    RATE_LIMIT_TIME: int = 60                # 时间窗口（秒）
    RATE_LIMIT_STRATEGY: str = "stall"       # 限流策略: "stall" | "discard"

    # ── 内容安全配置 ────────────────────────────────
    CONTENT_SAFETY_ENABLED: bool = True      # 是否启用内容安全检查
    CONTENT_SAFETY_KEYWORDS: bool = True     # 是否启用关键词策略
    CONTENT_SAFETY_LLM_JUDGE: bool = False   # 是否启用 LLM 裁判策略

    # ── 上下文压缩配置 ──────────────────────────────
    CONTEXT_COMPRESS_ENABLED: bool = True    # 是否启用上下文压缩
    CONTEXT_MAX_TOKENS: int = 64000          # 最大上下文 token
    CONTEXT_COMPRESS_THRESHOLD: float = 0.82 # 压缩触发阈值
    CONTEXT_KEEP_RECENT_RATIO: float = 0.15  # LLM 压缩时保留的最近上下文比例

    # ── Cron 定时任务配置 ───────────────────────────
    CRON_ENABLED: bool = True                # 是否启用定时任务系统

    # ── 插件系统配置 ──────────────────────────────
    PLUGINS_ENABLED: bool = True             # 是否启用插件系统
    PLUGINS_AUTO_DISCOVER: bool = True       # 是否自动发现插件
    PLUGINS_DIRS: str = "plugins,builtin_plugins"  # 插件目录（逗号分隔）

    # ── 事件总线配置 ──────────────────────────────
    EVENT_BUS_ENABLED: bool = True           # 是否启用事件总线
    EVENT_BUS_MAX_CONCURRENT: int = 100      # 事件总线最大并发任务数

    # ── 对话管理配置 ──────────────────────────────
    CONVERSATION_MAX_HISTORY: int = 100      # 对话历史最大轮次
    CONVERSATION_AUTO_TITLE: bool = True     # 是否自动生成对话标题

    # ── 消息历史配置 ──────────────────────────────
    MESSAGE_HISTORY_ENABLED: bool = True     # 是否启用消息历史记录
    MESSAGE_HISTORY_RETENTION_DAYS: int = 7  # 消息历史保留天数

    # ── 工具图片缓存配置 ──────────────────────────
    TOOL_IMAGE_CACHE_ENABLED: bool = True    # 是否启用工具图片缓存
    TOOL_IMAGE_CACHE_EXPIRY_SECONDS: int = 3600  # 缓存过期时间（秒）

    # MCP 服务器配置（JSON 格式，通过环境变量 MCP_SERVERS 注入）
    # 格式: [{"name":"filesystem","transport":"stdio","command":"npx","args":["-y","@modelcontextprotocol/server-filesystem","."]}]
    MCP_SERVERS: str = "[]"                  # MCP 服务器配置 JSON

    # ── 知识库配置 ────────────────────────────────
    KB_SQLITE_PATH: str = "data/kb_metadata.db"  # KB 元数据 SQLite 路径
    KB_REPAIR_ENABLED: bool = True           # 是否启用 LLM 文本修复
    KB_URL_PARSER_ENABLED: bool = True       # 是否启用 URL 导入

    # ── 图像生成配置 ────────────────────────────────
    IMAGE_GEN_ENABLED: bool = True           # 是否启用图像生成
    STABILITY_API_KEY: str = ""              # Stability AI API key
    COMFYUI_BASE_URL: str = ""               # ComfyUI 服务地址

    # ── 语音配置 ──────────────────────────────────
    VOICE_ENABLED: bool = True               # 是否启用语音服务 (TTS/STT)

    # ── Webhook 配置 ───────────────────────────────
    WEBHOOK_ENABLED: bool = True             # 是否启用 Webhook 系统
    WEBHOOK_MAX_RETRIES: int = 3             # 默认最大重试次数
    WEBHOOK_TIMEOUT_SECONDS: float = 10.0    # 默认超时 秒

    # ── Web 搜索配置 ────────────────────────────────
    TAVILY_API_KEY: str = ""                 # Tavily API key（逗号分隔多key）
    BRAVE_API_KEY: str = ""                  # Brave Search API key
    FIRECRAWL_API_KEY: str = ""              # Firecrawl API key

    # ── 备份配置 ───────────────────────────────────
    BACKUP_ENABLED: bool = True              # 是否启用备份系统

    # ── 技能配置 ───────────────────────────────────
    SKILLS_ROOT: str = "skills"              # 技能根目录
    SKILLS_ENABLED: bool = True              # 是否启用技能系统

    # ── 提示词模板配置 ────────────────────────────
    PROMPT_TEMPLATES_ENABLED: bool = True    # 是否启用斜杠命令模板

    # ── 任务管理配置 ──────────────────────────────
    TASK_MANAGER_ENABLED: bool = True        # 是否启用 AI 多步骤任务工作流

    # ── OpenAPI 发现配置 ───────────────────────────
    OPENAPI_DISCOVERY_ENABLED: bool = True   # 是否启用 OpenAPI 自动发现

    # ── 访问控制配置 ──────────────────────────────
    ACCESS_CONTROL_ENABLED: bool = False     # 是否启用访问控制白名单
    PLATFORM_API_KEYS: str = ""              # 平台 API key（逗号分隔）

    # ── Sandbox 沙箱配置 ───────────────────────────
    SANDBOX_ENABLED: bool = True             # 是否启用沙箱隔离
    SANDBOX_TYPE: str = "local"              # Sandbox 类型: local | docker
    SANDBOX_WORKSPACE: str = os.path.join(os.getcwd(), "workspace")  # 沙箱工作区
    SANDBOX_COMMAND_TIMEOUT: int = 120       # 命令执行超时（秒）
    SANDBOX_DOCKER_IMAGE: str = "python:3.11-slim"

    # ── Trajectory 轨迹配置 ────────────────────────
    TRAJECTORY_ENABLED: bool = True          # 是否启用轨迹记录
    TRAJECTORY_OUTPUT_DIR: str = "trajectories/"  # 轨迹输出目录

    # ── CKG 代码知识图谱配置 ───────────────────────
    CKG_ENABLED: bool = True                 # 是否启用代码知识图谱
    CKG_DB_PATH: str = "data/ckg.db"         # CKG SQLite 数据库路径

    # ── Redis 分布式缓存配置 ─────────────────────
    REDIS_ENABLED: bool = True               # 是否启用 Redis
    REDIS_URL: str = ""                      # Redis 完整 URL（优先，为空则用分片配置）
    REDIS_HOST: str = "localhost"            # Redis 主机
    REDIS_PORT: int = 6379                   # Redis 端口
    REDIS_PASSWORD: str = ""                 # Redis 密码
    REDIS_DB: int = 0                        # Redis 数据库编号

    # ── Redis 分布式限流配置 ─────────────────────
    REDIS_RATE_LIMIT_ENABLED: bool = True    # 是否启用分布式限流
    REDIS_RATE_LIMIT_PER_IP: int = 100       # 每 IP 每分钟最大请求数
    REDIS_RATE_LIMIT_WINDOW: int = 60        # 滑动窗口秒数

    # ── 后台任务队列配置 ─────────────────────────
    TASK_QUEUE_ENABLED: bool = True          # 是否启用 Celery 任务队列
    CELERY_BROKER_URL: str = ""             # Celery broker URL（为空则复用 Redis 配置）
    CELERY_RESULT_BACKEND: str = ""          # Celery result backend（为空则复用 broker）

    # ── Metrics 监控配置 ─────────────────────────
    METRICS_ENABLED: bool = True             # 是否启用 Prometheus 指标导出

    # ── GPU 控制层配置 ─────────────────────────
    GPU_ENABLED: bool = True                 # 是否启用 GPU 控制层
    GPU_MONITOR_INTERVAL: float = 5.0        # GPU 监控间隔（秒）
    GPU_TEMP_WARNING_C: float = 80.0         # GPU 温度警告阈值
    GPU_TEMP_CRITICAL_C: float = 90.0        # GPU 温度严重阈值
    GPU_MEM_WARNING_PCT: float = 85.0        # GPU 显存使用警告阈值
    GPU_MEM_CRITICAL_PCT: float = 95.0       # GPU 显存使用严重阈值

    # ── 系统资源监控配置 ────────────────────────
    RESOURCE_COLLECTOR_ENABLED: bool = True  # 是否启用资源采集器
    RESOURCE_COLLECTOR_INTERVAL: float = 10.0  # 采集间隔（秒）

    # ── 模型目录配置 ────────────────────────────
    CATALOG_ENABLED: bool = True             # 是否启用模型目录
    CATALOG_FILE: str = ""                   # 自定义 catalog YAML 路径（空=内置）

    # ── Auth 增强配置 ───────────────────────────
    API_KEY_ENABLED: bool = True             # 是否启用 API Key 管理
    REFRESH_TOKEN_ENABLED: bool = True       # 是否启用 Refresh Token
    REFRESH_TOKEN_TTL_HOURS: int = 168       # Refresh Token 有效期（小时，默认7天）

    # ── 远程代理配置 ───────────────────────────
    REMOTE_AGENT_ENABLED: bool = True        # 是否启用远程代理
    PORT_FORWARD_ENABLED: bool = True        # 是否启用端口转发
    PORT_FORWARD_RANGE_START: int = 10000    # 代理端口起始
    PORT_FORWARD_RANGE_END: int = 20000      # 代理端口结束
    WORKSPACE_TRUST_ENABLED: bool = True     # 是否启用工作区信任

    # ── EventBus 分布式配置 ─────────────────────
    EVENT_COORDINATOR_TYPE: str = "local"    # 协调器类型: local | redis
    EVENT_COORDINATOR_REDIS_URL: str = ""    # Redis URL（coordinator_type=redis 时使用）

    # ── Sandbox K8s 配置 ─────────────────────────
    SANDBOX_K8S_ENABLED: bool = False        # 是否启用 K8s 沙箱
    SANDBOX_K8S_NAMESPACE: str = "ai-sandbox"
    SANDBOX_K8S_IMAGE: str = "python:3.12-slim"
    SANDBOX_K8S_CPU_LIMIT: str = "2"
    SANDBOX_K8S_MEMORY_LIMIT: str = "4Gi"

    # ── 配置热加载配置 ─────────────────────────
    CONFIG_WATCH_ENABLED: bool = True         # 是否启用配置文件监听
    CONFIG_WATCH_INTERVAL: float = 5.0        # 监听间隔（秒）
    CONFIG_RELOAD_API_ENABLED: bool = True    # 是否启用配置热加载 API

    # ── 终端/PTY 配置 ─────────────────────────
    TERMINAL_ENABLED: bool = True             # 是否启用远程终端
    TERMINAL_DEFAULT_SHELL: str = ""          # 默认 shell（空=自动检测）

    # ── Benchmark 配置 ────────────────────────
    BENCHMARK_ENABLED: bool = True            # 是否启用 Benchmark 引擎
    BENCHMARK_MAX_CONCURRENT: int = 2         # 最大并发 Benchmark 数

    # ── 统一存储配置（用户可自定义）───────────────
    STORAGE_ROOT: str = "storage"             # 存储根目录
    STORAGE_MAX_GB: int = 100                 # 全局最大存储（GB），0=不限
    STORAGE_MAX_WORKSPACE_GB: int = 10        # 单工作区最大（GB），0=不限
    STORAGE_AUTO_CLEANUP_HOURS: int = 72      # 自动清理超过N小时的文件

    # ── Checkpoint 检查点配置 ──────────────────
    CHECKPOINT_ENABLED: bool = True           # 是否启用 Git 检查点
    CHECKPOINT_MAX_COUNT: int = 50            # 最大检查点数量
    CHECKPOINT_AUTO_CREATE: bool = True       # 工具调用前自动创建检查点

    # ── Guardrails 护栏配置 ────────────────────
    GUARDRAILS_ENABLED: bool = True           # 是否启用护栏系统
    GUARDRAILS_DEFAULT_LEVEL: str = "warn"    # 默认介入级别: allow/warn/ask_user/block
    GUARDRAILS_MAX_FILE_SIZE_MB: float = 100  # 操作文件最大大小

    # ── 多租户配置 ──────────────────────────────
    MULTI_TENANCY_ENABLED: bool = False       # 是否启用多租户

    # ── Standalone 独立运行配置 ─────────────────
    STANDALONE_MODE: bool = False              # 是否运行在独立模式（非 Docker）
    STANDALONE_WATCHDOG_ENABLED: bool = True   # 是否启用守护进程
    STANDALONE_API_AUTH_ENABLED: bool = True   # 是否启用 API 鉴权
    STANDALONE_SMART_SLEEP_ENABLED: bool = True  # 是否启用智能休眠
    STANDALONE_SLEEP_IDLE_TIMEOUT: int = 300   # 休眠空闲超时（秒）
    STANDALONE_SLEEP_UNLOAD_MODELS: bool = True  # 休眠时卸载模型
    STANDALONE_SLEEP_REDUCE_CPU_PRIORITY: bool = True  # 休眠时降低 CPU 优先级
    STANDALONE_REMOTE_ACCESS_ENABLED: bool = True  # 是否允许远程访问
    STANDALONE_BIND_HOST: str = "0.0.0.0"      # 绑定地址
    STANDALONE_BIND_PORT: int = 18000           # 绑定端口
    STANDALONE_MAX_RESTARTS: int = 10           # 最大重启次数
    STANDALONE_HEALTH_CHECK_INTERVAL: int = 5   # 健康检查间隔（秒）
    STANDALONE_PRESET_API_KEYS: str = ""        # 预置 API 密钥（逗号分隔）

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
