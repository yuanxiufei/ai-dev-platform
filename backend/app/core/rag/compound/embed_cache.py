"""
Embedding 缓存层 — 借鉴 claude-obsidian embed-cache

按 {model}:{body_hash} 键缓存 embedding 向量。
避免重复计算相同文本的向量，降低 API 成本。

设计要点:
- 磁盘持久化 JSON + 内存 LRU 热缓存
- 并发安全: threading.Lock + 原子写入 (tmp + os.replace)
- body_hash = sha256(content) 实现不变性检测
- 支持批量写入和读取
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.core.rag.compound.embed_cache")


class EmbeddingCache:
    """
    Embedding 缓存

    两层缓存:
    - L1: 内存 LRU（快速命中的热数据）
    - L2: 磁盘持久化（跨进程/跨重启）

    Usage:
        cache = EmbeddingCache(cache_dir="rag_data/compound")

        # 检查缓存
        vec = cache.get("BAAI/bge-base-zh-v1.5", "hello world")
        if vec:
            return vec

        # 计算后写入
        vec = await embedder.embed("hello world")
        cache.put("BAAI/bge-base-zh-v1.5", "hello world", vec)
    """

    def __init__(
        self,
        cache_dir: str = "rag_data/compound",
        mem_max_size: int = 5000,
    ):
        self._cache_dir = Path(cache_dir) / "embeddings"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._disk_path = self._cache_dir / "cache.json"

        # L1: 内存 LRU
        self._mem: OrderedDict[str, list[float]] = OrderedDict()
        self._mem_max = mem_max_size
        self._lock = threading.Lock()

        # 预加载磁盘缓存
        self._disk: dict[str, list[float]] = {}
        self._load_disk()

    # ── Public API ─────────────────────────────────────

    def get(self, model: str, text: str) -> list[float] | None:
        """
        查询缓存

        Key: {model_name}:{sha256(text)}
        """
        key = self._make_key(model, text)

        # L1
        with self._lock:
            if key in self._mem:
                self._mem.move_to_end(key)  # LRU touch
                return self._mem[key][:]

        # L2
        if key in self._disk:
            vec = self._disk[key][:]
            # 提升到 L1
            with self._lock:
                self._mem_set(key, vec)
            return vec

        return None

    def put(self, model: str, text: str, vector: list[float]) -> None:
        """写入缓存（内存 + 磁盘）"""
        key = self._make_key(model, text)

        with self._lock:
            self._mem_set(key, vector)
            self._disk[key] = vector

        # 异步写入磁盘（每 100 次写入 flush 一次，简单策略）
        self._maybe_flush()

    def put_batch(
        self,
        entries: list[tuple[str, str, list[float]]],  # [(model, text, vector), ...]
    ) -> int:
        """批量写入"""
        count = 0
        with self._lock:
            for model, text, vec in entries:
                key = self._make_key(model, text)
                self._mem_set(key, vec)
                self._disk[key] = vec
                count += 1
        self._maybe_flush()
        return count

    def flush(self) -> int:
        """强制将磁盘缓存写入文件"""
        with self._lock:
            return self._flush_disk()

    def stats(self) -> dict:
        return {
            "mem_size": len(self._mem),
            "mem_max": self._mem_max,
            "disk_size": len(self._disk),
            "disk_path": str(self._disk_path),
        }

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._mem.clear()
            self._disk.clear()
            if self._disk_path.exists():
                self._disk_path.unlink()

    # ── Key ────────────────────────────────────────────

    @staticmethod
    def _make_key(model: str, text: str) -> str:
        body_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{model}:{body_hash}"

    # ── Memory (L1) ────────────────────────────────────

    def _mem_set(self, key: str, vector: list[float]) -> None:
        """内存 LRU 写入"""
        if key in self._mem:
            del self._mem[key]
        elif len(self._mem) >= self._mem_max:
            # 淘汰最老
            self._mem.popitem(last=False)
        self._mem[key] = vector

    # ── Disk (L2) ──────────────────────────────────────

    _flush_counter: int = 0
    _flush_threshold: int = 100

    def _maybe_flush(self) -> None:
        """阈值触发写入磁盘"""
        self._flush_counter += 1
        if self._flush_counter >= self._flush_threshold:
            self._flush_counter = 0
            self._flush_disk()

    def _flush_disk(self) -> int:
        """原子写入磁盘"""
        data = {
            "schema_version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._disk),
            "entries": self._disk,
        }
        tmp = self._disk_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._disk_path)
        logger.debug("Embedding cache flushed: %d entries", len(self._disk))
        return len(self._disk)

    def _load_disk(self) -> None:
        """加载磁盘缓存"""
        if not self._disk_path.exists():
            return
        try:
            data = json.loads(self._disk_path.read_text(encoding="utf-8"))
            self._disk = data.get("entries", {})
            logger.info("Embedding cache loaded: %d entries", len(self._disk))
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            self._disk = {}


# ── 全局单例 ──────────────────────────────────────────────

_global_embed_cache: Optional[EmbeddingCache] = None


def init_embed_cache(cache_dir: str = "rag_data/compound") -> EmbeddingCache:
    global _global_embed_cache
    _global_embed_cache = EmbeddingCache(cache_dir=cache_dir)
    return _global_embed_cache


def get_embed_cache() -> Optional[EmbeddingCache]:
    return _global_embed_cache
