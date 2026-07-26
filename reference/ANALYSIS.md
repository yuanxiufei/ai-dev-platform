# 开源 RAG 项目技术调研报告

> 日期：2026-07-25 | 对比基准：AI全栈平台现有 RAG 系统

---

## 一、AnythingLLM（41.4k ⭐）— 全栈参考

### 技术栈
```
前端：React (frontend/)     后端：Node.js Express (server/)     向量库：LanceDB/Qdrant/Chroma
模型：多 Provider 插件     文件系统：本地 JSON 持久化
```

### 文档解析管线
| 维度 | AnythingLLM | 本项目 |
|------|------------|--------|
| 解析器注册 | 统一 `DocumentManager` + 插件模式 | 策略模式 `crawler/` |
| PDF 解析 | 依赖第三方 collector 插件 | URLParser 三级回退 + MinerU 离线 |
| 文本清洗 | 内建 `sanitize` + content truncation | 分段去HTML标签 |
| 分块策略 | **LangChain RecursiveCharacterTextSplitter**，可配置 chunkSize(默认1000)/overlap(20) | 基于分隔符的 naive split |
| 🔥 ChunkHeader | **每个 chunk 前拼接文档标题+元数据，保持上下文** | ❌ 未实现 |

**🔥 核心可借鉴设计 — chunkHeader 模式**：
```javascript
// AnythingLLM: 每个 chunk 保留来源上下文
this.chunkHeader = `[Document: ${title}]\n[Source: ${url}]\n[Published: ${date}]\n\n`
// 切分后每个 chunk 都带这个 header，检索时不会丢失上下文
```

### 向量化多 Provider 架构
- 每种 Embedding provider 声明 `maxConcurrentChunks` 和 `maxChunkLength`
- 切分时自动感知 provider 限制做截断
- Provider 切换零代码改动

### Agent 工具调用
- 工具通过 `@agent` skill JSON 声明式注册
- 内建 `rag-memory`、`web-browsing`、`sql-agent` 等内置 agent
- 工具发现走 MCP 协议

### 💡 可落地借鉴清单
1. **chunkHeader 模式**：文档切分时自动注入标题/来源/日期到每个 chunk（低改动，高价值）
2. **Embedder 能力声明**：每种 embedding provider 暴露 `max_chunk_tokens` 属性，切分器按此截断
3. **插件化解析器注册**：统一 `BaseParser` 接口，按 MIME 类型自动路由

---

## 二、RAGFlow（45.9k ⭐）— 文档解析王者

### 核心架构
```
deepdoc/  →  文档解析引擎（20+ 解析器）
rag/nlp/  →  NLP 处理（分词/关键词/TF-IDF/RAPTOR 摘要）
rag/      →  RAG 管线（检索/排序/生成）
api/      →  Flask REST API
```

### 文档解析引擎（deepdoc/parser/）
| 解析器 | 核心技术 | 本项目对应 |
|--------|---------|-----------|
| `pdf_parser.py` | pdfplumber + **xgboost 布局检测** + OCR | MinerU (离线) / URLParser |
| `docx_parser.py` | python-docx + LazyImage(图片懒提取) | MinerU |
| `excel_parser.py` | pandas + openpyxl | MinerU |
| `html_parser.py` | BeautifulSoup | SiteCrawler |
| `mineru_parser.py` | magic-pdf 调用 | ✅ 同款 MinerU |
| `ppt_parser.py` | python-pptx | ❌ |
| `resume_parser.py` | 专为简历优化 | ❌ |

### 🔥 ML 驱动的 PDF 布局分析
```python
# RAGFlow pdf_parser 独特做法：用 xgboost+KMeans 做布局分类
# 不再依赖 rule-based 区域检测，而是训练 ML 模型区分：
# - 标题/正文/表格/图片/页眉页脚
# 输出带语义标签的结构化段落树
```

### RAPTOR 递归摘要
- 对长文档逐层生成摘要，形成"摘要树"
- 检索时优先匹配高层摘要，再深入底层细节
- 本项目无此能力

### 💡 可落地借鉴清单
1. **解析器注册表（ParserRegistry）**：用 `{mime_type: ParserClass}` 字典 + `auto_detect()`，我们目前是硬编码 if-else
2. **图片懒提取（LazyImage）**：解析文档时不立即提取图片，只记 offset，检索命中时再加载（节省内存）
3. **文档结构树**：解析出 `[{title, level, content, children}]` 树结构，检索时保留层级关系
4. **TF-IDF 关键词权重**：对 chunk 做关键词提取并加权检索，弥补纯向量检索的不足（我们有 FTS5，可以结合）

---

## 三、Chroma（向量数据库）— 存储架构参考

### Segment 分离架构
```
Chroma 的核心设计：元数据和向量存储完全分离

Metadata   →  SQLite (元数据/过滤)    │  我们的: SQLite FTS5 存文本
Vector     →  HNSW (向量索引)         │  我们的: FAISS 384dim
Record     →  BlockFile (原始数据)    │  我们的: 无独立存储（从DB回查）
```

### 关键设计模式
1. **Collection 模型**：知识库 = Collection {id, name, metadata, embedding_function}
2. **SegmentManager 工厂**：根据配置自动选择 `HNSW_LOCAL_MEMORY` 或 `HNSW_LOCAL_PERSISTED`
3. **Where 过滤 DSL**：`{ "$and": [{"tag": "AI"}, {"date": {"$gte": "2026-01-01"}}] }` — 元数据过滤语法

### 💡 可落地借鉴清单
1. **Segment 抽象**：将元数据存储和向量存储解耦为可替换的 Segment，将来切换向量引擎（FAISS→HNSW）只换一个 Segment
2. **Where 过滤 DSL**：统一元数据过滤语法，替代当前的散装 filter 参数

---

## 四、LangChain-Chatchat（34.3k ⭐）— 中文知识库标杆

### 架构
```
libs/chatchat-server/ (281 .py)  →  知识库服务端
libs/python-sdk/                 →  Python SDK
```

### LLM 知识库管理
- KBService 工厂：根据 `vs_type` 切换向量库（FAISS/Milvus/ES/PGVector）
- 文档加载器注册表：`LOADER_DICT = {"pdf": ..., "docx": ..., "md": ...}`
- 知识库 → 文件 → 分段 三层数据模型

### 💡 可落地借鉴清单
1. **向量库多后端**：类似 Chroma Segment，但我们的策略是不引入外部向量库（规则约束），此点不适用
2. **知识库问答链**：`kb → search → rerank → prompt_template → llm` 的标准链编排，我们目前也有类似流程但不够标准化

---

## 五、设计模式综合对比

| 设计模式 | AnythingLLM | RAGFlow | Chroma | LangChain | **本项目** | 差距 |
|---------|------------|---------|--------|-----------|-----------|------|
| 解析器注册 | 插件式 | ParserRegistry | - | LoaderDict | 硬编码 if-else | 🔴 可改进 |
| 分块策略 | LangChain RC | Token-aware | - | Multiple | naive split | 🟡 可增强 |
| Chunk 上下文保留 | ✅ ChunkHeader | ❌ | ❌ | ❌ | ❌ | 🔴 高价值 |
| 向量库抽象 | Provider | - | Segment | VectorStore | 直接 FAISS | 🟡 中期考虑 |
| 元数据过滤 | - | ES DSL | Where DSL | - | SQL WHERE | 🟢 基本够用 |
| 图片处理 | - | LazyImage | - | - | 全量加载 | 🟡 可优化 |
| 布局分析 | - | xgboost+KMeans | - | - | MinerU | 🟢 已对齐 |
| RAPTOR/摘要树 | - | ✅ | - | - | ❌ | 🟡 远期 |

---

## 六、推荐实施路线（按优先级）

### Phase 1 — 低改动高价值（本周可做）
1. **chunkHeader 上下文注入**：切分时保留文档标题/URL/日期（参考 AnythingLLM）
2. **ParserRegistry 解析器注册表**：`{mime: Parser}` dict 替代硬编码（参考 RAGFlow/LangChain）

### Phase 2 — 中期增强（1-2 周）
3. **LazyImage 图片懒加载**：文档解析时不提取图片，只记位置，检索命中时按需加载
4. **分段能力声明**：Embedding provider 暴露 `max_tokens_per_chunk`，切分器自适应
5. **Where 过滤 DSL**：统一元数据查询格式

### Phase 3 — 远期规划
6. **ML 布局分析**：探索 xgboost 辅助 PDF 布局（已有 MinerU 可暂不动）
7. **RAPTOR 摘要树**：长文档递归摘要 + 层级检索
8. **Segment 抽象**：解耦向量存储到可替换后端

---

## 附录：克隆的仓库
| 仓库 | 路径 | 用途 |
|------|------|------|
| anything-llm | `reference/anything-llm/` | 全栈架构、ChunkHeader、Agent 插件 |
| ragflow | `reference/ragflow/` | 深度文档解析、RAPTOR、解析器注册 |
| chroma | `reference/chroma/` | 向量库 Segment 架构 |
| Langchain-Chatchat | `reference/Langchain-Chatchat/` | 中文知识库标准流程 |
| dify | `reference/dify/` | Agent 工作流（已有桥接） |
