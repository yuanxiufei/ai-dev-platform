"""
元数据 Segment — PostgreSQL tsvector 全文索引

元数据表: (doc_id, content, metadata JSONB, tsv)
- PostgreSQL tsvector + GIN 索引实现全文检索
- query() 双模式: 全文搜索 / LIKE 降级
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

import psycopg

from app.core.rag.segments import Segment

logger = logging.getLogger("app.core.rag.segments.metadata")

# ── PG DSN 兜底：直接从 .env / 环境变量读取，确保始终用同一个数据库 ──


def _get_pg_dsn() -> str:
    """从环境变量直接读取 PostgreSQL DSN，兜底 callers 传入空串

    读取策略（与 app.core.config.settings.PG_DSN 等价）:
    1. PG_DSN 环境变量（直接指定）
    2. DATABASE_URL（转换为 postgresql:// 格式）
    3. POSTGRES_{SERVER,PORT,USER,PASSWORD,DB} + PG_SSLMODE 拼接

    保证 metadata_segment 即使在没有 settings 导入的上下文中，
    也始终连接正确的数据库，而非默认 localhost:5432 等错误目标。
    """
    # 1) 直接指定 PG_DSN
    pg_dsn = os.getenv("PG_DSN", "").strip()
    if pg_dsn:
        return _ensure_sslmode(pg_dsn)

    # 2) DATABASE_URL → 转为 postgresql:// (去掉 +asyncpg/+psycopg 前缀)
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if database_url.startswith("sqlite://"):
            # SQLite DSN 不适用于 PG，跳过让 POSTGRES_* 拼接生效
            pass
        else:
            url = database_url
            for scheme in ("postgresql+asyncpg://", "postgresql+psycopg://"):
                if url.startswith(scheme):
                    url = "postgresql://" + url[len(scheme):]
                    break
            return _ensure_sslmode(url)

    # 3) POSTGRES_* 拼接
    host = os.getenv("POSTGRES_SERVER", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "admin")
    password = os.getenv("POSTGRES_PASSWORD", "")
    db = os.getenv("POSTGRES_DB", "studio")

    dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return _ensure_sslmode(dsn)


def _ensure_sslmode(dsn: str) -> str:
    """确保 DSN 包含 sslmode 参数，默认 disable（WSL Docker 网络环境）"""
    if "sslmode=" in dsn:
        return dsn
    sslmode = os.getenv("PG_SSLMODE", "disable")
    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}sslmode={sslmode}"


class MetadataSegment(Segment):
    """PostgreSQL 元数据存储 + tsvector 全文索引

    实现 Segment ABC:
    - add(ids, records)    → 批量 INSERT ... ON CONFLICT + tsvector 更新
    - get(ids)             → SELECT by doc_id
    - delete(ids)          → DELETE
    - query(keyword, k)    → tsvector @@ tsquery (全文搜索模式)
    - query(vector, k)     → 不支持 (向量搜索走 VectorSegment)
    """

    _DDL_EXECUTED: set[str] = set()  # 类级 DDL 去重 (每个 DSN 只建表一次)

    def __init__(self, pg_dsn: str = "", scope: str = "default"):
        """初始化 PostgreSQL 元数据段

        Args:
            pg_dsn: PostgreSQL 连接字符串。若为空，从 .env / 环境变量自动读取
            scope: 段作用域标识
        """
        super().__init__(name="metadata", scope=scope)
        self._pg_dsn = pg_dsn or _get_pg_dsn()
        self._lock = threading.Lock()
        self._fts_available = True
        self._pg_unavailable = False  # PG 不可用时优雅降级，而非抛 500
        self._init_db()

    # ── 数据库初始化 ─────────────────────────────────────

    def _get_conn(self) -> "psycopg.Connection":
        """创建新的 psycopg 连接"""
        conn = psycopg.connect(self._pg_dsn, autocommit=False)
        return conn

    def _ensure_ddl(self, conn):
        """确保表结构存在（DDL 去重：每个 DSN 仅执行一次）"""
        if self._pg_dsn in self._DDL_EXECUTED:
            return

        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                doc_id TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                search_text TEXT,
                tsv tsvector GENERATED ALWAYS AS (
                    to_tsvector('simple', COALESCE(search_text, ''))
                ) STORED,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_doc_id
            ON documents(doc_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_tsv
            ON documents USING GIN(tsv)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_metadata
            ON documents USING GIN(metadata)
        """)
        conn.commit()

        self._DDL_EXECUTED.add(self._pg_dsn)
        logger.info("MetadataSegment DDL ensured (PG: %s...)", self._pg_dsn[:50])

    def _init_db(self):
        """初始化数据库表结构"""
        with self._lock:
            try:
                conn = self._get_conn()
            except Exception as e:
                logger.warning(
                    "MetadataSegment PG 连接失败，元数据搜索不可用：%s", e
                )
                self._fts_available = False
                self._pg_unavailable = True
                return
            try:
                self._ensure_ddl(conn)
            except Exception as e:
                logger.warning("MetadataSegment DDL failed: %s, FTS disabled", e)
                self._fts_available = False
            finally:
                conn.close()

    # ── Segment ABC 实现 ─────────────────────────────────

    def add(self, ids: list[str], records: list[dict]) -> int:
        """批量添加元数据记录"""
        if self._pg_unavailable or not ids or not records:
            return 0

        with self._lock:
            conn = self._get_conn()
            n = 0
            try:
                for rec_id, rec in zip(ids, records):
                    content = rec.get("content", "")
                    meta = rec.get("metadata", {})
                    doc_id = rec.get("doc_id", rec_id)
                    search_text = self._tokenize_for_tsv(content)

                    try:
                        conn.execute(
                            "INSERT INTO documents (doc_id, content, search_text, metadata) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (doc_id) DO UPDATE SET "
                            "content = EXCLUDED.content, "
                            "search_text = EXCLUDED.search_text, "
                            "metadata = EXCLUDED.metadata",
                            (doc_id, content, search_text, json.dumps(meta)),
                        )
                        n += 1
                    except Exception as e:
                        logger.warning(
                            "MetadataSegment.add failed for %s: %s", doc_id, e
                        )

                conn.commit()
                return n
            finally:
                conn.close()

    def get(self, ids: list[str]) -> dict[str, dict]:
        """批量查询元数据"""
        if self._pg_unavailable or not ids:
            return {}

        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "SELECT doc_id, content, metadata FROM documents "
                    "WHERE doc_id = ANY(%s)",
                    (ids,),
                )
                rows = cur.fetchall()
            finally:
                conn.close()

        return {
            row[0]: {"content": row[1], "metadata": row[2] if isinstance(row[2], dict) else json.loads(str(row[2]))}
            for row in rows
        }

    def delete(self, ids: list[str]) -> int:
        """批量删除元数据"""
        if self._pg_unavailable or not ids:
            return 0

        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM documents WHERE doc_id = ANY(%s)",
                    (ids,),
                )
                n = cur.rowcount
                conn.commit()
                return n
            finally:
                conn.close()

    def count(self) -> int:
        if self._pg_unavailable:
            return 0
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
                return row[0] if row else 0
            finally:
                conn.close()

    def clear(self):
        if self._pg_unavailable:
            return
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM documents")
                conn.commit()
            finally:
                conn.close()

    def close(self):
        pass

    # ── tsvector 全文检索 ────────────────────────────────

    def query(
        self, keyword: str, limit: int = 20, filter_dict: dict | None = None,
    ) -> list[dict]:
        """tsvector 全文搜索 (按 keyword)，支持 WhereFilter 元数据过滤

        Args:
            keyword: 搜索关键词
            limit: 返回数量
            filter_dict: 元数据过滤条件 (WhereFilter DSL)

        Returns:
            [{"doc_id": ..., "content": ..., "metadata": {...}, "score": 0.0-1.0}, ...]
        """
        if self._pg_unavailable or not keyword or not self._fts_available:
            return []

        tokens = self._tokenize(keyword)
        if not tokens:
            return []

        # 构建 tsquery：token1 | token2 | token3 (OR 语义)
        escaped = [t.replace("'", "''").replace("\\", "\\\\") for t in tokens]
        ts_query_str = " | ".join(escaped)

        where_clause, where_params = self._build_filter_clause(filter_dict)

        # pg tsquery 占位符用 %s
        sql = (
            "SELECT d.doc_id, d.content, d.metadata, "
            "ts_rank(d.tsv, to_tsquery('simple', %s)) AS rank "
            "FROM documents d "
            "WHERE d.tsv @@ to_tsquery('simple', %s)"
        )
        params: list = [ts_query_str, ts_query_str]

        if where_clause:
            sql += f" AND {where_clause}"
            params.extend(where_params)

        sql += " ORDER BY rank DESC LIMIT %s"
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception as e:
                logger.warning("tsquery search failed: %s, fallback to LIKE", e)
                conn.close()
                return self._fallback_like_search(keyword, limit, filter_dict)
            finally:
                conn.close()

        results = []
        ranks = [r[3] for r in rows if r[3] is not None]
        max_rank = max(ranks) if ranks else 1

        for r in rows:
            score = (
                r[3] / (max_rank + 1e-6) if r[3] and max_rank > 0 else 0.5
            )
            meta = r[2]
            if isinstance(meta, str):
                meta = json.loads(meta)
            results.append({
                "doc_id": r[0],
                "content": r[1],
                "metadata": meta if meta else {},
                "score": round(score, 4),
            })
        return results

    def _fallback_like_search(
        self, keyword: str, limit: int = 20, filter_dict: dict | None = None,
    ) -> list[dict]:
        """ILIKE 降级搜索，支持元数据过滤"""
        where_clause, where_params = self._build_filter_clause(filter_dict)

        pattern = f"%{keyword}%"
        params: list = [pattern]
        if where_clause:
            params.extend(where_params)

        sql = (
            "SELECT doc_id, content, metadata FROM documents "
            "WHERE content ILIKE %s"
        )
        if where_clause:
            sql += f" AND {where_clause}"
        sql += " LIMIT %s"
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()

        return [
            {
                "doc_id": r[0],
                "content": r[1],
                "metadata": r[2] if isinstance(r[2], dict) else (json.loads(str(r[2])) if r[2] else {}),
                "score": 0.3,
            }
            for r in rows
        ]

    @staticmethod
    def _build_filter_clause(filter_dict: dict | None) -> tuple[str, list]:
        """将 WhereFilter DSL 转为 SQL WHERE 片段（不含 WHERE 关键字）"""
        if not filter_dict:
            return "", []
        from app.core.rag.filters import WhereFilter
        full_where, params = WhereFilter.to_sql(filter_dict)
        if not full_where:
            return "", []
        return full_where[6:], params

    # ── 分词 ─────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中文分词 + 去停用词"""
        try:
            import jieba
            stopwords = {
                "的", "了", "在", "是", "我", "有", "和", "就",
                "不", "人", "都", "一", "一个", "上", "也", "很",
                "到", "说", "要", "去", "你", "会", "着", "没有",
                "看", "好", "自己", "这",
            }
            words = jieba.lcut(text)
            return [w for w in words if len(w) > 1 and w not in stopwords][:20]
        except ImportError:
            return text.lower().split()[:20]

    @staticmethod
    def _tokenize_for_tsv(text: str) -> str:
        """分词后用空格连接，供 PostgreSQL to_tsvector('simple', ...) 使用"""
        tokens = MetadataSegment._tokenize(text)
        return " ".join(tokens)

    # ── 分页列出 Chunk ────────────────────────────────────

    def list_chunks_paginated(
        self, doc_filter_id: str = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[dict], int]:
        """分页列出 chunk，支持按 doc_id 过滤

        Returns:
            (chunks, total_count)
        """
        if self._pg_unavailable:
            return [], 0
        with self._lock:
            conn = self._get_conn()
            try:
                if doc_filter_id:
                    count_sql = (
                        "SELECT COUNT(*) FROM documents "
                        "WHERE metadata->>'_doc_id' = %s"
                    )
                    data_sql = (
                        "SELECT doc_id, content, metadata FROM documents "
                        "WHERE metadata->>'_doc_id' = %s "
                        "ORDER BY id LIMIT %s OFFSET %s"
                    )
                    total = conn.execute(count_sql, (doc_filter_id,)).fetchone()[0]
                    rows = conn.execute(
                        data_sql, (doc_filter_id, limit, skip)
                    ).fetchall()
                else:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM documents"
                    ).fetchone()[0]
                    rows = conn.execute(
                        "SELECT doc_id, content, metadata FROM documents "
                        "ORDER BY id LIMIT %s OFFSET %s",
                        (limit, skip),
                    ).fetchall()
            finally:
                conn.close()

        chunks = [
            {
                "doc_id": r[0],
                "content": r[1],
                "metadata": r[2] if isinstance(r[2], dict) else (json.loads(str(r[2])) if r[2] else {}),
            }
            for r in rows
        ]
        return chunks, total

    # ── 辅助方法 ─────────────────────────────────────────

    def get_all_ids(self) -> list[str]:
        """获取所有 doc_id"""
        if self._pg_unavailable:
            return []
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT doc_id FROM documents").fetchall()
                return [r[0] for r in rows]
            finally:
                conn.close()

    def search_by_metadata(
        self, field: str, value: Any, limit: int = 50,
    ) -> list[dict]:
        """按元数据字段过滤 (JSONB 查询)

        Args:
            field: metadata JSONB 中的 key
            value: 过滤值
            limit: 返回数量
        """
        if self._pg_unavailable:
            return []
        json_path = f"$.{field}"
        param_val = json.dumps(value) if not isinstance(value, str) else value

        with self._lock:
            conn = self._get_conn()
            try:
                # PostgreSQL jsonb 路径提取
                rows = conn.execute(
                    "SELECT doc_id, content, metadata FROM documents "
                    "WHERE metadata#>>%s = %s "
                    "LIMIT %s",
                    (f"{{{field}}}", param_val, limit),
                ).fetchall()
            finally:
                conn.close()

        return [
            {
                "doc_id": r[0],
                "content": r[1],
                "metadata": r[2] if isinstance(r[2], dict) else (json.loads(str(r[2])) if r[2] else {}),
            }
            for r in rows
        ]
