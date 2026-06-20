"""Aerumentis — Unit Tests: Operations Service."""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from aerumentis.core.database import Base


@pytest_asyncio.fixture
async def ops_db():
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


class TestAircraft:
    @pytest.mark.asyncio
    async def test_create_aircraft(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            db=ops_db, tail_number="N12345", flight_number="AA104",
            aircraft_type="B737-800", airline="American Airlines", gate="B12",
        )
        assert aircraft.id is not None
        assert aircraft.tail_number == "N12345"
        assert aircraft.flight_number == "AA104"
        assert aircraft.status == "scheduled"
        assert aircraft.departure_risk == "low"

    @pytest.mark.asyncio
    async def test_update_aircraft_status(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            db=ops_db, tail_number="N99999", flight_number="DL200",
            aircraft_type="A320", gate="C5",
        )
        updated = await operations_service.update_aircraft_status(
            ops_db, aircraft.id, "landed", delay_minutes=0,
        )
        assert updated.status == "landed"

    @pytest.mark.asyncio
    async def test_list_aircraft(self, ops_db):
        from aerumentis.services import operations_service
        await operations_service.create_aircraft(
            ops_db, tail_number="N111", flight_number="UA1", aircraft_type="B777",
        )
        await operations_service.create_aircraft(
            ops_db, tail_number="N222", flight_number="UA2", aircraft_type="B737",
        )
        aircraft_list, total = await operations_service.list_aircraft(ops_db)
        assert total == 2


class TestTurnaround:
    @pytest.mark.asyncio
    async def test_create_turnaround_with_tasks(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N77777", flight_number="WN100",
            aircraft_type="B737-700", gate="A1",
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="WN100",
            tail_number="N77777", gate="A1",
            arrival_time=datetime.now(timezone.utc),
            scheduled_departure=datetime.now(timezone.utc) + timedelta(minutes=45),
        )
        assert turnaround.id is not None
        assert turnaround.status == "pending"
        assert turnaround.total_tasks > 0  # Standard tasks auto-generated
        # Should have fueling, catering, baggage_unload, baggage_load, cleaning, etc.
        assert turnaround.total_tasks >= 10

    @pytest.mark.asyncio
    async def test_turnaround_task_dependencies(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N888", flight_number="AA50",
            aircraft_type="A321", gate="B3",
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="AA50",
            tail_number="N888", gate="B3",
        )
        tasks = await operations_service.list_turnaround_tasks(ops_db, turnaround.id)
        # boarding should depend on cleaning
        boarding = next(t for t in tasks if t.task_type == "boarding")
        cleaning = next(t for t in tasks if t.task_type == "cleaning")
        assert boarding.depends_on_task_id == cleaning.id

    @pytest.mark.asyncio
    async def test_update_task_status(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N666", flight_number="DL300",
            aircraft_type="B737-800", gate="D1",
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="DL300",
            tail_number="N666", gate="D1",
        )
        tasks = await operations_service.list_turnaround_tasks(ops_db, turnaround.id)
        fueling_task = next(t for t in tasks if t.task_type == "fueling")

        updated = await operations_service.update_task_status(
            ops_db, fueling_task.id, "in_progress",
        )
        assert updated.status == "in_progress"
        assert updated.started_at is not None

        completed = await operations_service.update_task_status(
            ops_db, fueling_task.id, "completed",
        )
        assert completed.status == "completed"
        assert completed.completed_at is not None
        assert completed.actual_duration_min is not None

    @pytest.mark.asyncio
    async def test_get_turnaround_by_flight(self, ops_db):
        from aerumentis.services import operations_service
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N555", flight_number="UA500",
            aircraft_type="B777", gate="E7",
        )
        await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="UA500",
            tail_number="N555", gate="E7",
        )
        detail = await operations_service.get_turnaround_by_flight(ops_db, "UA500")
        assert detail is not None
        assert detail["flight_number"] == "UA500"
        assert detail["gate"] == "E7"
        assert len(detail["tasks"]) > 0
        assert "progress_percent" in detail


class TestCrew:
    @pytest.mark.asyncio
    async def test_create_crew_member(self, ops_db):
        from aerumentis.services import operations_service
        crew = await operations_service.create_crew_member(
            ops_db, name="John Smith", role="fueler",
            qualifications=["fueling", "gpu_connect"],
        )
        assert crew.id is not None
        assert crew.name == "John Smith"
        assert crew.role == "fueler"
        assert crew.status == "available"

    @pytest.mark.asyncio
    async def test_list_crew(self, ops_db):
        from aerumentis.services import operations_service
        await operations_service.create_crew_member(ops_db, name="Alice", role="ramp_agent")
        await operations_service.create_crew_member(ops_db, name="Bob", role="fueler")
        crew_list, total = await operations_service.list_crew(ops_db)
        assert total == 2

    @pytest.mark.asyncio
    async def test_assign_crew_to_task(self, ops_db):
        from aerumentis.services import operations_service
        # Setup
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N444", flight_number="SW200",
            aircraft_type="B737", gate="F1",
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="SW200",
            tail_number="N444", gate="F1",
        )
        tasks = await operations_service.list_turnaround_tasks(ops_db, turnaround.id)
        fueling_task = next(t for t in tasks if t.task_type == "fueling")
        crew = await operations_service.create_crew_member(ops_db, name="Fuel Joe", role="fueler")

        # Assign
        task = await operations_service.assign_crew_to_task(ops_db, fueling_task.id, crew.id)
        assert task.assigned_crew_id == crew.id
        assert task.status == "assigned"

    @pytest.mark.asyncio
    async def test_get_available_crew(self, ops_db):
        from aerumentis.services import operations_service
        await operations_service.create_crew_member(ops_db, name="Available Alice", role="cleaner")
        available = await operations_service.get_available_crew(ops_db)
        assert len(available) >= 1
        assert all(c.status == "available" for c in available)


class TestEquipment:
    @pytest.mark.asyncio
    async def test_create_equipment(self, ops_db):
        from aerumentis.services import operations_service
        equip = await operations_service.create_equipment(
            ops_db, name="Fuel Truck 01", equipment_type="fuel_truck",
            current_location="Ramp North", fuel_capacity_liters=20000,
            current_fuel_liters=18000,
        )
        assert equip.id is not None
        assert equip.equipment_type == "fuel_truck"
        assert equip.status == "available"
        assert equip.fuel_capacity_liters == 20000

    @pytest.mark.asyncio
    async def test_list_equipment(self, ops_db):
        from aerumentis.services import operations_service
        await operations_service.create_equipment(ops_db, name="Tug 01", equipment_type="tug")
        await operations_service.create_equipment(ops_db, name="GPU 01", equipment_type="gpu")
        equipment_list, total = await operations_service.list_equipment(ops_db)
        assert total == 2


class TestDelayPrediction:
    @pytest.mark.asyncio
    async def test_risk_assessment_low(self, ops_db):
        from aerumentis.services import operations_service
        # Create a turnaround with plenty of time
        arrival = datetime.now(timezone.utc)
        departure = datetime.now(timezone.utc) + timedelta(minutes=200)
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N333", flight_number="AA700",
            aircraft_type="B737-800", gate="G1",
            arrival_time=arrival, scheduled_departure=departure,
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="AA700",
            tail_number="N333", gate="G1",
            arrival_time=arrival, scheduled_departure=departure,
        )
        risk = await operations_service.recalculate_risk(ops_db, turnaround.id)
        # With 200 min remaining and ~148 min of tasks, time pressure is low
        # But unassigned critical tasks add a small penalty
        assert risk["risk"] in ("low", "medium")
        assert risk["delay_minutes"] <= 10

    @pytest.mark.asyncio
    async def test_risk_assessment_with_issues(self, ops_db):
        from aerumentis.services import operations_service
        # Create a turnaround with very little time
        arrival = datetime.now(timezone.utc) - timedelta(minutes=30)
        departure = datetime.now(timezone.utc) + timedelta(minutes=5)  # Only 5 min left
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N222", flight_number="DL800",
            aircraft_type="A320", gate="H1",
            arrival_time=arrival, scheduled_departure=departure,
        )
        turnaround = await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="DL800",
            tail_number="N222", gate="H1",
            arrival_time=arrival, scheduled_departure=departure,
        )
        risk = await operations_service.recalculate_risk(ops_db, turnaround.id)
        # With many pending tasks and only 5 min, risk should be high or critical
        assert risk["risk"] in ("high", "critical")
        assert risk["delay_minutes"] > 0
        assert len(risk["factors"]) > 0


class TestAlerts:
    @pytest.mark.asyncio
    async def test_create_manual_alert(self, ops_db):
        from aerumentis.services import operations_service
        alert = await operations_service.create_manual_alert(
            ops_db, alert_type="weather", severity="high",
            title="Thunderstorm warning — ground operations suspended",
            description="Severe weather alert for the terminal area. All ramp operations halted.",
            gate="A1",
        )
        assert alert.id is not None
        assert alert.alert_type == "weather"
        assert alert.severity == "high"
        assert alert.status == "active"

    @pytest.mark.asyncio
    async def test_acknowledge_and_resolve_alert(self, ops_db):
        from aerumentis.services import operations_service
        alert = await operations_service.create_manual_alert(
            ops_db, alert_type="gate_conflict", severity="medium",
            title="Gate conflict for flight AA100",
            description="Two aircraft assigned to gate B5",
        )
        acked = await operations_service.acknowledge_alert(ops_db, alert.id, "user-123")
        assert acked.status == "acknowledged"
        assert acked.acknowledged_by == "user-123"

        resolved = await operations_service.resolve_alert(ops_db, alert.id)
        assert resolved.status == "resolved"

    @pytest.mark.asyncio
    async def test_list_alerts(self, ops_db):
        from aerumentis.services import operations_service
        await operations_service.create_manual_alert(
            ops_db, alert_type="crew_shortage", severity="medium",
            title="Short staffed", description="Not enough ramp agents",
        )
        alerts, total = await operations_service.list_alerts(ops_db, status="active")
        assert total >= 1


class TestDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_empty(self, ops_db):
        from aerumentis.services import operations_service
        dashboard = await operations_service.get_dashboard(ops_db)
        assert dashboard["active_aircraft_count"] == 0
        assert dashboard["active_turnarounds_count"] == 0
        assert dashboard["active_alerts_count"] == 0
        assert "risk_distribution" in dashboard
        assert "aircraft_status_distribution" in dashboard

    @pytest.mark.asyncio
    async def test_dashboard_with_data(self, ops_db):
        from aerumentis.services import operations_service
        # Create some data
        aircraft = await operations_service.create_aircraft(
            ops_db, tail_number="N111", flight_number="AA100",
            aircraft_type="B737", gate="A1",
        )
        await operations_service.create_turnaround(
            db=ops_db, aircraft_id=aircraft.id, flight_number="AA100",
            tail_number="N111", gate="A1",
        )
        await operations_service.create_crew_member(ops_db, name="Test Crew", role="ramp_agent")
        await operations_service.create_manual_alert(
            ops_db, alert_type="equipment_failure", severity="high",
            title="GPU failure at gate A1", description="Ground power unit not working",
        )
        dashboard = await operations_service.get_dashboard(ops_db)
        assert dashboard["active_aircraft_count"] == 1
        assert dashboard["active_turnarounds_count"] == 1
        assert dashboard["active_alerts_count"] == 1
        assert dashboard["available_crew_count"] == 1
