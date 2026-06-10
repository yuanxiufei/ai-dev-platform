# AI Models — 统一模型管理层

按**能力类型**（而非格式/平台）组织 AI 模型，支持 safetensors 和 GGUF 两种格式自动适配。

## 设计理念

```
┌─────────────────────────────────────────────────┐
│  Worker / API 层                                │
│  只需 import get_coder_model()                   │
│  不用关心底层是 Qwen / Gemma / GPT                │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  registry.py — 中心注册                          │
│  按 ModelType 分类，priority 自动选最优            │
└──────┬──────────┬──────────┬────────────────────┘
       │          │          │
  ┌────▼────┐ ┌──▼───┐ ┌───▼──────┐
  │VLModel  │ │Coder │ │VideoModel│
  │截图→布局 │ │代码生成│ │视频生成  │
  └─────────┘ └──────┘ └──────────┘
       │          │          │
       └──────────┴──────────┘
                  │
       ┌──────────▼──────────┐
       │  自动适配格式          │
       │  safetensors / GGUF  │
       └─────────────────────┘
```

- **按能力分类**，不按平台/厂商分类 —— 未来加新模型只需在 `registry.py` 注册一行
- **同类型多模型**通过 `priority` 自动选最优（数字越大越优先）
- **格式透明**：调用方无需知道底层是 safetensors 还是 GGUF

## 目录结构

```
ai_models/
├── README.md           # 本文档
├── __init__.py         # 包入口，导出公共 API
├── base.py             # 基类 + 共享类型（ModelType, ModelFormat, ModelConfig）
├── registry.py         # 模型注册中心
├── coder_model.py      # 代码生成（自动适配 safetensors/GGUF）
├── vl_model.py         # 视觉理解（截图→布局 JSON）
├── video_model.py      # 视频生成（文本→视频 / UI 演示）
├── prompts/
│   ├── __init__.py
│   ├── code_gen.py     # 代码相关 Prompt 模板
│   └── video_gen.py    # 视频相关 Prompt 模板
└── pyproject.toml
```

## 快速开始

### 1. 下载/放置模型

```bash
# 默认扫描 {项目根}/models/ 目录
mkdir -p models/

# safetensors 格式（从 HuggingFace 下载）
cd models/
git lfs install
git clone https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct

# GGUF 格式（本地量化模型）
# 直接把 .gguf 文件放在 models/gemma-4-31B-it-qat-GGUF/ 下
```

### 2. 配置环境变量

```bash
# 模型根目录（可选，默认 {项目根}/models/）
export MODELS_DIR=/your/path/to/models

# 覆盖单个模型路径
export MODEL_GEMMA_31B_PATH=D:/app/LLM/models/gemma-4-31B-it-qat-GGUF
export MODEL_QWEN25_VL_7B_PATH=/home/models/Qwen2.5-VL-7B-Instruct
```

### 3. 使用模型

```python
# 代码生成 — 自动选最优可用模型
from ai_models.coder_model import get_coder_model

model = get_coder_model()  # priority 高的自动选中
model.load()
code = model.generate_code(layout_json, framework="vue")

# 视觉理解 — 截图转布局
from ai_models.vl_model import get_vl_model

model = get_vl_model()
model.load()
layout = model.analyze_screenshot("screenshot.png")

# 视频生成
from ai_models.video_model import get_video_model

model = get_video_model()
model.load()
result = model.generate_video("sunset over mountains")
```

### 4. 查看已注册模型

```python
from ai_models import list_all, list_by_type, ModelType

# 全部模型
for name, cfg in list_all().items():
    print(f"{name}: {cfg.display_name}")

# 按类型筛选
coders = list_by_type(ModelType.CODE_GENERATION)
for c in sorted(coders, key=lambda x: x.priority, reverse=True):
    print(f"  {c.display_name} [priority={c.priority}]")
```

## 核心概念

### ModelType — 能力分类

| 类型 | 说明 | 示例模型 |
|------|------|---------|
| `VISION_LANGUAGE` | 视觉理解 | Qwen2.5-VL |
| `CODE_GENERATION` | 代码生成 | Qwen-Coder, Gemma |
| `VIDEO_GENERATION` | 视频生成 | CogVideoX |
| `TEXT_GENERATION` | 通用文本（预留） | — |

### ModelFormat — 文件格式

| 格式 | 加载器 | 适用场景 |
|------|--------|---------|
| `SAFETENSORS` | transformers / diffusers | 视觉语言、扩散模型（需 GPU） |
| `GGUF` | llama-cpp-python | 本地大模型量化推理（CPU/GPU 均可） |

> **格式限制**：GGUF 仅支持自回归文本生成，扩散模型（CogVideoX）和视觉语言模型（Qwen-VL）必须使用 safetensors。

### Priority 机制

同类型多个模型时，按 `priority` 降序选择：

```python
# registry.py 示例
register(ModelConfig(..., model_type=ModelType.CODE_GENERATION, priority=20))  # 优先
register(ModelConfig(..., model_type=ModelType.CODE_GENERATION, priority=10))  # 回退
```

### ModelConfig 关键字段

| 字段 | 作用 | 示例 |
|------|------|------|
| `name` | 唯一标识 | `"gemma-31b"` |
| `model_type` | 能力类型 | `ModelType.CODE_GENERATION` |
| `model_format` | 文件格式 | `ModelFormat.GGUF` |
| `model_path` | 模型目录/文件路径 | 自动从 `MODELS_DIR` 拼接 |
| `model_file` | GGUF 文件名 | `"gemma-4-31B-it-qat-UD-Q4_K_XL.gguf"` |
| `n_gpu_layers` | GGUF GPU 卸载层数 | `-1`=全部, `0`=纯 CPU |
| `n_ctx` | GGUF 上下文长度 | `8192` |
| `priority` | 同类型优先级 | 越大越优先 |

## 如何添加新模型

1. **在 `registry.py` 注册一行**：

```python
register(ModelConfig(
    name="my-new-model",
    display_name="My New LLM (代码生成)",
    model_type=ModelType.CODE_GENERATION,
    model_format=ModelFormat.GGUF,
    model_path=_model_path("my-new-model", "my-model-dir"),
    model_file="my-model-Q4.gguf",
    n_ctx=4096,
    priority=30,  # 比 Gemma 更高就用这个
))
```

2. **无需修改任何模型代码** — 同类型自动复用 `CodeGenerationModel`

3. **如果需要新的能力类型**：
   - 在 `ModelType` 枚举加新类型
   - 创建新 `xxx_model.py`，继承 `BaseModel`，实现 `load()` 和业务方法

## 依赖说明

依赖采用"按需安装"策略，避免强制安装重型 ML 框架：

```toml
# 必装
"llama-cpp-python>=0.3.0"  # GGUF 推理（轻量，纯 CPU 可用）

# 按需安装（GPU 环境）
# "torch>=2.4.0",
# "transformers>=4.45.0",   # Qwen-VL, Qwen-Coder
# "diffusers>=0.30.0",      # CogVideoX
# "accelerate>=0.33.0",
```

如果只使用 GGUF 模型，只需 `pip install llama-cpp-python`。
如果需要 safetensors 模型，取消注释对应的依赖行后安装。

## 架构决策记录

1. **为什么按能力分类而不用平台/厂商分类？**
   - 同一个代码生成能力可以有 Qwen-Coder / Gemma / DeepSeek-Coder / GPT 等不同厂商
   - 同能力模型调用方式完全一致，只需一份代码
   - 添加新厂商只需注册一条配置

2. **为什么 safetensors 和 GGUF 不统一格式？**
   - GGUF 是量化自回归格式，无法支持扩散模型和视觉-语言模型
   - 不同格式适用于不同场景，统一会丧失各自优势

3. **为什么采用 priority 而非显式选择？**
   - 生产环境可能有多个代码模型（本地 GGUF + 远程 API）
   - 自动降级避免硬编码
   - 通过环境变量控制优先即可切换
