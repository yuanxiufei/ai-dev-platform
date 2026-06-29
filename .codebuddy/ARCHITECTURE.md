# AI Fullstack Platform — 架构规范与实现路线图

> **定位**：本文档是 Studio（AI编程工具）和 Video（视频生成工具）两个子项目的唯一权威架构文档。
> 所有代码实现（无论人工还是 AI 辅助）均须遵循本文档定义的模块边界、接口契约与数据流。
>
> **许可证合规声明**：本文档描述的架构概念（多后端代理、优先级调度、模型状态机等）均为通用计算机科学模式，
> 不包含任何第三方专有代码。最终代码为自主实现，项目采用 MIT 许可证。

---

## 目录

1. [系统总览](#1-系统总览)
2. [Studio 项目架构](#2-studio-项目架构)
3. [Video 项目架构](#3-video-项目架构)
4. [共享基础设施](#4-共享基础设施)
  5. [数据模型定义](#5-数据模型定义)
  6. [API 接口契约](#6-api-接口契约)
  7. [模型管理层架构](#7-模型管理层架构)
  8. [多模型动态调度](#8-多模型动态调度)
  9. [实现路线图](#9-实现路线图)
  10. [代码规范](#10-代码规范)
  11. [闭环系统架构](#11-闭环系统架构)

---

## 1. 系统总览

```
┌──────────────────────────────────────────────────────────────┐
│                      系统架构全景                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐          ┌──────────────────┐         │
│  │  studio-admin     │          │  video-admin      │         │
│  │  (Vue 3 管理端)    │          │  (Vue 3 管理端)    │         │
│  │  port:5175        │          │  port:5176        │         │
│  └────────┬─────────┘          └────────┬─────────┘         │
│           │                             │                    │
│  ┌────────┴─────────┐          ┌────────┴─────────┐         │
│  │  studio-client    │          │  video-client     │         │
│  │  (Vue 3 C端)      │          │  (Vue 3 C端)      │         │
│  │  port:5173        │          │  port:5174        │         │
│  └────────┬─────────┘          └────────┬─────────┘         │
│           │                             │                    │
│           └──────────┬──────────────────┘                    │
│                      │ /api/v1/*                             │
│              ┌───────┴────────┐                              │
│              │   FastAPI 后端   │  port:8000                  │
│              │  ┌───────────┐  │                              │
│              │  │ 认证/用户   │  │  (已实现)                    │
│              │  │ Studio路由  │  │  (待实现)                    │
│              │  │ Video路由   │  │  (待实现)                    │
│              │  │ 模型管理API │  │  (待实现)                    │
│              │  └───────────┘  │                              │
│              └───────┬────────┘                              │
│                      │                                       │
│     ┌────────────────┼────────────────┐                      │
│     │                │                │                      │
│  ┌──┴──────────┐ ┌──┴────────┐ ┌─────┴──────────┐          │
│  │ ai_models   │ │ Workers   │ │ External APIs  │          │
│  │ (模型管理层)  │ │ (任务队列)  │ │ (OpenAI/Claude │          │
│  │             │ │            │ │  /Replicate等)  │          │
│  │ - 注册中心   │ │ - 异步推理  │ │                │          │
│  │ - 下载管理   │ │ - 任务调度  │ │                │          │
│  │ - 调度路由   │ │            │ │                │          │
│  │ - 自动优化   │ │            │ │                │          │
│  └─────────────┘ └───────────┘ └────────────────┘          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 核心设计原则

1. **能力导向**：模型按能力分类（代码生成/视频生成/视觉理解），不按厂商分类
2. **回退链**：本地模型 → 第三方API → 内置基础模型，三者自动切换
3. **统一接口**：所有模型调用走同一套 API 契约，屏蔽底层差异
4. **自主实现**：所有代码自研，仅参考公开标准和通用架构模式

---

## 2. Studio 项目架构

### 2.1 定位
AI 编程工具：截图转代码、自然语言生成全栈项目、AI 对话辅助编程。

### 2.2 功能模块

| 模块 | 管理端(admin) | C端(client) | 优先级 |
|------|:---:|:---:|:---:|
| 项目管理 (CRUD) | ✅ | ✅(只读) | P0 |
| 模板市场 | ✅ | ✅ | P0 |
| AI 对话编程 | — | ✅ | P0 |
| 会话管理 | — | ✅ | P0 |
| 代码生成（截图→代码） | ✅ | ✅ | P1 |
| 全栈项目生成 | ✅ | ✅ | P1 |
| 模型管理（下载/切换） | ✅ | ✅ | P1 |
| 部署管理 | ✅ | — | P2 |
| 使用数据分析 | ✅ | — | P2 |

### 2.3 数据流

```
用户输入（截图/文本描述）
    │
    ▼
┌──────────────────┐
│  FastAPI 路由      │  POST /studio/chat  or  POST /studio/projects
│  studio/client/*  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  ModelRouter      │  选择最优模型（本地优先 → API回退）
│  (模型调度器)      │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌──────┐  ┌──────────┐
│ 本地   │  │ 第三方API  │
│ 模型   │  │ (OpenAI等) │
└──┬───┘  └─────┬─────┘
   │            │
   └─────┬──────┘
         ▼
   生成的代码/响应
         │
         ▼
    返回前端展示
```

---

## 3. Video 项目架构

### 3.1 定位
视频生成工具：文字转视频、UI演示视频、视频管理平台。

### 3.2 功能模块

| 模块 | 管理端(admin) | C端(client) | 优先级 |
|------|:---:|:---:|:---:|
| 视频 CRUD | ✅ | — | P0 |
| 视频生成 | ✅ | ✅ | P0 |
| 视频浏览/搜索 | — | ✅ | P0 |
| 视频播放 | — | ✅ | P0 |
| 数据分析 | ✅ | — | P1 |
| 内容审核 | ✅ | — | P1 |
| 模型下载/切换 | ✅ | ✅ | P1 |
| 生成任务队列 | ✅ | ✅ | P1 |

### 3.3 数据流

```
用户输入（文本提示词）
    │
    ▼
┌──────────────────┐
│  FastAPI 路由      │  POST /videos/generate
│  video/client/*   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  VideoTaskQueue   │  异步任务队列（视频生成耗时长）
│  (workers/)       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  ModelRouter      │  视频生成模型选择
│  (模型调度器)      │
└────────┬─────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌──────┐  ┌──────────┐
│ 本地   │  │ 第三方API  │
│CogVideo│  │(Replicate │
│       │  │ /Runway等) │
└──┬───┘  └─────┬─────┘
   │            │
   ▼            ▼
┌──────────────────┐
│  视频文件 + 缩略图  │
└────────┬─────────┘
         ▼
    存储到文件系统/CDN
```

---

## 4. 共享基础设施

### 4.1 目录结构

```
backend/app/
├── models/                     # 数据模型（SQLModel表）
│   ├── __init__.py
│   ├── studio_models.py        # Studio域模型
│   ├── video_models.py         # Video域模型
│   └── system_models.py        # 系统模型（模型信息、下载任务等）
├── core/
│   ├── config.py               # 全局配置（已有，需扩展）
│   ├── db.py                   # 数据库引擎（已有）
│   ├── security.py             # 认证（已有）
│   ├── model_router.py         # 【新增】模型调度路由器
│   ├── api_gateway.py          # 【新增】第三方API统一网关
│   ├── fallback_chain.py       # 【新增】回退链管理器
│   └── model_downloader.py     # 【新增】模型下载服务
├── api/routes/
│   ├── studio/                 # Studio路由（已有stub，需实现）
│   │   ├── admin/projects.py
│   │   ├── admin/templates.py
│   │   └── client/chat.py, sessions.py, models.py
│   ├── video/                  # Video路由（已有stub，需实现）
│   │   ├── admin/videos.py, analytics.py, moderation.py
│   │   └── client/browse.py, generate.py, play.py
│   └── system/                 # 【新增】系统管理路由
│       ├── models.py           # 模型列表/下载/状态
│       └── health.py           # 系统健康检查
└── crud.py                     # 数据库操作（已有，需扩展）

ai_models/
├── base.py                     # 基类（已有）
├── registry.py                 # 注册中心（已有，需扩展）
├── coder_model.py              # 代码生成模型（已有）
├── video_model.py              # 视频生成模型（已有）
├── vl_model.py                 # 视觉语言模型（已有）
├── scheduler.py                # 【新增】多模型动态调度器
├── api_proxy.py                # 【新增】第三方API代理
├── downloader.py               # 【新增】模型下载管理器
├── optimizer.py                # 【新增】使用数据自动优化引擎
└── prompts/                    # Prompt模板（已有）
```

### 4.2 数据库扩展计划

在现有 `User` + `Item` 基础上新增以下表：

```
studio_projects      — Studio项目管理
studio_templates     — 项目模板
chat_sessions        — AI对话会话
chat_messages        — 对话消息
video_tasks          — 视频生成任务
video_assets         — 视频资产
model_downloads      — 模型下载记录
model_usage_stats    — 模型使用统计（用于自动优化）
api_credentials      — 第三方API密钥存储（加密）
```

---

## 5. 数据模型定义

### 5.1 已有模型（不改动）

```python
# backend/app/models.py — 保持不变
User(id, email, is_active, is_superuser, full_name, hashed_password, created_at)
Item(id, title, description, owner_id, created_at)
```

### 5.2 Studio 域模型 (backend/app/models/studio_models.py)

```python
class StudioProject(SQLModel, table=True):
    """AI 编程项目"""
    __tablename__ = "studio_projects"
    id: uuid.UUID = PK
    name: str(255)
    description: str(2000) | None
    status: Enum[draft|building|deploying|running|failed]
    framework: str(50)          # vue | react | html
    stack: str(100)             # fastapi+vue | django+react
    template_id: FK → studio_templates.id (nullable)
    generated_code: JSON | None # 生成的代码 {filename: code}
    build_log: Text | None
    deploy_url: str(500) | None
    owner_id: FK → user.id
    created_at: datetime
    updated_at: datetime

class StudioTemplate(SQLModel, table=True):
    """项目模板"""
    __tablename__ = "studio_templates"
    id: uuid.UUID = PK
    name: str(255)
    description: str(2000) | None
    category: str(100)          # landing-page | dashboard | api-service
    framework: str(50)
    stack: str(100)
    preview_url: str(500) | None
    template_data: JSON | None  # 模板代码
    usage_count: int = 0
    is_public: bool = True
    created_by: FK → user.id (nullable)
    created_at: datetime

class ChatSession(SQLModel, table=True):
    """AI 对话会话"""
    __tablename__ = "chat_sessions"
    id: uuid.UUID = PK
    title: str(255) = "New Chat"
    model_name: str(100) | None # 使用的模型
    project_id: FK → studio_projects.id (nullable)
    owner_id: FK → user.id
    created_at: datetime
    updated_at: datetime

class ChatMessage(SQLModel, table=True):
    """对话消息"""
    __tablename__ = "chat_messages"
    id: uuid.UUID = PK
    session_id: FK → chat_sessions.id
    role: Enum[user|assistant|system|tool]
    content: Text
    metadata: JSON | None       # token数、模型名等
    created_at: datetime
```

### 5.3 Video 域模型 (backend/app/models/video_models.py)

```python
class VideoTask(SQLModel, table=True):
    """视频生成任务"""
    __tablename__ = "video_tasks"
    id: uuid.UUID = PK
    prompt: Text                 # 生成提示词
    status: Enum[pending|generating|completed|failed]
    model_name: str(100)         # 使用的模型
    params: JSON | None          # 生成参数 {num_frames, fps, seed}
    output_path: str(500) | None # 生成的视频路径
    thumbnail_path: str(500) | None
    duration: float | None       # 视频时长（秒）
    error_message: Text | None
    progress: int = 0           # 0-100
    owner_id: FK → user.id
    created_at: datetime

class VideoAsset(SQLModel, table=True):
    """视频资产（管理端）"""
    __tablename__ = "video_assets"
    id: uuid.UUID = PK
    title: str(255)
    description: str(2000) | None
    task_id: FK → video_tasks.id (nullable)
    file_path: str(500)
    thumbnail_path: str(500) | None
    duration: float | None
    tags: JSON | None           # ["demo", "tutorial"]
    view_count: int = 0
    is_public: bool = True
    is_approved: bool = False   # 审核状态
    owner_id: FK → user.id
    created_at: datetime
```

### 5.4 系统模型 (backend/app/models/system_models.py)

```python
class ModelDownload(SQLModel, table=True):
    """模型下载记录"""
    __tablename__ = "model_downloads"
    id: uuid.UUID = PK
    model_name: str(100)
    source: str(200)           # HuggingFace URL / 本地路径
    status: Enum[pending|downloading|completed|failed]
    progress: int = 0          # 0-100
    file_size: int | None      # 字节数
    downloaded: int = 0        # 已下载字节数
    error_message: str | None
    started_by: FK → user.id
    created_at: datetime

class ModelUsageStat(SQLModel, table=True):
    """模型使用统计（驱动自动优化）"""
    __tablename__ = "model_usage_stats"
    id: uuid.UUID = PK
    model_name: str(100)
    task_type: str(50)         # code_gen | video_gen | chat
    success: bool
    latency_ms: int            # 推理耗时
    token_count: int | None
    error_message: str | None
    user_id: FK → user.id (nullable)
    created_at: datetime

class ApiCredential(SQLModel, table=True):
    """第三方API密钥（加密存储）"""
    __tablename__ = "api_credentials"
    id: uuid.UUID = PK
    provider: str(50)          # openai | anthropic | replicate | azure
    api_key_encrypted: str(500) # AES加密后的密钥
    endpoint: str(300) | None  # 自定义endpoint
    is_active: bool = True
    owner_id: FK → user.id
    created_at: datetime
```

---

## 6. API 接口契约

### 6.1 模型管理层 API（新增核心接口）

```
GET    /api/v1/models                          # 列出所有可用模型（本地+远程）
GET    /api/v1/models/{name}                   # 模型详情
POST   /api/v1/models/download                 # 触发模型下载（异步）
GET    /api/v1/models/download/{task_id}       # 查询下载进度
DELETE /api/v1/models/{name}                   # 删除本地模型
POST   /api/v1/models/{name}/load              # 加载模型到内存
POST   /api/v1/models/{name}/unload            # 卸载模型

GET    /api/v1/models/providers                 # 列出支持的第三方API提供商
POST   /api/v1/models/providers                # 配置/更新第三方API密钥

GET    /api/v1/models/usage-stats              # 模型使用统计
POST   /api/v1/models/optimize                 # 触发自动优化
```

### 6.2 Studio API（实现现有stub）

```
# 项目管理
GET    /api/v1/studio/projects                 # 项目列表（分页+筛选）
POST   /api/v1/studio/projects                 # 创建项目
GET    /api/v1/studio/projects/{id}            # 项目详情
PUT    /api/v1/studio/projects/{id}            # 更新项目
DELETE /api/v1/studio/projects/{id}            # 删除项目
POST   /api/v1/studio/projects/{id}/build      # 构建项目
POST   /api/v1/studio/projects/{id}/deploy     # 部署项目
POST   /api/v1/studio/projects/generate        # AI生成项目（文本→全栈代码）

# 模板管理
GET    /api/v1/studio/templates                # 模板列表
GET    /api/v1/studio/templates/{id}           # 模板详情
POST   /api/v1/studio/templates/{id}/use       # 使用模板创建项目

# AI对话
POST   /api/v1/studio/chat                     # 发送消息（支持SSE流式）
GET    /api/v1/studio/chat/{session_id}/messages  # 历史消息
POST   /api/v1/studio/chat/stream               # WebSocket流式对话

# 会话管理
GET    /api/v1/studio/sessions                 # 会话列表
POST   /api/v1/studio/sessions                 # 创建会话
DELETE /api/v1/studio/sessions/{id}            # 删除会话
PUT    /api/v1/studio/sessions/{id}            # 重命名会话
```

### 6.3 Video API（实现现有stub）

```
# 管理端
GET    /api/v1/videos                          # 视频列表
POST   /api/v1/videos                          # 上传/创建视频记录
GET    /api/v1/videos/{id}                     # 视频详情
PUT    /api/v1/videos/{id}                     # 更新视频信息
DELETE /api/v1/videos/{id}                     # 删除视频

# 数据分析
GET    /api/v1/videos/analytics/overview       # 整体数据概览
GET    /api/v1/videos/analytics/{id}           # 单个视频分析

# 内容审核
GET    /api/v1/videos/moderation/queue         # 审核队列
POST   /api/v1/videos/moderation/{id}/approve  # 批准
POST   /api/v1/videos/moderation/{id}/reject   # 驳回

# C端
GET    /api/v1/videos/browse                   # 浏览（公开视频分页）
GET    /api/v1/videos/search                   # 搜索
GET    /api/v1/videos/{id}/play                # 播放信息
GET    /api/v1/videos/{id}/subtitles           # 字幕

# 生成
POST   /api/v1/videos/generate                 # 发起生成任务
GET    /api/v1/videos/generate/{task_id}       # 查询任务状态
WS     /api/v1/videos/generate/{task_id}/ws    # WebSocket实时进度
```

---

## 7. 模型管理层架构

### 7.1 整体设计

```
┌─────────────────────────────────────────────────────────┐
│                    ModelRouter（调度入口）                  │
│                                                         │
│  generate(request: ModelRequest) → ModelResponse         │
│     │                                                   │
│     ├── 1. 查询 registry 获取候选模型                       │
│     ├── 2. Filter: 按 capability + availability 过滤       │
│     ├── 3. Rank: 按 priority分数 + usage_stats 排序         │
│     ├── 4. Try: 依次尝试，失败自动回退                       │
│     └── 5. Record: 记录 usage_stats 供 optimizer 使用       │
│                                                         │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
    ┌──────┴──────┐ ┌─────┴─────┐ ┌─────┴──────────┐
    │ LocalModel  │ │ APIGateway│ │ FallbackModel  │
    │ (ai_models) │ │           │ │ (内置基础模型)   │
    └─────────────┘ └───────────┘ └────────────────┘
```

### 7.2 ModelRequest / ModelResponse 契约

```python
@dataclass
class ModelRequest:
    """统一的模型请求结构"""
    capability: ModelType          # 所需能力类型
    prompt: str
    system_prompt: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    extra_params: dict = {}        # 模型特定参数
    preferred_model: str | None = None  # 用户指定模型（可选）
    stream: bool = False

@dataclass
class ModelResponse:
    """统一的模型响应结构"""
    content: str                   # 生成内容
    model_used: str                # 实际使用的模型名
    provider: str                  # local | openai | anthropic | replicate
    tokens_used: int | None
    latency_ms: int
    finish_reason: str             # stop | length | error
    is_fallback: bool = False     # 是否经过回退
```

### 7.3 回退链逻辑

```
优先级（从高到低）：
  1. 用户指定模型（preferred_model）
  2. 本地最优模型（按 registry priority + optimizer_score 排序）
  3. 本地次优模型（降级尝试）
  4. 第三方API（OpenAI → Claude → 其他）
  5. 内置轻量模型（tiny-llama 等，确保永远有兜底）

Failover 逻辑（伪代码）：
  for candidate in ranked_candidates:
      try:
          response = candidate.generate(request)
          record_success(candidate, response)
          return response
      except ModelUnavailableError:
          continue
      except Exception as e:
          record_failure(candidate, e)
          continue
  # 全部失败
  raise AllModelsExhaustedError()
```

### 7.4 第三方API网关

```python
class ApiGateway:
    """统一的第三方API调用接口"""

    # 支持的提供商
    providers = {
        "openai":    OpenAiProvider,
        "anthropic": AnthropicProvider,
        "azure":     AzureOpenAiProvider,
        "replicate": ReplicateProvider,
        # 可扩展...
    }

    def generate(self, request: ModelRequest, provider: str) -> ModelResponse:
        """调用特定提供商的API"""
        cred = self._get_credential(provider)
        provider_instance = self.providers[provider](cred)
        return provider_instance.generate(request)

    def list_available(self) -> list[str]:
        """列出已配置且可用的提供商"""

    def verify_credential(self, provider: str) -> bool:
        """验证API密钥有效性"""
```

### 7.5 模型下载管理器

```python
class ModelDownloadManager:
    """模型下载生命周期管理"""

    sources = {
        "huggingface": HFDwonloadSource,
        "modelscope":  ModelScopeSource,  # HuggingFace不可用时的替代
        "local":       LocalCopySource,
    }

    def start_download(
        self, model_id: str, source: str = "huggingface"
    ) -> str:
        """启动异步下载，返回 task_id"""

    def get_progress(self, task_id: str) -> DownloadProgress:
        """查询下载进度（0-100%, speed, ETA）"""

    def cancel_download(self, task_id: str):
        """取消下载"""

    def verify_integrity(self, model_path: str) -> bool:
        """校验模型文件完整性（SHA256）"""
```

---

## 8. 多模型动态调度

### 8.1 调度算法

```
每个模型维护一个动态评分 DynamicScore：
  DynamicScore = base_priority × availability_factor × performance_factor

其中：
  - base_priority: registry 中配置的静态优先级（0-100）
  - availability_factor: 0=不可用, 0.5=降级模式, 1=完全可用
  - performance_factor: 基于最近N次调用的成功率 × 速度因子

调度流程：
  1. 获取所有 capability 匹配的候选模型
  2. 计算每个候选的 DynamicScore
  3. 按 DynamicScore 降序排列
  4. 依次尝试（fail-fast, timeout=30s）
  5. 记录每次调用的 usage_stats
```

### 8.2 自动优化引擎

```python
class AutoOptimizer:
    """基于使用数据自动调整模型优先级"""

    def analyze(self, days: int = 7):
        """分析最近N天的使用数据"""
        # 1. 统计每个模型的成功率
        # 2. 计算平均延迟
        # 3. 检测异常模式（频繁报错、延迟飙升）

    def recommend(self) -> list[OptimizationAction]:
        """生成优化建议"""
        # - 降级：成功率低于阈值 → 降低 priority
        # - 升级：新模型表现优异 → 提升 priority
        # - 移除：持续失败 → 标记不可用
        # - 预加载：高峰时段 → 提前加载热门模型

    def apply(self, actions: list[OptimizationAction]):
        """应用优化动作到 registry"""

    def get_optimal_model(self, capability: ModelType) -> str:
        """根据历史数据推荐最优模型"""
```

### 8.3 本地/远程无缝切换

```python
class UnifiedModelInterface:
    """统一模型接口 — 对调用方透明"""

    def __init__(self):
        self.router = ModelRouter()
        self.fallback = FallbackChain()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        # 尝试本地模型
        try:
            local_model = self.router.select_local(request.capability)
            if local_model and local_model.is_available:
                return await local_model.generate(request)
        except ModelNotAvailableError:
            pass

        # 回退到第三方API
        try:
            api_response = await self.api_gateway.generate(request)
            return api_response
        except ApiNotConfiguredError:
            pass

        # 最后回退到内置基础模型
        return await self.fallback_base_model.generate(request)
```

---

## 9. 实现路线图

### Phase 1：核心基础设施（当前阶段）

```
[ ] 1.1 创建数据模型文件
    backend/app/models/studio_models.py   — Studio域模型
    backend/app/models/video_models.py    — Video域模型
    backend/app/models/system_models.py   — 系统模型
    backend/app/models/__init__.py        — 更新导出

[ ] 1.2 模型调度核心
    backend/app/core/model_router.py      — ModelRouter + UnifiedModelInterface
    backend/app/core/api_gateway.py       — ApiGateway + 多Provider适配
    backend/app/core/fallback_chain.py    — FallbackChain 回退逻辑
    backend/app/core/model_downloader.py  — 下载管理器

[ ] 1.3 ai_models 扩展
    ai_models/scheduler.py                — 动态评分 + 候选排序
    ai_models/api_proxy.py               — 第三方API统一代理
    ai_models/downloader.py              — 模型下载实现
    ai_models/optimizer.py               — 自动优化引擎
    ai_models/registry.py                — 扩展注册中心（支持远程模型）

[ ] 1.4 数据库迁移
    alembic 创建迁移文件，包含所有新表
```

### Phase 2：API 路由实现

```
[ ] 2.1 Studio 路由实现
    backend/app/api/routes/studio/admin/projects.py   — 完整CRUD + build/deploy
    backend/app/api/routes/studio/admin/templates.py  — 完整CRUD + use
    backend/app/api/routes/studio/client/chat.py      — SSE流式 + 历史
    backend/app/api/routes/studio/client/sessions.py  — 会话CRUD
    backend/app/api/routes/studio/client/models.py    — 模型列表/下载

[ ] 2.2 Video 路由实现
    backend/app/api/routes/video/admin/videos.py      — 完整CRUD
    backend/app/api/routes/video/admin/analytics.py   — 数据分析
    backend/app/api/routes/video/admin/moderation.py  — 审核流程
    backend/app/api/routes/video/client/browse.py     — 浏览/搜索
    backend/app/api/routes/video/client/generate.py   — 生成任务
    backend/app/api/routes/video/client/play.py       — 播放/字幕

[ ] 2.3 系统路由
    backend/app/api/routes/system/models.py           — 模型管理API
    backend/app/api/routes/system/__init__.py
```

### Phase 3：前端实现

```
[ ] 3.1 Studio 前端
    studio-admin/pages/
      ProjectList.vue 增强      — 状态筛选、批量操作
      ProjectDetail.vue 增强    — 代码预览、构建日志
      ModelManager.vue 新增     — 模型列表/下载/切换
    studio-client/pages/
      ChatWorkspace.vue 新增    — AI编程聊天界面
      ModelSelector.vue 新增    — 模型选择器
      CodePreview.vue  新增     — 生成代码预览

[ ] 3.2 Video 前端
    video-admin/pages/
      VideoManager.vue 新增     — 视频管理列表
      Analytics.vue    新增     — 数据看板
      Moderation.vue   新增     — 审核队列
    video-client/pages/
      VideoGenerate.vue 新增    — 视频生成界面
      VideoPlayer.vue  新增     — 视频播放器
      VideoBrowse.vue  新增     — 视频浏览页
```

---

## 10. 代码规范

### 10.1 Python 后端规范

```python
# 导入顺序：标准库 → 第三方 → 项目内部
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import SessionDep, CurrentUser
from app.models.studio_models import StudioProject

# 类型注解：所有函数必须标注参数和返回值类型
def get_project(project_id: str, session: SessionDep, user: CurrentUser) -> StudioProject:
    ...

# 错误处理：使用 HTTPException，不要在路由里裸 raise
from fastapi import HTTPException, status

if not project:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

# 分页：统一格式
# 请求: ?page=1&size=20
# 响应: {"data": [...], "total": 100, "page": 1, "size": 20}
```

### 10.2 Vue 前端规范

```vue
<script setup lang="ts">
// 使用 <script setup> 语法
// 类型导入用 import type
import type { Project } from '@/types/studio'
import { ref, computed } from 'vue'
</script>

<template>
  <!-- 用 TailwindCSS 4 类名，不写内联style -->
</template>
```

### 10.3 通用原则

1. **单一职责**：每个文件/类只做一件事
2. **接口先行**：先定义接口契约，再实现
3. **错误可追溯**：所有异常包含足够上下文信息
4. **无魔法数字**：配置项统一在 config.py 或 .env
5. **可测试性**：核心逻辑不依赖全局状态，可注入依赖

---

## 11. 闭环系统架构

> **状态**：四大闭环系统已于 2026-06-29 完成实现，59 项端到端测试全部通过。

### 11.1 闭环总览

```
                         ┌──────────────────────────────────────┐
                         │        Agent 层 (决策中心)            │
                         │  AgentOrchestrator (Planner→Coder→    │
                         │  Reviewer→Memory) + PrioritizedToolSet│
                         │  + AgentModes (6 modes)               │
                         └──────┬──────────────────────┬────────┘
                                │                      │
                   ┌────────────▼──────────┐  ┌────────▼──────────┐
                   │   Skills 层            │  │   Memory 层        │
                   │   (能力注入)            │  │   (上下文提供)      │
                   │   SkillManager          │  │   CodebaseMemory  │
                   │   SKILL.md × 8          │  │   LongTermMemory  │
                   │   6 modes ├ skills      │  │   MemoryExtractor │
                   └────────────────────────┘  │   MemoryRetriever │
                                               └───────────────────┘
                                │                      │
                   ┌────────────▼──────────────────────▼─────────┐
                   │         Tool 层 (执行能力)                    │
                   │  AutoCLI (5-level security) / FileOps /      │
                   │  ModelRouter / ToolRegistry                  │
                   └──────────────────────────────────────────────┘
```

### 11.2 闭环 1：CodebaseMemory（代码库知识图谱）

**定位**：自研 Python 代码解析 + 知识图谱系统，无需外部 MCP Server。

```
backend/app/core/codebase_memory/
  graph.py         — CodeGraph + Node/Edge 数据模型 + SQLite 持久化
  parser.py        — PythonParser (AST) + GenericParser (regex) + TreeSitterParser (三层回退)
  indexer.py       — FileIndexer (文件扫描 + 增量哈希索引 + SQLite 持久化)
  tools.py         — 8 个查询工具 (search_graph/search_code/get_code_snippet/...)
  __init__.py      — init_codebase_memory() 全局入口
```

**数据模型**：
- 13 种节点类型: File/Folder/Module/Class/Function/Method/Variable/Import/Route/Decorator/Type/Enum/Field
- 10 种边类型: CONTAINS/DEFINES/CALLS/IMPORTS/INHERITS/DECORATES/USAGE/HTTP_CALLS/TESTS/DATA_FLOWS

**关键设计**：
- 三层解析回退：tree-sitter AST → regex → skip
- SQLite WAL 模式持久化，支持增量更新（文件哈希对比）
- JSON 文件作为后备加载
- 已合并原 CKG 系统（`backend/app/core/ckg/` 已删除）

### 11.3 闭环 2：LongTermMemory（长期记忆）

**定位**：双层记忆架构 — 图记忆 + 向量记忆，自主实现零外部依赖。

```
backend/app/core/memory/
  memory_store.py      — MemoryNode/Edge 数据模型 + SQLite 持久化 + 重要性衰减
  memory_extractor.py  — 从对话/代码变更/反思提取结构化记忆
  memory_retriever.py  — 关键词 + 图遍历综合检索 + Agent 上下文注入
  store.py             — 原有向量记忆 (语义搜索)
  embedding.py         — 多 Provider embedding 生成
```

**关键设计**：
- 衰减公式: `decay = importance × 1/(1 + hours_since_access) + log(1 + access_count) × 0.1`
- 6 种记忆类型: code/conversation/decision/lesson/fact/pattern/preference
- 8 种关系类型: RELATES_TO/DEPENDS_ON/BEFORE/AFTER/CAUSED_BY/...
- 自动遗忘: `forget(threshold)` 清除低分段记忆

### 11.4 闭环 3：Agent 协同（多 Agent 流水线）

**定位**：借鉴 Agent-Reach 的 Planner→Coder→Reviewer→Tester 流水线。

```
backend/app/core/agent/
  orchestrator.py    — AgentOrchestrator (Planner→Coder→Reviewer→Memory 全链路)
  tool_priority.py   — PrioritizedToolSet (HIGH/MEDIUM/LOW 三级) + 前置推荐
  agent_runner.py    — AgentRunner (多轮工具调用循环) [已有]
  agent_modes.py     — 6 modes × skills 绑定 [已增强]
  tool_executor.py   — ToolExecutor [已有]
  handoff.py         — SubAgent 委派 [已有]
  reflection.py      — Agent 自省 [已有]
```

**Agent Mode → Skill 绑定**：
| Mode | Skills |
|------|--------|
| architect | code-review, explain |
| code | frontend-design, refactor |
| debug | debug, explain |
| test | test-gen, webapp-testing |
| review | code-review |
| docs | explain |

### 11.5 闭环 4：AutoCLI（安全命令行）

**定位**：5 级安全策略梯度 + 命令白名单 + Shell 注入检测。

```
backend/app/core/tools/autocli.py
  SecurityLevel: READ_ONLY(0) → FILE_CREATE(1) → FILE_MODIFY(2) → SYSTEM(3) → UNSAFE(4)
  55 个命令白名单 + Git 子命令分级
  Shell 注入检测 (危险字符正则)
  输出截断 (max_output_chars=8000)
```

### 11.6 闭环联动流程

```
用户请求 → AgentOrchestrator
  1. SkillsManager 加载对应技能 (build_skills_prompt)
  2. PrioritizedToolSet 排序工具 (HIGH→MEDIUM→LOW)
  3. CodebaseMemory 提供代码结构上下文 (search_graph/trace_path)
  4. MemoryRetriever 注入历史记忆 (retrieve_as_context)
  5. ModelRouter 调度模型执行 (回退链)
  6. AutoCLI 安全执行命令 (白名单+注入检测)
  7. MemoryExtractor 保存决策/教训 (extract_and_save)
```

### 11.7 测试验证

```bash
cd /path/to/ai-fullstack-platform
PYTHONPATH="$PWD/backend:$PYTHONPATH" python3 tests/test_closed_loop.py
# 预期: 59/59 通过
```

---

## 附录：关键技术决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| Python LLM Runtime | llama-cpp-python | 已有集成，MIT协议，无需额外服务 |
| 视频生成引擎 | diffusers (CogVideoX) | 已有框架，HuggingFace生态 |
| API密钥存储 | AES-256加密 + DB | 安全存储，不硬编码 |
| 流式响应 | SSE (Server-Sent Events) | 相比WebSocket更轻量，浏览器原生支持 |
| 任务队列 | 复用 workers/ 目录 | 已有基础，视频生成需要异步 |
| 模型下载源 | HuggingFace + ModelScope 双源 | 国内可用性保障 |
| 代码解析 | Python ast + tree-sitter 三层回退 | 零外部依赖，自研可控 |
| 长期记忆 | SQLite 图存储 | 无需向量数据库，闭环自主 |
| CLI 安全 | 5 级白名单 + 注入检测 | 借鉴 AutoCLI 策略梯度设计 |

---

> **文档版本**: v2.0
> **最后更新**: 2026-06-29
> **维护者**: AI Fullstack Platform Team
