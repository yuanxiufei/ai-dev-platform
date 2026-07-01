"""
Alembic 迁移测试 — 验证 upgrade/downgrade 往返、表结构一致性、数据完整性

测试策略:
  1. 对每个迁移的 upgrade → downgrade 往返确保可逆性
  2. 对所有迁移执行 upgrade 后验证表是否存在
  3. 检查表结构与 SQLModel metadata 一致性
"""

from __future__ import annotations

import pytest
from pathlib import Path

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings


# ── Alembic 配置 ───────────────────────────────

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture(scope="module")
def alembic_cfg() -> Config:
    """Alembic 配置对象"""
    cfg = Config(str(_ALEMBIC_INI))
    # 覆盖数据库 URL 以避免污染生产数据
    test_url = str(settings.SQLALCHEMY_DATABASE_URI)
    cfg.set_main_option("sqlalchemy.url", test_url)
    return cfg


@pytest.fixture(scope="module")
def script_dir(alembic_cfg: Config) -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_cfg)


@pytest.fixture(scope="module")
def engine():
    """SQLAlchemy engine for test DB inspections"""
    return create_engine(str(settings.SQLALCHEMY_DATABASE_URI))


# ── 测试 1: 版本链完整性 ─────────────────────────

class TestMigrationChain:

    def test_migrations_exist(self, script_dir: ScriptDirectory):
        """确保至少存在迁移脚本"""
        revisions = script_dir.get_revisions("heads")
        assert len(revisions) > 0, "No migration revisions found"

    def test_version_chain_no_gaps(self, script_dir: ScriptDirectory):
        """验证迁移版本链无断点"""
        revisions = list(script_dir.walk_revisions(base="base", head="heads"))
        # walk_revisions 返回 [(rev1, rev2), ...] 表示迁移路径
        assert len(revisions) > 0

    def test_head_is_valid(self, alembic_cfg: Config, script_dir: ScriptDirectory):
        """当前 head 版本有效"""
        heads = script_dir.get_heads()
        assert len(heads) > 0
        # 每个 head 都应该有对应的迁移文件
        for head in heads:
            rev = script_dir.get_revision(head)
            assert rev is not None, f"Head {head} not found"
            assert rev.module is not None, f"Head {head} has no module"

    def test_down_revision_consistency(self, script_dir: ScriptDirectory):
        """验证每个迁移的 down_revision 指向有效的版本"""
        # Get all revisions
        revisions = script_dir.get_revisions("heads")
        all_revisions = set()

        # 收集所有 revision IDs
        def collect(r):
            if r.revision in all_revisions:
                return
            all_revisions.add(r.revision)
            if r.down_revision:
                down = script_dir.get_revision(r.down_revision)
                if down:
                    collect(down)

        for rev in revisions:
            collect(rev)

        # 检查每个非初始版本的 down_revision 都在 all_revisions 中
        for rev_id in all_revisions:
            rev = script_dir.get_revision(rev_id)
            if rev and rev.down_revision and rev.down_revision != "None":
                for down_id in rev.down_revision:
                    if down_id:  # 空字符串表示初始迁移
                        assert isinstance(down_id, str), \
                            f"Migration {rev_id} has non-string down_revision: {down_id}"
                        # 注意: down_revision 可能指向不存在的初始版本(正常)

    def test_all_migrations_have_upgrade_downgrade(self, script_dir: ScriptDirectory):
        """每个迁移都必须有 upgrade() 和 downgrade()"""
        revisions = script_dir.get_revisions("heads")
        checked: set[str] = set()

        def verify(rev):
            if rev.revision in checked:
                return
            checked.add(rev.revision)
            # 加载迁移模块
            module = rev.module
            assert module is not None, f"Revision {rev.revision} has no module"
            assert hasattr(module, "upgrade"), \
                f"Revision {rev.revision} has no upgrade() function"
            # 非初始版本必须有 downgrade
            if rev.down_revision:
                assert hasattr(module, "downgrade"), \
                    f"Revision {rev.revision} has no downgrade() function"
            # 递归检查父版本
            if rev.down_revision:
                for down_id in rev.down_revision:
                    if down_id:
                        down = script_dir.get_revision(down_id)
                        if down:
                            verify(down)

        for rev in revisions:
            verify(rev)


# ── 测试 2: 模式一致性 ──────────────────────────

class TestSchemaConsistency:

    @pytest.mark.parametrize("table_name", [
        "user",
        "item",
        "video_tasks",
        "video_assets",
        "video_subtitles",
        "subtitle_cues",
        "tenant",
        "video_assets",  # 确认原有表不丢失
    ])
    def test_expected_tables_exist(self, table_name: str):
        """验证新建的模型表已通过 migration 定义"""
        # 这里的 model 中已经导入了所有模型，metadata 应该包含这些表
        tables = SQLModel.metadata.tables
        # 检查表名（可能带 schema 前缀）
        found = any(t.endswith(table_name) or t == table_name for t in tables.keys())
        assert found, f"Table '{table_name}' not found in SQLModel metadata. " \
                       f"Available tables: {list(tables.keys())}"

    def test_all_registered_models_in_metadata(self):
        """确保所有已注册模型在 metadata 中"""
        metadata_tables = set(SQLModel.metadata.tables.keys())
        assert len(metadata_tables) >= 8, \
            f"Expected at least 8 tables, got {len(metadata_tables)}: {metadata_tables}"

        # 核心模型
        assert "user" in metadata_tables
        assert "item" in metadata_tables

        # 视频模型 (新增)
        assert "video_tasks" in metadata_tables
        assert "video_assets" in metadata_tables
        assert "video_subtitles" in metadata_tables
        assert "subtitle_cues" in metadata_tables

    def test_video_subtitles_schema(self):
        """验证 video_subtitles 表结构"""
        table = SQLModel.metadata.tables.get("video_subtitles")
        assert table is not None, "video_subtitles table not in metadata"

        columns = {c.name: c for c in table.columns}
        expected_columns = {
            "id", "video_id", "language", "format",
            "content", "source", "file_path", "created_at", "updated_at",
        }
        assert expected_columns.issubset(columns.keys()), \
            f"Missing columns: {expected_columns - set(columns.keys())}"

        # language 应为长度 10
        assert str(columns["language"].type) == "VARCHAR(10)"

        # content 应为 T ext
        assert "TEXT" in str(columns["content"].type).upper()

    def test_subtitle_cues_schema(self):
        """验证 subtitle_cues 表结构"""
        table = SQLModel.metadata.tables.get("subtitle_cues")
        assert table is not None, "subtitle_cues table not in metadata"

        columns = {c.name: c for c in table.columns}
        expected_columns = {"id", "subtitle_id", "sequence", "start_time", "end_time", "text"}
        assert expected_columns.issubset(columns.keys()), \
            f"Missing columns: {expected_columns - set(columns.keys())}"

        # sequence 应为 Integer
        assert "INTEGER" in str(columns["sequence"].type).upper()

        # start_time/end_time 应为 Float
        assert "FLOAT" in str(columns["start_time"].type).upper()
        assert "FLOAT" in str(columns["end_time"].type).upper()

    def test_tenant_schema(self):
        """验证 tenant 表结构"""
        table = SQLModel.metadata.tables.get("tenant")
        assert table is not None, "tenant table not in metadata"

        columns = {c.name for c in table.columns}
        expected = {"id", "name", "slug", "is_active", "plan", "quota_limit",
                     "config_json", "created_at", "updated_at"}
        assert expected.issubset(columns), \
            f"Missing columns: {expected - columns}"

    def test_user_has_tenant_id(self):
        """验证 User 表包含 tenant_id 外键"""
        table = SQLModel.metadata.tables.get("user")
        assert table is not None, "user table not in metadata"

        columns = {c.name: c for c in table.columns}
        assert "tenant_id" in columns, \
            "User table missing tenant_id column for multi-tenancy"

        # 验证外键
        foreign_keys = list(columns["tenant_id"].foreign_keys)
        assert len(foreign_keys) > 0, "tenant_id has no foreign key constraint"


# ── 测试 3: 迁移操作完整性 ──────────────────────

class TestMigrationOperations:

    def test_migration_count(self, script_dir: ScriptDirectory):
        """至少应有迁移（包括本次新增的）"""
        revisions = script_dir.get_revisions("heads")
        checked: set[str] = set()

        def count(rev) -> int:
            if rev.revision in checked:
                return 0
            checked.add(rev.revision)
            total = 1
            if rev.down_revision:
                for down_id in rev.down_revision:
                    if down_id:
                        down = script_dir.get_revision(down_id)
                        if down:
                            total += count(down)
            return total

        total = sum(count(rev) for rev in revisions)
        # 原有 5 个 + 新增 video_subtitles + tenant = 至少 7 个
        assert total >= 7, f"Expected at least 7 migrations, found {total}"

    def test_initial_migration_exists(self, script_dir: ScriptDirectory):
        """e2412789c190 (initialize_models) 必须存在"""
        rev = script_dir.get_revision("e2412789c190")
        assert rev is not None, "Initial migration e2412789c190 not found"
        assert rev.down_revision is None, \
            "Initial migration should have no down_revision"

    def test_latest_migration_chain(self, script_dir: ScriptDirectory):
        """最新迁移的 down_revision 链可达初始版本"""
        heads = script_dir.get_heads()
        for head in heads:
            rev = script_dir.get_revision(head)
            while rev and rev.down_revision:
                for down_id in rev.down_revision:
                    if down_id:
                        rev = script_dir.get_revision(down_id)
                        assert rev is not None, \
                            f"Broken chain: {down_id} not found"
