"""Aerumentis — Integration Tests: Phase 2 Knowledge endpoints."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aerumentis.core import database as db_module
from aerumentis.core.database import Base


@pytest_asyncio.fixture
async def app_with_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    orig_engine = db_module.engine
    orig_factory = db_module.async_session_factory
    db_module.engine = engine
    db_module.async_session_factory = factory

    from aerumentis.core import security as sec_module
    orig_sec_factory = sec_module.async_session_factory
    sec_module.async_session_factory = factory

    from aerumentis.main import create_app
    app = create_app()

    yield app

    db_module.engine = orig_engine
    db_module.async_session_factory = orig_factory
    sec_module.async_session_factory = orig_sec_factory
    await engine.dispose()


@pytest.fixture
def client(app_with_db):
    with TestClient(app_with_db) as c:
        yield c


@pytest.fixture
def auth_token(client):
    import uuid
    unique = uuid.uuid4().hex[:8]
    response = client.post("/api/v1/auth/register", json={
        "email": f"test_{unique}@aerumentis.com",
        "password": "TestPassword123!",
        "full_name": "Test Engineer",
        "organization_name": f"TestOrg_{unique}",
        "organization_type": "airline",
    })
    assert response.status_code == 201
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestKnowledgeEntries:
    def test_create_entry(self, client, auth_headers):
        r = client.post("/api/v1/knowledge/entries", json={
            "title": "Hydraulic pump replacement tip",
            "content": "Always depressurize the system before removing the hydraulic pump. Torque to 150 ft-lbs.",
            "entry_type": "troubleshooting_tip",
            "aircraft_model": "737 NG",
            "system_affected": "hydraulic",
            "tags": ["hydraulic", "pump", "safety"],
            "confidence_score": 0.9,
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create failed: {r.text}"
        data = r.json()
        assert data["title"] == "Hydraulic pump replacement tip"
        assert data["entry_type"] == "troubleshooting_tip"
        assert data["aircraft_model"] == "737 NG"
        assert "hydraulic" in data["tags"]
        assert data["verified"] is False
        assert data["from_interview"] is False

    def test_list_entries(self, client, auth_headers):
        client.post("/api/v1/knowledge/entries", json={
            "title": "Entry 1", "content": "Content 1 with enough text to pass validation",
        }, headers=auth_headers)
        client.post("/api/v1/knowledge/entries", json={
            "title": "Entry 2", "content": "Content 2 with enough text to pass validation",
        }, headers=auth_headers)
        r = client.get("/api/v1/knowledge/entries", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 2
        assert len(data["entries"]) >= 2

    def test_get_entry(self, client, auth_headers):
        create_r = client.post("/api/v1/knowledge/entries", json={
            "title": "Get me", "content": "Content to retrieve here",
        }, headers=auth_headers)
        entry_id = create_r.json()["id"]
        r = client.get(f"/api/v1/knowledge/entries/{entry_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == entry_id

    def test_get_entry_not_found(self, client, auth_headers):
        r = client.get("/api/v1/knowledge/entries/nonexistent-id", headers=auth_headers)
        assert r.status_code == 404

    def test_verify_entry(self, client, auth_headers):
        create_r = client.post("/api/v1/knowledge/entries", json={
            "title": "Verify me", "content": "Content that needs verification",
        }, headers=auth_headers)
        entry_id = create_r.json()["id"]
        r = client.post(f"/api/v1/knowledge/entries/{entry_id}/verify", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["verified"] is True

    def test_delete_entry(self, client, auth_headers):
        create_r = client.post("/api/v1/knowledge/entries", json={
            "title": "Delete me", "content": "Content to be archived",
        }, headers=auth_headers)
        entry_id = create_r.json()["id"]
        r = client.delete(f"/api/v1/knowledge/entries/{entry_id}", headers=auth_headers)
        assert r.status_code == 200

    def test_entries_require_auth(self, client):
        assert client.get("/api/v1/knowledge/entries").status_code == 401

    def test_invalid_entry_type(self, client, auth_headers):
        r = client.post("/api/v1/knowledge/entries", json={
            "title": "Bad type", "content": "Content here",
            "entry_type": "invalid",
        }, headers=auth_headers)
        assert r.status_code == 422


class TestRepairHistory:
    def test_create_repair(self, client, auth_headers):
        r = client.post("/api/v1/knowledge/repairs", json={
            "aircraft_model": "737 NG",
            "aircraft_tail_number": "N12345",
            "system_affected": "hydraulic",
            "symptom": "Low hydraulic pressure on system A during climb",
            "diagnosis": "EDP internal seal failure causing pressure loss",
            "resolution": "Replaced EDP with new unit, part number 74A123456",
            "parts_replaced": "EDP-74A123456",
            "labor_hours": 4.5,
            "downtime_hours": 8.0,
            "severity": "moderate",
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create repair failed: {r.text}"
        data = r.json()
        assert data["aircraft_tail_number"] == "N12345"
        assert data["recurrence"] == "first_occurrence"
        assert data["pattern_match_count"] == 0
        assert data["knowledge_entry_id"] is not None

    def test_list_repairs(self, client, auth_headers):
        client.post("/api/v1/knowledge/repairs", json={
            "symptom": "Issue A", "diagnosis": "Cause A", "resolution": "Fix A",
        }, headers=auth_headers)
        r = client.get("/api/v1/knowledge/repairs", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 1


class TestVoiceInterviews:
    def test_create_interview(self, client, auth_headers):
        r = client.post("/api/v1/knowledge/interviews", json={
            "technician_name": "Bob Wilson",
            "technician_role": "Senior A&P Mechanic",
            "years_experience": 35,
            "topic": "Hydraulic system maintenance on 737 NG",
            "aircraft_model": "737 NG",
            "system_affected": "hydraulic",
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create interview failed: {r.text}"
        data = r.json()
        assert data["technician_name"] == "Bob Wilson"
        assert data["status"] == "pending_upload"

    def test_add_transcript(self, client, auth_headers):
        create_r = client.post("/api/v1/knowledge/interviews", json={
            "technician_name": "Test Tech", "topic": "Brake systems",
        }, headers=auth_headers)
        interview_id = create_r.json()["id"]
        r = client.post(f"/api/v1/knowledge/interviews/{interview_id}/transcript", json={
            "transcript": "The key thing about brake systems is to check the wear pins first. Most guys skip that step and it causes problems later.",
            "duration_sec": 45.0,
        }, headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "transcribed"
        assert data["transcript_word_count"] > 0

    def test_list_interviews(self, client, auth_headers):
        client.post("/api/v1/knowledge/interviews", json={
            "technician_name": "Tech 1", "topic": "Topic 1",
        }, headers=auth_headers)
        r = client.get("/api/v1/knowledge/interviews", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 1


class TestPatternMatching:
    def test_pattern_match_endpoint(self, client, auth_headers):
        r = client.post("/api/v1/knowledge/patterns", json={
            "symptom": "Low hydraulic pressure on system A",
            "aircraft_model": "737 NG",
        }, headers=auth_headers)
        assert r.status_code == 200, f"Pattern match failed: {r.text}"
        data = r.json()
        assert "total_occurrences" in data
        assert "summary" in data
        assert isinstance(data["most_common_causes"], list)
        assert isinstance(data["related_entries"], list)

    def test_pattern_match_requires_auth(self, client):
        r = client.post("/api/v1/knowledge/patterns", json={"symptom": "test issue"})
        assert r.status_code == 401


class TestKnowledgeStats:
    def test_stats_endpoint(self, client, auth_headers):
        r = client.get("/api/v1/knowledge/stats", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_entries" in data
        assert "total_repairs" in data
        assert "total_interviews" in data


class TestKnowledgeGraph:
    def test_graph_endpoint(self, client, auth_headers):
        r = client.get("/api/v1/knowledge/graph", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
