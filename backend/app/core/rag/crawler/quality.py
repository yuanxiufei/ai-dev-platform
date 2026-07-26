"""
内容质量管控

- SimHash 去重 (避免重复抓取)
- 内容评分 (字数/文本密度/模板率)
- 语言检测 (langdetect / fasttext 回退)
- 重试策略 (指数退避 + 抖动)
- HTML 噪音清理 (去除导航/广告/脚本)
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from typing import Optional

from .types import ContentQuality, PageResult, QualityConfig

logger = logging.getLogger("rag.crawler.quality")


# ── SimHash 去重 ───────────────────────────────────────


class SimHashDeduper:
    """SimHash 去重器

    原理: SimHash 是一种局部敏感哈希，相似文本产生相似哈希值。
    汉明距离 ≤ threshold 即判定为重复。
    """

    # Unicode 中文范围
    _CJK_RANGE = (0x4E00, 0x9FFF)

    def __init__(self, threshold: int = 3, hash_bits: int = 64):
        self.threshold = threshold
        self.hash_bits = hash_bits
        self._fingerprints: list[int] = []    # 指纹列表
        self._url_hashes: set[str] = set()     # URL 精确去重

    def add(self, text: str, url: str = "") -> bool:
        """添加文档指纹，返回是否已存在 (True=重复)"""
        # URL 精确去重 (最快)
        if url:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            if url_hash in self._url_hashes:
                return True
            self._url_hashes.add(url_hash)

        # SimHash 近重复检测
        fp = self._compute_fingerprint(text)
        if self._is_duplicate(fp):
            return True

        self._fingerprints.append(fp)
        return False

    def _compute_fingerprint(self, text: str) -> int:
        """计算 SimHash 指纹"""
        if not text:
            return 0

        # 特征提取: n-gram tokens (1-3 gram)
        tokens = self._tokenize(text)
        if not tokens:
            return hash(text) & ((1 << self.hash_bits) - 1)

        # 向量累加
        vector = [0] * self.hash_bits
        for token in tokens:
            h = hash(token)
            for i in range(self.hash_bits):
                if h & (1 << i):
                    vector[i] += 1
                else:
                    vector[i] -= 1

        # 折叠为二进制指纹
        fingerprint = 0
        for i, v in enumerate(vector):
            if v > 0:
                fingerprint |= (1 << i)

        return fingerprint

    def _is_duplicate(self, fp: int) -> bool:
        """检查是否与已有指纹重复 (汉明距离)"""
        for existing in self._fingerprints:
            if self._hamming_distance(fp, existing) <= self.threshold:
                return True
        return False

    def _tokenize(self, text: str) -> list[str]:
        """文本分词 (中英混合 n-gram)"""
        tokens = []
        words = text.split()[:500]  # 取前500词

        for i, w in enumerate(words):
            w = w.strip(".,!?;:()[]{}\"'\\/")
            if len(w) >= 2:
                tokens.append(w)
            if len(w) > 2:  # 大词拆成 bigram
                for j in range(len(w) - 1):
                    tokens.append(w[j:j + 2])
            # unigram 中文
            elif len(w) == 1:
                for ch in w:
                    tokens.append(ch)

        return tokens

    @staticmethod
    def _hamming_distance(a: int, b: int) -> int:
        """汉明距离"""
        return bin(a ^ b).count("1")

    def size(self) -> int:
        return len(self._fingerprints)

    def clear(self):
        self._fingerprints.clear()
        self._url_hashes.clear()


# ── 内容评分 ───────────────────────────────────────────


class ContentScorer:
    """内容质量评分器

    评分维度:
    - 字数 (30%): 越多越好，上限 ~2000 字
    - 文本密度 (30%): 文本/HTML原始长度 比例
    - 结构化信息 (20%): 是否有 title/author/date/OG/schema
    - 模板噪声 (20%): 惩罚高频模板内容
    """

    def __init__(self, config: Optional[QualityConfig] = None):
        self.config = config or QualityConfig()

    def score(self, result: PageResult) -> PageResult:
        """对抓取结果评分，返回带评分的结果"""
        scores = {
            "word_count": self._score_word_count(len(result.text.split())),
            "text_density": self._score_text_density(result),
            "structure": self._score_structure(result),
            "noise_penalty": self._score_noise_penalty(result),
        }

        # 加权综合评分
        weights = {"word_count": 0.30, "text_density": 0.30, "structure": 0.20, "noise_penalty": 0.20}
        total = sum(s * weights[k] for k, s in scores.items())

        result.quality_score = max(0.0, min(1.0, total))

        # 质量分级
        if result.quality_score >= 0.8:
            result.quality = ContentQuality.EXCELLENT
        elif result.quality_score >= 0.6:
            result.quality = ContentQuality.GOOD
        elif result.quality_score >= 0.4:
            result.quality = ContentQuality.FAIR
        else:
            result.quality = ContentQuality.POOR

        # 条件拒绝
        if (result.text_length or 0) < self.config.min_word_count:
            result.quality = ContentQuality.REJECTED
            result.quality_score = 0.0
        elif result.quality_score < 0.15:
            result.quality = ContentQuality.REJECTED

        return result

    def _score_word_count(self, words: int) -> float:
        """字数评分: 2000字满分"""
        if words <= 0:
            return 0.0
        return min(1.0, words / 2000.0)

    def _score_text_density(self, result: PageResult) -> float:
        """文本密度评分: 文本/(文本+标签)"""
        html_len = len(result.html) if result.html else 0
        text_len = result.text_length or len(result.text) if result.text else 0
        if html_len == 0 or text_len == 0:
            return 0.0
        density = text_len / max(html_len, 1)
        if density < self.config.min_text_density:
            return 0.0
        return min(1.0, density / 0.8)

    def _score_structure(self, result: PageResult) -> float:
        """结构化信息评分"""
        score = 0.0
        if result.title:
            score += 0.3
        if result.author:
            score += 0.15
        if result.published_date:
            score += 0.2
        if result.schema_org:
            score += 0.2
        if result.open_graph:
            score += 0.15
        return min(1.0, score)

    def _score_noise_penalty(self, result: PageResult) -> float:
        """模板噪声惩罚 (检查常见 boilerplate 文本比例)"""
        boilerplate_patterns = [
            "copyright", "all rights reserved", "版权所有",
            "nav", "navbar", "footer", "sidebar",
            "advertisement", "sponsored", "广告",
            "登录", "注册", "login", "register",
            "评论", "comment", "点赞", "分享",
        ]
        text_lower = result.text.lower()[:3000]
        if not text_lower:
            return 1.0

        boilerplate_count = sum(1 for p in boilerplate_patterns if p.lower() in text_lower)
        match_count = len(text_lower.split()) // 100  # 每100词一个匹配
        ratio = boilerplate_count / max(match_count, 1)
        return max(0.0, 1.0 - ratio * 2.0)


# ── 语言检测 ───────────────────────────────────────────


class LanguageDetector:
    """语言检测器 (langdetect + 字符集回退)"""

    def __init__(self, allowed_languages: Optional[list[str]] = None):
        self.allowed = set(allowed_languages or [])
        self._langdetect = None

    def _get_detector(self):
        if self._langdetect is None:
            try:
                from langdetect import DetectorFactory, detect
                DetectorFactory.seed = 0
                self._langdetect = detect
            except ImportError:
                self._langdetect = False
        return self._langdetect

    def detect(self, text: str) -> str:
        """检测文本语言"""
        if not text or len(text) < 50:
            return self._detect_by_charset(text)

        detector = self._get_detector()
        if detector and detector is not False:
            try:
                return detector(text[:500])
            except Exception:
                pass

        return self._detect_by_charset(text)

    def _detect_by_charset(self, text: str) -> str:
        """字符集回退检测"""
        if not text:
            return "unknown"
        cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        latin = sum(1 for c in text if c.isascii() and c.isalpha())
        if cjk > latin:
            return "zh"
        if latin > 0:
            return "en"
        return "unknown"

    def is_allowed(self, text: str) -> bool:
        """检查文本语言是否在允许列表中"""
        if not self.allowed:
            return True
        lang = self.detect(text)
        return lang in self.allowed

    def filter_language(self, lang: str) -> bool:
        """检查语言代码是否允许"""
        if not self.allowed:
            return True
        return lang in self.allowed


# ── 重试管理器 ─────────────────────────────────────────


class RetryManager:
    """智能重试管理器 (指数退避 + 随机抖动)"""

    def __init__(self, config: Optional[QualityConfig] = None):
        self.config = config or QualityConfig()
        self._domain_failures: dict[str, int] = {}  # 域名连续失败计数

    def should_retry(self, status_code: int, domain: str, retry_count: int) -> bool:
        """判断是否应该重试"""
        if retry_count >= self.config.max_retries:
            return False

        # 仅对可重试状态码重试
        if status_code not in self.config.retry_on_status:
            # 网络连接错误 (status_code=0) 始终可重试
            if status_code != 0:
                return False

        return True

    def get_backoff(self, retry_count: int) -> float:
        """计算退避时间 (指数退避 + 全抖动)"""
        base = self.config.retry_backoff_base
        max_wait = self.config.retry_backoff_max
        wait = min(base * (2 ** retry_count), max_wait)
        # 全抖动: random(0, wait)
        return random.uniform(0, wait)

    def record_failure(self, domain: str):
        """记录域名失败"""
        self._domain_failures[domain] = self._domain_failures.get(domain, 0) + 1

    def record_success(self, domain: str):
        """重置域名失败计数"""
        self._domain_failures[domain] = 0

    def is_domain_degraded(self, domain: str, threshold: int = 5) -> bool:
        """域名是否应该降级 (连续失败过多)"""
        return self._domain_failures.get(domain, 0) >= threshold


# ── HTML 噪音清理 ──────────────────────────────────────


class HTMLCleaner:
    """HTML 内容清理器

    去除:
    - <script>, <style>, <noscript> 标签
    - 导航栏 (nav), 页脚 (footer), 侧边栏 (aside)
    - 评论区域
    - 广告容器
    - 空白文本节点
    """

    # 噪音选择器
    _NOISE_SELECTORS = [
        "script", "style", "noscript", "iframe", "svg",
        "nav", "header", "footer",
        "aside", ".sidebar", "#sidebar",
        ".advertisement", ".ads", ".ad-container", "[class*='ad-']",
        ".comment", ".comments", "#comments",
        ".cookie-banner", ".cookie-consent",
        '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
        ".related-posts", ".recommended", ".suggested",
        ".social-share", ".share-buttons",
    ]

    def __init__(self):
        self._bs4 = None

    def _ensure_bs4(self):
        """延迟导入 BeautifulSoup"""
        if self._bs4 is None:
            try:
                from bs4 import BeautifulSoup
                self._bs4 = BeautifulSoup
            except ImportError:
                self._bs4 = False
        return self._bs4

    def clean(self, html: str) -> str:
        """清理 HTML 噪音"""
        BS = self._ensure_bs4()
        if not BS or BS is False:
            # 回退: 简单正则清理
            return self._regex_clean(html)

        soup = BS(html, "lxml" if self._has_lxml() else "html.parser")

        # 移除噪音元素
        for selector in self._NOISE_SELECTORS:
            for el in soup.select(selector):
                el.decompose()

        # 提取主体文本
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)
        else:
            text = soup.get_text(separator="\n", strip=True)

        return self._normalize_whitespace(text)

    def _regex_clean(self, html: str) -> str:
        """正则回退清理"""
        import re
        # 移除脚本 & 样式
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<noscript[^>]*>.*?</noscript>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # 移除注释
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        # 移除所有标签
        text = re.sub(r'<[^>]+>', ' ', text)
        return self._normalize_whitespace(text)

    def extract_readability(self, html: str, url: str = "") -> tuple[str, str]:
        """使用 readability-lxml 提取正文 (标题, 内容)"""
        try:
            from readability import Document
            doc = Document(html)
            title = doc.title()
            content_html = doc.summary()
            # 清理提取后的内容
            content = self._regex_clean(content_html)
            return title, content
        except ImportError:
            pass
        except Exception:
            pass
        return "", ""

    @staticmethod
    def _has_lxml() -> bool:
        try:
            import lxml  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """规范化空白字符"""
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        return text.strip()


# ── 全局工具 ───────────────────────────────────────────

_cleaner: Optional[HTMLCleaner] = None
_scorer: Optional[ContentScorer] = None
_deduper: Optional[SimHashDeduper] = None
_retry_mgr: Optional[RetryManager] = None
_lang_detector: Optional[LanguageDetector] = None


def get_cleaner() -> HTMLCleaner:
    global _cleaner
    if _cleaner is None:
        _cleaner = HTMLCleaner()
    return _cleaner


def get_scorer(config: Optional[QualityConfig] = None) -> ContentScorer:
    global _scorer
    if _scorer is None:
        _scorer = ContentScorer(config)
    return _scorer


def get_deduper(threshold: int = 3) -> SimHashDeduper:
    global _deduper
    if _deduper is None:
        _deduper = SimHashDeduper(threshold=threshold)
    return _deduper


def get_retry_manager(config: Optional[QualityConfig] = None) -> RetryManager:
    global _retry_mgr
    if _retry_mgr is None:
        _retry_mgr = RetryManager(config)
    return _retry_mgr


def get_language_detector(allowed: Optional[list[str]] = None) -> LanguageDetector:
    global _lang_detector
    if _lang_detector is None:
        _lang_detector = LanguageDetector(allowed)
    return _lang_detector
