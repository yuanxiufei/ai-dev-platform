"""
爬虫系统类型定义

多策略并发爬取的完整类型体系:
  - 爬取策略枚举 (StrategyType)
  - 任务定义 (CrawlTask, BatchCrawlTask)
  - 结果定义 (PageResult, BatchResult)
  - 反爬配置 (AntiDetectConfig)
  - 调度配置 (SchedulerConfig)
  - 质量配置 (QualityConfig)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional


# ── 爬取策略枚举 ──────────────────────────────────────


class StrategyType(str, Enum):
    """爬取策略类型"""
    STATIC = "static"             # 静态 HTML 解析 (readability + metadata)
    DYNAMIC = "dynamic"           # 动态渲染抓取 (Headless Browser)
    API = "api"                   # API 接口调用 (REST/GraphQL)
    SITEMAP = "sitemap"           # Sitemap 批量抓取
    FEED = "feed"                 # RSS/Atom Feed 解析
    AUTO = "auto"                 # 自动选择最优策略


class TaskPriority(int, Enum):
    """任务优先级"""
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"           # 等待调度
    QUEUED = "queued"             # 已入队
    RUNNING = "running"           # 执行中
    RETRYING = "retrying"         # 重试中
    SUCCESS = "success"           # 成功
    FAILED = "failed"             # 失败 (重试耗尽)
    CANCELLED = "cancelled"       # 已取消


class ContentQuality(str, Enum):
    """内容质量等级"""
    EXCELLENT = "excellent"       # 优质: >1000字 + 完整元数据
    GOOD = "good"                 # 良好: 500-1000字
    FAIR = "fair"                 # 一般: 200-500字
    POOR = "poor"                 # 差: <200字 或 大量噪音
    REJECTED = "rejected"         # 拒绝: 无有效内容


# ── 反爬配置 ──────────────────────────────────────────


@dataclass
class AntiDetectConfig:
    """反爬应对配置"""
    # User-Agent 轮换
    ua_rotation: bool = True              # 是否启用 UA 轮换
    ua_pool_size: int = 20                # UA 池大小
    # 请求延迟
    min_delay: float = 0.3                # 最小请求间隔 (秒)
    max_delay: float = 3.0                # 最大请求间隔 (秒)
    jitter: float = 0.5                   # 随机抖动系数
    # 代理
    proxy_enabled: bool = False           # 是否启用代理
    proxy_pool: list[str] = field(default_factory=list)
    proxy_rotation: str = "round_robin"   # round_robin | random | sticky
    # Cookie / Session
    cookie_persistence: bool = True       # 是否持久化 Cookie
    session_reuse: bool = True            # 是否复用 Session
    # 请求头随机化
    header_randomization: bool = True     # 随机化 Accept-Language / Accept-Encoding
    referer_spoofing: bool = True         # 伪造 Referer
    # 行为模拟 (动态渲染专用)
    simulate_human: bool = False          # 模拟人类行为
    scroll_delay: float = 2.0             # 滚动延迟
    mouse_movement: bool = False          # 鼠标移动模拟
    # 指纹对抗
    fingerprint_randomize: bool = True    # TLS 指纹随机化
    viewport_randomize: bool = True       # 视口大小随机化


# ── 质量管控配置 ──────────────────────────────────────


@dataclass
class QualityConfig:
    """内容质量管控配置"""
    # 去重
    dedup_enabled: bool = True            # 启用去重
    dedup_method: str = "simhash"         # simhash | minhash | exact
    simhash_threshold: int = 3            # SimHash 汉明距离阈值
    # 内容评分
    min_word_count: int = 50              # 最小字数
    min_text_density: float = 0.3         # 最小文本密度 (text/HTML ratio)
    max_boilerplate_ratio: float = 0.6    # 最大模板内容比例
    # 语言检测
    language_filter: list[str] = field(default_factory=list)  # 允许的语言列表 (空=全部)
    # 重试
    max_retries: int = 3                  # 最大重试次数
    retry_backoff_base: float = 1.0       # 退避基数 (秒)
    retry_backoff_max: float = 60.0       # 最大退避间隔
    retry_on_status: list[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    # 超时
    request_timeout: float = 30.0         # 单次请求超时
    page_timeout: float = 60.0            # 单页处理总超时


# ── 调度配置 ──────────────────────────────────────────


@dataclass
class SchedulerConfig:
    """并发调度配置"""
    # 全局限制
    max_concurrent_tasks: int = 10        # 最大并发任务数
    max_queued_tasks: int = 1000          # 最大排队任务数
    # 域名级别限制
    per_domain_max_concurrent: int = 3    # 单域名最大并发
    per_domain_rate_limit: float = 5.0    # 单域名每秒请求数上限
    per_domain_daily_limit: int = 10000   # 单域名每日请求上限
    # 自适应并发
    adaptive_concurrency: bool = True     # 启用自适应并发调整
    concurrency_increment: int = 1        # 每次增量
    concurrency_decrement: int = 2        # 每次减量
    max_concurrency: int = 20             # 自适应最大并发
    min_concurrency: int = 1              # 自适应最小并发
    # 失败处理
    domain_cooldown_seconds: int = 60     # 域名冷却时间 (连续失败后)
    domain_failure_threshold: int = 5     # 触发冷却的连续失败次数
    # 优先级
    priority_aging_enabled: bool = True   # 启用优先级老化
    priority_aging_interval: int = 60     # 老化间隔 (秒)
    priority_aging_boost: int = 5         # 每次老化提升量
    # robots.txt
    robots_respect: bool = True           # 遵守 robots.txt
    robots_cache_seconds: int = 3600      # robots.txt 缓存时间


# ── 域名运行时速率限制 ──────────────────────────────


@dataclass
class DomainRateLimit:
    """单个域名的运行时速率限制（区别于 SchedulerConfig 的全局默认）"""
    domain: str = ""
    max_concurrent: int = 3
    delay_seconds: float = 1.0
    daily_limit: int = 10000
    daily_used: int = 0
    cooldown_until: float = 0.0
    consecutive_failures: int = 0


# ── 任务 / 结果 ───────────────────────────────────────


@dataclass
class CrawlTask:
    """单页爬取任务"""
    url: str
    task_id: str = ""
    strategy: StrategyType = StrategyType.AUTO
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    # 元数据
    domain: str = ""
    depth: int = 0                        # 爬取深度
    parent_url: str = ""                  # 来源页面
    tags: list[str] = field(default_factory=list)
    # 策略参数
    render_js: bool = False               # 是否需要 JS 渲染
    api_headers: dict = field(default_factory=dict)
    api_body: dict = field(default_factory=dict)
    api_method: str = "GET"
    # 调度信息
    created_at: float = 0.0
    queued_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    retry_count: int = 0
    # 回调
    on_complete: Optional[Callable] = None
    metadata: dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """任务等待时长"""
        import time
        return time.time() - (self.queued_at or self.created_at or time.time())

    def __hash__(self) -> int:
        return hash(self.url)


@dataclass
class PageResult:
    """单页爬取结果"""
    url: str
    task_id: str = ""
    strategy: StrategyType = StrategyType.AUTO
    success: bool = False
    # 内容
    title: str = ""
    text: str = ""
    html: str = ""                        # 原始 HTML (可选保留)
    text_length: int = 0
    # OCR 增强 (SmolDocling)
    ocr_text: str = ""                    # 图片 OCR 提取文本
    ocr_images: list[str] = field(default_factory=list)  # 已 OCR 的图片 URL
    ocr_elapsed_ms: float = 0.0           # OCR 总耗时
    # 质量
    quality: ContentQuality = ContentQuality.POOR
    quality_score: float = 0.0            # 0.0-1.0
    # 元数据
    domain: str = ""
    content_type: str = ""
    language: str = ""
    published_date: str = ""
    author: str = ""
    # 抓取信息
    http_status: int = 0
    fetch_time_ms: float = 0.0
    retry_count: int = 0
    error: str = ""
    # 结构化提取
    schema_org: dict = field(default_factory=dict)
    open_graph: dict = field(default_factory=dict)
    json_ld: list[dict] = field(default_factory=list)
    # 链接发现
    discovered_urls: list[str] = field(default_factory=list)
    # 扩展
    extra: dict = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        """获取完整文本 (正文 + OCR 提取)"""
        parts = [self.text]
        if self.ocr_text and self.ocr_text.strip():
            parts.append("\n\n<!-- OCR extracted -->\n")
            parts.append(self.ocr_text)
        return "".join(parts)

    def to_document(self) -> dict:
        """转换为文档格式 (用于知识库导入)"""
        return {
            "url": self.url,
            "title": self.title or self.url.rsplit("/", 1)[-1],
            "text": self.full_text,
            "word_count": self.text_length or len(self.text.split()),
            "metadata": {
                "source": self.url,
                "domain": self.domain,
                "content_type": self.content_type,
                "language": self.language,
                "author": self.author,
                "published_date": self.published_date,
                "quality": self.quality.value,
                "quality_score": self.quality_score,
                "strategy": self.strategy.value,
                "fetch_time_ms": self.fetch_time_ms,
                "ocr_chars": len(self.ocr_text or ""),
                "ocr_images": len(self.ocr_images),
                "ocr_time_ms": self.ocr_elapsed_ms,
            },
        }


@dataclass
class BatchResult:
    """批量爬取结果汇总"""
    # 统计
    total_tasks: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    # 结果
    pages: list[PageResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # 耗时
    total_time_seconds: float = 0.0
    avg_fetch_time_ms: float = 0.0
    # 域名统计
    per_domain: dict[str, dict] = field(default_factory=dict)
    # 质量分布
    quality_distribution: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.succeeded / self.total_tasks

    @property
    def all_documents(self) -> list[dict]:
        """所有成功结果的文档格式列表"""
        return [p.to_document() for p in self.pages if p.success]


@dataclass
class CrawlProgress:
    """爬取进度 (WebSocket 推送)"""
    task_id: str = ""
    domain: str = ""
    status: str = ""                      # starting | crawling | processing | done | error
    done: int = 0
    total: int = 0
    current_url: str = ""
    succeeded: int = 0
    failed: int = 0
    message: str = ""
    elapsed_seconds: float = 0.0
