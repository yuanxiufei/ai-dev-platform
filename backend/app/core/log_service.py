"""
Log Service — 日志通道管理与流式输出

对标: vscode/src/vs/workbench/services/output/ + vscode/src/vs/platform/log/
功能: 多通道日志, 级别过滤, 内存环形缓冲, WebSocket 实时推送
"""

from __future__ import annotations
import time, threading, json, asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, AsyncGenerator
from collections import deque
from enum import Enum


class LogLevel(Enum):
    TRACE = 0
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    FATAL = 50

    @classmethod
    def from_str(cls, s: str) -> "LogLevel":
        return getattr(cls, s.upper(), cls.INFO)

    @classmethod
    def names(cls) -> list[str]:
        return [l.name.lower() for l in cls]


@dataclass
class LogEntry:
    timestamp: float = field(default_factory=time.time)
    level: LogLevel = LogLevel.INFO
    channel: str = "default"
    message: str = ""
    source: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "time": time.strftime("%H:%M:%S", time.localtime(self.timestamp)),
            "level": self.level.name,
            "channel": self.channel,
            "message": self.message,
            "source": self.source,
            "metadata": self.metadata,
        }


class LogChannel:
    """单个日志通道, 含环形缓冲区"""

    def __init__(self, name: str, max_entries: int = 1000, min_level: LogLevel = LogLevel.TRACE):
        self.name = name
        self.max_entries = max_entries
        self.min_level = min_level
        self._buffer: deque[LogEntry] = deque(maxlen=max_entries)
        self._subscribers: dict[str, Callable[[LogEntry], None]] = {}
        self._lock = threading.Lock()

    def write(self, entry: LogEntry) -> None:
        if entry.level.value < self.min_level.value:
            return
        with self._lock:
            self._buffer.append(entry)
        for cb in list(self._subscribers.values()):
            try:
                cb(entry)
            except Exception:
                pass

    def subscribe(self, sid: str, cb: Callable[[LogEntry], None]) -> None:
        self._subscribers[sid] = cb

    def unsubscribe(self, sid: str) -> None:
        self._subscribers.pop(sid, None)

    def get_entries(
        self, level: Optional[LogLevel] = None, limit: int = 200, offset: int = 0
    ) -> list[dict]:
        with self._lock:
            entries = list(self._buffer)
        if level is not None:
            entries = [e for e in entries if e.level.value >= level.value]
        return [e.to_dict() for e in entries[offset:offset + limit]]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    @property
    def count(self) -> int:
        return len(self._buffer)


class LogService:
    """多通道日志管理服务"""

    _instance: Optional["LogService"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "LogService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._channels: dict[str, LogChannel] = {}
        self._ensure_channel("default")
        self._ensure_channel("system")
        self._ensure_channel("agent")
        self._ensure_channel("git")
        self._ensure_channel("debug")
        self._ensure_channel("tasks")
        self._ensure_channel("extensions")
        self._ensure_channel("api")

    def _ensure_channel(self, name: str) -> LogChannel:
        if name not in self._channels:
            self._channels[name] = LogChannel(name)
        return self._channels[name]

    def log(
        self, message: str, level: LogLevel = LogLevel.INFO,
        channel: str = "default", source: str = "", **metadata
    ) -> LogEntry:
        """写入日志"""
        ch = self._ensure_channel(channel)
        entry = LogEntry(
            level=level, channel=channel, message=message,
            source=source, metadata=metadata
        )
        ch.write(entry)
        return entry

    def debug(self, message: str, channel: str = "default", **kw) -> LogEntry:
        return self.log(message, LogLevel.DEBUG, channel, **kw)

    def info(self, message: str, channel: str = "default", **kw) -> LogEntry:
        return self.log(message, LogLevel.INFO, channel, **kw)

    def warn(self, message: str, channel: str = "default", **kw) -> LogEntry:
        return self.log(message, LogLevel.WARN, channel, **kw)

    def error(self, message: str, channel: str = "default", **kw) -> LogEntry:
        return self.log(message, LogLevel.ERROR, channel, **kw)

    def get_channel(self, name: str) -> LogChannel:
        return self._ensure_channel(name)

    def list_channels(self) -> list[dict]:
        return [
            {"name": name, "count": ch.count}
            for name, ch in self._channels.items()
        ]

    def get_entries(
        self, channel: str = "default", level: Optional[LogLevel] = None,
        limit: int = 200, offset: int = 0
    ) -> list[dict]:
        ch = self._ensure_channel(channel)
        return ch.get_entries(level, limit, offset)

    def clear_channel(self, channel: str = "default") -> None:
        self._ensure_channel(channel).clear()

    def subscribe(self, channel: str, sid: str, cb: Callable[[LogEntry], None]) -> None:
        self._ensure_channel(channel).subscribe(sid, cb)

    def unsubscribe(self, channel: str, sid: str) -> None:
        ch = self._channels.get(channel)
        if ch:
            ch.unsubscribe(sid)

    def search(self, query: str, channel: Optional[str] = None,
               level: Optional[LogLevel] = None, limit: int = 100) -> list[dict]:
        """全文搜索日志"""
        results = []
        channels = [channel] if channel else list(self._channels.keys())
        for ch_name in channels:
            ch = self._channels.get(ch_name)
            if not ch:
                continue
            for entry in list(ch._buffer):
                if level and entry.level.value < level.value:
                    continue
                if query.lower() in entry.message.lower():
                    results.append(entry.to_dict())
                    if len(results) >= limit:
                        return results
        return results


def log_service() -> LogService:
    return LogService.get_instance()


def logger(channel: str = "default"):
    """便捷方法: 返回带预配置 channel 的日志函数"""
    svc = log_service()
    return SimpleLogger(svc, channel)


class SimpleLogger:
    def __init__(self, svc: LogService, channel: str):
        self._svc = svc
        self._ch = channel

    def debug(self, msg: str, **kw) -> LogEntry:
        return self._svc.debug(msg, self._ch, **kw)

    def info(self, msg: str, **kw) -> LogEntry:
        return self._svc.info(msg, self._ch, **kw)

    def warn(self, msg: str, **kw) -> LogEntry:
        return self._svc.warn(msg, self._ch, **kw)

    def error(self, msg: str, **kw) -> LogEntry:
        return self._svc.error(msg, self._ch, **kw)

    def log(self, msg: str, level: LogLevel = LogLevel.INFO, **kw) -> LogEntry:
        return self._svc.log(msg, level, self._ch, **kw)
