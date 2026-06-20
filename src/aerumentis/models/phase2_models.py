"""
Aerumentis — Phase 2 Database Models
Knowledge entries, voice interviews, knowledge graph nodes/edges, repair histories.
"""
from __future__ import annotations

from sqlalchemy import String, Text, Integer, Float, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aerumentis.core.database import Base, TimestampMixin, UUIDMixin


class KnowledgeEntry(UUIDMixin, TimestampMixin, Base):
    """A piece of captured institutional knowledge — technician notes, repair history, incident reports."""
    __tablename__ = "knowledge_entries"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(50), nullable=False, default="technician_note")
    # technician_note, repair_history, incident_report, troubleshooting_tip, best_practice, safety_advisory

    # Classification
    aircraft_model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    system_affected: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    component_affected: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ata_chapter: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # ATA chapter code
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated

    # Provenance
    author_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    # Status & quality
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")  # active, archived, flagged
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)  # 0.0-1.0, AI-assessed
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # verified by senior tech/engineer
    verified_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    # RAG metadata
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of Qdrant point IDs

    # If derived from an interview
    interview_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("voice_interviews.id"), nullable=True)

    interview: Mapped[VoiceInterview | None] = relationship(
        back_populates="entries", foreign_keys=[interview_id]
    )

    __table_args__ = (
        Index("ix_knowledge_org_aircraft", "org_id", "aircraft_model"),
        Index("ix_knowledge_org_type", "org_id", "entry_type"),
        Index("ix_knowledge_org_ata", "org_id", "ata_chapter"),
        Index("ix_knowledge_org_system", "org_id", "system_affected"),
    )


class VoiceInterview(UUIDMixin, TimestampMixin, Base):
    """A voice interview with a technician — transcribed and processed into knowledge entries."""
    __tablename__ = "voice_interviews"

    technician_name: Mapped[str] = mapped_column(String(255), nullable=False)
    technician_role: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "Senior A&P Mechanic"
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    aircraft_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    system_affected: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Audio file info
    audio_file_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)  # private storage URI
    audio_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    audio_format: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Transcription
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    transcript_word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Processing status
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending_upload")
    # pending_upload, uploaded, transcribing, transcribed, extracting, completed, failed
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Derived knowledge
    entries_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Ownership
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    conducted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    entries: Mapped[list[KnowledgeEntry]] = relationship(
        back_populates="interview", foreign_keys="KnowledgeEntry.interview_id"
    )


class KnowledgeNode(UUIDMixin, TimestampMixin, Base):
    """A node in the knowledge graph — represents an entity (problem, solution, component, aircraft, system)."""
    __tablename__ = "knowledge_nodes"

    node_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # problem, solution, component, aircraft_model, system, procedure, tool, symptom
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON for extra attributes

    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    # Stats
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date

    __table_args__ = (
        Index("ix_knowledge_nodes_org_type_label", "org_id", "node_type", "label"),
    )


class KnowledgeEdge(UUIDMixin, TimestampMixin, Base):
    """An edge in the knowledge graph — relationship between two nodes."""
    __tablename__ = "knowledge_edges"

    source_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_node_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # caused_by, fixed_by, relates_to, part_of, occurs_on, requires_tool, symptom_of, prerequisite_for
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # confidence/frequency
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # how many KB entries support this
    source_entry_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of knowledge entry IDs

    __table_args__ = (
        Index("ix_knowledge_edges_source_type", "source_node_id", "edge_type"),
        Index("ix_knowledge_edges_target_type", "target_node_id", "edge_type"),
    )


class RepairHistory(UUIDMixin, TimestampMixin, Base):
    """A structured repair history record — links to knowledge entries and tracks recurring issues."""
    __tablename__ = "repair_history"

    aircraft_tail_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    aircraft_model: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    system_affected: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    component_affected: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ata_chapter: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # The repair
    symptom: Mapped[str] = mapped_column(Text, nullable=False)
    diagnosis: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, nullable=False)
    parts_replaced: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    labor_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    downtime_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Classification
    recurrence: Mapped[str] = mapped_column(String(20), nullable=False, default="first_occurrence")
    # first_occurrence, recurring, chronic
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="minor")
    # minor, moderate, major, critical

    # Provenance
    technician_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    technician_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    org_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)

    # AI metadata
    knowledge_entry_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_entries.id"), nullable=True)
    pattern_match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # how many similar past repairs

    __table_args__ = (
        Index("ix_repair_org_aircraft", "org_id", "aircraft_model"),
        Index("ix_repair_org_system", "org_id", "system_affected"),
        Index("ix_repair_org_ata", "org_id", "ata_chapter"),
        Index("ix_repair_org_recurrence", "org_id", "recurrence"),
    )
