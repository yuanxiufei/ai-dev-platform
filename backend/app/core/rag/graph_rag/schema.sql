-- ═══════════════════════════════════════════════════════════════
-- GraphRAG 数据库 Schema
-- 借鉴 SAG migrations/001_init.sql 设计
--
-- 双引擎: SQLite (开发) / PostgreSQL + pgvector (生产)
-- 下方为 SQLite 版本，PostgreSQL 用户请先执行 pgvector 段
-- ═══════════════════════════════════════════════════════════════
--
-- ── PostgreSQL + pgvector 专用 (生产环境) ────────────────────
--   CREATE EXTENSION IF NOT EXISTS vector;
--   ALTER TABLE graph_entities ADD COLUMN embedding vector(1536);
--   ALTER TABLE graph_events  ADD COLUMN title_embedding vector(1536);
--   ALTER TABLE graph_events  ADD COLUMN content_embedding vector(1536);
--   CREATE INDEX ON graph_entities USING hnsw (embedding vector_cosine_ops);
--   CREATE INDEX ON graph_events  USING hnsw (title_embedding vector_cosine_ops);
--   CREATE INDEX ON graph_events  USING hnsw (content_embedding vector_cosine_ops);
-- ─────────────────────────────────────────────────────────────
--
-- 表说明:
--   entity_types     - 实体类型定义 (person, org, concept, ...)
--   graph_entities   - 实体表 (跨文档归一化)
--   graph_events     - 事件表 (chunk 粒度的事件化表达)
--   graph_event_entities - 事件-实体关联表
--   mcp_tool_calls   - MCP 工具调用记录

-- ═══════════════════════════════════════════════════════════
-- 实体类型定义
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS entity_types (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1,
    is_default  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(type)
);

-- 种子数据
INSERT OR IGNORE INTO entity_types (type, display_name, is_default) VALUES
    ('person',     '人物', 0),
    ('org',        '组织', 0),
    ('concept',    '概念', 1),
    ('technology', '技术', 0),
    ('location',   '地点', 0),
    ('product',    '产品', 0),
    ('event',      '事件', 0),
    ('other',      '其他', 0);

-- ═══════════════════════════════════════════════════════════
-- 实体表 (跨文档归一化的命名实体)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS graph_entities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id       TEXT NOT NULL UNIQUE,
    source_id       TEXT NOT NULL,              -- KB ID
    entity_type_id  INTEGER,
    type            TEXT NOT NULL DEFAULT 'concept',
    name            TEXT NOT NULL,
    normalized_name TEXT NOT NULL,              -- 小写归一化名
    description     TEXT NOT NULL DEFAULT '',
    embedding_json  TEXT,                       -- JSON 序列化向量
    
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (entity_type_id) REFERENCES entity_types(id)
);

CREATE INDEX IF NOT EXISTS idx_entities_source ON graph_entities(source_id);
CREATE INDEX IF NOT EXISTS idx_entities_type ON graph_entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_norm_name ON graph_entities(normalized_name);
-- 唯一约束: 同一知识库中同类型同名实体只保留一条
CREATE UNIQUE INDEX IF NOT EXISTS uq_entities_dedup 
    ON graph_entities(source_id, type, normalized_name);

-- ═══════════════════════════════════════════════════════════
-- 事件表 (chunk 粒度的事件化表达)
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS graph_events (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                TEXT NOT NULL UNIQUE,
    source_id               TEXT NOT NULL,
    document_id             TEXT,
    chunk_id                TEXT,
    title                   TEXT NOT NULL,
    summary                 TEXT NOT NULL DEFAULT '',
    content                 TEXT NOT NULL DEFAULT '',
    rank                    INTEGER NOT NULL DEFAULT 0,
    score                   REAL,
    
    title_embedding_json    TEXT,               -- 标题向量
    content_embedding_json  TEXT,               -- 内容向量
    
    deleted_at              TEXT,
    created_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at              TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (source_id) REFERENCES knowledge_bases(kb_id),
    FOREIGN KEY (document_id) REFERENCES kb_documents(doc_id)
);

CREATE INDEX IF NOT EXISTS idx_events_source ON graph_events(source_id);
CREATE INDEX IF NOT EXISTS idx_events_document ON graph_events(document_id);
CREATE INDEX IF NOT EXISTS idx_events_chunk ON graph_events(chunk_id);
CREATE INDEX IF NOT EXISTS idx_events_deleted ON graph_events(deleted_at);

-- ═══════════════════════════════════════════════════════════
-- 事件-实体关联表
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS graph_event_entities (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id    TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    
    FOREIGN KEY (event_id) REFERENCES graph_events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES graph_entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ee_event ON graph_event_entities(event_id);
CREATE INDEX IF NOT EXISTS idx_ee_entity ON graph_event_entities(entity_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_entity 
    ON graph_event_entities(event_id, entity_id);

-- ═══════════════════════════════════════════════════════════
-- MCP 工具调用记录
-- ═══════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS mcp_tool_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id         TEXT NOT NULL UNIQUE,
    session_id      TEXT NOT NULL,
    message_id      TEXT,
    tool_name       TEXT NOT NULL,
    arguments_json  TEXT NOT NULL DEFAULT '{}',
    result_json     TEXT,
    status          TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | SUCCEEDED | FAILED
    duration_ms     REAL,
    error           TEXT,
    
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mcp_tc_session ON mcp_tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tc_tool ON mcp_tool_calls(tool_name);
CREATE INDEX IF NOT EXISTS idx_mcp_tc_status ON mcp_tool_calls(status);
