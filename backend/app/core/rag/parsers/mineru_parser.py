"""
MinerU 批量文档解析器 — 离线高精度 PDF/Office 解析

MinerU (上海 AI Lab / OpenDataLab, 1.2B 参数):
  - PDF/DOCX/PPTX/XLSX/EPUB → Markdown (含布局/表格/公式)
  - 中文文档解析精度最高, 学术论文场景尤其强
  - 作为知识库文档导入的前置处理器, 离线批量运行

使用方式:
    parser = MinerUParser(output_dir="/app/knowledge-data/documents")
    result = await parser.parse_file("/path/to/doc.pdf")
    # result.markdown → 可直接 upload_text() 导入知识库

架构:
    文档文件 → MinerU CLI/Python API → Markdown + Metadata → 知识库导入
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rag.parsers.mineru")


# ══════════════════════════════════════════════════════════════
# 配置
# ══════════════════════════════════════════════════════════════

@dataclass
class MinerUConfig:
    """MinerU 解析配置"""
    # 运行模式
    mode: str = "cli"                     # cli | python_api
    cli_path: str = "magic-pdf"           # CLI 路径 (pip install magic-pdf)
    python_backend: str = "paddle"        # paddle | pytorch (python_api 模式)

    # 输出控制
    output_dir: str = ""                  # 输出目录 (空=临时目录)
    output_format: str = "markdown"       # markdown | json | content_list
    keep_images: bool = True              # 是否保留提取的图片
    image_dpi: int = 150                  # 图片导出 DPI

    # 解析选项
    enable_formula: bool = True           # 启用公式识别
    enable_table: bool = True             # 启用表格识别
    enable_ocr: bool = True               # 启用 OCR (图片型 PDF)
    lang: str = "ch"                      # 文档语言: ch | en | auto
    start_page: int = 0                   # 起始页码 (0=全文档)
    end_page: int = 0                     # 结束页码 (0=全文档)

    # 并发与超时
    max_concurrent: int = 1               # 最大并发解析 (MinerU 吃 GPU, 建议 1)
    timeout_per_file: float = 300.0       # 单文件超时 (秒)
    timeout_total: float = 3600.0         # 批量总超时 (秒)

    # 缓存
    cache_enabled: bool = True            # 启用缓存 (文件哈希 → 结果)
    cache_dir: str = ""                   # 缓存目录 (空=output_dir/.cache)
    clean_temp: bool = True               # 是否清理临时文件

    # 支持的格式
    supported_extensions: tuple = (
        ".pdf", ".docx", ".doc", ".pptx", ".ppt",
        ".xlsx", ".xls", ".epub", ".mobi",
        ".jpg", ".jpeg", ".png", ".bmp",    # 图片也可解析
    )


# ══════════════════════════════════════════════════════════════
# 解析结果
# ══════════════════════════════════════════════════════════════

@dataclass
class MinerUResult:
    """单个文档解析结果"""
    file_path: str = ""
    file_hash: str = ""
    file_size_mb: float = 0.0
    success: bool = False
    error: str = ""

    # 解析输出
    markdown: str = ""                    # Markdown 正文 (主要输出)
    content_list: list[dict] = field(default_factory=list)  # 结构化内容列表
    metadata: dict = field(default_factory=dict)

    # 统计
    page_count: int = 0
    word_count: int = 0
    image_count: int = 0
    table_count: int = 0
    formula_count: int = 0
    parse_time_ms: float = 0.0

    # 输出文件路径
    output_md_path: str = ""              # Markdown 文件路径
    output_images_dir: str = ""           # 图片目录路径

    @property
    def title(self) -> str:
        """从 metadata 或文件名提取标题"""
        title = self.metadata.get("title", "")
        if not title:
            title = Path(self.file_path).stem
        return title

    def to_document(self, chunk_size: int = 512, chunk_overlap: int = 50) -> dict:
        """转换为知识库文档格式"""
        text = self.markdown or ""
        return {
            "title": self.title,
            "text": text,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "metadata": {
                "source": self.file_path,
                "file_hash": self.file_hash,
                "file_size_mb": self.file_size_mb,
                "content_type": Path(self.file_path).suffix.lower().lstrip("."),
                "page_count": self.page_count,
                "word_count": self.word_count or len(text.split()),
                "image_count": self.image_count,
                "table_count": self.table_count,
                "formula_count": self.formula_count,
                "parse_time_ms": self.parse_time_ms,
                "parser": "mineru",
                **self.metadata,
            },
        }


# ══════════════════════════════════════════════════════════════
# MinerU 解析器
# ══════════════════════════════════════════════════════════════

class MinerUParser:
    """MinerU 批量文档解析器

    两种运行模式:
    1. CLI 模式 (推荐): 子进程调用 `magic-pdf`, 隔离性好
    2. Python API 模式: 直接 import magic_pdf, 更灵活但依赖更重

    特性:
      - 文件哈希缓存: 相同文件不重复解析
      - 超时保护: 单文件 + 批量超时
      - 降级: 解析失败不中断批量任务
      - 自动格式检测: 根据扩展名选择合适的解析路径
    """

    def __init__(self, config: Optional[MinerUConfig] = None):
        self.config = config or MinerUConfig()
        self._cache: dict[str, MinerUResult] = {}
        self._total_files = 0
        self._total_time_ms = 0.0

    # ── 单文件解析 ───────────────────────────────────

    async def parse_file(self, file_path: str) -> MinerUResult:
        """解析单个文件

        Args:
            file_path: 文档文件路径 (PDF/DOCX/PPTX/XLSX/图片)

        Returns:
            MinerUResult 包含 Markdown 和元数据
        """
        path = Path(file_path)
        if not path.exists():
            return MinerUResult(file_path=file_path, success=False, error=f"File not found: {file_path}")

        # 格式检查
        ext = path.suffix.lower()
        if ext not in self.config.supported_extensions:
            return MinerUResult(
                file_path=file_path,
                success=False,
                error=f"Unsupported format: {ext}",
            )

        # 文件哈希
        file_hash = self._hash_file(file_path)
        file_size_mb = path.stat().st_size / (1024 * 1024)

        # 缓存查询
        if self.config.cache_enabled and file_hash in self._cache:
            logger.debug("MinerU: cache hit for %s", file_path)
            return self._cache[file_hash]

        self._total_files += 1
        t0 = time.monotonic()

        try:
            if self.config.mode == "python_api":
                result = await self._parse_python_api(file_path, file_hash, file_size_mb)
            else:
                result = await self._parse_cli(file_path, file_hash, file_size_mb)

        except asyncio.TimeoutError:
            result = MinerUResult(
                file_path=file_path, file_hash=file_hash,
                file_size_mb=file_size_mb, success=False,
                error=f"Timeout ({self.config.timeout_per_file}s)",
            )
        except Exception as e:
            logger.warning("MinerU: parse failed for %s: %s", file_path, e)
            result = MinerUResult(
                file_path=file_path, file_hash=file_hash,
                file_size_mb=file_size_mb, success=False,
                error=str(e),
            )

        result.parse_time_ms = (time.monotonic() - t0) * 1000
        self._total_time_ms += result.parse_time_ms

        # 缓存
        if self.config.cache_enabled and result.success:
            self._cache[file_hash] = result

        if result.success:
            logger.info(
                "MinerU: %s → %d words, %d pages, %dms",
                Path(file_path).name, result.word_count,
                result.page_count, int(result.parse_time_ms),
            )

        return result

    # ── CLI 模式 ─────────────────────────────────────

    async def _parse_cli(self, file_path: str, file_hash: str, file_size_mb: float) -> MinerUResult:
        """通过 CLI 子进程调用 magic-pdf"""
        output_dir = self.config.output_dir or tempfile.mkdtemp(prefix="mineru_")

        cmd = [
            self.config.cli_path,
            "-p", file_path,
            "-o", output_dir,
            "-f", self.config.output_format,
        ]

        if self.config.enable_formula:
            cmd.extend(["--enable-formula"])
        if self.config.enable_table:
            cmd.extend(["--enable-table"])
        if self.config.enable_ocr:
            cmd.extend(["--enable-ocr"])
        if self.config.lang:
            cmd.extend(["--lang", self.config.lang])
        if self.config.start_page > 0:
            cmd.extend(["--start-page", str(self.config.start_page)])
        if self.config.end_page > 0:
            cmd.extend(["--end-page", str(self.config.end_page)])

        logger.debug("MinerU CLI: %s", " ".join(cmd))

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=30.0,  # 启动超时
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.timeout_per_file,
            )

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="replace")[:500]
                return MinerUResult(
                    file_path=file_path, file_hash=file_hash,
                    file_size_mb=file_size_mb, success=False,
                    error=f"CLI exit {proc.returncode}: {err_msg}",
                )

            return self._collect_output(file_path, file_hash, file_size_mb, output_dir)

        except asyncio.TimeoutError:
            raise

    # ── Python API 模式 ──────────────────────────────

    async def _parse_python_api(self, file_path: str, file_hash: str, file_size_mb: float) -> MinerUResult:
        """通过 Python API 直接调用 MinerU"""
        try:
            from magic_pdf.pipe.UNIPipe import UNIPipe
            from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
        except ImportError:
            return MinerUResult(
                file_path=file_path, file_hash=file_hash,
                file_size_mb=file_size_mb, success=False,
                error="magic_pdf not installed. Run: pip install magic-pdf[full]",
            )

        output_dir = self.config.output_dir or tempfile.mkdtemp(prefix="mineru_")
        img_dir = os.path.join(output_dir, "images")
        os.makedirs(img_dir, exist_ok=True)

        try:
            # MinerU pipeline
            pipe = UNIPipe(
                pdf_bytes=open(file_path, "rb").read(),
                jso_useful_key={"_pdf_type": "ocr" if self.config.enable_ocr else "txt"},
                image_writer=DiskReaderWriter(img_dir),
                is_debug=False,
                start_page_id=self.config.start_page,
                end_page_id=self.config.end_page or None,
            )
            pipe.pipe_classify()
            pipe.pipe_analyze()
            pipe.pipe_parse()

            # 提取内容
            content_list = pipe.pipe_mk_uni_markdown(img_dir, drop_mode="none")
            md_content = pipe.pipe_mk_markdown(img_dir, drop_mode="none")

            return self._build_result(
                file_path, file_hash, file_size_mb, output_dir,
                markdown=md_content, content_list=content_list,
            )

        except Exception as e:
            raise

    # ── 批量解析 ─────────────────────────────────────

    async def parse_batch(
        self,
        file_paths: list[str],
        on_progress: Optional[callable] = None,
    ) -> list[MinerUResult]:
        """批量解析文件 (限制并发)

        Args:
            file_paths: 文件路径列表
            on_progress: 进度回调 (done: int, total: int, current: str)

        Returns:
            MinerUResult 列表
        """
        if not file_paths:
            return []

        results: list[MinerUResult] = []
        sem = asyncio.Semaphore(self.config.max_concurrent)
        total = len(file_paths)

        t0 = time.monotonic()

        async def _parse_one(fp: str, idx: int) -> MinerUResult:
            async with sem:
                result = await self.parse_file(fp)
                if on_progress:
                    on_progress(len(results) + 1, total, fp)
                return result

        try:
            tasks = [_parse_one(fp, i) for i, fp in enumerate(file_paths)]
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.timeout_total,
            )
        except asyncio.TimeoutError:
            logger.warning("MinerU: batch timeout after %.0fs", time.monotonic() - t0)

        # 异常转为失败结果
        final: list[MinerUResult] = []
        for fp, r in zip(file_paths, results):
            if isinstance(r, Exception):
                final.append(MinerUResult(
                    file_path=fp, success=False, error=str(r),
                ))
            else:
                final.append(r)

        elapsed = time.monotonic() - t0
        ok = sum(1 for r in final if r.success)
        logger.info(
            "MinerU batch: %d/%d ok in %.1fs (%.1f files/min)",
            ok, total, elapsed, ok / max(elapsed, 0.1) * 60,
        )

        return final

    # ── 目录扫描 ─────────────────────────────────────

    def scan_directory(
        self,
        directory: str,
        recursive: bool = True,
        max_files: int = 500,
    ) -> list[str]:
        """扫描目录中的可解析文件

        Args:
            directory: 目录路径
            recursive: 是否递归
            max_files: 最大文件数

        Returns:
            文件路径列表
        """
        files = []
        dir_path = Path(directory)
        if not dir_path.exists():
            return []

        pattern = "**/*" if recursive else "*"
        for p in dir_path.glob(pattern):
            if p.is_file() and p.suffix.lower() in self.config.supported_extensions:
                files.append(str(p))
                if len(files) >= max_files:
                    break

        files.sort()
        logger.info("MinerU scan: %s → %d supported files", directory, len(files))
        return files

    # ── 内部方法 ─────────────────────────────────────

    def _collect_output(
        self,
        file_path: str,
        file_hash: str,
        file_size_mb: float,
        output_dir: str,
    ) -> MinerUResult:
        """收集 CLI 输出结果"""
        path = Path(file_path)
        name = path.stem

        # MinerU CLI 输出结构: output_dir/{name}/{name}.md + images/
        result_dir = Path(output_dir) / name
        md_path = result_dir / f"{name}.md"
        img_dir = result_dir / "images"

        markdown = ""
        if md_path.exists():
            markdown = md_path.read_text(encoding="utf-8", errors="replace")

        # 统计
        page_count = markdown.count("\n---\n") + 1
        word_count = len(markdown.split())
        image_count = len(list(img_dir.glob("*"))) if img_dir.exists() else 0
        table_count = markdown.count("| --- |")
        formula_count = markdown.count("$$")

        # 元数据
        metadata = self._extract_metadata(markdown, file_path)

        return MinerUResult(
            file_path=file_path,
            file_hash=file_hash,
            file_size_mb=file_size_mb,
            success=True,
            markdown=markdown,
            metadata=metadata,
            page_count=page_count,
            word_count=word_count,
            image_count=image_count,
            table_count=table_count,
            formula_count=formula_count,
            output_md_path=str(md_path) if md_path.exists() else "",
            output_images_dir=str(img_dir) if img_dir.exists() else "",
        )

    def _build_result(
        self,
        file_path: str,
        file_hash: str,
        file_size_mb: float,
        output_dir: str,
        markdown: str,
        content_list: list,
    ) -> MinerUResult:
        """构建 Python API 结果"""
        word_count = len(markdown.split())
        page_count = markdown.count("\n---\n") + 1

        metadata = self._extract_metadata(markdown, file_path)
        metadata["parser_mode"] = "python_api"

        return MinerUResult(
            file_path=file_path,
            file_hash=file_hash,
            file_size_mb=file_size_mb,
            success=True,
            markdown=markdown,
            content_list=content_list,
            metadata=metadata,
            page_count=page_count,
            word_count=word_count,
            output_md_path=os.path.join(output_dir, f"{Path(file_path).stem}.md"),
        )

    def _extract_metadata(self, markdown: str, file_path: str) -> dict:
        """从 Markdown 和文件路径提取元数据"""
        meta = {
            "filename": Path(file_path).name,
            "extension": Path(file_path).suffix.lower(),
        }

        # 尝试提取 frontmatter
        if markdown.startswith("---"):
            parts = markdown.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()

        return meta

    @staticmethod
    def _hash_file(file_path: str) -> str:
        """文件 SHA256 哈希 (缓存键)"""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── 统计 ─────────────────────────────────────────

    @property
    def stats(self) -> dict:
        return {
            "total_files": self._total_files,
            "cache_hits": sum(1 for r in self._cache.values() if r.success),
            "cache_size": len(self._cache),
            "total_time_ms": self._total_time_ms,
            "avg_time_ms": self._total_time_ms / max(self._total_files, 1),
        }


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_mineru_parser: Optional[MinerUParser] = None


def get_mineru_parser(config: Optional[MinerUConfig] = None) -> MinerUParser:
    """获取全局 MinerU 解析器实例"""
    global _mineru_parser
    if _mineru_parser is None:
        _mineru_parser = MinerUParser(config)
    elif config is not None:
        _mineru_parser.config = config
    return _mineru_parser
