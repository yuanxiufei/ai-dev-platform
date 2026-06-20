"""
会话热缓存 (Hot Cache) — 借鉴 claude-obsidian hot.md + 跨会话上下文

让 AI 知识库的上下文跨 LLM 会话持久化:
- 每次会话结束时自动记录关键上下文
- 下次会话开始时注入 hot cache 到 prompt
- 无需用户手动 recap

设计:
- hot.md — 当前活跃上下文 (~200 tokens)
- long.md — 长期压缩记忆 (~1000 tokens)
- 自动修剪: 旧条目按 access_count 和 recency 衰减
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.core.rag.compound.hot_cache")


@dataclass
class HotCacheEntry:
    """单条热缓存条目"""
    key: str                          # 记忆键
    summary: str                      # 1-2 句摘要
    importance: float = 0.5           # 0-1
    access_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "summary": self.summary,
            "importance": self.importance,
            "access_count": self.access_count,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HotCacheEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class HotCache:
    """
    会话热缓存管理器

    两层持久化:
    - hot.json: 短期热上下文（最多 10 条，每条 ≤ 50 字）
    - long.json: 长期压缩记忆（最多 50 条，每条 ≤ 200 字）

    Usage:
        cache = HotCache(cache_dir="rag_data/compound")

        # 会话结束时记录
        cache.add("Python typing rules", "All functions must have type annotations", importance=0.7)

        # 会话开始时注入
        context = cache.get_prompt_context()  # → "Recent context: ..."

        # 查询时标记访问
        cache.touch("Python typing rules")
    """

    MAX_HOT: int = 10          # 热缓存最多条目
    MAX_LONG: int = 50         # 长期缓存最多条目
    MAX_SUMMARY_LEN: int = 200 # 摘要最大字符数

    def __init__(self, cache_dir: str = "rag_data/compound"):
        self._cache_dir = Path(cache_dir) / "hotcache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._hot_path = self._cache_dir / "hot.json"
        self._long_path = self._cache_dir / "long.json"

        self._hot: dict[str, HotCacheEntry] = {}
        self._long: dict[str, HotCacheEntry] = {}
        self._lock = threading.Lock()

        self._load()

    # ── Public API ─────────────────────────────────────

    def add(
        self,
        key: str,
        summary: str,
        importance: float = 0.5,
        promote_to_long: bool = False,
    ) -> HotCacheEntry:
        """
        添加一条热缓存记忆

        Args:
            key: 记忆键（唯一标识）
            summary: 1-2 句摘要
            importance: 重要性 0-1
            promote_to_long: 是否同时写入长期缓存
        """
        summary = summary[:self.MAX_SUMMARY_LEN]

        with self._lock:
            entry = HotCacheEntry(key=key, summary=summary, importance=importance)

            # 写入 hot
            self._hot[key] = entry
            self._prune_hot()

            # 写入 long
            if promote_to_long:
                self._long[key] = entry
                self._prune_long()

            self._save()
            return entry

    def get(self, key: str) -> HotCacheEntry | None:
        entry = self._hot.get(key) or self._long.get(key)
        if entry:
            self.touch(key)
        return entry

    def touch(self, key: str) -> None:
        """标记访问，增加计数"""
        with self._lock:
            entry = self._hot.get(key) or self._long.get(key)
            if entry:
                entry.access_count += 1
                entry.last_accessed_at = datetime.now(timezone.utc).isoformat()

    def remove(self, key: str) -> bool:
        with self._lock:
            removed = False
            if key in self._hot:
                del self._hot[key]
                removed = True
            if key in self._long:
                del self._long[key]
                removed = True
            if removed:
                self._save()
            return removed

    def clear_session(self) -> None:
        """会话结束时清除 hot（保留 long）"""
        with self._lock:
            self._hot.clear()
            self._save()

    def get_prompt_context(self, max_chars: int = 1500) -> str:
        """
        生成可注入 prompt 的上下文文本

        Returns:
            "## Recent Context (auto-loaded)\n- entry1 summary\n- entry2 summary\n..."
        """
        with self._lock:
            entries = sorted(
                self._hot.values(),
                key=lambda e: (e.importance * (1 + e.access_count * 0.1)),
                reverse=True,
            )[:self.MAX_HOT]

        if not entries:
            return ""

        lines = []
        for e in entries:
            access_str = f" (accessed {e.access_count}x)" if e.access_count > 0 else ""
            lines.append(f"- {e.summary}{access_str}")

        context = "## Recent Context (auto-loaded from session cache)\n" + "\n".join(lines)

        # 额外追加长期记忆摘要
        if self._long:
            top_long = sorted(
                self._long.values(),
                key=lambda e: (e.importance * (1 + e.access_count * 0.1)),
                reverse=True,
            )[:3]
            long_lines = [f"- {e.summary}" for e in top_long]
            context += "\n\n## Long-Term Knowledge\n" + "\n".join(long_lines)

        return context[:max_chars]

    def stats(self) -> dict:
        return {
            "hot_count": len(self._hot),
            "long_count": len(self._long),
            "total_accesses": sum(e.access_count for e in list(self._hot.values()) + list(self._long.values())),
        }

    def promote_to_long(self, key: str) -> bool:
        """将 hot 条目提升为 long"""
        with self._lock:
            entry = self._hot.get(key)
            if not entry:
                return False
            self._long[key] = entry
            self._prune_long()
            self._save()
            return True

    # ── Internal ───────────────────────────────────────

    def _prune_hot(self) -> None:
        """hot 超限时剪枝（移除最不重要的）"""
        while len(self._hot) > self.MAX_HOT:
            worst = min(self._hot.values(), key=lambda e: e.importance)
            del self._hot[worst.key]

    def _prune_long(self) -> None:
        """long 超限时剪枝"""
        while len(self._long) > self.MAX_LONG:
            worst = min(self._long.values(),
                        key=lambda e: e.importance * (1 + e.access_count * 0.05))
            del self._long[worst.key]

    def _save(self) -> None:
        """保存 hot 和 long 到磁盘"""
        # hot
        hot_data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._hot),
            "entries": {k: v.to_dict() for k, v in self._hot.items()},
        }
        tmp = self._hot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(hot_data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._hot_path)

        # long
        long_data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(self._long),
            "entries": {k: v.to_dict() for k, v in self._long.items()},
        }
        tmp = self._long_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(long_data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._long_path)

    def _load(self) -> None:
        """从磁盘加载"""
        for path, target in [(self._hot_path, self._hot), (self._long_path, self._long)]:
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in data.get("entries", {}).items():
                    target[k] = HotCacheEntry.from_dict(v)
                logger.debug("Loaded %s: %d entries", path.name, len(target))
            except (json.JSONDecodeError, KeyError):
                pass


# ── 全局单例 ──────────────────────────────────────────────

_global_hot_cache: Optional[HotCache] = None


def init_hot_cache(cache_dir: str = "rag_data/compound") -> HotCache:
    global _global_hot_cache
    _global_hot_cache = HotCache(cache_dir=cache_dir)
    return _global_hot_cache


def get_hot_cache() -> Optional[HotCache]:
    return _global_hot_cache
