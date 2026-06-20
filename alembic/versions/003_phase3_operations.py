"""Phase 3 schema - operations tables

Revision ID: 003_phase3_operations
Revises: 002_phase2_knowledge
Create Date: 2025-01-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_phase3_operations"
down_revision: Union[str, None] = "002_phase2_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operations_turnarounds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("aircraft_id", sa.String(36), sa.ForeignKey("operations_aircraft.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("flight_number", sa.String(20), nullable=False, index=True),
        sa.Column("tail_number", sa.String(20), nullable=False),
        sa.Column("gate", sa.String(20), nullable=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_departure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_departure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("total_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("in_progress_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pending_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("turnaround_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turnaround_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_turnaround_min", sa.Integer, nullable=False, server_default="45"),
        sa.Column("actual_turnaround_min", sa.Integer, nullable=True),
        sa.Column("departure_risk", sa.String(20), nullable=False, server_default="low"),
        sa.Column("delay_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delay_reason", sa.Text, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_turnaround_org_status", "operations_turnarounds", ["org_id", "status"])

    op.create_table(
        "operations_aircraft",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tail_number", sa.String(20), nullable=False, index=True),
        sa.Column("flight_number", sa.String(20), nullable=False, index=True),
        sa.Column("aircraft_type", sa.String(50), nullable=False),
        sa.Column("airline", sa.String(100), nullable=True),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("scheduled_departure", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("actual_departure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gate", sa.String(20), nullable=True, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("turnaround_id", sa.String(36), sa.ForeignKey("operations_turnarounds.id"), nullable=True),
        sa.Column("departure_risk", sa.String(20), nullable=False, server_default="low"),
        sa.Column("delay_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_aircraft_org_status", "operations_aircraft", ["org_id", "status"])
    op.create_index("ix_ops_aircraft_org_gate", "operations_aircraft", ["org_id", "gate"])

    op.create_table(
        "operations_turnaround_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("turnaround_id", sa.String(36), sa.ForeignKey("operations_turnarounds.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("task_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("assigned_crew_id", sa.String(36), sa.ForeignKey("operations_crew.id"), nullable=True),
        sa.Column("assigned_equipment_id", sa.String(36), sa.ForeignKey("operations_equipment.id"), nullable=True),
        sa.Column("estimated_duration_min", sa.Integer, nullable=False, server_default="15"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_duration_min", sa.Integer, nullable=True),
        sa.Column("depends_on_task_id", sa.String(36), sa.ForeignKey("operations_turnaround_tasks.id"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("issue_flag", sa.Boolean, server_default=sa.text("false")),
        sa.Column("issue_description", sa.Text, nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_task_turnaround_type", "operations_turnaround_tasks", ["turnaround_id", "task_type"])
    op.create_index("ix_ops_task_turnaround_status", "operations_turnaround_tasks", ["turnaround_id", "status"])

    op.create_table(
        "operations_crew",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("current_task_id", sa.String(36), sa.ForeignKey("operations_turnaround_tasks.id"), nullable=True),
        sa.Column("current_gate", sa.String(20), nullable=True),
        sa.Column("shift_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shift_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qualifications", sa.Text, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_crew_org_status", "operations_crew", ["org_id", "status"])

    op.create_table(
        "operations_equipment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("equipment_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="available"),
        sa.Column("current_location", sa.String(100), nullable=True),
        sa.Column("assigned_gate", sa.String(20), nullable=True),
        sa.Column("fuel_capacity_liters", sa.Integer, nullable=True),
        sa.Column("current_fuel_liters", sa.Integer, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_equipment_org_status", "operations_equipment", ["org_id", "status"])
    op.create_index("ix_ops_equipment_org_type", "operations_equipment", ["org_id", "equipment_type"])

    op.create_table(
        "operations_alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("aircraft_id", sa.String(36), sa.ForeignKey("operations_aircraft.id", ondelete="SET NULL"), nullable=True),
        sa.Column("turnaround_id", sa.String(36), sa.ForeignKey("operations_turnarounds.id", ondelete="SET NULL"), nullable=True),
        sa.Column("flight_number", sa.String(20), nullable=True, index=True),
        sa.Column("gate", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("acknowledged_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("predicted_delay_min", sa.Integer, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("contributing_factors", sa.Text, nullable=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ops_alerts_org_severity", "operations_alerts", ["org_id", "severity"])
    op.create_index("ix_ops_alerts_org_status", "operations_alerts", ["org_id", "status"])


def downgrade() -> None:
    op.drop_table("operations_alerts")
    op.drop_table("operations_equipment")
    op.drop_table("operations_crew")
    op.drop_table("operations_turnaround_tasks")
    op.drop_table("operations_aircraft")
    op.drop_table("operations_turnarounds")
