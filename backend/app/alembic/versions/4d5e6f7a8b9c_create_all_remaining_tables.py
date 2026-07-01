"""create all remaining tables (22 tables previously only created via create_all)

Revision ID: 4d5e6f7a8b9c
Revises: 3c4d5e6f7a8b
Create Date: 2025-07-01 06:20:00.000000

This migration creates all tables that were previously only initialized
via SQLModel.metadata.create_all() in db.py, bringing Alembic coverage
from 18.5% (5/27) to 100% (27/27).

Tables created (in dependency order):
  Group A — user-dependent: rules, integrations, agent_configs, model_downloads,
           model_usage_stats, api_credentials, model_presets, arena_comparisons,
           model_usage_logs, memory_entries, studio_templates
  Group B — chain-dependent: studio_projects, arena_votes, elo_rankings
  Group C — deeper chain: chat_sessions, video_tasks, agent_traces
  Group D — leaf nodes: chat_messages, video_assets, agent_tool_calls,
           agent_file_changes, agent_execution_logs
"""
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers
revision = "4d5e6f7a8b9c"
down_revision = "3c4d5e6f7a8b"
branch_labels = None
depends_on = None


def upgrade():
    # ═══ Group A: tables with only `user` foreign keys ═══

    op.create_table(
        "rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("triggers", sa.Text(), nullable=True),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_rules_user_id"), "rules", ["user_id"])

    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_integrations_user_id"), "integrations", ["user_id"])

    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("agentic_mode", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("tools", sa.Text(), nullable=True),
        sa.Column("tool_categories", sa.Text(), nullable=True),
        sa.Column("mcp_servers", sa.Text(), nullable=True),
        sa.Column("auto_run", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_agent_configs_project_id"), "agent_configs", ["project_id"])
    op.create_index(op.f("ix_agent_configs_user_id"), "agent_configs", ["user_id"])

    op.create_table(
        "model_downloads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("downloaded", sa.Integer(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["started_by"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_model_downloads_started_by"), "model_downloads", ["started_by"])

    op.create_table(
        "model_usage_stats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_model_usage_stats_user_id"), "model_usage_stats", ["user_id"])

    op.create_table(
        "api_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_api_credentials_owner_id"), "api_credentials", ["owner_id"])
    op.create_index(op.f("ix_api_credentials_provider"), "api_credentials", ["provider"])

    op.create_table(
        "model_presets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("tools", sa.Text(), nullable=True),
        sa.Column("force_tools", sa.Boolean(), nullable=False),
        sa.Column("knowledge_bases", sa.Text(), nullable=True),
        sa.Column("variables", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "arena_comparisons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("model_a", sa.String(length=100), nullable=False),
        sa.Column("response_a", sa.Text(), nullable=False),
        sa.Column("latency_a_ms", sa.Float(), nullable=True),
        sa.Column("tokens_a", sa.Integer(), nullable=True),
        sa.Column("model_b", sa.String(length=100), nullable=False),
        sa.Column("response_b", sa.Text(), nullable=False),
        sa.Column("latency_b_ms", sa.Float(), nullable=True),
        sa.Column("tokens_b", sa.Integer(), nullable=True),
        sa.Column("winner", sa.String(length=10), nullable=True),
        sa.Column("voter_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["voter_id"], ["user.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "model_usage_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("capability", sa.String(length=50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_model_usage_logs_model_name"), "model_usage_logs", ["model_name"])
    op.create_index(op.f("ix_model_usage_logs_provider"), "model_usage_logs", ["provider"])
    op.create_index(op.f("ix_model_usage_logs_capability"), "model_usage_logs", ["capability"])
    op.create_index(op.f("ix_model_usage_logs_created_at"), "model_usage_logs", ["created_at"])

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=500), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("access_count", sa.Integer(), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frontmatter_tags", sa.Text(), nullable=True),
        sa.Column("frontmatter_aliases", sa.Text(), nullable=True),
        sa.Column("frontmatter_status", sa.String(length=50), nullable=True),
        sa.Column("frontmatter_priority", sa.String(length=20), nullable=True),
        sa.Column("frontmatter_due_date", sa.String(length=30), nullable=True),
        sa.Column("frontmatter_extra", sa.Text(), nullable=True),
        sa.Column("forward_links", sa.Text(), nullable=True),
        sa.Column("linked_from", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "studio_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column("stack", sa.String(length=100), nullable=True),
        sa.Column("preview_url", sa.String(length=500), nullable=True),
        sa.Column("template_data", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
    )

    # ═══ Group B: tables depending on Group A ═══

    op.create_table(
        "studio_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column("stack", sa.String(length=100), nullable=True),
        sa.Column("template_id", sa.Uuid(), nullable=True),
        sa.Column("generated_code", sa.Text(), nullable=True),
        sa.Column("build_log", sa.Text(), nullable=True),
        sa.Column("deploy_url", sa.String(length=500), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["studio_templates.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_studio_projects_owner_id"), "studio_projects", ["owner_id"])
    op.create_index(op.f("ix_studio_projects_template_id"), "studio_projects", ["template_id"])

    op.create_table(
        "arena_votes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("comparison_id", sa.Uuid(), nullable=False),
        sa.Column("model_won", sa.String(length=100), nullable=False),
        sa.Column("model_lost", sa.String(length=100), nullable=False),
        sa.Column("elo_before_winner", sa.Float(), nullable=False),
        sa.Column("elo_before_loser", sa.Float(), nullable=False),
        sa.Column("elo_after_winner", sa.Float(), nullable=False),
        sa.Column("elo_after_loser", sa.Float(), nullable=False),
        sa.Column("voter_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["comparison_id"], ["arena_comparisons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["voter_id"], ["user.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "model_elo_rankings",
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("elo", sa.Float(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("ties", sa.Integer(), nullable=False),
        sa.Column("total_comparisons", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("model_name"),
    )

    # ═══ Group C: tables depending on prior groups ═══

    op.create_table(
        "video_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("params", sa.Text(), nullable=True),
        sa.Column("output_path", sa.String(length=500), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_video_tasks_owner_id"), "video_tasks", ["owner_id"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["studio_projects.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_chat_sessions_owner_id"), "chat_sessions", ["owner_id"])
    op.create_index(op.f("ix_chat_sessions_project_id"), "chat_sessions", ["project_id"])

    op.create_table(
        "agent_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("total_tool_calls", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Float(), nullable=False),
        sa.Column("final_model", sa.String(length=100), nullable=False),
        sa.Column("final_provider", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cancelled", sa.Boolean(), nullable=False),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_agent_traces_agent_id"), "agent_traces", ["agent_id"])
    op.create_index(op.f("ix_agent_traces_status"), "agent_traces", ["status"])

    # ═══ Group D: leaf-node tables (deepest dependencies) ═══

    op.create_table(
        "video_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_path", sa.String(length=500), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["video_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_video_assets_owner_id"), "video_assets", ["owner_id"])
    op.create_index(op.f("ix_video_assets_task_id"), "video_assets", ["task_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_call_id", sa.String(length=200), nullable=True),
        sa.Column("tool_calls", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"])

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("tool_call_id", sa.String(length=100), nullable=False),
        sa.Column("arguments", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("result_full", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("sandbox_mode", sa.String(length=20), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trace_id"], ["agent_traces.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_agent_tool_calls_trace_id"), "agent_tool_calls", ["trace_id"])
    op.create_index(op.f("ix_agent_tool_calls_tool_call_id"), "agent_tool_calls", ["tool_call_id"])

    op.create_table(
        "agent_file_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tool_call_id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("file_path", sa.String(length=2000), nullable=False),
        sa.Column("change_type", sa.String(length=20), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("content_before", sa.Text(), nullable=True),
        sa.Column("content_after", sa.Text(), nullable=True),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("file_size_before", sa.Integer(), nullable=True),
        sa.Column("file_size_after", sa.Integer(), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["agent_tool_calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trace_id"], ["agent_traces.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_agent_file_changes_tool_call_id"), "agent_file_changes", ["tool_call_id"])
    op.create_index(op.f("ix_agent_file_changes_trace_id"), "agent_file_changes", ["trace_id"])

    op.create_table(
        "agent_execution_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=True),
        sa.Column("tool_call_id", sa.Uuid(), nullable=True),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(length=30), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("exec_context", sa.Text(), nullable=True),
        sa.Column("extra_metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trace_id"], ["agent_traces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tool_call_id"], ["agent_tool_calls.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_agent_execution_logs_trace_id"), "agent_execution_logs", ["trace_id"])
    op.create_index(op.f("ix_agent_execution_logs_tool_call_id"), "agent_execution_logs", ["tool_call_id"])


def downgrade():
    """Drop all tables in reverse dependency order."""
    op.drop_index(op.f("ix_agent_execution_logs_tool_call_id"), table_name="agent_execution_logs")
    op.drop_index(op.f("ix_agent_execution_logs_trace_id"), table_name="agent_execution_logs")
    op.drop_table("agent_execution_logs")

    op.drop_index(op.f("ix_agent_file_changes_trace_id"), table_name="agent_file_changes")
    op.drop_index(op.f("ix_agent_file_changes_tool_call_id"), table_name="agent_file_changes")
    op.drop_table("agent_file_changes")

    op.drop_index(op.f("ix_agent_tool_calls_tool_call_id"), table_name="agent_tool_calls")
    op.drop_index(op.f("ix_agent_tool_calls_trace_id"), table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")

    op.drop_index(op.f("ix_chat_messages_session_id"), table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(op.f("ix_video_assets_task_id"), table_name="video_assets")
    op.drop_index(op.f("ix_video_assets_owner_id"), table_name="video_assets")
    op.drop_table("video_assets")

    op.drop_index(op.f("ix_agent_traces_status"), table_name="agent_traces")
    op.drop_index(op.f("ix_agent_traces_agent_id"), table_name="agent_traces")
    op.drop_table("agent_traces")

    op.drop_index(op.f("ix_chat_sessions_project_id"), table_name="chat_sessions")
    op.drop_index(op.f("ix_chat_sessions_owner_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_index(op.f("ix_video_tasks_owner_id"), table_name="video_tasks")
    op.drop_table("video_tasks")

    op.drop_table("model_elo_rankings")

    op.drop_table("arena_votes")

    op.drop_index(op.f("ix_studio_projects_template_id"), table_name="studio_projects")
    op.drop_index(op.f("ix_studio_projects_owner_id"), table_name="studio_projects")
    op.drop_table("studio_projects")

    op.drop_table("studio_templates")

    op.drop_table("memory_entries")

    op.drop_index(op.f("ix_model_usage_logs_created_at"), table_name="model_usage_logs")
    op.drop_index(op.f("ix_model_usage_logs_capability"), table_name="model_usage_logs")
    op.drop_index(op.f("ix_model_usage_logs_provider"), table_name="model_usage_logs")
    op.drop_index(op.f("ix_model_usage_logs_model_name"), table_name="model_usage_logs")
    op.drop_table("model_usage_logs")

    op.drop_table("arena_comparisons")

    op.drop_table("model_presets")

    op.drop_index(op.f("ix_api_credentials_provider"), table_name="api_credentials")
    op.drop_index(op.f("ix_api_credentials_owner_id"), table_name="api_credentials")
    op.drop_table("api_credentials")

    op.drop_index(op.f("ix_model_usage_stats_user_id"), table_name="model_usage_stats")
    op.drop_table("model_usage_stats")

    op.drop_index(op.f("ix_model_downloads_started_by"), table_name="model_downloads")
    op.drop_table("model_downloads")

    op.drop_index(op.f("ix_agent_configs_user_id"), table_name="agent_configs")
    op.drop_index(op.f("ix_agent_configs_project_id"), table_name="agent_configs")
    op.drop_table("agent_configs")

    op.drop_index(op.f("ix_integrations_user_id"), table_name="integrations")
    op.drop_table("integrations")

    op.drop_index(op.f("ix_rules_user_id"), table_name="rules")
    op.drop_table("rules")
