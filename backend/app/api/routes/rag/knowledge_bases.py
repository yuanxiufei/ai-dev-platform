"""知识库管理 CRUD

端到端流:
    创建 KB → 上传文档 → 自动解析+分块+嵌入 → KB Ready
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/rag/knowledge-bases", tags=["RAG — 知识库"])

logger = logging.getLogger("app.api.rag.kb")


# ── 知识库 CRUD ──────────────────────────────────────────

class CreateKBRequest(BaseModel):
    name: str
    description: str = ""
    chunk_strategy: str = "recursive"  # recursive | markdown | code | fixed
    chunk_size: int = 512
    chunk_overlap: int = 100


@router.get("")
async def list_knowledge_bases():
    """列出所有知识库"""
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    kbs = mgr.list_all()
    return {
        "data": [
            {
                "kb_id": kb.kb_id,
                "name": kb.name,
                "description": kb.description,
                "stats": kb.stats,
                "created_at": str(kb.created_at) if kb.created_at else None,
            }
            for kb in kbs
        ],
        "total": len(kbs),
    }


@router.post("")
async def create_knowledge_base(body: CreateKBRequest):
    """创建新知识库"""
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    kb = await mgr.create(
        name=body.name,
        description=body.description,
        chunk_strategy=body.chunk_strategy,
        chunk_size=body.chunk_size,
        chunk_overlap=body.chunk_overlap,
    )
    return {
        "kb_id": kb.kb_id,
        "name": kb.name,
        "description": kb.description,
        "stats": kb.stats,
    }


@router.get("/{kb_id}")
async def get_knowledge_base(kb_id: str):
    """获取单个知识库详情"""
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    kb = mgr.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")
    return {
        "kb_id": kb.kb_id,
        "name": kb.name,
        "description": kb.description,
        "stats": kb.stats,
        "chunk_strategy": kb.chunk_strategy,
        "chunk_size": kb.chunk_size,
        "created_at": str(kb.created_at) if kb.created_at else None,
    }


@router.delete("/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """删除知识库及其所有索引"""
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    ok = await mgr.delete(kb_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")
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
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    kb = mgr.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

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
            count = await mgr.upload_file(kb, tmp_path, title or file.filename)
        finally:
            os.unlink(tmp_path)

        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "filename": file.filename}

    if url:
        doc_title = title or url.rsplit("/", 1)[-1] or "web_page"
        count = await mgr.upload_url(kb, url, title=doc_title)
        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "url": url}

    if text:
        doc_title = title or "text_snippet"
        count = await mgr.upload_text(kb, text, title=doc_title)
        return {"status": "uploaded", "kb_id": kb_id, "chunks": count, "title": doc_title}

    raise HTTPException(status_code=400, detail="Provide file, text, or url")


@router.post("/{kb_id}/documents/batch")
async def upload_documents_batch(
    kb_id: str,
    files: list[UploadFile] = File(...),
):
    """批量上传文档"""
    from app.core.rag.knowledge_base import get_knowledge_base
    import tempfile
    import os

    mgr = get_knowledge_base()
    kb = mgr.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail=f"Knowledge base '{kb_id}' not found")

    results = []
    for f in files:
        suffix = os.path.splitext(f.filename or "upload.txt")[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await f.read())
            tmp_path = tmp.name

        try:
            count = await mgr.upload_file(kb, tmp_path, f.filename)
            results.append({"filename": f.filename, "chunks": count, "status": "ok"})
        except Exception as e:
            results.append({"filename": f.filename, "status": "error", "error": str(e)})
        finally:
            os.unlink(tmp_path)

    return {"kb_id": kb_id, "results": results}
