"""initial schema — 7 tables

Revision ID: 0001
Revises:
Create Date: 2026-04-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("clerk_user_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("clerk_user_id"),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_teams_slug", "teams", ["slug"])

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("git_remote_url", sa.String(512), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("team_id", "slug", name="uq_project_team_slug"),
    )
    op.create_index("ix_projects_team_id", "projects", ["team_id"])

    op.create_table(
        "fixes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("content_hash", sa.String(16), nullable=False),
        sa.Column("issue", sa.Text, nullable=False),
        sa.Column("resolution", sa.Text, nullable=False),
        sa.Column("error_excerpt", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("author", sa.String(128), nullable=True),
        sa.Column("author_email", sa.String(320), nullable=True),
        sa.Column("is_private", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_error_ids", sa.JSON, nullable=True),
        sa.Column("applied_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("memory_type", sa.String(16), nullable=False, server_default="fix"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("team_id", "content_hash", name="uq_fix_team_content_hash"),
    )
    op.create_index("ix_fixes_team_id", "fixes", ["team_id"])
    op.create_index("ix_fixes_project_id", "fixes", ["project_id"])
    op.create_index("ix_fixes_content_hash", "fixes", ["content_hash"])

    op.create_table(
        "pending_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("error_id", sa.String(32), nullable=False),
        sa.Column("error_type", sa.String(32), nullable=False),
        sa.Column("short_message", sa.Text, nullable=False),
        sa.Column("error_excerpt", sa.Text, nullable=False),
        sa.Column("tags", sa.Text, nullable=False, server_default=""),
        sa.Column("deferred_at", sa.String(64), nullable=False),
        sa.Column("resource_address", sa.String(256), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("file", sa.String(512), nullable=True),
        sa.Column("command", sa.Text, nullable=True),
        sa.Column("cwd", sa.String(512), nullable=True),
        sa.Column("session_id", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("command_family", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(32), nullable=True),
        sa.Column("worthiness", sa.String(32), nullable=False, server_default="memory_worthy"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pending_team_id", "pending_entries", ["team_id"])
    op.create_index("ix_pending_project_id", "pending_entries", ["project_id"])
    op.create_index("ix_pending_error_id", "pending_entries", ["error_id"])
    op.create_index("ix_pending_session_id", "pending_entries", ["session_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("hashed_token", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("hashed_token"),
    )
    op.create_index("ix_api_keys_team_id", "api_keys", ["team_id"])
    op.create_index("ix_api_keys_hashed_token", "api_keys", ["hashed_token"])

    op.create_table(
        "github_installations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("installation_id", sa.BigInteger, nullable=False),
        sa.Column("team_id", sa.Uuid(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repositories", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("installed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("installation_id"),
    )
    op.create_index("ix_github_installations_installation_id", "github_installations", ["installation_id"])
    op.create_index("ix_github_installations_team_id", "github_installations", ["team_id"])


def downgrade() -> None:
    op.drop_table("github_installations")
    op.drop_table("api_keys")
    op.drop_table("pending_entries")
    op.drop_table("fixes")
    op.drop_table("projects")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_table("users")
