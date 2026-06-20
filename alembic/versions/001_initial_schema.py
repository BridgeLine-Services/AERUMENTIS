"""Initial schema - all tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("org_type", sa.String(50), nullable=False, server_default="mro"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(64), nullable=False, index=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("aircraft_model", sa.String(100), nullable=True, index=True),
        sa.Column("manual_type", sa.String(50), nullable=True, index=True),
        sa.Column("manual_number", sa.String(100), nullable=True),
        sa.Column("revision", sa.String(50), nullable=True),
        sa.Column("effective_date", sa.String(20), nullable=True),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_org_aircraft", "documents", ["org_id", "aircraft_model"])
    op.create_index("ix_documents_org_manual_type", "documents", ["org_id", "manual_type"])

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False, server_default="Untitled Conversation"),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("message_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("retrieval_time_ms", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("generation_time_ms", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("total_time_ms", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("context_chunks_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("citations_json", sa.Text, nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_chat_messages_session_created", "chat_messages", ["session_id", "created_date"])


def downgrade() -> None:
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("documents")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("organizations")
