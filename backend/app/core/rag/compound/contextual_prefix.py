"""
上下文前缀生成器 — 借鉴 Anthropic Contextual Retrieval + claude-obsidian

每个 chunk 在索引前附加上下文前缀:
"This passage is from the wiki page 'Foo'. The page discusses Bar and introduces Baz..."

三层策略（自动降级）:
  Tier 1: API (OpenAI/Anthropic) — LLM 生成准确前缀
  Tier 2: ModelRouter — 本地模型生成（免费）
  Tier 3: Synthetic — 零成本回退（标题 + 首段摘要）
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.core.rag.compound.contextual_prefix")


@dataclass
class PrefixContext:
    """单个 chunk 的上下文前缀结果"""
    page_path: str
    chunk_index: int
    raw_text: str
    contextualized_text: str          # "<prefix>\n\n<raw_text>"
    prefix_source: str                # "api" | "local" | "synthetic" | "skipped"
    char_count: int
    body_hash: str                    # sha256 of raw_text
    page_body_hash: str               # sha256 of entire page
    created_at: str

    def to_dict(self) -> dict:
        return {
            "page_path": self.page_path,
            "chunk_index": self.chunk_index,
            "raw_text": self.raw_text,
            "contextualized_text": self.contextualized_text,
            "prefix_source": self.prefix_source,
            "char_count": self.char_count,
            "body_hash": self.body_hash,
            "page_body_hash": self.page_body_hash,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PrefixContext":
        return cls(**d)


class ContextualPrefixer:
    """
    上下文前缀生成器

    Usage:
        prefixer = ContextualPrefixer(cache_dir="rag_data/prefixes")
        chunks = prefixer.process_page(
            "docs/my_doc.md",
            page_body,          # 整个文档正文
            raw_chunks,         # 已分块的 chunk 列表
        )
        # chunks[0].contextualized_text → "<prefix>\n\n<chunk_text>"
    """

    # ── 配置 ──

    CHUNK_TARGET_CHARS: int = 2000   # ~500 tokens
    CHUNK_OVERLAP_CHARS: int = 200

    # 合成前缀模板
    SYNTHETIC_PREFIX_TEMPLATE: str = (
        "This passage is from the document \"{title}\". "
        "The document opens with: {first_sentence}"
    )

    def __init__(
        self,
        cache_dir: str = "rag_data/compound",
        api_key: str | None = None,
        allow_egress: bool = False,
    ):
        self._cache_dir = Path(cache_dir) / "prefixes"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._allow_egress = allow_egress

    # ── Public API ─────────────────────────────────────

    def process_page(
        self,
        page_path: str,
        page_body: str,
        title: str = "",
        raw_chunks: list[str] | None = None,
        force_tier: str | None = None,     # "api" | "local" | "synthetic"
        rebuild: bool = False,
    ) -> list[PrefixContext]:
        """
        处理单个页面的所有 chunk，生成上下文前缀

        Returns:
            PrefixContext 列表，每个 chunk 的 contextualized_text 可用于 BM25 索引和 embedding
        """
        page_hash = self._sha256(page_body)

        # 分块
        chunks = raw_chunks or self._chunk_body(page_body)

        if not chunks:
            return []

        # 确定前缀策略
        tier = force_tier or self._pick_prefix_tier()

        results: list[PrefixContext] = []
        page_slug = self._slug_path(page_path)

        for i, chunk_text in enumerate(chunks):
            body_hash = self._sha256(chunk_text)

            # 增量检测
            if not rebuild:
                existing = self._load_cached(page_slug, i, body_hash, page_hash)
                if existing:
                    results.append(existing)
                    continue

            prefix = self._generate_prefix(tier, title, page_body, chunk_text)
            contextualized = f"{prefix}\n\n{chunk_text}"

            ctx = PrefixContext(
                page_path=page_path,
                chunk_index=i,
                raw_text=chunk_text,
                contextualized_text=contextualized,
                prefix_source=tier,
                char_count=len(contextualized),
                body_hash=body_hash,
                page_body_hash=page_hash,
                created_at=datetime.now(timezone.utc).isoformat(),
            )

            self._save_chunk(page_slug, i, ctx)
            results.append(ctx)

        logger.info("Page '%s': %d chunks, tier=%s", title or page_path, len(results), tier)
        return results

    def process_batch(
        self,
        pages: list[tuple[str, str]],   # [(page_path, page_body), ...]
        titles: list[str] | None = None,
    ) -> dict[str, list[PrefixContext]]:
        """批量处理多页"""
        results: dict[str, list[PrefixContext]] = {}
        for j, (path, body) in enumerate(pages):
            title = titles[j] if titles and j < len(titles) else ""
            results[path] = self.process_page(path, body, title=title)
        return results

    def get_chunk(self, page_path: str, chunk_index: int) -> PrefixContext | None:
        page_slug = self._slug_path(page_path)
        return self._load_cached(page_slug, chunk_index)

    def delete_page(self, page_path: str) -> bool:
        """删除一个页面的所有缓存 chunk"""
        page_slug = self._slug_path(page_path)
        page_dir = self._cache_dir / page_slug
        if page_dir.exists():
            import shutil
            shutil.rmtree(page_dir)
            return True
        return False

    # ── Chunking ───────────────────────────────────────

    def _chunk_body(self, body: str) -> list[str]:
        """段落边界分块 + 重叠"""
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        chunks: list[str] = []
        cur: list[str] = []
        cur_len = 0

        for p in paragraphs:
            cur.append(p)
            cur_len += len(p) + 2
            if cur_len >= self.CHUNK_TARGET_CHARS:
                chunk_text = "\n\n".join(cur)
                chunks.append(chunk_text)
                tail = chunk_text[-self.CHUNK_OVERLAP_CHARS:] if self.CHUNK_OVERLAP_CHARS > 0 else ""
                cur = [tail] if tail else []
                cur_len = len(tail)

        if cur and "".join(cur).strip():
            chunks.append("\n\n".join(cur))
        if not chunks and body.strip():
            chunks = [body.strip()]

        return chunks

    # ── Prefix Generation ──────────────────────────────

    def _pick_prefix_tier(self) -> str:
        """
        自动选择前缀生成层级
        Tier 1: API key 存在 + egress 允许
        Tier 2: 降级到 synthetic（本地模型需要 model_router 注入，外部调用）
        Tier 3: synthetic（始终可用）
        """
        if self._api_key and self._allow_egress:
            return "api"
        return "synthetic"

    def _generate_prefix(
        self,
        tier: str,
        title: str,
        page_body: str,
        chunk_text: str,
    ) -> str:
        """生成 chunk 的上下文前缀"""
        if tier == "api":
            prefix = self._generate_api_prefix(title, page_body, chunk_text)
            if prefix:
                return prefix
            logger.warning("API prefix failed, falling back to synthetic for chunk")
            return self._generate_synthetic(title, page_body)

        if tier == "synthetic":
            return self._generate_synthetic(title, page_body)

        return self._generate_synthetic(title, page_body)

    async def _generate_local_prefix(
        self,
        title: str,
        page_body: str,
        chunk_text: str,
    ) -> str | None:
        """Tier 2: 通过本地 ModelRouter 生成前缀（异步）"""
        try:
            from app.core.model_router import get_model_router
            from app.core.model_router import ModelRequest

            system = (
                "You are a retrieval-augmentation assistant. Given a document and "
                "one chunk extracted from it, write a single sentence (under 35 words) "
                "that situates the chunk within the document's scope and topic. "
                "Output only the sentence — no prefix, no quotes, no commentary."
            )
            prompt = (
                f"<document title=\"{title}\">\n{page_body[:4000]}\n</document>\n\n"
                f"<chunk>\n{chunk_text[:2000]}\n</chunk>\n\n"
                f"Situating sentence (one sentence only):"
            )

            router = get_model_router()
            response = await router.generate(ModelRequest(
                query=prompt,
                system_message=system,
                capability="CODE_GENERATION",
                max_tokens=80,
                temperature=0.0,
            ))

            if response and response.content:
                prefix = response.content.strip().strip('"').strip("'")
                if len(prefix) > 10:
                    return prefix
        except Exception as e:
            logger.warning("Local prefix generation failed: %s", e)

        return None

    def _generate_api_prefix(
        self,
        title: str,
        page_body: str,
        chunk_text: str,
    ) -> str | None:
        """Tier 1: 通过 OpenAI API 生成前缀"""
        if not self._api_key:
            return None

        try:
            import urllib.request

            system = (
                "You are a retrieval-augmentation assistant. Given a document and "
                "one chunk extracted from it, write a single sentence (under 35 words) "
                "that situates the chunk within the document's scope and topic. "
                "Output only the sentence — no prefix, no quotes, no commentary."
            )
            prompt = (
                f"<document title=\"{title}\">\n{page_body[:4000]}\n</document>\n\n"
                f"<chunk>\n{chunk_text[:2000]}\n</chunk>\n\n"
                f"Situating sentence:"
            )

            body = json.dumps({
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 80,
                "temperature": 0.0,
            }).encode()

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                prefix = data["choices"][0]["message"]["content"].strip()
                prefix = prefix.strip('"').strip("'")
                if len(prefix) > 5:
                    return prefix
        except Exception as e:
            logger.warning("API prefix generation failed: %s", e)

        return None

    def _generate_synthetic(self, title: str, page_body: str) -> str:
        """Tier 3: 零成本合成前缀 — 标题 + 文档首段"""
        doc_title = title.strip() or "(untitled)"
        first_sentences = re.split(r"(?<=[.。!！?？])\s+", page_body.strip(), maxsplit=1)
        first = first_sentences[0][:300] if first_sentences else ""
        return self.SYNTHETIC_PREFIX_TEMPLATE.format(
            title=doc_title, first_sentence=first
        )

    # ── Cache I/O ──────────────────────────────────────

    def _slug_path(self, filepath: str) -> str:
        """将文件路径转为缓存友好的 slug"""
        return hashlib.sha1(filepath.encode()).hexdigest()[:12]

    def _chunk_dir(self, page_slug: str) -> Path:
        d = self._cache_dir / page_slug
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _chunk_file(self, page_slug: str, chunk_index: int) -> Path:
        return self._chunk_dir(page_slug) / f"chunk-{chunk_index:03d}.json"

    def _save_chunk(self, page_slug: str, chunk_index: int, ctx: PrefixContext) -> None:
        """原子写入 chunk 缓存"""
        path = self._chunk_file(page_slug, chunk_index)
        # 原子写入: tmp + rename
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ctx.to_dict(), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)

    def _load_cached(
        self,
        page_slug: str,
        chunk_index: int,
        body_hash: str | None = None,
        page_hash: str | None = None,
    ) -> PrefixContext | None:
        """加载缓存的 chunk（可选 hash 校验）"""
        path = self._chunk_file(page_slug, chunk_index)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Hash 校验
            if body_hash and data.get("body_hash") != body_hash:
                return None  # chunk 内容已变
            if page_hash and data.get("page_body_hash") != page_hash:
                return None  # 页面已变
            return PrefixContext.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    @staticmethod
    def _sha256(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── 全局单例 ──────────────────────────────────────────────

_global_prefixer: Optional[ContextualPrefixer] = None


def init_prefixer(cache_dir: str = "rag_data/compound") -> ContextualPrefixer:
    global _global_prefixer
    _global_prefixer = ContextualPrefixer(cache_dir=cache_dir)
    return _global_prefixer


def get_prefixer() -> ContextualPrefixer:
    global _global_prefixer
    if _global_prefixer is None:
        return init_prefixer()
    return _global_prefixer
