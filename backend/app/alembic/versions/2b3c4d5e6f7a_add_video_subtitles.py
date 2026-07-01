"""add video_subtitles and subtitle_cues

Revision ID: 2b3c4d5e6f7a
Revises: fe56fa70289e
Create Date: 2025-07-01 06:00:00.000000

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision = "2b3c4d5e6f7a"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "video_subtitles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["video_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_video_subtitles_video_id"), "video_subtitles", ["video_id"])
    op.create_index(op.f("ix_video_subtitles_language"), "video_subtitles", ["language"])

    op.create_table(
        "subtitle_cues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subtitle_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["subtitle_id"], ["video_subtitles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subtitle_cues_subtitle_id"), "subtitle_cues", ["subtitle_id"])


def downgrade():
    op.drop_index(op.f("ix_subtitle_cues_subtitle_id"), table_name="subtitle_cues")
    op.drop_table("subtitle_cues")
    op.drop_index(op.f("ix_video_subtitles_language"), table_name="video_subtitles")
    op.drop_index(op.f("ix_video_subtitles_video_id"), table_name="video_subtitles")
    op.drop_table("video_subtitles")
