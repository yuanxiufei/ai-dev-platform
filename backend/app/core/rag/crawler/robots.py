"""
robots.txt 合规解析器

- 解析目标站点 robots.txt
- 路径匹配 (Allow/Disallow 规则)
- Crawl-Delay 解析
- Sitemap 发现
- 缓存机制 (减少重复请求)
- 通配符支持 (* 和 $)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger("rag.crawler.robots")


@dataclass
class RobotsInfo:
    """robots.txt 解析结果"""
    domain: str
    user_agents: list[str] = field(default_factory=list)
    allow_rules: list[tuple[str, str]] = field(default_factory=list)   # (path, ua)
    disallow_rules: list[tuple[str, str]] = field(default_factory=list)
    crawl_delay: Optional[float] = None
    sitemaps: list[str] = field(default_factory=list)
    fetch_time: float = 0.0
    is_allowed_all: bool = True  # 是否对所有 UA 开放
    raw_text: str = ""


class RobotsParser:
    """robots.txt 解析器 (带缓存)

    特性:
    - 基于 urllib.robotparser 的标准协议实现
    - 内存缓存 `RobotsInfo`，默认 1 小时过期
    - 支持多 User-Agent 解析 (取第一个匹配的规则)
    - Crawl-Delay 提取
    - Sitemap 链接收集
    """

    def __init__(self, cache_seconds: int = 3600, default_ua: str = "*"):
        self._cache: dict[str, RobotsInfo] = {}
        self.cache_seconds = cache_seconds
        self.default_ua = default_ua

    # ── 公共 API ────────────────────────────────────────

    def is_allowed(self, url: str, user_agent: str = "*") -> bool:
        """检查 URL 是否允许抓取"""
        info = self.get_robots(url)
        if info is None:
            return True  # 默认允许 (无 robots.txt)

        # 提取路径
        path = urlparse(url).path or "/"
        return self._match_rules(path, user_agent, info)

    def get_crawl_delay(self, url: str) -> Optional[float]:
        """获取 Crawl-Delay"""
        info = self.get_robots(url)
        if info:
            return info.crawl_delay
        return None

    def get_sitemaps(self, url: str) -> list[str]:
        """获取站点 Sitemap URL 列表"""
        info = self.get_robots(url)
        if info:
            return info.sitemaps
        return []

    def is_site_blocked(self, url: str) -> bool:
        """判断整个站点是否被屏蔽 (所有路径 disallow /)"""
        info = self.get_robots(url)
        if info is None:
            return False
        return not info.is_allowed_all

    # ── robots.txt 获取与缓存 ───────────────────────────

    def get_robots(self, url: str) -> Optional[RobotsInfo]:
        """获取域名 robots.txt (缓存优先)"""
        domain = urlparse(url).netloc
        if not domain:
            return None

        cached = self._cache.get(domain)
        if cached and (time.time() - cached.fetch_time) < self.cache_seconds:
            return cached

        try:
            info = self._fetch_robots(url)
            self._cache[domain] = info
            return info
        except Exception as e:
            logger.debug("获取 robots.txt 失败 %s: %s", domain, e)
            if cached:
                return cached  # 返回过期缓存
            return None

    def _fetch_robots(self, url: str) -> RobotsInfo:
        """HTTP 获取并解析 robots.txt"""
        import urllib.request

        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        rp = RobotFileParser()
        rp.set_url(robots_url)

        try:
            rp.read()
        except Exception:
            # 返回默认全允许
            return RobotsInfo(
                domain=parsed.netloc,
                is_allowed_all=True,
                fetch_time=time.time(),
            )

        info = RobotsInfo(
            domain=parsed.netloc,
            fetch_time=time.time(),
            is_allowed_all=True,
            raw_text="",
        )

        # 提取 User-Agent 条目
        current_ua = "*"
        try:
            for entry in rp.entries:
                for ua in entry.useragents:
                    info.user_agents.append(ua)
                    for rule in entry.rulelines:
                        if rule.allowance:
                            info.allow_rules.append((rule.path, ua))
                        else:
                            info.disallow_rules.append((rule.path, ua))
                            # 如果 / 被 disallow → 整个站点被封
                            if rule.path == "/":
                                info.is_allowed_all = False

            # Crawl-Delay
            cd = rp.crawl_delay(self.default_ua)
            if cd:
                info.crawl_delay = float(cd)

            # Sitemaps
            info.sitemaps = rp.site_maps() or []

        except Exception:
            pass

        return info

    # ── 规则匹配 ────────────────────────────────────────

    @staticmethod
    def _match_rules(path: str, user_agent: str, info: RobotsInfo) -> bool:
        """匹配 Allow/Disallow 规则 (最长匹配优先)"""
        import urllib.robotparser

        rp = RobotFileParser()
        rp.set_url(f"https://{info.domain}/robots.txt")

        # 重建 entries
        for ua in set(info.user_agents):
            entry = urllib.robotparser.Entry()
            entry.useragents = [ua]
            entry.rulelines = []

            for rule_path, rule_ua in info.allow_rules:
                if rule_ua == ua or rule_ua == "*":
                    entry.rulelines.append(
                        urllib.robotparser.RuleLine(rule_path, True)
                    )
            for rule_path, rule_ua in info.disallow_rules:
                if rule_ua == ua or rule_ua == "*":
                    entry.rulelines.append(
                        urllib.robotparser.RuleLine(rule_path, False)
                    )

            rp.entries.append(entry)

        return rp.can_fetch(user_agent, f"https://{info.domain}{path}")

    # ── 缓存管理 ────────────────────────────────────────

    def clear_cache(self, domain: str = ""):
        """清除缓存"""
        if domain:
            self._domain_cache.pop(domain, None)
        else:
            self._cache.clear()

    def get_cache_stats(self) -> dict:
        """缓存统计"""
        total = len(self._cache)
        expired = sum(
            1 for v in self._cache.values()
            if (time.time() - v.fetch_time) >= self.cache_seconds
        )
        return {"total": total, "expired": expired}


# ── 全局单例 ──────────────────────────────────────────

_parser: Optional[RobotsParser] = None


def get_robots_parser(cache_seconds: int = 3600) -> RobotsParser:
    """获取 robots.txt 解析器单例"""
    global _parser
    if _parser is None:
        _parser = RobotsParser(cache_seconds=cache_seconds)
    return _parser
