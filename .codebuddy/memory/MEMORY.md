# AI Fullstack Platform — 长期记忆

## 项目偏好
- 所有代码使用中文注释和文档
- 遵循闭环系统开发规范（不可破坏四层联动）
- Python 后端使用 FastAPI + SQLite 原生持久化，零外部向量数据库
- 代码风格：类型标注 + 全局单例 + 回退链设计

## 关键里程碑
- 2026-06-29: 四大闭环系统自主实现（CodebaseMemory/LongTermMemory/Agent/AutoCLI），59 项测试通过
- Session 05-20 (6月): 视频系统前后端、Agent封闭环增强、客户端UX全量增强、代码质量加固
- Session 21-54 (7月): VSCode/hermes 全量对标迁移 — 编辑/终端/Git/调试/搜索/主题/Settings/LSP/格式化/Notebook 等全部面板和功能，累计 200+ 文件，零 lint 错误
- Session 55 (2026-07-06): RAG/Embedding CPU 性能优化 — embed_batch 批量编码 + MiniLM 小模型替代 + ONNX CPU 加速

## 重要技术经验
- **Tauri WebView2 不支持 `color-mix()` / Tailwind JIT 渐变** → 用 CSS 变量 + rgba + inline style 替代
- **Pinia setup store 中 `subStore.ref` 是 unwrap 快照**，需 `storeToRefs()` 保持反应性
- **Monaco 0.50+** `onCursorPositionChanged` → `onDidChangeCursorPosition`; ESM 需 `mod.default ?? mod`
- **FileTree 引导线公式**: `left=(depth-1)*step+(paddingBase+step/2)`, 缩进 `depth*step+paddingBase`
- **IDE 关键样式** 优先原生 CSS 变量 + rgba + inline style，不依赖编译产物
- **本地开发后端** POSTGRES_SERVER=localhost, REDIS=localhost:6379, QDRANT=localhost, 端口 18000
- **CodeBuddy 自定义模型**: deepseek-v4-flash 和 deepseek-v4-pro 是有效 ID
- **llama-cpp (A5000 24G)**: n_gpu_layers -1, n_ctx 32768, cache_type q8_0, 端口 3081

## Docker 服务配置
- **vLLM**: `webhie/Qwen3.6-27B-int4-AutoRound-Code` (代码场景校准, OpenCodeInstruct 数据集, auto-round-best 量化), GPU 推理, dtype=auto, quantization=auto_round, max-model-len 24576, gpu-memory-utilization 0.85, max-num-seqs 4, **enforce-eager** (禁用 CUDA Graph, Ampere sm_86 兼容), **无 fp8 kv-cache** (需 sm_89+, A5000 不支持), **无 flashinfer** (需 sm_90+), 端口 3080。vLLM v0.24.0 使用 CUDA 13.2，Docker Desktop WSL2 GPU 直通下 RTX A5000 driver 596.72 兼容。模型路径: `/mnt/d/app/LLM/models/huggingface/hub/models--webhie--Qwen3.6-27B-int4-AutoRound-Code:/models/vllm:ro`
- **llama-cpp**: `Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-Q4_K_P.gguf` (16.3GB), n_gpu_layers -1, n_ctx 32768, n_batch 512, cache_type q8_0, chat_format chatml, verbose false, 端口 3081。模型位于 `gguf/qwen3.6-27b/` 子目录，卷挂载 `${MODELS_DIR:-../models}/gguf:/models:ro`，容器路径 `/models/qwen3.6-27b/Qwen3.6-27B-...gguf`
- **Ollama**: 本地 CPU/GPU 推理, qwen3:32b 等模型
- **模型目录链接** (2026-07-19): `.env` 已移除 `MODELS_DIR`/`HF_HOME`/`HF_HUB_CACHE` 硬编码路径，改为 `models/` 下目录链接 → `D:/app/LLM/models/`（gguf/huggingface/ollama 三个 Junction）。Linux 原生启动时需手动创建 symlink: `ln -s /mnt/d/app/LLM/models/gguf models/gguf` 等

## 顶部菜单结构 (Session 40+)
`文件 / 编辑 / 选择 / 查看 / 转到 / 运行 / 终端 / Studio / 帮助`

## 架构约定
- `backend/app/core/` 为核心基础设施，不可引入外部依赖闭环
- API 前缀 `/api/v1/`，分页格式 `{data, total, page, size}`
- Agent 流水线顺序不可变: Planner → Coder → Reviewer → Memory
- 模型回退链: 本地最优 → 本地次优 → 第三方 API → 内置基础
- UI 颜色通过 CSS 变量引用 `var(--color-ide-*)`，禁止硬编码
- 主题切换流程: applyHtmlClass() → 清除旧类 → 添加新主题 → no-transitions 防闪烁

## Docker Compose 生产部署 (2026-07-19)
- **统一文件**：`deploy/compose.shared.yml` 为全栈服务定义，`compose.yml` 仅引用外部网络 `ai-platform-net`
- **模型卷默认路径**：已清理硬编码路径，`.env` 不设 `MODELS_DIR`，compose fallback `${MODELS_DIR:-../models}` 通过目录链接自动解析，Windows/Linux 双平台统一
- **启动命令**：`COMPOSE_FILE=deploy/compose.shared.yml docker compose -f deploy/compose.shared.yml up -d`（排除 `compose.override.yml` 避免 DNS/db 冲突）
- **prestart 修复**：需添加 `PROJECT_NAME=${PROJECT_NAME:-AI Fullstack Platform}` 环境变量（config.py 必填字段）
- **卷挂载**：backend 不可挂载 `${MODELS_DIR}/huggingface:/data/models:ro`（Windows 路径 `D:/` 冒号冲突），后端通过 API 网关访问模型
- **监控服务**：prometheus/grafana 需 `user: root`（named/bind volume 写权限），alertmanager 正常无此问题
- **GPU 服务**：ollama/vLLM/open-webui 用 `docker run --runtime=nvidia --gpus all` 直接启动（绕过 compose pull 镜像源不可达问题）
- **已知问题**：Docker daemon 腾讯镜像 `mirror.ccs.tencentyun.com` DNS 不可达，需切换为无镜像配置（`docker-daemon-nomirror.json`），但需重启 Docker Desktop 生效；open-webui 无法从 HuggingFace 拉取 `all-MiniLM-L6-v2`（WSL/Docker 网络不可达）

## 禁止事项
1. 不可重建 `backend/app/core/ckg/` 目录
2. 不可在 Memory 中引入外部向量数据库（Qdrant/Pinecone）
3. 不可绕过 AutoCLI 安全检测直接执行命令
4. 不可删除 Agent Mode 的 skills 绑定
5. 不可在 codebase_memory 中引入非标准库依赖
