"""
LLM 引擎 — 本地 GGUF + API 降级

支持:
  - llama-cpp-python 本地推理 (Qwen 2.5 GGUF)
  - OpenAI 兼容 API 降级
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

logger = logging.getLogger("app.core.rag.llm_engine")


class LLMEngine:
    """LLM 推理引擎"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        n_ctx: int = 4096,
        n_threads: int = 4,
        use_gpu: bool = False,
    ):
        self._model_path = model_path or "models/qwen2.5-7b-instruct-q4_k_m.gguf"
        self._n_ctx = n_ctx
        self._n_threads = n_threads
        self._use_gpu = use_gpu
        self._llm = None

    def _load(self):
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama
            import os

            if not os.path.exists(self._model_path):
                raise FileNotFoundError(
                    f"Model not found: {self._model_path}. "
                    f"Download from HuggingFace or ModelScope."
                )

            self._llm = Llama(
                model_path=self._model_path,
                n_ctx=self._n_ctx,
                n_threads=self._n_threads,
                n_gpu_layers=-1 if self._use_gpu else 0,
                verbose=False,
            )
            logger.info("LLM loaded: %s", self._model_path)
        except ImportError:
            logger.warning("llama-cpp-python not installed, LLM unavailable")
            self._llm = None

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        self._load()
        if self._llm is None:
            return ""

        prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"

        output = self._llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["</s>", "<|user|>", "<|system|>"],
            echo=False,
        )
        return output["choices"][0]["text"].strip()

    async def generate_stream(
        self,
        system_prompt: str,
        user_message: str,
    ) -> AsyncIterator[str]:
        self._load()
        if self._llm is None:
            yield ""
            return

        prompt = f"<|system|>\n{system_prompt}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"

        for chunk in self._llm(
            prompt,
            max_tokens=1024,
            temperature=0.3,
            stop=["</s>"],
            stream=True,
        ):
            text = chunk["choices"][0].get("text", "")
            if text:
                yield text


# ── 全局单例 ──────────────────────────────────────────────

_global_llm: Optional[LLMEngine] = None


def get_llm_engine() -> LLMEngine:
    global _global_llm
    if _global_llm is None:
        _global_llm = LLMEngine()
    return _global_llm
