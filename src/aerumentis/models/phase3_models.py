"""
Aerumentis — Phase 3 Database Models
Ground operations: aircraft, turnarounds, tasks, crew, equipment, alerts.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, Boolean, ForeignKey, Index, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aerumentis.core.database import Base, TimestampMixin, UUIDMixin


class Aircraft(UUIDMixin, TimestampMixin, Base):
    """An aircraft currently at or expected at the airport."""
    __tablename__ = "operations_aircraft"

    tail_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    flight_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    aircraft_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "B737-800", "A320"
    airline: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Schedule
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    scheduled_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Current state
    gate: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    # scheduled, arriving, landed, taxiing_to_gate, at_gate, boarding, taxiing_out, departed, delayed, cancelled

    # Turnaround tracking
    turnaround_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_turnarounds.id"), nullable=True)
    departure_risk: Mapped[str] = mapped_column(String(20), nullable=False, default="low")  # low, medium, high
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_ops_aircraft_org_status", "org_id", "status"),
        Index("ix_ops_aircraft_org_gate", "org_id", "gate"),
    )


class Turnaround(UUIDMixin, TimestampMixin, Base):
    """A turnaround event — the orchestrated process of getting an aircraft ready for its next flight."""
    __tablename__ = "operations_turnarounds"

    aircraft_id: Mapped[str] = mapped_column(String(36), ForeignKey("operations_aircraft.id", ondelete="CASCADE"), nullable=False, index=True)
    flight_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    tail_number: Mapped[str] = mapped_column(String(20), nullable=False)

    gate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Turnaround status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    # pending, in_progress, completed, delayed, cancelled

    # Performance metrics
    total_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_progress_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timing
    turnaround_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turnaround_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_turnaround_min: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    actual_turnaround_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Risk
    departure_risk: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    aircraft: Mapped[Aircraft | None] = relationship(back_populates="turnaround_ref", foreign_keys=[aircraft_id])
    tasks: Mapped[list["TurnaroundTask"]] = relationship(
        back_populates="turnaround", cascade="all, delete-orphan", foreign_keys="TurnaroundTask.turnaround_id"
    )

    __table_args__ = (
        Index("ix_ops_turnaround_org_status", "org_id", "status"),
    )


# Back-reference on Aircraft
Aircraft.turnaround_ref = relationship(
    "Turnaround", back_populates="aircraft", foreign_keys=[Turnaround.aircraft_id], uselist=False
)


class TurnaroundTask(UUIDMixin, TimestampMixin, Base):
    """A single task within a turnaround — fueling, catering, baggage, cleaning, maintenance check, etc."""
    __tablename__ = "operations_turnaround_tasks"

    turnaround_id: Mapped[str] = mapped_column(String(36), ForeignKey("operations_turnarounds.id", ondelete="CASCADE"), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # fueling, catering, baggage_unload, baggage_load, cleaning, lavatory, water,
    # deicing, maintenance_check, gpu_connect, gpu_disconnect, pushback, boarding, cargo

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending, assigned, in_progress, completed, skipped, delayed

    # Assignment
    assigned_crew_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_crew.id"), nullable=True)
    assigned_equipment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_equipment.id"), nullable=True)

    # Timing
    estimated_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Sequencing — some tasks must happen before others
    depends_on_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_turnaround_tasks.id"), nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    turnaround: Mapped[Turnaround | None] = relationship(
        back_populates="tasks", foreign_keys=[turnaround_id]
    )

    __table_args__ = (
        Index("ix_ops_task_turnaround_type", "turnaround_id", "task_type"),
        Index("ix_ops_task_turnaround_status", "turnaround_id", "status"),
    )


class GroundCrew(UUIDMixin, TimestampMixin, Base):
    """A ground crew member — ramp agent, fueler, cleaner, baggage handler, etc."""
    __tablename__ = "operations_crew"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    # ramp_agent, fueler, cleaner, baggage_handler, lavatory_service, caterer, mechanic, supervisor

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    # available, assigned, on_break, off_duty

    current_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_turnaround_tasks.id"), nullable=True)
    current_gate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    shift_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shift_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Qualifications — which task types can this crew member perform?
    qualifications: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of task types

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_ops_crew_org_status", "org_id", "status"),
    )


class Equipment(UUIDMixin, TimestampMixin, Base):
    """Ground service equipment — fuel trucks, tugs, GPUs, catering trucks, etc."""
    __tablename__ = "operations_equipment"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # fuel_truck, tug, gpu, catering_truck, baggage_cart, deicing_truck, lavatory_truck, water_truck, pushback

    # Status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    # available, in_use, maintenance, offline

    current_location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    assigned_gate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # For fuel trucks
    fuel_capacity_liters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_fuel_liters: Mapped[int | None] = mapped_column(Integer, nullable=True)

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_ops_equipment_org_status", "org_id", "status"),
        Index("ix_ops_equipment_org_type", "org_id", "equipment_type"),
    )


class OperationsAlert(UUIDMixin, TimestampMixin, Base):
    """An operational alert — delay prediction, equipment failure, crew shortage, etc."""
    __tablename__ = "operations_alerts"

    alert_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # delay_prediction, equipment_failure, crew_shortage, weather, maintenance_alert, security, gate_conflict

    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    # info, low, medium, high, critical

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Related entities
    aircraft_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_aircraft.id", ondelete="SET NULL"), nullable=True)
    turnaround_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("operations_turnarounds.id", ondelete="SET NULL"), nullable=True)
    flight_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    gate: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # State
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # active, acknowledged, resolved, dismissed
    acknowledged_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    # AI prediction metadata
    predicted_delay_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    contributing_factors: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_ops_alerts_org_severity", "org_id", "severity"),
        Index("ix_ops_alerts_org_status", "org_id", "status"),
    )
