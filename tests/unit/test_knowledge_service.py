"""Aerumentis — Unit Tests: Knowledge Service."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aerumentis.core.database import Base


@pytest_asyncio.fixture
async def knowledge_db():
    """Create a test DB session with all Phase 2 tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


class TestKnowledgeEntryCreation:
    @pytest.mark.asyncio
    async def test_create_knowledge_entry(self, knowledge_db):
        from aerumentis.services import knowledge_service
        entry = await knowledge_service.create_knowledge_entry(
            db=knowledge_db,
            title="Hydraulic pump pressure drop on 737 NG",
            content="When the hydraulic pump pressure drops below 2500 PSI, check the EDP first. Most common cause is sensor degradation.",
            entry_type="troubleshooting_tip",
            aircraft_model="737 NG",
            system_affected="hydraulic",
            tags=["hydraulic", "pump", "sensor"],
            author_name="John Smith",
            org_id=None,
        )
        assert entry.id is not None
        assert entry.title == "Hydraulic pump pressure drop on 737 NG"
        assert entry.entry_type == "troubleshooting_tip"
        assert entry.status == "active"
        assert entry.verified is False
        assert entry.confidence_score == 0.5

    @pytest.mark.asyncio
    async def test_create_knowledge_entry_invalid_type(self, knowledge_db):
        from aerumentis.services import knowledge_service
        with pytest.raises(ValueError):
            await knowledge_service.create_knowledge_entry(
                db=knowledge_db, title="Test", content="Test content here",
                entry_type="invalid_type",
            )

    @pytest.mark.asyncio
    async def test_list_knowledge_entries(self, knowledge_db):
        from aerumentis.services import knowledge_service
        for i in range(3):
            await knowledge_service.create_knowledge_entry(
                db=knowledge_db, title=f"Entry {i}", content=f"Content {i} with enough text",
                entry_type="technician_note",
            )
        entries, total = await knowledge_service.list_knowledge_entries(knowledge_db, limit=10)
        assert total == 3
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_list_with_filter(self, knowledge_db):
        from aerumentis.services import knowledge_service
        await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="737 tip", content="Useful 737 tip content here",
            entry_type="troubleshooting_tip", aircraft_model="737 NG",
        )
        await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="A320 tip", content="Useful A320 tip content here",
            entry_type="troubleshooting_tip", aircraft_model="A320",
        )
        entries, total = await knowledge_service.list_knowledge_entries(
            knowledge_db, aircraft_model="737 NG"
        )
        assert total == 1
        assert entries[0].aircraft_model == "737 NG"

    @pytest.mark.asyncio
    async def test_verify_knowledge_entry(self, knowledge_db):
        from aerumentis.services import knowledge_service
        entry = await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="Verify me", content="Content to be verified here",
        )
        verified = await knowledge_service.verify_knowledge_entry(knowledge_db, entry.id, "verifier-user-id")
        assert verified.verified is True
        assert verified.verified_by == "verifier-user-id"

    @pytest.mark.asyncio
    async def test_delete_knowledge_entry(self, knowledge_db):
        from aerumentis.services import knowledge_service
        entry = await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="Delete me", content="Content to be deleted here",
        )
        success = await knowledge_service.delete_knowledge_entry(knowledge_db, entry.id)
        assert success is True
        # Should be archived, not hard deleted
        fetched = await knowledge_service.get_knowledge_entry(knowledge_db, entry.id)
        assert fetched.status == "archived"


class TestRepairHistory:
    @pytest.mark.asyncio
    async def test_create_repair_history(self, knowledge_db):
        from aerumentis.services import knowledge_service
        repair = await knowledge_service.create_repair_history(
            db=knowledge_db,
            aircraft_model="737 NG", system_affected="hydraulic",
            symptom="Low hydraulic pressure on system A",
            diagnosis="EDP internal leak", resolution="Replaced EDP, part number 12345",
            parts_replaced="EDP-12345", labor_hours=4.5,
            technician_name="Jane Doe",
        )
        assert repair.id is not None
        assert repair.recurrence == "first_occurrence"
        assert repair.severity == "minor"
        assert repair.pattern_match_count == 0
        # Should also create a knowledge entry
        assert repair.knowledge_entry_id is not None

    @pytest.mark.asyncio
    async def test_repair_recurrence_detection(self, knowledge_db):
        from aerumentis.services import knowledge_service
        # First occurrence
        await knowledge_service.create_repair_history(
            db=knowledge_db, symptom="Fuel pressure fluctuation on 737",
            diagnosis="Fuel pump wear", resolution="Replaced fuel pump",
            aircraft_model="737 NG",
        )
        # Second occurrence — should detect recurrence
        repair2 = await knowledge_service.create_repair_history(
            db=knowledge_db, symptom="Fuel pressure fluctuation on 737",
            diagnosis="Fuel pump wear again", resolution="Replaced fuel pump again",
            aircraft_model="737 NG",
        )
        assert repair2.recurrence in ("recurring", "chronic")
        assert repair2.pattern_match_count > 0

    @pytest.mark.asyncio
    async def test_list_repair_history(self, knowledge_db):
        from aerumentis.services import knowledge_service
        await knowledge_service.create_repair_history(
            db=knowledge_db, symptom="Issue 1", diagnosis="Cause 1", resolution="Fix 1",
        )
        await knowledge_service.create_repair_history(
            db=knowledge_db, symptom="Issue 2", diagnosis="Cause 2", resolution="Fix 2",
        )
        repairs, total = await knowledge_service.list_repair_history(knowledge_db)
        assert total == 2
        assert len(repairs) == 2


class TestVoiceInterviews:
    @pytest.mark.asyncio
    async def test_create_voice_interview(self, knowledge_db):
        from aerumentis.services import knowledge_service
        interview = await knowledge_service.create_voice_interview(
            db=knowledge_db, technician_name="Bob Wilson",
            technician_role="Senior A&P Mechanic", years_experience=35,
            topic="Hydraulic system maintenance on 737 NG",
            aircraft_model="737 NG", system_affected="hydraulic",
        )
        assert interview.id is not None
        assert interview.technician_name == "Bob Wilson"
        assert interview.status == "pending_upload"
        assert interview.transcript is None

    @pytest.mark.asyncio
    async def test_update_transcript(self, knowledge_db):
        from aerumentis.services import knowledge_service
        interview = await knowledge_service.create_voice_interview(
            db=knowledge_db, technician_name="Test Tech", topic="Brake systems",
        )
        updated = await knowledge_service.update_interview_transcript(
            knowledge_db, interview.id,
            transcript="So the key thing about the brake system is to always check the wear pins first before doing anything else.",
            duration_sec=120.5,
        )
        assert updated.status == "transcribed"
        assert updated.transcript_word_count > 0
        assert updated.audio_duration_sec == 120.5

    @pytest.mark.asyncio
    async def test_list_interviews(self, knowledge_db):
        from aerumentis.services import knowledge_service
        await knowledge_service.create_voice_interview(
            db=knowledge_db, technician_name="Tech 1", topic="Topic 1",
        )
        await knowledge_service.create_voice_interview(
            db=knowledge_db, technician_name="Tech 2", topic="Topic 2",
        )
        interviews, total = await knowledge_service.list_voice_interviews(knowledge_db)
        assert total == 2


class TestKnowledgeStats:
    @pytest.mark.asyncio
    async def test_knowledge_stats(self, knowledge_db):
        from aerumentis.services import knowledge_service
        await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="Stat 1", content="Content 1 here",
            entry_type="technician_note", aircraft_model="737 NG",
        )
        await knowledge_service.create_knowledge_entry(
            db=knowledge_db, title="Stat 2", content="Content 2 here",
            entry_type="troubleshooting_tip", aircraft_model="A320",
        )
        await knowledge_service.create_repair_history(
            db=knowledge_db, symptom="Issue", diagnosis="Cause", resolution="Fix",
        )
        # Note: create_repair_history also creates a knowledge entry
        stats = await knowledge_service.get_knowledge_stats(knowledge_db)
        assert stats["total_entries"] >= 2
        assert "technician_note" in stats["by_type"]
        assert stats["total_repairs"] >= 1


class TestPatternSummary:
    def test_summary_with_no_matches(self):
        from aerumentis.services.knowledge_service import _generate_pattern_summary
        summary = _generate_pattern_summary(0, [], [])
        assert "No similar occurrences" in summary
        assert "new issue" in summary

    def test_summary_with_matches(self):
        from aerumentis.services.knowledge_service import _generate_pattern_summary
        causes = [("Sensor degradation", 15), ("Wiring fault", 5)]
        resolutions = [("Replace sensor", 12), ("Repair wiring", 3)]
        summary = _generate_pattern_summary(23, causes, resolutions)
        assert "23 similar occurrences" in summary
        assert "Sensor degradation" in summary
        assert "Replace sensor" in summary

    def test_summary_singular(self):
        from aerumentis.services.knowledge_service import _generate_pattern_summary
        summary = _generate_pattern_summary(1, [("One cause", 1)], [("One fix", 1)])
        assert "1 similar occurrence" in summary  # singular
