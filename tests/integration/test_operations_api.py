"""Aerumentis — Integration Tests: Phase 3 Operations endpoints."""
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
        "email": f"ops_{unique}@aerumentis.com",
        "password": "TestPassword123!",
        "full_name": "Ops Manager",
        "organization_name": f"OpsOrg_{unique}",
        "organization_type": "airport",
    })
    assert response.status_code == 201
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestAircraft:
    def test_create_aircraft(self, client, auth_headers):
        r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N12345",
            "flight_number": "AA104",
            "aircraft_type": "B737-800",
            "airline": "American Airlines",
            "gate": "B12",
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create failed: {r.text}"
        data = r.json()
        assert data["tail_number"] == "N12345"
        assert data["flight_number"] == "AA104"
        assert data["status"] == "scheduled"
        assert data["gate"] == "B12"

    def test_list_aircraft(self, client, auth_headers):
        client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N111", "flight_number": "UA1", "aircraft_type": "B777",
        }, headers=auth_headers)
        client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N222", "flight_number": "UA2", "aircraft_type": "B737",
        }, headers=auth_headers)
        r = client.get("/api/v1/operations/aircraft", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 2

    def test_update_aircraft_status(self, client, auth_headers):
        create_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N999", "flight_number": "DL500", "aircraft_type": "A320",
        }, headers=auth_headers)
        aircraft_id = create_r.json()["id"]
        r = client.patch(f"/api/v1/operations/aircraft/{aircraft_id}/status", json={
            "status": "landed", "gate": "C5",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "landed"
        assert r.json()["gate"] == "C5"

    def test_aircraft_requires_auth(self, client):
        assert client.get("/api/v1/operations/aircraft").status_code == 401


class TestTurnarounds:
    def test_create_turnaround(self, client, auth_headers):
        # First create aircraft
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N777", "flight_number": "WN100", "aircraft_type": "B737-700",
            "gate": "A1",
        }, headers=auth_headers)
        aircraft_id = aircraft_r.json()["id"]

        r = client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_id,
            "flight_number": "WN100",
            "tail_number": "N777",
            "gate": "A1",
            "auto_generate_tasks": True,
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create turnaround failed: {r.text}"
        data = r.json()
        assert data["flight_number"] == "WN100"
        assert data["total_tasks"] >= 10  # Standard tasks generated

    def test_get_turnaround_by_flight(self, client, auth_headers):
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N888", "flight_number": "AA200", "aircraft_type": "A321",
            "gate": "B3",
        }, headers=auth_headers)
        aircraft_id = aircraft_r.json()["id"]
        client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_id, "flight_number": "AA200",
            "tail_number": "N888", "gate": "B3",
        }, headers=auth_headers)

        r = client.get("/api/v1/operations/turnarounds/flight/AA200", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["flight_number"] == "AA200"
        assert data["gate"] == "B3"
        assert len(data["tasks"]) > 0
        assert "progress_percent" in data

    def test_list_turnaround_tasks(self, client, auth_headers):
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N666", "flight_number": "DL300", "aircraft_type": "B737",
        }, headers=auth_headers)
        aircraft_id = aircraft_r.json()["id"]
        turnaround_r = client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_id, "flight_number": "DL300",
            "tail_number": "N666",
        }, headers=auth_headers)
        turnaround_id = turnaround_r.json()["id"]

        r = client.get(f"/api/v1/operations/turnarounds/{turnaround_id}/tasks", headers=auth_headers)
        assert r.status_code == 200
        tasks = r.json()
        assert len(tasks) >= 10
        task_types = [t["task_type"] for t in tasks]
        assert "fueling" in task_types
        assert "boarding" in task_types

    def test_update_task_status(self, client, auth_headers):
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N555", "flight_number": "UA900", "aircraft_type": "B777",
        }, headers=auth_headers)
        aircraft_id = aircraft_r.json()["id"]
        turnaround_r = client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_id, "flight_number": "UA900",
            "tail_number": "N555",
        }, headers=auth_headers)
        turnaround_id = turnaround_r.json()["id"]
        tasks_r = client.get(f"/api/v1/operations/turnarounds/{turnaround_id}/tasks", headers=auth_headers)
        task_id = tasks_r.json()[0]["task_id"]

        r = client.patch(f"/api/v1/operations/tasks/{task_id}", json={
            "status": "in_progress",
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "in_progress"
        assert r.json()["started_at"] is not None


class TestCrew:
    def test_create_crew(self, client, auth_headers):
        r = client.post("/api/v1/operations/crew", json={
            "name": "John Smith",
            "role": "fueler",
            "qualifications": ["fueling", "gpu_connect"],
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create crew failed: {r.text}"
        data = r.json()
        assert data["name"] == "John Smith"
        assert data["role"] == "fueler"
        assert data["status"] == "available"
        assert "fueling" in data["qualifications"]

    def test_list_crew(self, client, auth_headers):
        client.post("/api/v1/operations/crew", json={
            "name": "Alice", "role": "ramp_agent",
        }, headers=auth_headers)
        r = client.get("/api/v1/operations/crew", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_get_available_crew(self, client, auth_headers):
        client.post("/api/v1/operations/crew", json={
            "name": "Available Bob", "role": "cleaner",
        }, headers=auth_headers)
        r = client.get("/api/v1/operations/crew/available", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_assign_crew_to_task(self, client, auth_headers):
        # Setup: create aircraft, turnaround, get task, create crew
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N444", "flight_number": "SW100", "aircraft_type": "B737",
        }, headers=auth_headers)
        turnaround_r = client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_r.json()["id"], "flight_number": "SW100",
            "tail_number": "N444",
        }, headers=auth_headers)
        tasks_r = client.get(
            f"/api/v1/operations/turnarounds/{turnaround_r.json()['id']}/tasks", headers=auth_headers
        )
        fueling_task = next(t for t in tasks_r.json() if t["task_type"] == "fueling")

        crew_r = client.post("/api/v1/operations/crew", json={
            "name": "Fuel Joe", "role": "fueler",
        }, headers=auth_headers)

        r = client.post("/api/v1/operations/crew/assign", json={
            "task_id": fueling_task["task_id"],
            "crew_id": crew_r.json()["id"],
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["assigned_crew_id"] == crew_r.json()["id"]
        assert r.json()["status"] == "assigned"


class TestEquipment:
    def test_create_equipment(self, client, auth_headers):
        r = client.post("/api/v1/operations/equipment", json={
            "name": "Fuel Truck 01",
            "equipment_type": "fuel_truck",
            "current_location": "Ramp North",
            "fuel_capacity_liters": 20000,
            "current_fuel_liters": 18000,
        }, headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["equipment_type"] == "fuel_truck"
        assert data["status"] == "available"

    def test_list_equipment(self, client, auth_headers):
        client.post("/api/v1/operations/equipment", json={
            "name": "Tug 01", "equipment_type": "tug",
        }, headers=auth_headers)
        r = client.get("/api/v1/operations/equipment", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 1


class TestAlerts:
    def test_create_alert(self, client, auth_headers):
        r = client.post("/api/v1/operations/alerts", json={
            "alert_type": "weather",
            "severity": "high",
            "title": "Thunderstorm warning",
            "description": "Severe weather alert for terminal area. Ramp operations halted.",
            "gate": "A1",
        }, headers=auth_headers)
        assert r.status_code == 201, f"Create alert failed: {r.text}"

    def test_list_alerts(self, client, auth_headers):
        client.post("/api/v1/operations/alerts", json={
            "alert_type": "crew_shortage", "severity": "medium",
            "title": "Short staffed", "description": "Not enough ramp agents",
        }, headers=auth_headers)
        r = client.get("/api/v1/operations/alerts", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_acknowledge_alert(self, client, auth_headers):
        create_r = client.post("/api/v1/operations/alerts", json={
            "alert_type": "gate_conflict", "severity": "medium",
            "title": "Gate conflict", "description": "Two aircraft at gate B5",
        }, headers=auth_headers)
        alert_id = create_r.json()["id"]
        r = client.post(f"/api/v1/operations/alerts/{alert_id}/acknowledge", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "acknowledged"

    def test_resolve_alert(self, client, auth_headers):
        create_r = client.post("/api/v1/operations/alerts", json={
            "alert_type": "equipment_failure", "severity": "low",
            "title": "GPU issue", "description": "GPU running rough at gate C1",
        }, headers=auth_headers)
        alert_id = create_r.json()["id"]
        r = client.post(f"/api/v1/operations/alerts/{alert_id}/resolve", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "resolved"


class TestRiskAssessment:
    def test_risk_assessment(self, client, auth_headers):
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N333", "flight_number": "AA700", "aircraft_type": "B737",
        }, headers=auth_headers)
        turnaround_r = client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_r.json()["id"], "flight_number": "AA700",
            "tail_number": "N333",
        }, headers=auth_headers)
        turnaround_id = turnaround_r.json()["id"]

        r = client.get(f"/api/v1/operations/turnarounds/{turnaround_id}/risk", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "risk" in data
        assert "delay_minutes" in data
        assert "factors" in data


class TestDashboard:
    def test_dashboard_empty(self, client, auth_headers):
        r = client.get("/api/v1/operations/dashboard", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["active_aircraft_count"] == 0
        assert data["active_turnarounds_count"] == 0
        assert "risk_distribution" in data

    def test_dashboard_with_data(self, client, auth_headers):
        # Create aircraft, turnaround, crew, alert
        aircraft_r = client.post("/api/v1/operations/aircraft", json={
            "tail_number": "N111", "flight_number": "AA100", "aircraft_type": "B737",
            "gate": "A1",
        }, headers=auth_headers)
        client.post("/api/v1/operations/turnarounds", json={
            "aircraft_id": aircraft_r.json()["id"], "flight_number": "AA100",
            "tail_number": "N111", "gate": "A1",
        }, headers=auth_headers)
        client.post("/api/v1/operations/crew", json={
            "name": "Test Crew", "role": "ramp_agent",
        }, headers=auth_headers)
        client.post("/api/v1/operations/alerts", json={
            "alert_type": "equipment_failure", "severity": "high",
            "title": "GPU failure", "description": "GPU not working at gate A1",
        }, headers=auth_headers)

        r = client.get("/api/v1/operations/dashboard", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["active_aircraft_count"] == 1
        assert data["active_turnarounds_count"] == 1
        assert data["active_alerts_count"] == 1
        assert data["available_crew_count"] == 1
