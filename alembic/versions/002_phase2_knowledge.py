"""Phase 2 schema - knowledge tables

Revision ID: 002_phase2_knowledge
Revises: 001_initial
Create Date: 2025-01-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_phase2_knowledge"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_interviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("technician_name", sa.String(255), nullable=False),
        sa.Column("technician_role", sa.String(100), nullable=True),
        sa.Column("years_experience", sa.Integer, nullable=True),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("aircraft_model", sa.String(100), nullable=True),
        sa.Column("system_affected", sa.String(200), nullable=True),
        sa.Column("audio_file_uri", sa.String(500), nullable=True),
        sa.Column("audio_duration_sec", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("audio_format", sa.String(20), nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("transcript_language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("transcript_word_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_upload"),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("entries_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("conducted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "knowledge_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("entry_type", sa.String(50), nullable=False, server_default="technician_note"),
        sa.Column("aircraft_model", sa.String(100), nullable=True, index=True),
        sa.Column("system_affected", sa.String(200), nullable=True, index=True),
        sa.Column("component_affected", sa.String(200), nullable=True),
        sa.Column("ata_chapter", sa.String(20), nullable=True, index=True),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("verified", sa.Boolean, server_default=sa.text("false")),
        sa.Column("verified_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("vector_ids", sa.Text, nullable=True),
        sa.Column("interview_id", sa.String(36), sa.ForeignKey("voice_interviews.id"), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_org_aircraft", "knowledge_entries", ["org_id", "aircraft_model"])
    op.create_index("ix_knowledge_org_type", "knowledge_entries", ["org_id", "entry_type"])
    op.create_index("ix_knowledge_org_ata", "knowledge_entries", ["org_id", "ata_chapter"])
    op.create_index("ix_knowledge_org_system", "knowledge_entries", ["org_id", "system_affected"])

    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("node_type", sa.String(50), nullable=False, index=True),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_seen", sa.String(20), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_nodes_org_type_label", "knowledge_nodes", ["org_id", "node_type", "label"])

    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("target_node_id", sa.String(36), sa.ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("edge_type", sa.String(50), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("evidence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source_entry_ids", sa.Text, nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_knowledge_edges_source_type", "knowledge_edges", ["source_node_id", "edge_type"])
    op.create_index("ix_knowledge_edges_target_type", "knowledge_edges", ["target_node_id", "edge_type"])

    op.create_table(
        "repair_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("aircraft_tail_number", sa.String(20), nullable=True, index=True),
        sa.Column("aircraft_model", sa.String(100), nullable=True, index=True),
        sa.Column("system_affected", sa.String(200), nullable=True, index=True),
        sa.Column("component_affected", sa.String(200), nullable=True),
        sa.Column("ata_chapter", sa.String(20), nullable=True, index=True),
        sa.Column("symptom", sa.Text, nullable=False),
        sa.Column("diagnosis", sa.Text, nullable=False),
        sa.Column("resolution", sa.Text, nullable=False),
        sa.Column("parts_replaced", sa.Text, nullable=True),
        sa.Column("labor_hours", sa.Float, nullable=True),
        sa.Column("downtime_hours", sa.Float, nullable=True),
        sa.Column("recurrence", sa.String(20), nullable=False, server_default="first_occurrence"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="minor"),
        sa.Column("technician_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("technician_name", sa.String(255), nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("knowledge_entry_id", sa.String(36), sa.ForeignKey("knowledge_entries.id"), nullable=True),
        sa.Column("pattern_match_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_repair_org_aircraft", "repair_history", ["org_id", "aircraft_model"])
    op.create_index("ix_repair_org_system", "repair_history", ["org_id", "system_affected"])
    op.create_index("ix_repair_org_ata", "repair_history", ["org_id", "ata_chapter"])
    op.create_index("ix_repair_org_recurrence", "repair_history", ["org_id", "recurrence"])


def downgrade() -> None:
    op.drop_table("repair_history")
    op.drop_table("knowledge_edges")
    op.drop_table("knowledge_nodes")
    op.drop_table("knowledge_entries")
    op.drop_table("voice_interviews")
