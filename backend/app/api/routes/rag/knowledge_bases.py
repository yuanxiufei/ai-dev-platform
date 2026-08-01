"""知识库管理 CRUD

端到端流:
    创建 KB → 上传文档 → 自动解析+分块+嵌入 → KB Ready
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter(prefix="/rag/knowledge-bases", tags=["RAG — 知识库"])

logger = logging.getLogger("app.api.rag.kb")

# 统一使用 v2 持久化管理器 (KB 元数据写入 SQLite，重启不丢失)
from app.core.rag.kb_manager import get_kb_manager_v2


# ── 知识库 CRUD ──────────────────────────────────────────

class CreateKBRequest(BaseModel):
    name: str
    description: str = ""
    summary: str = ""
    chunk_strategy: str = "recursive"  # recursive | markdown | code | fixed
    chunk_size: int = 512
    chunk_overlap: int = 100


@router.get("")
async def list_knowledge_bases():
    """列出所有知识库"""
    mgr = get_kb_manager_v2()
    kbs = await mgr.list_all()
    return {
        "data": [
            {
                "kb_id": inst.model.kb_id,
                "name": inst.model.kb_name,
                "description": inst.model.description,
                "summary": inst.model.summary,
                "chunk_size": inst.model.chunk_size,
                "chunk_overlap": inst.model.chunk_overlap,
                "document_count": inst.model.doc_count,
                "chunk_count": inst.model.chunk_count,
                "created_at": str(inst.model.created_at) if inst.model.created_at else None,
            }
            for inst in kbs
        ],
        "total": len(kbs),
    }


@router.post("")
async def create_knowledge_base(body: CreateKBRequest):
    """创建新知识库"""
    try:
        mgr = get_kb_manager_v2()
        inst = await mgr.create(
            name=body.name,
            description=body.description,
            summary=body.summary,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
    except Exception:
        logger.exception("Failed to create KB '%s'", body.name)
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {body.name}")
    return {
        "kb_id": inst.model.kb_id,
        "name": inst.model.kb_name,
        "description": inst.model.description,
        "summary": inst.model.summary,
        "chunk_size": inst.model.chunk_size,
        "chunk_overlap": inst.model.chunk_overlap,
        "document_count": inst.model.doc_count,
        "chunk_count": inst.model.chunk_count,
        "created_at": str(inst.model.created_at) if inst.model.created_at else None,
    }


@router.get("/{kb_id}")
async def get_knowledge_base(kb_id: str):
    """获取单个知识库详情"""
    mgr = get_kb_manager_v2()
    inst = mgr.get(kb_id)
    if not inst:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")
    return {
        "kb_id": inst.model.kb_id,
        "name": inst.model.kb_name,
        "description": inst.model.description,
        "summary": inst.model.summary,
        "chunk_size": inst.model.chunk_size,
        "chunk_overlap": inst.model.chunk_overlap,
        "document_count": inst.model.doc_count,
        "chunk_count": inst.model.chunk_count,
        "created_at": str(inst.model.created_at) if inst.model.created_at else None,
    }


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库及其所有索引"""
    mgr = get_kb_manager_v2()
    await mgr.delete(kb_id)
    return {"status": "deleted", "kb_id": kb_id}


# ── 文档上传 ─────────────────────────────────────────────

@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(None),
    text: str = Form(None),
    title: str = Form(None),
    url: str = Form(None),
):
    """
    上传文档到知识库

    支持三种方式:
      - 文件上传 (file)
      - 纯文本 (text + title)
      - URL 抓取 (url)
    """
    mgr = get_kb_manager_v2()

    if file:
        import tempfile
        import os

        # 文件大小限制：10MB
        _MAX_UPLOAD_BYTES = 10 * 1024 * 1024
        file_content = await file.read()
        if len(file_content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail=f"File too large, max {_MAX_UPLOAD_BYTES // (1024*1024)}MB")

        suffix = os.path.splitext(file.filename or "upload.txt")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            count = await mgr.upload_file(kb_id, tmp_path, progress_callback=title or file.filename)
        finally:
            os.unlink(tmp_path)

        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "filename": file.filename}

    if url:
        doc_title = title or url.rsplit("/", 1)[-1] or "web_page"
        count = await mgr.upload_url(kb_id, url, title=doc_title)
        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "url": url}

    if text:
        doc_title = title or "text_snippet"
        count = await mgr.upload_text(kb_id, text, title=doc_title)
        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "title": doc_title}

    raise HTTPException(status_code=400, detail="Provide file, text, or url")


@router.post("/{kb_id}/documents/batch")
async def upload_documents_batch(
    kb_id: str,
    files: list[UploadFile] = File(...),
):
    """批量上传文档"""
    import tempfile
    import os

    mgr = get_kb_manager_v2()
    results = []
    for f in files:
        suffix = os.path.splitext(f.filename or "upload.txt")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await f.read())
            tmp_path = tmp.name

        try:
            count = await mgr.upload_file(kb_id, tmp_path)
            results.append({"filename": f.filename, "chunks": count, "status": "ok"})
        except Exception as e:
            results.append({"filename": f.filename, "status": "error", "error": str(e)})
        finally:
            os.unlink(tmp_path)

    return {"kb_id": kb_id, "results": results}


# ── 批量 URL 导入 (文档网站) ──────────────────────────────


class BatchImportUrlsRequest(BaseModel):
    """批量导入 URL 请求 — 支持 sitemap 自动发现或 URL 列表"""
    sitemap_url: str = ""            # sitemap URL (自动解析所有页面链接)
    urls: list[str] = []             # 直接传入 URL 列表
    max_pages: int = 100             # 最大导入页数
    max_concurrent: int = 3          # 并发抓取数


@router.post("/{kb_id}/documents/import-from-site")
async def import_from_site(kb_id: str, body: BatchImportUrlsRequest):
    """
    批量导入文档网站到知识库

    支持两种方式:
      1. sitemap 模式 — 传入 sitemap_url (如 https://docs.example.com/sitemap.xml)，
         自动解析 XML 获取所有页面链接，逐个抓取导入
      2. URL 列表模式 — 传入 urls 列表，逐个抓取导入

    每个页面通过 URLParser 三级回退策略提取正文:
      Tavily Extract → readability-lxml → 简单 HTML 清洗

    ☑ 异步非阻塞：爬取 + 嵌入在后台执行，立即返回 job_id 供前端轮询
    """
    from app.core.rag.parsers.site_crawler import SiteCrawler

    mgr = get_kb_manager_v2()
    if not mgr.get(kb_id):
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    if not body.sitemap_url and not body.urls:
        raise HTTPException(status_code=400, detail="Provide sitemap_url or urls")

    # 后台爬取+导入，避免阻塞事件循环
    asyncio.create_task(
        _run_import_from_site(kb_id, body)
    )

    return {
        "status": "processing",
        "kb_id": kb_id,
        "message": "Import started in background — pages are being crawled and indexed",
    }


async def _run_import_from_site(
    kb_id: str, body: BatchImportUrlsRequest,
):
    """后台执行：爬取站点页面 → 分块嵌入 → 写入向量存储"""
    from app.core.rag.parsers.site_crawler import SiteCrawler

    crawler = SiteCrawler(
        max_concurrent=body.max_concurrent,
        request_delay=0.5,
        same_domain_only=True,
    )

    try:
        if body.sitemap_url:
            logger.info("Batch import from sitemap: %s (max=%d)", body.sitemap_url, body.max_pages)
            batch = await crawler.crawl_sitemap(
                sitemap_url=body.sitemap_url,
                max_pages=body.max_pages,
            )
            # 降级：sitemap 解析失败时，回退到链接发现模式
            if not batch.pages:
                logger.info(
                    "Sitemap yielded no URLs, falling back to link discovery from %s",
                    body.sitemap_url,
                )
                batch = await crawler.crawl_from_page(
                    start_url=body.sitemap_url,
                    max_pages=body.max_pages,
                )
        else:
            logger.info("Batch import from %d URLs (max=%d)", len(body.urls), body.max_pages)
            batch = await crawler.crawl_urls(
                urls=body.urls[:body.max_pages],
            )

        if not batch.pages:
            logger.warning("No pages crawled for kb=%s", kb_id)
            return

        # 逐个导入
        mgr = get_kb_manager_v2()
        imported = 0
        for page in batch.pages:
            try:
                await mgr.upload_text(
                    kb_id,
                    text=page.text,
                    title=page.title,
                    metadata={
                        "source": page.url,
                        "content_type": "web_page",
                        "word_count": page.word_count,
                    },
                )
                imported += 1
            except Exception as e:
                logger.warning("Failed to import page %s: %s", page.url, e)

        logger.info(
            "Import from site complete: kb=%s total=%d imported=%d",
            kb_id, batch.total_urls, imported,
        )
    except Exception as e:
        logger.error("Import from site failed for kb=%s: %s", kb_id, e)


# ── 文档管理 (列/删) ──────────────────────────────────────


@router.get("/{kb_id}/documents")
async def list_documents(
    kb_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
):
    """列出知识库中所有已上传的文档"""
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    docs = await mgr.list_documents(kb_id)
    total = len(docs)
    page_docs = docs[skip : skip + limit]
    return {
        "data": [
            {
                "doc_id": d.doc_id,
                "doc_name": d.doc_name,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "chunk_count": d.chunk_count,
                "media_count": d.media_count,
                "embedding_status": d.embedding_status,
                "embedded_at": d.embedded_at,
                "created_at": d.created_at,
            }
            for d in page_docs
        ],
        "total": total,
        "page": skip // limit + 1 if limit else 1,
        "size": limit,
    }


@router.delete("/{kb_id}/documents/{doc_id}")
async def delete_document(kb_id: str, doc_id: str):
    """从知识库中删除指定文档（同时清除向量和元数据）"""
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    await mgr.delete_document(kb_id, doc_id)
    return {"detail": "ok", "message": f"Document {doc_id} deleted from {kb_id}"}


# ── Dify 知识桥接 ─────────────────────────────────────────


class ImportFromDifyRequest(BaseModel):
    kb_name: str
    kb_description: str = ""
    doc_dir: str = "/app/knowledge-data/documents/"
    chunk_size: int = 512
    chunk_overlap: int = 50


@router.post("/import-from-dify")
async def import_from_dify(body: ImportFromDifyRequest):
    """
    从 Dify 训练目录导入知识库（文件方式，推荐）

    读取 knowledge-data/documents/ 下的原始文档，
    走主项目 pipeline（解析→分块→BGE嵌入→FAISS+PostgreSQL存储）。

    支持的文件类型: .md, .txt, .pdf, .docx, .html, .csv, .json
    """
    from app.core.rag.dify_bridge import DifyKnowledgeBridge

    bridge = DifyKnowledgeBridge()
    stats = await bridge.import_from_files(
        kb_name=body.kb_name,
        kb_description=body.kb_description,
        doc_dir=body.doc_dir,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )

    if stats.errors and stats.total_embedded == 0:
        raise HTTPException(status_code=500, detail={
            "message": "Import failed",
            "errors": stats.errors,
        })

    return {
        "kb_name": stats.kb_name,
        "total_documents": stats.total_documents,
        "total_chunks": stats.total_chunks,
        "total_embedded": stats.total_embedded,
        "errors": stats.errors,
        "duration_sec": stats.duration_sec,
    }


# ── Dify Webhook 自动同步 ──────────────────────────────────


class DifyWebhookRequest(BaseModel):
    """Dify 自动同步回调 — Dify 知识库更新后触发"""
    kb_name: str
    kb_description: str = ""
    doc_dir: str = "/app/knowledge-data/documents/"
    chunk_size: int = 512
    chunk_overlap: int = 50
    mode: str = "replace"          # replace：清空重导 | append：增量追加
    secret: str = ""                # 简单密钥，与 DIFY_WEBHOOK_SECRET 环境变量匹配


@router.post("/dify-webhook")
async def dify_webhook(body: DifyWebhookRequest):
    """
    Dify 知识库自动同步回调

    当 Dify 完成知识库训练后，自动将文档同步到主项目 RAG 系统。

    推荐方式 — 同一 Docker 网络 (最简单):
      1. docker network connect ai-platform-net dify-api
      2. Dify 工作流 HTTP 节点: POST http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook
         Body: {"kb_name":"技术文档","mode":"replace"}
      3. 同网络无需密钥，不设 DIFY_WEBHOOK_SECRET 即可

    备用方式 — 不同网络 (需密钥):
      安全: 设置 DIFY_WEBHOOK_SECRET 环境变量启用验证，请求时带 secret 字段。
    """
    import os

    # 密钥验证（环境变量为空时跳过）
    expected_secret = os.environ.get("DIFY_WEBHOOK_SECRET", "")
    if expected_secret and body.secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    from app.core.rag.dify_bridge import DifyKnowledgeBridge

    bridge = DifyKnowledgeBridge()

    # replace 模式：先删旧 KB，再全量重导
    if body.mode == "replace":
        mgr = get_kb_manager_v2()
        existing = await mgr.get_by_name(body.kb_name)
        if existing:
            await mgr.delete(existing.model.kb_id)
            logger.info("Deleted existing KB '%s' (replace mode)", body.kb_name)

    stats = await bridge.import_from_files(
        kb_name=body.kb_name,
        kb_description=body.kb_description,
        doc_dir=body.doc_dir,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )

    if stats.errors and stats.total_embedded == 0:
        raise HTTPException(status_code=500, detail={
            "message": "Webhook sync failed",
            "errors": stats.errors,
        })

    return {
        "status": "synced",
        "kb_name": stats.kb_name,
        "mode": body.mode,
        "total_documents": stats.total_documents,
        "total_chunks": stats.total_chunks,
        "total_embedded": stats.total_embedded,
        "errors": stats.errors,
        "duration_sec": stats.duration_sec,
    }


# ── 高级多策略爬取 ────────────────────────────────────────


class AdvancedCrawlRequest(BaseModel):
    """高级多策略爬取请求 — 支持全部5种策略 + 并发调度"""
    urls: list[str] = []                # URL 列表
    sitemap_url: str = ""               # Sitemap 模式（自动发现所有页面）
    feed_url: str = ""                  # RSS/Atom Feed 模式
    start_url: str = ""                 # 站点全爬模式（robots + sitemap + 链接发现）
    # 并发控制
    max_concurrent: int = 5             # 全局最大并发
    domain_max_concurrent: int = 3      # 单域名最大并发
    delay_seconds: float = 1.0          # 请求间隔
    max_pages: int = 500                # 最大抓取页数
    # 域名限制
    same_domain_only: bool = True
    allowed_domains: list[str] = []
    disallowed_domains: list[str] = []
    # 质量过滤
    min_quality_score: float = 30.0     # 最低质量分
    min_text_length: int = 200          # 最低文本长度
    # 行为
    respect_robots: bool = True
    follow_links: bool = False
    # 反检测
    rotate_user_agent: bool = True
    use_proxy: bool = False
    proxy_url: str = ""
    timeout_seconds: int = 30
    # 导入知识库 (可选)
    kb_id: str = ""                     # 为空则只抓取不入库
    chunk_size: int = 512
    # OCR 增强
    enable_ocr: bool = False            # 启用 SmolDocling 实时图片文字提取


class MineRUBatchImportRequest(BaseModel):
    """MinerU 批量文档解析导入请求"""
    kb_id: str                          # 目标知识库 ID
    file_paths: list[str] = []          # 文件路径列表
    directory: str = ""                 # 目录路径 (扫描所有文档)
    recursive: bool = True              # 是否递归扫描子目录
    max_files: int = 200                # 最大处理文件数
    chunk_size: int = 512
    chunk_overlap: int = 50
    # MinerU 选项
    enable_formula: bool = True         # 公式识别
    enable_table: bool = True           # 表格识别
    enable_ocr: bool = True             # MinerU OCR (扫描件PDF)

class CrawlStatusRequest(BaseModel):
    """查看爬取任务状态"""
    task_id: str = ""


@router.post("/crawl")
async def advanced_crawl(body: AdvancedCrawlRequest):
    """
    高级多策略爬取 — 统一入口

    支持5种抓取策略自动路由:
      - API 接口调用 (JSON/分页/Token)
      - RSS/Atom Feed 解析
      - Sitemap 站点地图
      - 动态渲染 (Playwright, SPA)
      - 静态 HTML 解析 (兜底)

    四种启动模式:
      1. URL 列表 — urls 字段
      2. Sitemap — sitemap_url 字段
      3. Feed — feed_url 字段
      4. 站点全爬 — start_url 字段 (robots→sitemap→链接发现)

    反爬: UA轮换 + 请求头随机化 + 延迟抖动 + robots.txt 合规
    质量: SimHash去重 + 多维度内容评分 + 指数退避重试
    调度: 域名级并发限制 + 优先级老化 + 自适应调速

    结果自动导入知识库 (指定 kb_id) 或仅返回原始结果。
    """
    from app.core.rag.crawler import CrawlPipeline, CrawlConfig, AntiDetectConfig, QualityConfig

    # 构建配置
    cfg = CrawlConfig(
        max_concurrent=body.max_concurrent,
        domain_max_concurrent=body.domain_max_concurrent,
        delay_seconds=body.delay_seconds,
        max_pages=body.max_pages,
        same_domain_only=body.same_domain_only,
        allowed_domains=body.allowed_domains,
        disallowed_domains=body.disallowed_domains,
        min_quality_score=body.min_quality_score,
        min_text_length=body.min_text_length,
        respect_robots=body.respect_robots,
        follow_links=body.follow_links,
        anti_detect=AntiDetectConfig(
            ua_rotation=body.rotate_user_agent,
            proxy_enabled=body.use_proxy,
            proxy_pool=[body.proxy_url] if body.proxy_url else [],
        ),
        quality=QualityConfig(
            request_timeout=body.timeout_seconds,
            min_word_count=body.min_text_length,
        ),
        enable_ocr=body.enable_ocr,
    )

    pipeline = CrawlPipeline(config=cfg)

    # ── 选择启动模式 ─────────────────────────────────
    if body.start_url:
        logger.info("Crawl: site mode from %s", body.start_url)
        results = await pipeline.crawl_site(body.start_url)
    elif body.sitemap_url:
        logger.info("Crawl: sitemap mode from %s", body.sitemap_url)
        results = await pipeline.crawl_sitemap(body.sitemap_url)
    elif body.feed_url:
        logger.info("Crawl: feed mode from %s", body.feed_url)
        results = await pipeline.crawl_feed(body.feed_url)
    elif body.urls:
        logger.info("Crawl: batch mode with %d URLs", len(body.urls))
        results = await pipeline.crawl(body.urls)
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide urls, sitemap_url, feed_url, or start_url",
        )

    # ── 汇总 ─────────────────────────────────────────
    ok_count = sum(1 for r in results if r.success)
    bytes_total = sum(len(r.text or "") for r in results if r.success)
    ocr_chars_total = sum(len(r.ocr_text or "") for r in results if r.success)
    ocr_pages = sum(1 for r in results if r.success and r.ocr_text)
    strategies_used = {}
    for r in results:
        if r.strategy:
            s = r.strategy.value if hasattr(r.strategy, "value") else str(r.strategy)
            strategies_used[s] = strategies_used.get(s, 0) + 1

    # ── 导入知识库 (可选) ────────────────────────────
    imported = 0
    import_errors = []
    if body.kb_id and ok_count > 0:
        v2_mgr = get_kb_manager_v2()
        v2_inst = v2_mgr.get(body.kb_id)
        if not v2_inst:
            raise HTTPException(status_code=404, detail=f"Knowledge base '{body.kb_id}' not found")

        for r in results:
            if not r.success or not r.text:
                continue
            try:
                await v2_mgr.upload_text(
                    body.kb_id,
                    text=r.full_text,    # 正文 + OCR 提取
                    title=r.title or r.url.rsplit("/", 1)[-1] or "web_page",
                    metadata={
                        "source": r.url,
                        "content_type": "web_page",
                        "word_count": r.text_length,
                        "quality_score": r.quality_score,
                        "strategy": str(r.strategy) if r.strategy else "unknown",
                        "ocr_chars": len(r.ocr_text or ""),
                    },
                )
                imported += 1
            except Exception as e:
                import_errors.append(f"{r.url}: {str(e)}")
                logger.warning("Failed to import page %s: %s", r.url, e)

    return {
        "status": "completed",
        "total": len(results),
        "success": ok_count,
        "failed": len(results) - ok_count,
        "bytes_total": bytes_total,
        "ocr_chars": ocr_chars_total,
        "ocr_pages": ocr_pages,
        "strategies_used": strategies_used,
        "imported": imported,
        "import_errors": import_errors[:20],
        "results": [
            {
                "url": r.url,
                "title": r.title,
                "success": r.success,
                "text_length": len(r.text or ""),
                "ocr_text_length": len(r.ocr_text or ""),
                "ocr_images": len(r.ocr_images),
                "word_count": r.text_length,
                "quality_score": r.quality_score,
                "strategy": r.strategy.value if hasattr(r.strategy, "value") else str(r.strategy) if r.strategy else "unknown",
                "error": r.error[:200] if r.error else None,
            }
            for r in results
        ],
        "stats": pipeline.stats,
    }


# ══════════════════════════════════════════════════════════════
# MinerU 离线批量文档解析导入
# ══════════════════════════════════════════════════════════════

@router.post(
    "/{kb_id}/documents/import-with-mineru",
    response_model=dict,
    summary="MinerU 批量文档解析导入",
    description="使用 MinerU (上海 AI Lab) 高精度解析 PDF/DOCX/PPTX/XLSX/EPUB 并导入知识库",
)
async def import_with_mineru(
    kb_id: str,
    body: MineRUBatchImportRequest,
):
    """
    MinerU 离线批量文档解析导入

    支持格式: PDF, DOCX, PPTX, XLSX, EPUB, JPG/PNG 等
    输出 Markdown 含布局分析 + 表格 + 公式提取

    两种模式:
      - file_paths: 指定文件列表
      - directory: 扫描整个目录
    """
    from app.core.rag.parsers.mineru_parser import MinerUParser, MinerUConfig

    # 校验知识库
    v2_mgr = get_kb_manager_v2()
    v2_inst = v2_mgr.get(kb_id)
    if not v2_inst:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    # 收集文件
    file_paths: list[str] = []
    parser = MinerUParser(MinerUConfig(
        enable_formula=body.enable_formula,
        enable_table=body.enable_table,
        enable_ocr=body.enable_ocr,
    ))

    if body.directory:
        file_paths = parser.scan_directory(body.directory, recursive=body.recursive, max_files=body.max_files)
    elif body.file_paths:
        file_paths = body.file_paths
    else:
        raise HTTPException(status_code=400, detail="Provide file_paths or directory")

    if not file_paths:
        return {"status": "empty", "message": "No supported files found", "imported": 0}

    # 批量解析
    results = await parser.parse_batch(file_paths)

    # 导入知识库
    ok_results = [r for r in results if r.success and r.markdown]
    imported = 0
    import_errors: list[str] = []

    for r in ok_results:
        try:
            doc = r.to_document(chunk_size=body.chunk_size, chunk_overlap=body.chunk_overlap)
            await v2_mgr.upload_text(
                kb_id,
                text=doc["text"],
                title=doc["title"],
                metadata=doc["metadata"],
            )
            imported += 1
        except Exception as e:
            import_errors.append(f"{r.file_path}: {str(e)}")
            logger.warning("MinerU import failed for %s: %s", r.file_path, e)

    failed = [r for r in results if not r.success]

    return {
        "status": "completed",
        "total": len(file_paths),
        "parsed": len(ok_results),
        "failed": len(failed),
        "imported": imported,
        "import_errors": import_errors[:20],
        "parser_stats": parser.stats,
        "results": [
            {
                "file": r.file_path,
                "success": r.success,
                "title": r.title,
                "word_count": r.word_count,
                "page_count": r.page_count,
                "table_count": r.table_count,
                "formula_count": r.formula_count,
                "parse_time_ms": r.parse_time_ms,
                "error": r.error[:300] if r.error else None,
            }
            for r in results
        ],
    }


# ── WebSocket 训练进度 ──────────────────────────────────


@router.websocket("/{kb_id}/train-ws")
async def train_document_ws(websocket: WebSocket, kb_id: str):
    """通过 WebSocket 上传文档并实时回报训练进度

    客户端发送 JSON:
        {"filepath": "/data/doc.pdf", "repair": true}
    或   {"text": "原始文本...", "title": "文档标题"}

    服务端回报 JSON:
        {"stage": "parsing",     "pct":  10, "message": "正在解析..."}
        {"stage": "chunking",    "pct":  30, "message": "正在分块..."}
        {"stage": "embedding",   "pct":  60, "message": "正在向量化..."}
        {"stage": "indexing",    "pct":  90, "message": "正在建立索引..."}
        {"stage": "done",        "pct": 100, "message": "训练完成", "chunk_count": 42}
        {"stage": "error",       "pct":   0, "message": "错误详情"}
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    await websocket.accept()
    mgr = get_kb_manager_v2()

    async def send_progress(stage: str, pct: float, message: str = "", **extra):
        try:
            await websocket.send_json({
                "stage": stage,
                "pct": round(pct, 1),
                "message": message or _stage_label(stage),
                **extra,
            })
        except Exception:
            pass

    try:
        # 接收上传指令
        raw = await websocket.receive_text()
        data = json.loads(raw)

        filepath = data.get("filepath")
        text = data.get("text")
        repair = data.get("repair", False)

        if filepath:
            # 文件上传
            chunk_count = await mgr.upload_file(
                kb_id=kb_id,
                filepath=filepath,
                repair=repair,
                progress_callback=lambda stage, pct: asyncio.run_coroutine_threadsafe(
                    send_progress(stage, pct), asyncio.get_event_loop()
                ),
            )
            await send_progress("done", 100, "训练完成", chunk_count=chunk_count)

        elif text:
            # 文本上传
            title = data.get("title", "text_input")
            chunk_count = await mgr.upload_text(
                kb_id=kb_id,
                text=text,
                title=title,
            )
            await send_progress("embedding", 50)
            await send_progress("done", 100, "训练完成", chunk_count=chunk_count)

        else:
            await send_progress("error", 0, "缺少 filepath 或 text 参数")

    except WebSocketDisconnect:
        logger.info("WS train disconnected kb=%s", kb_id)
    except ValueError as e:
        await send_progress("error", 0, str(e))
    except Exception as e:
        logger.exception("WS train error kb=%s", kb_id)
        await send_progress("error", 0, str(e))
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _stage_label(stage: str) -> str:
    return {
        "parsing": "正在解析文档...",
        "chunking": "正在分块...",
        "repairing": "正在修复...",
        "embedding": "正在向量化...",
        "indexing": "正在建立索引...",
        "retrain": "正在重新训练...",
        "done": "训练完成",
        "error": "训练出错",
    }.get(stage, stage)


# ── Retrain 端点 ──────────────────────────────────────


@router.post("/{kb_id}/retrain")
async def retrain_knowledge_base(kb_id: str):
    """重新嵌入知识库中所有文档

    清空向量存储 → 重置所有文档状态 → 逐个重新上传（按 file_path）。

    返回: {"kb_id": str, "total": int, "success": int, "failed": int, "errors": list}
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    try:
        summary = await mgr.retrain_kb(kb_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("Retrain KB %s failed", kb_id)
        raise HTTPException(status_code=500, detail=str(e)) from e

    return summary


@router.websocket("/{kb_id}/retrain-ws")
async def retrain_knowledge_base_ws(websocket: WebSocket, kb_id: str):
    """WebSocket 重新训练 — 实时回报进度

    客户端无需发送数据，连上即开始重新训练。
    回报帧格式与 train-ws 一致: {stage, pct, message, ...}
    完成时额外包含 summary: {total, success, failed, errors}
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    await websocket.accept()

    async def send_progress(stage: str, pct: float, message: str = "", **extra):
        try:
            await websocket.send_json({
                "stage": stage,
                "pct": round(pct, 1),
                "message": message or _stage_label(stage),
                **extra,
            })
        except Exception:
            pass

    try:
        mgr = get_kb_manager_v2()
        summary = await mgr.retrain_kb(
            kb_id=kb_id,
            progress_callback=lambda stage, pct: asyncio.run_coroutine_threadsafe(
                send_progress(stage, pct), asyncio.get_event_loop()
            ),
        )
        await send_progress("done", 100, "重新训练完成", summary=summary)

    except WebSocketDisconnect:
        logger.info("Retrain WS disconnected kb=%s", kb_id)
    except ValueError as e:
        await send_progress("error", 0, str(e))
    except Exception as e:
        logger.exception("Retrain WS error kb=%s", kb_id)
        await send_progress("error", 0, str(e))
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ── Chunk CRUD ───────────────────────────────────────────

class ChunkListItem(BaseModel):
    doc_id: str       # SegmentManager 内部 _doc_id
    content: str
    metadata: dict = {}


class DeleteChunksRequest(BaseModel):
    chunk_ids: list[str]  # _doc_id 列表


@router.get("/{kb_id}/chunks")
async def list_chunks(
    kb_id: str,
    doc_id: Optional[str] = Query(None, description="按文档 doc_id 过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
):
    """分页列出知识库的 chunk（可选按文档过滤）

    返回 chunk 的 _doc_id 供 DELETE /{kb_id}/chunks 使用。
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    try:
        chunks, total = await mgr.list_chunks(
            kb_id=kb_id, doc_id=doc_id,
            skip=(page - 1) * size, limit=size,
        )
    except ValueError as e:
        raise HTTPException(404, str(e))

    return {
        "data": [
            {"doc_id": c["doc_id"], "content": c["content"], "metadata": c["metadata"]}
            for c in chunks
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.delete("/{kb_id}/chunks")
async def delete_chunks(
    kb_id: str,
    body: DeleteChunksRequest,
):
    """按 _doc_id 列表批量删除 chunk

    成功返回 {"total": N, "deleted": N}。
    注意：FAISS 不支持精确删除向量，仅从 ID 映射移除，大数据量删除建议之后执行 retrain。
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    if not body.chunk_ids:
        raise HTTPException(400, "chunk_ids 不能为空")
    if len(body.chunk_ids) > 1000:
        raise HTTPException(400, "单次最多删除 1000 个 chunk")

    mgr = get_kb_manager_v2()
    try:
        result = await mgr.delete_chunks(kb_id, body.chunk_ids)
    except ValueError as e:
        raise HTTPException(404, str(e))

    return result


# ── Job 管理 ─────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    job_type: str  # retrain | batch_embed | health_check
    payload: dict = {}


@router.post("/{kb_id}/jobs")
async def create_job(
    kb_id: str,
    body: CreateJobRequest,
):
    """提交异步任务（pending 状态，需在后台线程执行 run_job）"""
    from app.core.rag.kb_manager import get_kb_manager_v2

    if body.job_type not in ("retrain", "batch_embed", "file_parse", "health_check"):
        raise HTTPException(400, f"不支持的 job_type: {body.job_type}")

    mgr = get_kb_manager_v2()
    try:
        job = await mgr.create_job(kb_id, body.job_type, body.payload)
    except ValueError as e:
        raise HTTPException(404, str(e))

    return {
        "job_id": job.job_id,
        "status": job.status,
        "job_type": job.job_type,
        "created_at": job.created_at,
    }


@router.get("/{kb_id}/jobs")
async def list_jobs(
    kb_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
):
    """列出知识库的任务列表（按创建时间降序）"""
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    jobs = await mgr.list_jobs(kb_id=kb_id, limit=size, offset=(page - 1) * size)
    return {
        "data": [
            {
                "job_id": j.job_id,
                "job_type": j.job_type,
                "status": j.status,
                "progress": j.progress,
                "payload_json": j.payload_json,
                "result_json": j.result_json,
                "error_message": j.error_message,
                "created_at": j.created_at,
                "updated_at": j.updated_at,
            }
            for j in jobs
        ],
        "total": len(jobs),
        "page": page,
        "size": size,
    }


@router.get("/{kb_id}/jobs/{job_id}")
async def get_job(kb_id: str, job_id: str):
    """获取单个作业详情"""
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    try:
        job = await mgr.get_job(job_id)
        if not job:
            raise HTTPException(404, f"Job {job_id} not found")
    except ValueError as e:
        raise HTTPException(404, str(e)) from e

    return {
        "job_id": job.job_id,
        "job_type": job.job_type,
        "kb_id": job.kb_id,
        "status": job.status,
        "progress": job.progress,
        "result_json": job.result_json,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.post("/{kb_id}/jobs/{job_id}/run")
async def run_job(kb_id: str, job_id: str):
    """异步执行 pending 任务（asyncio.to_thread 后台执行，不阻塞事件循环）

    请求立即返回（状态变为 running），实际工作在后台线程中完成。
    客户端可定期轮询 GET /{kb_id}/jobs/{job_id} 检查状态。
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    try:
        job = await mgr.schedule_job_background(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    return {
        "job_id": job.job_id,
        "status": job.status,
        "message": "Job started in background thread",
    }


# ── FAISS 索引压缩（幽灵向量清理）──────────────────────


@router.get("/{kb_id}/ghost-stats")
async def get_ghost_stats(kb_id: str):
    """查看 FAISS 索引健康状态（幽灵向量比例）

    返回: {kb_id, index_total, alive_in_map, ghost_count, ghost_ratio, needs_compact}
    - ghost_ratio > 0.2 时建议执行 compact
    """
    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    stats = mgr.get_ghost_stats(kb_id)
    if stats is None:
        raise HTTPException(404, f"KB {kb_id} not found or not loaded")

    return stats


@router.get("/{kb_id}/documents/{doc_id}/structure")
async def get_document_structure(kb_id: str, doc_id: str):
    """获取文档的结构树（标题层级）

    返回：标题节点列表，每个节点含 level/text/position/children。
    借鉴 RAGFlow 文档结构树。
    """
    mgr = get_kb_manager_v2()
    tree = mgr.get_structure_tree(kb_id, doc_id)
    if tree is None:
        return {"data": None, "message": "该文档未提取到结构树"}
    return {"data": tree}


@router.post("/{kb_id}/compact")
async def compact_knowledge_base(kb_id: str):
    """压缩 FAISS 索引：重新嵌入所有有效 chunk 并重建索引

    用途：
    - 大规模删除 chunk 后的索引清理（清除幽灵向量）
    - 恢复因向量碎片导致的检索性能下降

    注意：
    - 此操作会重新嵌入所有剩余文本，耗时与 chunk 数成正比
    - 如果幽灵向量为 0，返回 {"status": "skipped"}
    """
    import asyncio as _asyncio

    from app.core.rag.kb_manager import get_kb_manager_v2

    mgr = get_kb_manager_v2()
    inst = mgr.get(kb_id)
    if not inst or not inst.storage:
        raise HTTPException(404, f"KB {kb_id} not found or not initialized")

    try:
        # compact_kb_sync 是 CPU 密集型（重新嵌入+重建 FAISS），放线程池执行
        result = await _asyncio.to_thread(mgr.compact_kb_sync, kb_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("Compact KB %s failed", kb_id)
        raise HTTPException(500, str(e)) from e

    return result


# ── 检索命中测试 ──────────────────────────────────────────


class HitTestRequest(BaseModel):
    """检索命中测试请求"""
    query: str
    top_k: int = 5
    similarity_threshold: float = 0.0


@router.post("/{kb_id}/hit-test")
async def hit_test(kb_id: str, req: HitTestRequest):
    """对指定知识库执行检索命中测试

    借鉴 Dify/RAGFlow 检索命中测试页：
    - 输入 query + 检索参数 (top_k, similarity_threshold)
    - 返回命中 chunks 列表 (content, score, metadata, doc_name)

    使用 KBManagerV2.retrieve() 复用现有检索管线
    """
    mgr = get_kb_manager_v2()
    inst = mgr.get(kb_id)
    if not inst:
        raise HTTPException(404, f"知识库 {kb_id} 不存在")

    try:
        result = await mgr.retrieve(
            query=req.query,
            kb_ids=[kb_id],
            top_m_final=req.top_k,
        )
    except Exception as e:
        logger.exception("Hit test KB %s failed: %s", kb_id, e)
        raise HTTPException(500, f"检索失败: {str(e)}") from e

    # 过滤低分结果 + 格式化输出
    hits = []
    for r in result.get("results", []):
        score = r.get("score", 0)
        if score < req.similarity_threshold:
            continue
        meta = r.get("metadata", {})
        hits.append({
            "content": r.get("content", ""),
            "score": round(score, 4),
            "rank": r.get("rank", len(hits) + 1),
            "doc_id": r.get("doc_id", ""),
            "metadata": meta,
            "kb_name": r.get("kb_name", inst.name),
            "source": meta.get("source", meta.get("file_path", "")),
        })

    return {
        "query": req.query,
        "kb_id": kb_id,
        "kb_name": inst.name,
        "total_hits": len(hits),
        "hits": hits,
    }
