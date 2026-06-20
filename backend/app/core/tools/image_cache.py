"""
工具图片缓存 — 缓存和管理工具调用返回的图片

借鉴 AstrBot tool_image_cache.py 设计：
- 工具执行后产生的图片保存到本地缓存
- 支持 Base64 编码/解码
- TTL 自动过期清理
- 单例模式

使用场景：Agent 调用图片生成工具后，图片先缓存供 LLM 审查再决定是否发送给用户。
"""

from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

logger = logging.getLogger("platform.tools.image_cache")


@dataclass
class CachedImage:
    """缓存图片的描述信息"""

    tool_call_id: str
    """产生此图片的 tool call ID"""
    tool_name: str
    """产生此图片的工具名"""
    file_path: str
    """缓存文件路径"""
    mime_type: str
    """MIME 类型"""
    created_at: float = field(default_factory=time.time)
    """缓存时间戳"""


class ToolImageCache:
    """工具图片缓存管理器。

    图片存储在 {temp_dir}/tool_images/ 目录下，
    默认 1 小时后自动过期。

    使用方式：
        >>> cache = ToolImageCache()
        >>> img = cache.save_image(b64_data, "call_123", "generate_image", mime="image/png")
        >>> b64, mime = cache.get_image_base64(img.file_path)
        >>> cache.cleanup_expired()
    """

    _instance: ClassVar[ToolImageCache | None] = None
    CACHE_DIR_NAME: ClassVar[str] = "tool_images"
    CACHE_EXPIRY_SECONDS: ClassVar[int] = 3600  # 1 小时

    def __new__(cls, cache_dir: str | None = None) -> ToolImageCache:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, cache_dir: str | None = None) -> None:
        if self._initialized:
            return
        self._initialized = True

        if cache_dir:
            base = Path(cache_dir)
        else:
            base = Path(os.getenv("TEMP", "/tmp")) / "platform"
        self._cache_dir = base / self.CACHE_DIR_NAME
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # 记录所有缓存的 CachedImage 元数据
        self._images: dict[str, CachedImage] = {}

    # ── 文件扩展名映射 ───────────────────────────────

    _MIME_TO_EXT: ClassVar[dict[str, str]] = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/svg+xml": ".svg",
    }

    # ── 保存图片 ─────────────────────────────────────

    def save_image(
        self,
        base64_data: str,
        tool_call_id: str,
        tool_name: str,
        index: int = 0,
        mime_type: str = "image/png",
    ) -> CachedImage:
        """将 Base64 图片保存到缓存目录。

        Args:
            base64_data: Base64 编码的图片数据
            tool_call_id: 产生此图片的 tool call ID
            tool_name: 工具名
            index: 同一 tool call 的多图索引
            mime_type: 图片 MIME 类型

        Returns:
            CachedImage 对象
        """
        ext = self._MIME_TO_EXT.get(mime_type.lower(), ".png")
        filename = f"{tool_call_id}_{index}{ext}"
        file_path = str(self._cache_dir / filename)

        try:
            image_bytes = base64.b64decode(base64_data)
            with open(file_path, "wb") as f:
                f.write(image_bytes)
            size_kb = len(image_bytes) / 1024
            logger.debug(
                "Cached tool image: %s (%.1fKB)", file_path, size_kb
            )
        except Exception as e:
            logger.error("Failed to save tool image: %s", e)
            raise

        img = CachedImage(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            file_path=file_path,
            mime_type=mime_type,
        )
        self._images[file_path] = img
        return img

    # ── 读取图片 ─────────────────────────────────────

    def get_image_base64(
        self, file_path: str, mime_type: str = "image/png"
    ) -> tuple[str, str] | None:
        """读取缓存图片并返回 Base64 编码。

        Returns:
            (base64_data, mime_type) 或 None
        """
        if not os.path.exists(file_path):
            logger.debug("Cached image not found: %s", file_path)
            return None

        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
            return base64_data, mime_type
        except Exception as e:
            logger.error(
                "Failed to read cached image '%s': %s", file_path, e
            )
            return None

    def get_image_url(self, file_path: str) -> str | None:
        """获取缓存图片的文件 URL（file:// 协议）。

        Returns:
            file:// URL 或 None
        """
        if not os.path.exists(file_path):
            return None
        abs_path = os.path.abspath(file_path).replace("\\", "/")
        return f"file:///{abs_path}"

    # ── 清理过期 ─────────────────────────────────────

    def cleanup_expired(self, max_age: int | None = None) -> int:
        """清理过期的缓存图片。

        Args:
            max_age: 最大保留时间（秒），默认 3600

        Returns:
            清理的图片数量
        """
        age = max_age or self.CACHE_EXPIRY_SECONDS
        now = time.time()
        cleaned = 0

        for file_path, img in list(self._images.items()):
            if now - img.created_at > age:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    del self._images[file_path]
                    cleaned += 1
                except OSError as e:
                    logger.warning(
                        "Failed to clean cached image '%s': %s",
                        file_path, e,
                    )

        if cleaned:
            logger.info(
                "Cleaned %d expired cached images (%d remaining)",
                cleaned, len(self._images),
            )

        return cleaned

    def get_stats(self) -> dict[str, int]:
        """获取缓存统计信息"""
        total_size = 0
        for fp in self._images:
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
        return {
            "cached_images": len(self._images),
            "total_size_bytes": total_size,
            "total_size_kb": total_size // 1024,
        }


# ── 全局单例 ─────────────────────────────────────────

def get_tool_image_cache() -> ToolImageCache:
    """获取工具图片缓存全局单例"""
    return ToolImageCache()
