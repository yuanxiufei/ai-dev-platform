"""
代码生成模型 — 统一接口，自动适配 safetensors / GGUF

支持的模型（按 priority 自动选最优）：
  - Gemma 31B (GGUF) — 本地量化，优先
  - Qwen2.5-Coder 7B (safetensors) — GPU 回退
  - 未来加其他厂商模型只需在 registry.py 注册一行配置

Usage:
    from ai_models.coder_model import get_coder_model
    model = get_coder_model()
    if model:
        model.load()
        code = model.generate_code(layout_json, framework="vue")
"""

import json
import logging
from pathlib import Path
from typing import Optional

from ai_models.base import BaseModel, ModelConfig, ModelFormat
from ai_models.prompts.code_gen import (
    LAYOUT_TO_CODE,
    TEXT_TO_FULLSTACK,
    API_GENERATION,
    PROJECT_STRUCTURE,
)
from ai_models.registry import list_by_type, ModelType

logger = logging.getLogger(__name__)


class CodeGenerationModel(BaseModel):
    """代码生成模型 — 统一 safetensors 和 GGUF。

    用法完全一致，不管底层是 Qwen / Gemma / Llama。
    """

    # ────────────────── 加载 ──────────────────

    def load(self) -> "CodeGenerationModel":
        """加载模型（自动按格式选加载器）。"""
        if self._loaded:
            return self

        if self.config.is_gguf:
            self._load_gguf()
        else:
            self._load_safetensors()
        return self

    def _load_safetensors(self) -> None:
        """加载 safetensors 格式（transformers）。

        使用 AutoModelForCausalLM + AutoTokenizer 加载。
        支持 GPU (CUDA) 和 CPU 推理。
        自动选择最佳 dtype 和设备映射。
        """
        logger.info(f"Loading {self.config.display_name} (safetensors)...")

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # 自动选择 dtype
            dtype_map = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }
            torch_dtype = dtype_map.get(self.config.dtype, "auto")

            # 设备选择
            device_map = "auto"
            if self.config.device == "cpu":
                device_map = None  # CPU only

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_path,
                trust_remote_code=True,
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.config.model_path,
                torch_dtype=torch_dtype,
                device_map=device_map,
                trust_remote_code=True,
            )
            self._loaded = True
            device_info = f"GPU (CUDA)" if self.config.device == "cuda" and torch.cuda.is_available() else "CPU"
            logger.info(f"{self.config.display_name} loaded successfully ({device_info})")

        except ImportError as e:
            logger.error(
                "transformers/torch not installed for safetensors loading. "
                "Run: pip install torch transformers accelerate. "
                "Error: %s", e
            )
        except Exception as e:
            logger.error(f"Failed to load {self.config.display_name}: {e}")

    def _load_gguf(self) -> None:
        """加载 GGUF 格式（llama-cpp-python）。

        需要安装 llama-cpp-python。支持 CPU 和 GPU（通过 n_gpu_layers 控制）。
        自动解析 .gguf 文件路径，排除 mmproj/mtp 文件。
        """
        gguf_path = self._resolve_gguf_path()
        if not gguf_path or not Path(gguf_path).exists():
            logger.error(f"GGUF file not found: {gguf_path}")
            return

        logger.info(
            f"Loading {self.config.display_name} "
            f"({Path(gguf_path).stat().st_size / 1e9:.1f} GB)..."
        )

        try:
            from llama_cpp import Llama

            self._llm = Llama(
                model_path=gguf_path,
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                verbose=False,
            )
            self._loaded = True
            device = "CPU-only" if self.config.n_gpu_layers <= 0 else f"GPU layers={self.config.n_gpu_layers}"
            logger.info(f"{self.config.display_name} loaded ({device})")
        except ImportError:
            logger.error("llama-cpp-python not installed. Run: pip install llama-cpp-python")
        except Exception as e:
            logger.error(f"Failed to load {self.config.display_name}: {e}")

    def unload(self) -> None:
        """释放资源（safetensors 或 GGUF）。"""
        for attr in ("_model", "_tokenizer", "_llm"):
            obj = getattr(self, attr, None)
            if obj is not None:
                del obj
                setattr(self, attr, None)
        self._loaded = False
        logger.info(f"{self.config.display_name} unloaded")

    # ────────────────── GGUF 路径解析 ──────────────────

    def _resolve_gguf_path(self) -> str:
        """解析 GGUF 文件完整路径。

        优先级：
          1. model_path + model_file 拼接
          2. model_path 直接指向 .gguf 文件
          3. model_path 目录内自动发现（排除 mmproj 和 mtp 文件）

        Returns:
            完整的 .gguf 文件路径
        """
        mp = self.config.model_path
        mf = self.config.model_file
        if mf:
            return str(Path(mp) / mf)
        if mp.endswith(".gguf"):
            return mp
        dir_path = Path(mp)
        if dir_path.is_dir():
            ggufs = list(dir_path.glob("*.gguf"))
            # 排除 mmproj（视觉投影层）和 mtp 文件
            main = [g for g in ggufs if "mmproj" not in g.name and "mtp" not in g.name]
            if main:
                return str(main[0])
            if ggufs:
                return str(ggufs[0])
        return mp

    # ────────────────── 核心推理 ──────────────────

    def generate(self, **kwargs) -> str:
        """文本生成（自动选推理路径）。

        Args:
            prompt: 用户 prompt 文本
            system: 系统 prompt（可选）
            max_tokens: 最大输出 token 数（默认使用 config.max_tokens）

        Returns:
            生成的文本字符串
        """
        if not self._loaded:
            self.load()
        if not self._loaded:
            return f"// {self.config.display_name} not available"

        if self.config.is_gguf:
            return self._generate_gguf(**kwargs)
        else:
            return self._generate_safetensors(**kwargs)

    def _generate_safetensors(self, **kwargs) -> str:
        """safetensors 推理（transformers 的 AutoModelForCausalLM）。

        Args:
            prompt: 用户 prompt
            system: 系统角色设定（可选）
            max_tokens: 最大输出 token 数

        Returns:
            模型生成的文本
        """
        prompt = kwargs.get("prompt", "")
        system = kwargs.get("system", "")
        max_new = kwargs.get("max_tokens", self.config.max_tokens)

        try:
            import torch

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            # 自动选择设备
            device = self.config.device
            if device == "cuda" and not torch.cuda.is_available():
                device = "cpu"
                logger.warning("CUDA not available, falling back to CPU")

            inputs = self._tokenizer(text, return_tensors="pt")
            if self.config.device != "cpu" and hasattr(self._model, 'device'):
                # device_map="auto" 时 model 已经自动分配
                pass
            else:
                inputs = {k: v.to(device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new,
                    temperature=kwargs.get("temperature", self.config.temperature),
                    do_sample=kwargs.get("temperature", self.config.temperature) > 0,
                )

            # 只解码新生成的部分
            input_len = inputs["input_ids"].shape[1]
            generated_ids = outputs[0][input_len:]
            result = self._tokenizer.decode(generated_ids, skip_special_tokens=True)
            return result

        except Exception as e:
            logger.error(f"Safetensors generation failed: {e}")
            return f"// Error: {e}"

    def _generate_gguf(self, **kwargs) -> str:
        """GGUF 推理（llama-cpp-python 的 create_chat_completion）。

        Args:
            prompt: 用户 prompt
            system: 系统角色设定（可选）
            max_tokens: 最大输出 token 数

        Returns:
            模型生成的文本（可能包含 markdown 代码块包裹）
        """
        prompt = kwargs.get("prompt", "")
        system = kwargs.get("system", "")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._llm.create_chat_completion(
                messages=messages,
                max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
                temperature=self.config.temperature,
            )
            return response["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"GGUF generation failed: {e}")
            return f"// Error: {e}"

    # ══════════════════════════════════════════════════
    # 业务接口（与格式无关，所有 coder 统一）
    # ══════════════════════════════════════════════════

    def generate_code(
        self, layout_json: dict, framework: str = "vue"
    ) -> dict[str, str]:
        """截图布局 → 前端代码。

        Args:
            layout_json: SCREENSHOT_TO_LAYOUT 输出的布局 JSON
            framework: 目标框架（vue / react / html），决定主文件名

        Returns:
            dict: {filename: code}，例如 {"App.vue": "<template>..."}
        """
        prompt = LAYOUT_TO_CODE.format(
            framework=framework,
            layout_json=json.dumps(layout_json, indent=2, ensure_ascii=False),
        )
        code = self.generate(prompt=prompt)
        if self.config.is_gguf:
            code = self._strip_markdown(code)
        main_file = {
            "vue": "App.vue",
            "react": "App.tsx",
            "html": "index.html",
        }.get(framework, f"App.{framework}")
        return {main_file: code}

    def generate_fullstack(
        self,
        description: str,
        framework: str = "react",
        include_backend: bool = True,
    ) -> dict:
        """文本 → 全栈项目。

        Args:
            description: 自然语言项目需求描述
            framework: 前端框架（react / vue / html）
            include_backend: 是否生成后端代码（FastAPI + SQLModel）

        Returns:
            dict::
                {
                    "frontend": str,  # 前端完整代码
                    "backend": str | None,  # 后端代码（include_backend=False 时为 None）
                }
        """
        backend_section = (
            "\n- Include PostgreSQL database models\n- Include CRUD endpoints"
            if include_backend else ""
        )
        prompt = TEXT_TO_FULLSTACK.format(
            description=description,
            framework=framework,
            backend_section=backend_section,
        )
        code = self.generate(prompt=prompt, max_tokens=4096)
        if self.config.is_gguf:
            code = self._strip_markdown(code)
        return {"frontend": code, "backend": code if include_backend else None}

    def generate_api(
        self,
        method: str,
        path: str,
        description: str,
        request_schema: str = "",
        response_schema: str = "",
    ) -> str:
        """生成 FastAPI 端点。

        Args:
            method: HTTP 方法（GET / POST / PUT / DELETE）
            path: API 路径（如 "/api/users"）
            description: 接口功能说明
            request_schema: 请求体 JSON Schema（可选）
            response_schema: 响应体 JSON Schema（可选）

        Returns:
            完整的 FastAPI 端点代码字符串
        """
        prompt = API_GENERATION.format(
            method=method,
            path=path,
            description=description,
            request_schema=request_schema,
            response_schema=response_schema,
        )
        code = self.generate(prompt=prompt)
        return self._strip_markdown(code) if self.config.is_gguf else code

    def suggest_structure(self, description: str, stack: str = "fastapi+react") -> str:
        """需求描述 → 项目结构建议。

        Args:
            description: 项目需求描述
            stack: 技术栈标识（如 "fastapi+react"、"django+vue"）

        Returns:
            目录树 + 简要说明的文本
        """
        prompt = PROJECT_STRUCTURE.format(description=description, stack=stack)
        return self.generate(prompt=prompt)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """去掉 GGUF 输出常见的 ``` 包裹。"""
        lines = text.strip().split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)


# ══════════════════════════════════════════════════
# 模块级获取（按 registry priority 自动选最优）
# ══════════════════════════════════════════════════

def get_coder_model() -> Optional[CodeGenerationModel]:
    """获取最优可用的代码生成模型（按 priority 降序）。"""
    coders = list_by_type(ModelType.CODE_GENERATION)
    for cfg in sorted(coders, key=lambda c: c.priority, reverse=True):
        logger.debug(f"Found coder: {cfg.display_name} [priority={cfg.priority}]")
        # 只返回配置，加载由调用方做（延迟加载）
        return CodeGenerationModel(cfg)
    return None
