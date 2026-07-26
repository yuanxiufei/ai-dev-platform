"""
SmolDocling 轻量级 OCR 插件 — 爬虫管线实时图片文字提取

SmolDocling (256M, IBM+HuggingFace) 是目前最轻量的端到端 OCR 模型:
  - 0.35s/页, 消费级显卡甚至 CPU 可跑
  - 支持 OCR + 布局分析 + 表格识别 + 公式提取
  - 嵌入爬虫管线不拖累吞吐

使用方式:
    plugin = SmolDoclingOCR(model_path="ds4sd/SmolDocling-256M-preview")
    page_result = await plugin.extract_text_from_html(html, base_url)
    # page_result.ocr_text 追加了图片文字

架构:
    HTML → 提取 <img> 标签 → 下载图片 → SmolDocling OCR → 追加到 PageResult.ocr_text
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger("rag.crawler.ocr")


# ══════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════

@dataclass
class OcrConfig:
    """OCR 插件配置"""
    enabled: bool = False                       # 是否启用 OCR
    model_path: str = "ds4sd/SmolDocling-256M-preview"  # HuggingFace 模型 ID
    use_gpu: bool = False                       # 是否使用 GPU (SmolDocling CPU 也够快)
    max_images_per_page: int = 10               # 单页最大处理图片数
    min_image_size: int = 100                   # 最小图片尺寸 (px, 过滤图标/小图)
    max_image_size_mb: float = 5.0              # 最大图片大小 (MB)
    timeout_per_image: float = 2.0              # 单张图片 OCR 超时 (秒)
    timeout_total: float = 15.0                 # 单页 OCR 总超时 (秒)
    cache_enabled: bool = True                  # 是否缓存 OCR 结果
    cache_size: int = 5000                      # LRU 缓存条目数
    # 输出控制
    min_ocr_text_length: int = 3                # 最短 OCR 文本 (低于则丢弃)
    merge_into_main_text: bool = True           # 是否合并到 PageResult.text
    keep_separate: bool = True                  # 是否保留独立 ocr_text 字段
    # 鉴权 (HuggingFace gated models)
    hf_token: str = ""                          # HF_API_TOKEN


# ══════════════════════════════════════════════════════════════
# SmolDocling OCR 引擎
# ══════════════════════════════════════════════════════════════

class SmolDoclingOCR:
    """SmolDocling OCR 引擎 — 单例, 懒加载

    特性:
      - 懒加载: 首次调用才加载模型, 不影响模块导入
      - LRU 缓存: URL → OCR 文本, 避免重复 OCR 同一图片
      - 超时保护: 单图 + 总超时, 不拖死爬虫管线
      - 降级: 模型不可用时静默跳过, 不影响主流程
    """

    def __init__(self, config: Optional[OcrConfig] = None):
        self.config = config or OcrConfig()
        self._model = None
        self._processor = None
        self._cache: dict[str, tuple[str, float]] = {}  # url_hash → (text, timestamp)
        self._cache_hits = 0
        self._cache_misses = 0
        self._total_ocr_ms = 0.0
        self._image_count = 0
        self._initialized = False
        self._init_error: Optional[str] = None

    # ── 懒加载 ───────────────────────────────────────

    def _ensure_model(self) -> bool:
        """懒加载模型, 失败不抛异常"""
        if self._initialized:
            return self._model is not None
        if self._init_error:
            return False

        self._initialized = True
        try:
            import torch
            from transformers import AutoProcessor, AutoModelForVision2Seq

            device = "cuda" if (self.config.use_gpu and torch.cuda.is_available()) else "cpu"
            logger.info("SmolDocling: loading model '%s' on %s ...", self.config.model_path, device)

            self._processor = AutoProcessor.from_pretrained(
                self.config.model_path,
                token=self.config.hf_token or True,
            )
            self._model = AutoModelForVision2Seq.from_pretrained(
                self.config.model_path,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                token=self.config.hf_token or True,
            ).to(device)

            self._model.eval()
            logger.info("SmolDocling: model loaded successfully on %s", device)
            return True

        except ImportError as e:
            self._init_error = f"ImportError: {e}. Install: pip install transformers torch pillow"
            logger.warning("SmolDocling: %s", self._init_error)
            return False
        except Exception as e:
            self._init_error = str(e)
            logger.warning("SmolDocling: model load failed: %s", e)
            return False

    # ── 单图 OCR ─────────────────────────────────────

    async def ocr_image(self, image_data: bytes, source_url: str = "") -> str:
        """对单张图片执行 OCR

        Args:
            image_data: 图片二进制数据 (JPEG/PNG/WebP)
            source_url: 图片来源 URL (用于缓存键)

        Returns:
            OCR 提取的文本 (失败返回空串)
        """
        if not self.config.enabled:
            return ""
        if not self._ensure_model():
            return ""

        # 缓存查询
        cache_key = hashlib.md5((source_url or image_data).encode() if isinstance(source_url, str) else image_data).hexdigest()
        if self.config.cache_enabled and cache_key in self._cache:
            text, _ts = self._cache[cache_key]
            self._cache_hits += 1
            return text

        self._cache_misses += 1
        self._image_count += 1

        try:
            from PIL import Image
            image = Image.open(BytesIO(image_data)).convert("RGB")

            # 尺寸过滤
            w, h = image.size
            if w < self.config.min_image_size or h < self.config.min_image_size:
                return ""

            # OCR
            t0 = time.monotonic()
            text = await asyncio.wait_for(
                self._do_ocr(image),
                timeout=self.config.timeout_per_image,
            )
            elapsed = (time.monotonic() - t0) * 1000
            self._total_ocr_ms += elapsed

            # 缓存
            if self.config.cache_enabled and text:
                if len(self._cache) >= self.config.cache_size:
                    # LRU 淘汰 (删最旧的 20%)
                    sorted_keys = sorted(self._cache.items(), key=lambda x: x[1][1])
                    for k, _ in sorted_keys[: max(1, self.config.cache_size // 5)]:
                        del self._cache[k]
                self._cache[cache_key] = (text.strip(), time.time())

            return text.strip() if text else ""

        except asyncio.TimeoutError:
            logger.debug("SmolDocling: timeout for %s", source_url)
            return ""
        except Exception as e:
            logger.debug("SmolDocling: OCR failed for %s: %s", source_url, e)
            return ""

    def _do_ocr(self, image) -> str:
        """同步 OCR 推理"""
        import torch

        inputs = self._processor(image, return_tensors="pt")
        if self._model.device.type == "cuda":
            inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=False,
            )

        text = self._processor.batch_decode(outputs, skip_special_tokens=True)[0]
        return text

    # ── HTML 页面图片批量 OCR ────────────────────────

    async def extract_from_html(
        self,
        html: str,
        base_url: str = "",
    ) -> OcrPageResult:
        """从 HTML 中提取所有图片并 OCR

        Args:
            html: 页面 HTML
            base_url: 页面 URL (用于解析相对路径)

        Returns:
            OcrPageResult 含 OCR 文本列表和合并结果
        """
        if not self.config.enabled or not html:
            return OcrPageResult()

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        img_urls = self._extract_image_urls(soup, base_url)

        if not img_urls:
            return OcrPageResult()

        # 并发 OCR
        t0 = time.monotonic()
        results: list[str] = []

        try:
            tasks = []
            for img_url in img_urls[: self.config.max_images_per_page]:
                tasks.append(self._download_and_ocr(img_url))

            done, _pending = await asyncio.wait(
                tasks,
                timeout=self.config.timeout_total,
            )

            for task in done:
                try:
                    text = task.result()
                    if text and len(text) >= self.config.min_ocr_text_length:
                        results.append(text)
                except Exception:
                    pass

        except asyncio.TimeoutError:
            logger.debug("SmolDocling: page total timeout exceeded for %s", base_url)

        elapsed_ms = (time.monotonic() - t0) * 1000
        merged = "\n".join(results) if results else ""

        logger.debug(
            "SmolDocling: %s → %d images, %d valid (%dms)",
            base_url, len(img_urls), len(results), int(elapsed_ms),
        )

        return OcrPageResult(
            ocr_texts=results,
            merged_text=merged,
            image_urls=img_urls[: self.config.max_images_per_page],
            ocr_count=len(results),
            elapsed_ms=elapsed_ms,
        )

    def _extract_image_urls(self, soup, base_url: str) -> list[str]:
        """从 BeautifulSoup 树上提取图片 URL, 过滤无效图片"""
        urls = []
        seen = set()

        # 1. <img src="...">
        for img in soup.find_all("img", src=True):
            src = self._resolve_url(img["src"], base_url)
            if src and src not in seen and self._is_image_url(src):
                urls.append(src)
                seen.add(src)

        # 2. <picture><source srcset="..."></picture>
        for source in soup.find_all("source", srcset=True):
            srcset = source["srcset"]
            # 取 srcset 中第一个 URL
            first = srcset.split(",")[0].strip().split(" ")[0]
            src = self._resolve_url(first, base_url)
            if src and src not in seen and self._is_image_url(src):
                urls.append(src)
                seen.add(src)

        # 3. data-src / data-lazy-src (懒加载)
        for img in soup.find_all(["img", "div"], attrs={"data-src": True}):
            src = self._resolve_url(img.get("data-src", ""), base_url)
            if src and src not in seen and self._is_image_url(src):
                urls.append(src)
                seen.add(src)

        # 4. 过滤 SVG (无文字价值) 和内联 data: URL (太小)
        urls = [u for u in urls if not u.endswith(".svg") and not u.startswith("data:image/svg")]

        return urls

    async def _download_and_ocr(self, img_url: str) -> str:
        """下载图片 → OCR, 失败返回空串"""
        try:
            import httpx

            # 大小检查 (HEAD 请求)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    head = await client.head(img_url)
                    content_length = head.headers.get("content-length")
                    if content_length:
                        size_mb = int(content_length) / (1024 * 1024)
                        if size_mb > self.config.max_image_size_mb:
                            logger.debug("SmolDocling: skip large image %s (%.1fMB)", img_url, size_mb)
                            return ""
            except Exception:
                pass  # HEAD 不可用时走 GET

            # GET 下载
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(img_url)
                resp.raise_for_status()

                # 二次大小检查
                size_mb = len(resp.content) / (1024 * 1024)
                if size_mb > self.config.max_image_size_mb:
                    return ""

                # 类型检查
                content_type = resp.headers.get("content-type", "")
                if not any(t in content_type for t in ("image/jpeg", "image/png", "image/webp", "image/gif")):
                    return ""

                return await self.ocr_image(resp.content, img_url)

        except Exception as e:
            logger.debug("SmolDocling: download failed for %s: %s", img_url, e)
            return ""

    def _resolve_url(self, src: str, base_url: str) -> Optional[str]:
        """解析相对 URL"""
        if not src:
            return None
        src = src.strip()
        if src.startswith("data:"):
            return None  # 内联 data URL 通常太小, 跳过
        if src.startswith("http"):
            return src
        if base_url:
            return urljoin(base_url, src)
        return None

    def _is_image_url(self, url: str) -> bool:
        """判断 URL 是否指向图片"""
        path = urlparse(url).path.lower()
        return any(
            path.endswith(ext)
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
        )

    # ── 统计 ─────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return {
            "initialized": self._model is not None,
            "init_error": self._init_error,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "image_count": self._image_count,
            "total_ocr_ms": self._total_ocr_ms,
            "avg_ocr_ms": self._total_ocr_ms / max(self._image_count, 1),
        }


# ══════════════════════════════════════════════════════════════
# OCR 结果
# ══════════════════════════════════════════════════════════════

@dataclass
class OcrPageResult:
    """单页 OCR 结果"""
    ocr_texts: list[str] = field(default_factory=list)    # 各图片的 OCR 文本
    merged_text: str = ""                                    # 合并后的文本
    image_urls: list[str] = field(default_factory=list)      # 处理的图片 URL
    ocr_count: int = 0                                       # 有效 OCR 结果数
    elapsed_ms: float = 0.0                                  # 耗时 (毫秒)

    @property
    def has_content(self) -> bool:
        return bool(self.merged_text.strip())

    @property
    def total_chars(self) -> int:
        return len(self.merged_text)


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_ocr_engine: Optional[SmolDoclingOCR] = None


def get_ocr_engine(config: Optional[OcrConfig] = None) -> SmolDoclingOCR:
    """获取全局 OCR 引擎实例"""
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = SmolDoclingOCR(config)
    elif config is not None:
        _ocr_engine.config = config
    return _ocr_engine
