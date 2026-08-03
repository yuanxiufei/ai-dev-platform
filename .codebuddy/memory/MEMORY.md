# AI Fullstack Platform — 长期记忆

## 项目约定
- 中文注释 | 闭环四层不可破 | FastAPI + SQLite 零外部向量库 | 类型标注 + 单例 + 回退链

## 本地开发
- 后端: port `18000` (uvicorn, backend目录)
- 前端: studio-client `5173`, studio-admin `5175`, 均代理到 `localhost:18000`
- 基础服务: Docker 本地运行 PostgreSQL 16/Redis 7/Qdrant/Ollama，容器名 postgres/redis/qdrant/ollama
- 数据库: PostgreSQL (`localhost:5432`, admin/admin123/studio) 为默认目标。本地开发若 Docker PG 不稳定可切回 SQLite (`DATABASE_URL=sqlite:///./test_platform.db`，注释掉 POSTGRES_* 变量)。所有 PG DSN 必须追加 `?sslmode=disable`
- **NTFS 挂载**: 项目代码位于 NTFS 分区（fuseblk 挂载），`chmod +x` 不生效。需将 esbuild 等二进制复制到 Linux ext4 分区（`~/.workbuddy/binaries/`）+ 设置 `ESBUILD_BINARY_PATH` 环境变量。vite 通过 `node <pnpm-store>/vite@6.4.3.../node_modules/vite/bin/vite.js` 启动
- **Node 版本**: 需要 >=20.19.0 或 >=22.12.0（vite 6.4.3 要求），当前用 22.12.0 (路径: `~/.workbuddy/binaries/node/versions/22.12.0/bin/node`)。esbuild 二进制从 `node/versions/<v>/lib/node_modules/esbuild/` 复制到 `~/.workbuddy/binaries/esbuild`
- 登录: admin/admin, `type="text"` 非 email
- `/chat` 走 IDE Shell overlay 模式, `/group-chat` 独立全屏

## 架构
- API `/api/v1/`, 分页 `{data,total,page,size}`
- Agent: Planner→Coder→Reviewer→Memory(不可变)
- 模型回退: 本地最优→次优→第三方→内置
- UI: CSS变量 `var(--color-ide-*)` 禁硬编码

## GPU/Docker
- vLLM(3080)/llama-cpp(3081)/Ollama GPU独占 (A5000 23GB), 用哪个启哪个
- 模型路径: `models/{gguf,huggingface,ollama}` symlink → 外部目录
- MODELS_DIR=models 永不改, 换OS只建符号链接
- **Docker 服务统一对接 (2026-07-25)**: 
  - `providers/vllm.py` (VLLMProvider, 端口 3080, 复用 OpenAI 兼容 API)
  - `providers/llama_cpp.py` 端口修复 18082→3081
  - `config.py` 新增 `VLLM_BASE_URL` / `LLAMA_CPP_BASE_URL`
  - `providers/__init__.py` ProviderRegistry 注册 vllm/llama_cpp (no_auth_required)
  - `ai_models/registry.py` 注册 2×vLLM + 2×llama.cpp 远程模型配置
  - `model_health.py` 新增 `_ping_vllm()` / `_ping_llama_cpp()` (GET /health 回退 /v1/models)
  - `model_downloader.py` 新增 `_execute_ollama_pull()` (POST /api/pull 流式 NDJSON) + 6 个 Ollama 模型配置
  - 全链路验证: 10 个 Provider 自动发现, 28 个 ModelRouter Adapter
  - **vLLM/llama.cpp 自动发现(2026-07-25)**: 新增 sync_models_sync() / sync_models(), 启动时通过 GET /v1/models 自动拉取模型列表, API refresh-provider 通用支持 ollama/vllm/llama_cpp
- **前端模型管理(2026-07-25)**: `/models` 页面 (ModelManager.vue), 前端API层 `modelManagerApi` 覆盖下载/删除/加载/卸载/进度轮询, 4 下载源 (HF-mirror/ModelScope/Ollama/HF直连), 10 预定义模型

## RAG
- BGE MiniLM(384dim) + FAISS + PostgreSQL tsvector
- Dify桥接(1536dim独立) 文本+元数据重嵌入
- 多策略爬取(`crawler/`), OCR双引擎(SmolDocling/MinerU)
- 本地开发: `pip install sentence-transformers faiss-cpu psycopg[binary] aiohttp aiosqlite` (否则 RAG API 500 + PostgreSQL 连接失败 + 站点爬取 500 + KBStore 初始化失败)
- **psycopg 统一 (2026-07-26)**: 移除 psycopg2-binary 冗余依赖，vector_store.py / metadata_segment.py 全部迁移到 psycopg v3 (`autocommit=False` 显式设置，原 v2 默认值)
- **重要**: 当前本地开发使用 SQLite (`backend/.env` 中 `DATABASE_URL=sqlite:///./test_platform.db`)。`SQLModel.create_all` 不会给已存在表加新列，模型新增字段需手动 `ALTER TABLE` 补齐。添加字段后可能需要重启后端才能生效
- **注意**: `knowledge-data/` 必须是目录，若 git clone 后变成空文件需手动删除重建目录，否则 `os.makedirs` 报 OSError 导致 RAG 全模块 500
- **P2 Chunk CRUD + Job 队列(2026-07-25)**:
  - models.py: KBJob(`kb_jobs`) job_id/uuid4, status(pending→running→completed|failed), progress 0~1
  - vector_store.py: DocumentStore.list_chunks_paginated/delete_chunk
  - kb_manager.py: list_chunks/delete_chunks/create_job/run_job/get_job/list_jobs
  - API: GET/DELETE /{kb_id}/chunks, POST/GET /{kb_id}/jobs
  - 前端 KnowledgeBaseDetail.vue: 文档行点击展开 chunk 面板（分页、勾选批量删除）
  - run_job 同步 blocking，需调用方放后台线程；FAISS 不支持单删除，仅从 ID 映射移除
- **双管理器统一(2026-07-25)**: HybridStorage → SegmentManager 完成。SegmentManager 补齐 list_chunks/delete_chunk/ghost_stats/compact/remove_by_doc_id/get_all_ids；VectorSegment 新增 ghost_stats/rebuild_index；MetadataSegment 新增 list_chunks_paginated；retrieval_manager/kb_manager/dify_bridge 全部迁移；HybridStorage 保留在 vector_store.py (不再使用)
- **RAG 修复(2026-07-25)**: ① MetadataSegment.list_chunks_paginated LIKE子串→json_extract精确匹配；② retrieval_manager._bm25_fallback storage.metadata.→storage. 绕过抽象层修复；③ vector_store.py $.doc_id→$._doc_id 命名一致；④ SegmentManager 补齐 get_all_ids() 委托；⑤ _bm25_fallback 修复 doc_id/文本错位 + BM25 结果 metadata 注入 _doc_id 使后过滤生效

## 前端 (studio-client)
- **前端功能迁移进度 (2026-08-02)**: P1-P7 全部完成
  - P1 Agent: AgentTraces, AgentReflection
  - P2 DevTools: WorktreeManager, SessionSummary, CodeKnowledgeGraph, BackupManager, FeatureFlags
  - P3 Advanced: BenchmarksPage, ModelCatalog, CLIPipeline, ConfigResolver, StateManager, RemoteSessions, CLIHistoryPage, MemoryGraph, ProblemMatchers
  - P4-P5: 中间批次 30+ API 模块 + 大量页面/路由
  - P6: 8 API 模块 (tasks/memory/webhooks/analytics/templates/diff/codeActions/agentTools) + 2 页面
  - P7: 填充 3 空 API (agentModes/gpuMonitor/modelArena) + 侧边栏 20 入口补齐
  - **当前**: 77 API 模块, 55 侧边栏入口, 所有路由已注册
  - **下一步 P8**: 类型校验/lint 修复, 或高级交互页面 (ImageGen/Voice/Benchmarks/CLIPipeline)

## 规则
- 镜像只构建一次, 环境差异走 env/symlink/volume
- 不可引入外部向量库 | 不可绕过AutoCLI | codebase_memory零非标准库依赖
