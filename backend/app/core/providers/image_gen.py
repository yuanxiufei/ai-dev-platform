"""
图像生成 Provider — DALL-E / Stable Diffusion / ComfyUI 三引擎

借鉴 Open WebUI 的 Images 集成：
- DALL-E (OpenAI): 原生 API，支持 DALL-E 2/3
- Stability AI: Stable Diffusion 3 / SDXL
- ComfyUI: 自托管工作流引擎
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


# ── 统一图像生成接口 ─────────────────────────────

class ImageSize(str, Enum):
    """图像尺寸"""
    S_256 = "256x256"
    S_512 = "512x512"
    S_1024 = "1024x1024"
    S_1024x1792 = "1024x1792"
    S_1792x1024 = "1792x1024"

    # SD 专用
    S_768 = "768x768"
    S_768x1344 = "768x1344"
    S_1344x768 = "1344x768"
    S_1152x896 = "1152x896"
    S_896x1152 = "896x1152"
    S_1216x832 = "1216x832"
    S_832x1216 = "832x1216"


class ImageStyle(str, Enum):
    """图像风格"""
    VIVID = "vivid"        # DALL-E 3: 超现实/戏剧化
    NATURAL = "natural"    # DALL-E 3: 自然/真实
    ANIME = "anime"         # SD: 动漫风格
    PHOTOGRAPHIC = "photographic"  # SD: 摄影风格
    DIGITAL_ART = "digital-art"    # SD: 数字艺术
    THREE_D = "3d-model"            # SD: 3D 渲染


@dataclass
class ImageGenRequest:
    """统一的图像生成请求"""
    prompt: str
    negative_prompt: str = ""
    size: ImageSize = ImageSize.S_1024
    style: ImageStyle = ImageStyle.NATURAL
    n: int = 1                     # 生成数量
    quality: str = "standard"      # standard | hd
    seed: int | None = None        # 随机种子
    steps: int = 30                # SD 采样步数
    cfg_scale: float = 7.0         # SD CFG scale
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageGenResponse:
    """统一的图像生成响应"""
    images: list[ImageResult] = field(default_factory=list)
    provider_used: str = ""
    latency_ms: float = 0.0
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageResult:
    """单张图像结果"""
    url: str = ""                  # 公开 URL
    b64_json: str = ""             # Base64 编码
    local_path: str = ""           # 本地保存路径
    revised_prompt: str = ""       # DALL-E 改写后的 prompt
    seed: int = 0
    width: int = 0
    height: int = 0


# ── DALL-E Provider ───────────────────────────────

class DallEProvider:
    """OpenAI DALL-E 图像生成 Provider"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _map_size(self, size: ImageSize) -> str:
        """DALL-E 3 只支持 1024x1024, 1024x1792, 1792x1024"""
        dalle3_sizes = {
            ImageSize.S_1024, ImageSize.S_1024x1792, ImageSize.S_1792x1024,
        }
        return size.value if size in dalle3_sizes else "1024x1024"

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        """调用 DALL-E API"""
        t0 = time.perf_counter()

        # 判断模型版本
        model = request.extra.get("model", "dall-e-3")
        is_dalle3 = "3" in model

        payload: dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            "n": min(request.n, 1 if is_dalle3 else 10),
            "size": self._map_size(request.size),
            "quality": request.quality if is_dalle3 else "standard",
        }

        if is_dalle3:
            payload["style"] = request.style.value

        response = await self.client.post("/images/generations", json=payload)
        response.raise_for_status()
        data = response.json()
        latency = (time.perf_counter() - t0) * 1000

        images = []
        for item in data.get("data", []):
            images.append(ImageResult(
                url=item.get("url", ""),
                b64_json=item.get("b64_json", ""),
                revised_prompt=item.get("revised_prompt", request.prompt),
            ))

        return ImageGenResponse(
            images=images,
            provider_used=f"dall-e ({model})",
            latency_ms=latency,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Stable Diffusion Provider ─────────────────────

class StabilityProvider:
    """Stability AI Stable Diffusion Provider"""

    ENGINE_MAP: dict[str, str] = {
        "sd3": "stable-diffusion-3.5-large",
        "sd3-turbo": "stable-diffusion-3.5-large-turbo",
        "sdxl": "stable-diffusion-xl-1024-v1-0",
        "core": "stable-image-core",
    }

    def __init__(self, api_key: str, base_url: str = "https://api.stability.ai"):
        self.api_key = api_key
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(180.0, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                },
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _parse_size(self, size: ImageSize) -> tuple[int, int]:
        w, _, h = size.value.partition("x")
        return int(w), int(h)

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        """调用 Stability AI API"""
        t0 = time.perf_counter()
        engine_name = request.extra.get("engine", "sd3")
        engine = self.ENGINE_MAP.get(engine_name, "stable-diffusion-3.5-large")
        width, height = self._parse_size(request.size)

        # Stability AI v2 API
        payload: dict[str, Any] = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "output_format": "png",
            "seed": request.seed or 0,
            "mode": "text-to-image",
        }
        if "turbo" not in engine:
            payload["cfg_scale"] = request.cfg_scale
            payload["steps"] = request.steps

        # 多文件表单上传
        files: dict[str, Any] = {"none": ""}

        response = await self.client.post(
            f"/v2beta/stable-image/generate/{engine.split('/')[-1]}",
            data=payload,
            files=files,
        )
        response.raise_for_status()
        data = response.json()
        latency = (time.perf_counter() - t0) * 1000

        images = []
        if "image" in data:
            b64 = data["image"]
            images.append(ImageResult(
                b64_json=b64,
                seed=data.get("seed", 0),
                width=width,
                height=height,
            ))
        elif "base64" in data:
            b64 = data["base64"]
            images.append(ImageResult(
                b64_json=b64,
                seed=data.get("seed", 0),
                width=width,
                height=height,
            ))

        return ImageGenResponse(
            images=images,
            provider_used=f"stability ({engine_name})",
            latency_ms=latency,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── ComfyUI Provider (自托管) ────────────────────

class ComfyUIProvider:
    """ComfyUI 工作流引擎 Provider（自托管）"""

    def __init__(self, base_url: str = "http://localhost:8188"):
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
        return self._client

    def is_available(self) -> bool:
        return True  # 本地自托管，需在调用时检查

    async def health_check(self) -> bool:
        """检查 ComfyUI 是否可达"""
        try:
            resp = await self.client.get("/system_stats")
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(self, request: ImageGenRequest) -> ImageGenResponse:
        """
        通过默认 SDXL 工作流在 ComfyUI 中生成图像

        使用 ComfyUI API: POST /prompt → GET /history/{prompt_id}
        """
        t0 = time.perf_counter()

        width, height = self._parse_size(request.size)

        # 构建默认 SDXL ComfyUI workflow
        workflow = self._build_default_workflow(
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            width=width,
            height=height,
            steps=request.steps,
            cfg_scale=request.cfg_scale,
            seed=request.seed or -1,
        )

        # 1. 提交 prompt
        queue_resp = await self.client.post("/prompt", json={"prompt": workflow})
        queue_resp.raise_for_status()
        prompt_id = queue_resp.json()["prompt_id"]

        # 2. 轮询等待结果
        max_wait = 120.0
        poll_interval = 1.0
        elapsed = 0.0
        images: list[ImageResult] = []

        while elapsed < max_wait:
            history_resp = await self.client.get(f"/history/{prompt_id}")
            history_resp.raise_for_status()
            history = history_resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    for img_data in node_output.get("images", []):
                        filename = img_data["filename"]
                        img_url = f"{self.base_url}/view?filename={filename}&type=output"
                        images.append(ImageResult(
                            url=img_url,
                            width=width,
                            height=height,
                            seed=request.seed or 0,
                        ))
                break

            import asyncio
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        latency = (time.perf_counter() - t0) * 1000

        if not images:
            raise RuntimeError(f"ComfyUI 生成超时 ({max_wait}s)")

        return ImageGenResponse(
            images=images,
            provider_used="comfyui",
            latency_ms=latency,
        )

    def _parse_size(self, size: ImageSize) -> tuple[int, int]:
        w, _, h = size.value.partition("x")
        return int(w), int(h)

    def _build_default_workflow(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
    ) -> dict[str, Any]:
        """构建默认 SDXL ComfyUI workflow JSON"""
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "cfg": cfg_scale,
                    "denoise": 1.0,
                    "latent_image": ["5", 0],
                    "model": ["4", 0],
                    "negative": ["7", 0],
                    "positive": ["6", 0],
                    "sampler_name": "euler_ancestral",
                    "scheduler": "normal",
                    "seed": seed if seed >= 0 else 0,
                    "steps": steps,
                },
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"},
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"batch_size": 1, "height": height, "width": width},
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": prompt},
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["4", 1], "text": negative_prompt},
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "ComfyUI", "images": ["8", 0]},
            },
        }

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── 统一调度器 ──────────────────────────────────

class ImageGenOrchestrator:
    """
    图像生成编排器 — 自动选择最优 Provider

    优先级：
    1. 用户指定 engine
    2. DALL-E（如果有 API key）
    3. Stability AI（如果有 API key）
    4. ComfyUI（本地自托管，兜底）
    """

    def __init__(
        self,
        dalle_key: str = "",
        stability_key: str = "",
        comfyui_url: str = "",
    ):
        self._dalle = DallEProvider(dalle_key) if dalle_key else None
        self._stability = StabilityProvider(stability_key) if stability_key else None
        self._comfyui = ComfyUIProvider(comfyui_url or "http://localhost:8188")

    def get_available_providers(self) -> list[str]:
        """列出可用的 Provider"""
        providers = []
        if self._dalle and self._dalle.is_available():
            providers.append("dalle")
        if self._stability and self._stability.is_available():
            providers.append("stability")
        providers.append("comfyui")  # 本地兜底
        return providers

    async def generate(
        self,
        request: ImageGenRequest,
        preferred_engine: str = "",
    ) -> ImageGenResponse:
        """
        生成图像，自动选择 Provider 和回退

        Args:
            request: 统一的图像生成请求
            preferred_engine: 偏好的引擎 (dalle | stability | comfyui)

        Returns:
            ImageGenResponse
        """
        engine = preferred_engine.lower() if preferred_engine else ""

        # 按优先级尝试
        candidates: list[tuple[str, Any]] = []

        if engine == "dalle":
            candidates = [("dalle", self._dalle)]
        elif engine == "stability":
            candidates = [("stability", self._stability)]
        elif engine == "comfyui":
            candidates = [("comfyui", self._comfyui)]
        else:
            # 自动选择
            if self._dalle and self._dalle.is_available():
                candidates.append(("dalle", self._dalle))
            if self._stability and self._stability.is_available():
                candidates.append(("stability", self._stability))
            candidates.append(("comfyui", self._comfyui))

        last_error: Exception | None = None

        for name, provider in candidates:
            if provider is None:
                continue
            try:
                if name == "comfyui":
                    if not await provider.health_check():
                        continue
                result = await provider.generate(request)
                result.provider_used = name
                return result
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(
            f"所有图像生成 Provider 均不可用，最后错误: {last_error}"
        )

    async def close(self):
        """关闭所有 Provider"""
        for p in [self._dalle, self._stability, self._comfyui]:
            if p:
                await p.close()
