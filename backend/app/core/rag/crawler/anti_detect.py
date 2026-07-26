"""
反爬应对机制

参考主流爬虫框架 (Scrapy, Crawlee, Nutch) 的最佳实践:
  - User-Agent 轮换池 (桌面 / 移动 / 爬虫混合)
  - 请求头随机化 (Accept-Language, Accept-Encoding, Sec-*)
  - Referer 伪造
  - Cookie / Session 持久化
  - 请求间隔随机化 (防止固定频率被识别)
  - TLS 指纹随机化说明 (httpx http2 + TLS 1.3)
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from typing import Optional
from urllib.parse import urlparse

from .types import AntiDetectConfig

logger = logging.getLogger("rag.crawler.anti_detect")

# ── User-Agent 轮换池 ─────────────────────────────────

# 主流浏览器 (Chrome / Firefox / Edge / Safari, Windows / Mac / Linux)
_UA_POOL = [
    # Chrome 130+, Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome, macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox 132+, Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    # Firefox, macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Edge, Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    # Safari, macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    # Chrome, Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Mobile Chrome, Android
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
    # Mobile Safari, iOS
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
]

# Accept-Language 变体
_ACCEPT_LANGUAGES = [
    "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "zh-CN,zh;q=0.9",
    "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "zh-CN,zh-HK;q=0.9,zh;q=0.8,en;q=0.7",
]

# Accept-Encoding 变体
_ACCEPT_ENCODINGS = [
    "gzip, deflate, br",
    "gzip, deflate, br, zstd",
    "gzip, deflate",
]

# Sec-CH-UA (Client Hints) 变体
_SEC_CH_UA = [
    '"Chromium";v="131", "Not=A?Brand";v="24"',
    '"Google Chrome";v="131", "Chromium";v="131", "Not=A?Brand";v="24"',
    '"Microsoft Edge";v="131", "Chromium";v="131", "Not=A?Brand";v="24"',
    "",  # 不发送 Client Hints
]

# Referer 源 (伪造用)
_REFERER_SOURCES = [
    "https://www.google.com/",
    "https://www.bing.com/",
    "https://www.baidu.com/",
    "https://github.com/",
    "",  # 直接访问
]


# ── 反检测引擎 ─────────────────────────────────────────


class AntiDetectEngine:
    """反爬应对引擎

    为每次请求生成独立的请求头/UA/延迟，模拟真实浏览器行为，
    避免被目标站点识别为爬虫。

    使用方式:
        engine = AntiDetectEngine(config)
        headers = engine.get_headers(url)
        delay = engine.get_delay(url)
    """

    def __init__(self, config: Optional[AntiDetectConfig] = None):
        self.config = config or AntiDetectConfig()
        self._ua_pool = _UA_POOL[:self.config.ua_pool_size]
        self._domain_ua: dict[str, str] = {}     # 域名→UA 映射 (sticky)
        self._domain_cookies: dict[str, dict] = {}  # 域名→Cookie
        self._domain_last_request: dict[str, float] = {}
        self._proxy_index = 0

    # ── User-Agent ──────────────────────────────────────

    def get_user_agent(self, domain: str = "", sticky: bool = False) -> str:
        """获取 User-Agent

        Args:
            domain: 目标域名
            sticky: 是否绑定域名 (同一域名始终使用相同 UA)

        注意: 不建议 sticky=True，否则同一域名固定 UA 更容易被追踪。
        默认不 sticky，每次随机选择。
        """
        if sticky and domain and domain in self._domain_ua:
            return self._domain_ua[domain]

        if not self.config.ua_rotation or not self._ua_pool:
            ua = _UA_POOL[0]
        else:
            ua = random.choice(self._ua_pool)

        if sticky and domain:
            self._domain_ua[domain] = ua

        return ua

    # ── 请求头生成 ─────────────────────────────────────

    def get_headers(self, url: str, domain: str = "") -> dict[str, str]:
        """生成完整请求头"""
        headers: dict[str, str] = {
            "User-Agent": self.get_user_agent(domain),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
            "Accept-Encoding": random.choice(_ACCEPT_ENCODINGS),
            "Cache-Control": random.choice(["max-age=0", "no-cache", "no-cache"]),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": random.choice(["none", "cross-site", "same-origin"]),
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "DNT": random.choice(["1", "0"]),
        }

        # Client Hints 随机化
        if self.config.header_randomization:
            ch_ua = random.choice(_SEC_CH_UA)
            if ch_ua:
                headers["Sec-CH-UA"] = ch_ua
            headers["Sec-CH-UA-Platform"] = random.choice(['"Windows"', '"macOS"', '"Linux"'])

        # Referer 伪造
        if self.config.referer_spoofing and url:
            parsed = urlparse(url)
            referer_choice = random.choice(_REFERER_SOURCES)
            if referer_choice and parsed.netloc not in referer_choice:
                headers["Referer"] = referer_choice

        # Cookie 持久化
        if self.config.cookie_persistence and domain and domain in self._domain_cookies:
            cookie_str = "; ".join(
                f"{k}={v}" for k, v in self._domain_cookies[domain].items()
            )
            if cookie_str:
                headers["Cookie"] = cookie_str

        return headers

    def get_api_headers(self, api_url: str = "") -> dict[str, str]:
        """生成 API 请求头 (Content-Type: application/json)"""
        headers = self.get_headers(api_url, domain=urlparse(api_url).netloc if api_url else "")
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Content-Type"] = "application/json"
        headers["Sec-Fetch-Dest"] = "empty"
        headers["Sec-Fetch-Mode"] = "cors"
        return headers

    # ── 延迟控制 ───────────────────────────────────────

    def get_delay(self, domain: str = "") -> float:
        """获取请求间隔延迟 (秒)

        使用随机抖动防止固定频率被反爬检测。
        delay = uniform(min_delay, max_delay) * (1 + jitter * [0,1))
        """
        base = random.uniform(self.config.min_delay, self.config.max_delay)
        jitter = self.config.jitter * random.random()
        delay = base * (1.0 + jitter)

        # 基于域名访问频率的动态调整
        if domain and domain in self._domain_last_request:
            elapsed = time.time() - self._domain_last_request[domain]
            if elapsed < delay:
                return delay - elapsed

        return delay

    def mark_request(self, domain: str):
        """记录域名最近请求时间"""
        self._domain_last_request[domain] = time.time()

    # ── Cookie 管理 ────────────────────────────────────

    def set_cookies(self, domain: str, cookies: dict[str, str]):
        """保存域名 Cookie"""
        if self.config.cookie_persistence:
            self._domain_cookies[domain] = {**self._domain_cookies.get(domain, {}), **cookies}

    def get_cookies(self, domain: str) -> dict[str, str]:
        """获取域名 Cookie"""
        return self._domain_cookies.get(domain, {})

    def clear_cookies(self, domain: str = ""):
        """清除 Cookies"""
        if domain:
            self._domain_cookies.pop(domain, None)
        else:
            self._domain_cookies.clear()

    # ── 代理 ────────────────────────────────────────────

    def get_proxy(self) -> Optional[str]:
        """获取下一个代理"""
        if not self.config.proxy_enabled or not self.config.proxy_pool:
            return None

        if self.config.proxy_rotation == "random":
            return random.choice(self.config.proxy_pool)
        else:  # round_robin
            proxy = self.config.proxy_pool[self._proxy_index % len(self.config.proxy_pool)]
            self._proxy_index += 1
            return proxy

    # ── URL 指纹 ────────────────────────────────────────

    @staticmethod
    def url_fingerprint(url: str) -> str:
        """URL 归一化指纹 (用于去重)"""
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return hashlib.md5(normalized.encode()).hexdigest()[:16]

    @staticmethod
    def generate_tls_fingerprint_seed() -> int:
        """生成 TLS 指纹随机种子 (httpx http2 + h2 协商)"""
        return random.randint(100000, 999999)


# ── 全局单例 ──────────────────────────────────────────

_engine: Optional[AntiDetectEngine] = None


def get_anti_detect(config: Optional[AntiDetectConfig] = None) -> AntiDetectEngine:
    """获取反爬引擎单例"""
    global _engine
    if _engine is None:
        _engine = AntiDetectEngine(config)
    elif config is not None:
        _engine.config = config
    return _engine
