# Dify → 主项目 知识库桥接方案

> **定位**：Dify 负责知识库训练（文档上传、分块、标注、质量检查），主项目负责知识检索（FAISS + SQLite FTS5 + BGE MiniLM）。桥接层将 Dify 训练好的文档导入主项目 RAG 系统。

## 架构设计

```
┌───────────── Dify 平台 ─────────────┐
│  文档上传 → 分块 → 标注 → 质量检查   │
│  (text-embedding-ada-002, 1536dim)  │
└──────────────┬──────────────────────┘
               │  文本 + 元数据（非向量直传）
               ▼
┌──── 桥接层 (dify_bridge.py) ────────┐
│  文件解析 → BGE分块 → FAISS嵌入     │
│  (BGE MiniLM all-MiniLM-L6-v2 384)  │
└──────────────┬──────────────────────┘
               │
               ▼
┌──── 主项目 RAG (知识检索) ──────────┐
│  FAISS 向量库 + SQLite FTS5 + 混合检索│
└─────────────────────────────────────┘
```

### 为何不直传向量？

| 系统 | Embedding 模型 | 维度 |
|------|---------------|------|
| Dify | text-embedding-ada-002 | **1536** |
| 主项目 | BGE MiniLM L6-v2 | **384** |

维度不匹配，无法混用。桥接层只传递**文本 + 元数据**，由主项目重做嵌入。

---

## 三种导入方式

| 方式 | 数据源 | 适用场景 | 推荐度 |
|------|--------|----------|--------|
| **文件导入** | `knowledge-data/documents/` 下的原始文档 | Dify 将文档导出到共享目录 | ⭐ 推荐 |
| **Dify API** | Dify REST API 拉取文档 | 需要网络访问 Dify API | 备选 |
| **Weaviate 直连** | 直读 Dify 的 Weaviate 向量库 | 可直连 Dify 数据库 | 高级用户 |

### 1. 文件导入（推荐）

Dify 训练后将文档写入共享目录 `knowledge-data/documents/`，主项目读取后走完整 pipeline：

```
原始文件 → 解析器(parser) → 分块器(chunker) → BGE嵌入 → FAISS + FTS5存储
```

**支持格式**：`.md` `.txt` `.pdf` `.docx` `.html` `.csv` `.json`

```bash
# API 调用示例
curl -X POST http://localhost:8000/api/v1/rag/knowledge-bases/import-from-dify \
  -H "Content-Type: application/json" \
  -d '{
    "kb_name": "技术文档库",
    "kb_description": "从 Dify 导入的技术文档",
    "doc_dir": "/app/knowledge-data/documents/",
    "chunk_size": 512,
    "chunk_overlap": 50
  }'
```

### 2. Dify API 导入

通过 Dify 知识库 REST API 直接拉取文档内容和分块。

### 3. Weaviate 直连

直连 Dify 的 Weaviate 向量库，提取已有分块文本。

---

## 部署配置

### 目录结构与挂载

```bash
# 项目根目录
knowledge-data -> /run/media/reginyuan/Software/app/knowledge-base/  # symlink (2.0T)
├── documents/     # Dify 训练后导出的原始文档
├── embeddings/    # 主项目 embedding 缓存
└── vector-store/  # FAISS 索引存储
```

**Docker Compose 配置**（`deploy/compose.shared.yml`）：

```yaml
backend:
  environment:
    - KNOWLEDGE_DATA_DIR=/app/knowledge-data
  volumes:
    - ../knowledge-data:/app/knowledge-data:ro   # 只读挂载
```

**本地开发配置**（`compose.yml` 根目录）：

```yaml
backend:
  environment:
    - KNOWLEDGE_DATA_DIR=/app/knowledge-data
  volumes:
    - ./knowledge-data:/app/knowledge-data:ro
```

> ⚠️ **路径注意事项**：`deploy/compose.shared.yml` 位于 `deploy/` 子目录，需用 `../knowledge-data` 映射到项目根目录的 symlink。根目录 `compose.yml` 用 `./knowledge-data` 即可。

### 创建 Symlink

```bash
# Linux
ln -s /run/media/reginyuan/Software/app/knowledge-base/ knowledge-data

# Windows (管理员 PowerShell)
mklink /J knowledge-data D:\app\knowledge-base
```

---

## 自动同步方案

### 方案一：Dify 工作流 HTTP 节点（推荐）

将 Dify 容器接入主项目 Docker 网络，通过工作流自动回调：

```bash
# 1. Dify 容器接入同一网络
docker network connect ai-platform-net dify-api

# 2. 在 Dify 工作流中添加 HTTP 节点：
#    POST http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook
#    Body: {"kb_name": "技术文档库", "mode": "replace"}
```

- **优势**：无需密钥、无需额外脚本、同网络容器名直连
- **限制**：Dify 和主项目必须在同一 Docker 网络

### 方案二：独立同步脚本（网络不互通时）

Dify 和主项目网络隔离时，用 `standalone-tools/dify_auto_sync.py` 监听文件变化：

```bash
# 部署在 Dify 服务器上
python standalone-tools/dify_auto_sync.py \
  --watch-dir /path/to/knowledge-data/documents/ \
  --api-url http://<主项目地址>:18000/api/v1/rag/knowledge-bases/dify-webhook \
  --kb-name 技术文档库 \
  --mode replace
```

**特性**：
- `inotify` 模式（Linux，实时文件监听）
- `polling` 模式（跨平台，定时扫描）
- `oneshot` 模式（一次性，适合 cron）
- Debounce 防抖机制，避免频繁触发

**跨网络安全**：设置 `DIFY_WEBHOOK_SECRET` 环境变量启用密钥验证。

---

## API 端点

### `POST /api/v1/rag/knowledge-bases/import-from-dify`

手动触发 Dify 知识库导入。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `kb_name` | string | **必填** | 目标知识库名称 |
| `kb_description` | string | `""` | 知识库描述 |
| `doc_dir` | string | `/app/knowledge-data/documents/` | 文档目录路径 |
| `chunk_size` | int | `512` | 分块大小 |
| `chunk_overlap` | int | `50` | 分块重叠长度 |

**响应**：

```json
{
  "kb_name": "技术文档库",
  "total_documents": 15,
  "total_chunks": 230,
  "total_embedded": 228,
  "errors": [],
  "duration_sec": 45.3
}
```

### `POST /api/v1/rag/knowledge-bases/dify-webhook`

Dify 自动同步回调端点。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `kb_name` | string | **必填** | 目标知识库名称 |
| `kb_description` | string | `""` | 知识库描述 |
| `doc_dir` | string | `/app/knowledge-data/documents/` | 文档目录路径 |
| `chunk_size` | int | `512` | 分块大小 |
| `chunk_overlap` | int | `50` | 分块重叠 |
| `mode` | string | `"replace"` | `replace` 清空重导 / `append` 增量追加 |
| `secret` | string | `""` | 密钥（`DIFY_WEBHOOK_SECRET` 非空时才验证） |

**同步模式**：
- **replace**：删除同名知识库后全量重导
- **append**：保留已有数据，增量追加新文档

---

## 核心代码结构

| 文件 | 作用 |
|------|------|
| `backend/app/core/rag/dify_bridge.py` | 核心桥接模块（~749 行） |
| `backend/app/api/routes/rag/knowledge_bases.py` | API 端点（`import-from-dify`, `dify-webhook`） |
| `backend/app/core/rag/__init__.py` | 导出 Dify 相关类型 |
| `standalone-tools/dify_auto_sync.py` | 自动同步守护脚本（~428 行） |
| `deploy/compose.shared.yml` | 生产部署 knowledge-data 挂载 |
| `compose.yml` | 本地开发 knowledge-data 挂载 |

### DifyKnowledgeBridge 关键类

```python
from app.core.rag.dify_bridge import DifyKnowledgeBridge

bridge = DifyKnowledgeBridge()

# 从文件导入（推荐）
stats = await bridge.import_from_files(
    kb_name="技术文档库",
    kb_description="Dify 训练知识",
    doc_dir="/app/knowledge-data/documents/",
    chunk_size=512,
    chunk_overlap=50,
)

# 从 Weaviate 导入
stats = await bridge.import_from_weaviate(
    kb_name="技术文档库",
    weaviate_url="http://localhost:8080",
    weaviate_class="DifyDocument",
)

# 从 Dify API 导入
stats = await bridge.import_from_api(
    kb_name="技术文档库",
    dify_api_url="http://dify-api:5001",
    dify_api_key="dataset-xxx",
)
```

### ImportStats 数据类

```python
@dataclass
class ImportStats:
    kb_name: str
    total_documents: int = 0
    total_chunks: int = 0
    total_embedded: int = 0
    errors: list = field(default_factory=list)
    duration_sec: float = 0.0
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KNOWLEDGE_DATA_DIR` | `/app/knowledge-data` | 知识库数据目录（容器内路径） |
| `DIFY_WEBHOOK_SECRET` | （空） | Webhook 密钥，为空时跳过验证 |

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 导入报 "No files found" | `knowledge-data/documents/` 为空或无挂载 | 检查 symlink 是否存在、Dify 是否已将文档写入 |
| 导入后检索无结果 | 向量维度不匹配 | 确认走的是文件导入（重嵌入），非向量直传 |
| Webhook 返回 403 | `DIFY_WEBHOOK_SECRET` 不匹配 | 同网络时清空环境变量，跨网络时确保 secret 一致 |
| Docker 容器找不到文件 | volume 路径解析错误 | `deploy/` 下需 `../knowledge-data`，根目录用 `./knowledge-data` |
| `total_embedded` 为 0 | 解析或嵌入失败 | 查看后端日志，检查 `errors` 数组 |
