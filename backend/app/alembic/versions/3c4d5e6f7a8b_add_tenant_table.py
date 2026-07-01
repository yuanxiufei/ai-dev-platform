"""add tenant table and tenant_id on user

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e6f7a
Create Date: 2025-07-01 06:10:00.000000

"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers
revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e6f7a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_tenant_slug"), "tenant", ["slug"], unique=True)

    op.add_column("user", sa.Column("tenant_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_user_tenant_id"), "user", ["tenant_id"])
    op.create_foreign_key(
        "fk_user_tenant_id", "user", "tenant", ["tenant_id"], ["id"], ondelete="SET NULL"
    )


def downgrade():
    op.drop_constraint("fk_user_tenant_id", "user", type_="foreignkey")
    op.drop_index(op.f("ix_user_tenant_id"), table_name="user")
    op.drop_column("user", "tenant_id")

    op.drop_index(op.f("ix_tenant_slug"), table_name="tenant")
    op.drop_table("tenant")
