"""
Aerumentis — Operations Service (Phase 3)
Real-time ground operations intelligence: aircraft tracking, turnaround orchestration,
crew assignment, equipment management, and AI-powered delay prediction.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import (
    Aircraft, Equipment, GroundCrew, OperationsAlert, Turnaround, TurnaroundTask,
)
from aerumentis.core.logging import get_logger

logger = get_logger("aerumentis.operations_service")

# Standard turnaround task templates with default durations (minutes)
STANDARD_TASKS = {
    "fueling": {"duration": 20, "requires_equipment": "fuel_truck"},
    "catering": {"duration": 15, "requires_equipment": "catering_truck"},
    "baggage_unload": {"duration": 10, "requires_equipment": "baggage_cart"},
    "baggage_load": {"duration": 10, "requires_equipment": "baggage_cart"},
    "cleaning": {"duration": 20, "requires_equipment": None},
    "lavatory": {"duration": 10, "requires_equipment": "lavatory_truck"},
    "water": {"duration": 10, "requires_equipment": "water_truck"},
    "gpu_connect": {"duration": 5, "requires_equipment": "gpu"},
    "gpu_disconnect": {"duration": 3, "requires_equipment": "gpu"},
    "maintenance_check": {"duration": 15, "requires_equipment": None},
    "boarding": {"duration": 20, "requires_equipment": None},
    "pushback": {"duration": 10, "requires_equipment": "tug"},
}

# Task dependencies — which tasks must be completed before others
TASK_DEPENDENCIES = {
    "baggage_load": "baggage_unload",  # load after unload
    "boarding": "cleaning",  # board after cleaning
    "pushback": "boarding",  # pushback after boarding
    "gpu_disconnect": "pushback",  # disconnect GPU right before pushback
}


# ─── Aircraft ───

async def create_aircraft(
    db: AsyncSession,
    tail_number: str, flight_number: str, aircraft_type: str,
    airline: str | None = None, gate: str | None = None,
    arrival_time: datetime | None = None, scheduled_departure: datetime | None = None,
    org_id: str | None = None,
) -> Aircraft:
    aircraft = Aircraft(
        id=str(uuid.uuid4()), tail_number=tail_number, flight_number=flight_number,
        aircraft_type=aircraft_type, airline=airline, gate=gate,
        arrival_time=arrival_time, scheduled_departure=scheduled_departure,
        status="scheduled", org_id=org_id,
    )
    db.add(aircraft)
    await db.flush()
    logger.info("aircraft_created", tail=tail_number, flight=flight_number, gate=gate)
    return aircraft


async def get_aircraft(db: AsyncSession, aircraft_id: str) -> Aircraft | None:
    result = await db.execute(select(Aircraft).where(Aircraft.id == aircraft_id))
    return result.scalar_one_or_none()


async def get_aircraft_by_flight(db: AsyncSession, flight_number: str, org_id: str | None = None) -> Aircraft | None:
    query = select(Aircraft).where(Aircraft.flight_number == flight_number)
    if org_id:
        query = query.where(Aircraft.org_id == org_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_aircraft(
    db: AsyncSession, org_id: str | None = None, status: str | None = None,
    gate: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[Sequence[Aircraft], int]:
    query = select(Aircraft)
    count_q = select(func.count(Aircraft.id))
    if org_id:
        query = query.where(Aircraft.org_id == org_id)
        count_q = count_q.where(Aircraft.org_id == org_id)
    if status:
        query = query.where(Aircraft.status == status)
        count_q = count_q.where(Aircraft.status == status)
    if gate:
        query = query.where(Aircraft.gate == gate)
        count_q = count_q.where(Aircraft.gate == gate)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(Aircraft.arrival_time.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


async def update_aircraft_status(
    db: AsyncSession, aircraft_id: str, status: str,
    gate: str | None = None, delay_minutes: int | None = None,
) -> Aircraft | None:
    aircraft = await get_aircraft(db, aircraft_id)
    if not aircraft:
        return None
    aircraft.status = status
    if gate:
        aircraft.gate = gate
    if delay_minutes is not None:
        aircraft.delay_minutes = delay_minutes
    await db.flush()
    logger.info("aircraft_status_updated", aircraft_id=aircraft_id, status=status)
    return aircraft


# ─── Turnarounds ───

async def create_turnaround(
    db: AsyncSession,
    aircraft_id: str, flight_number: str, tail_number: str,
    gate: str | None = None, arrival_time: datetime | None = None,
    scheduled_departure: datetime | None = None,
    org_id: str | None = None,
    auto_generate_tasks: bool = True,
) -> Turnaround:
    turnaround = Turnaround(
        id=str(uuid.uuid4()), aircraft_id=aircraft_id,
        flight_number=flight_number, tail_number=tail_number,
        gate=gate, arrival_time=arrival_time, scheduled_departure=scheduled_departure,
        status="pending", org_id=org_id,
        turnaround_start=arrival_time,
        estimated_turnaround_min=_calc_estimated_turnaround(arrival_time, scheduled_departure),
    )
    db.add(turnaround)
    await db.flush()

    # Link aircraft to turnaround
    aircraft = await get_aircraft(db, aircraft_id)
    if aircraft:
        aircraft.turnaround_id = turnaround.id
        await db.flush()

    if auto_generate_tasks:
        await _generate_standard_tasks(db, turnaround.id)

    # Recount tasks
    await _update_turnaround_counts(db, turnaround.id)
    await db.flush()

    logger.info("turnaround_created", turnaround_id=turnaround.id, flight=flight_number, gate=gate)
    return turnaround


def _calc_estimated_turnaround(arrival: datetime | None, departure: datetime | None) -> int:
    if arrival and departure:
        delta = (departure - arrival).total_seconds() / 60
        return int(max(delta, 30))  # minimum 30 min turnaround
    return 45


async def _generate_standard_tasks(db: AsyncSession, turnaround_id: str) -> list[TurnaroundTask]:
    """Generate the standard set of turnaround tasks."""
    tasks = []
    for task_type, config in STANDARD_TASKS.items():
        depends_on = None
        if task_type in TASK_DEPENDENCIES:
            dep_type = TASK_DEPENDENCIES[task_type]
            # We'll set the dependency after all tasks are created
            pass

        task = TurnaroundTask(
            id=str(uuid.uuid4()), turnaround_id=turnaround_id,
            task_type=task_type, status="pending",
            estimated_duration_min=config["duration"],
        )
        db.add(task)
        tasks.append(task)

    await db.flush()

    # Set dependencies now that we have IDs
    task_by_type = {t.task_type: t for t in tasks}
    for task_type, dep_type in TASK_DEPENDENCIES.items():
        if task_type in task_by_type and dep_type in task_by_type:
            task_by_type[task_type].depends_on_task_id = task_by_type[dep_type].id

    await db.flush()
    return tasks


async def _update_turnaround_counts(db: AsyncSession, turnaround_id: str) -> None:
    result = await db.execute(
        select(
            func.count(TurnaroundTask.id),
            func.sum(case((TurnaroundTask.status == "completed", 1), else_=0)),
            func.sum(case((TurnaroundTask.status == "in_progress", 1), else_=0)),
            func.sum(case((TurnaroundTask.status == "pending", 1), else_=0)),
        ).where(TurnaroundTask.turnaround_id == turnaround_id)
    )
    total, completed, in_progress, pending = result.one()
    turnaround = await db.get(Turnaround, turnaround_id)
    if turnaround:
        turnaround.total_tasks = total or 0
        turnaround.completed_tasks = completed or 0
        turnaround.in_progress_tasks = in_progress or 0
        turnaround.pending_tasks = pending or 0
        await db.flush()


async def get_turnaround(db: AsyncSession, turnaround_id: str) -> Turnaround | None:
    result = await db.execute(select(Turnaround).where(Turnaround.id == turnaround_id))
    return result.scalar_one_or_none()


async def get_turnaround_by_flight(
    db: AsyncSession, flight_number: str, org_id: str | None = None,
) -> dict | None:
    """Get full turnaround details including tasks — the dashboard view."""
    query = select(Turnaround).where(Turnaround.flight_number == flight_number)
    if org_id:
        query = query.where(Turnaround.org_id == org_id)
    result = await db.execute(query)
    turnaround = result.scalar_one_or_none()
    if not turnaround:
        return None

    # Fetch tasks
    tasks_result = await db.execute(
        select(TurnaroundTask).where(TurnaroundTask.turnaround_id == turnaround.id)
        .order_by(TurnaroundTask.task_type)
    )
    tasks = tasks_result.scalars().all()

    # Calculate progress
    progress_pct = 0
    if turnaround.total_tasks > 0:
        progress_pct = int((turnaround.completed_tasks / turnaround.total_tasks) * 100)

    # Check for issues
    issues = [t for t in tasks if t.issue_flag]

    return {
        "turnaround_id": turnaround.id,
        "flight_number": turnaround.flight_number,
        "tail_number": turnaround.tail_number,
        "gate": turnaround.gate,
        "status": turnaround.status,
        "arrival_time": turnaround.arrival_time.isoformat() if turnaround.arrival_time else None,
        "scheduled_departure": turnaround.scheduled_departure.isoformat() if turnaround.scheduled_departure else None,
        "actual_departure": turnaround.actual_departure.isoformat() if turnaround.actual_departure else None,
        "progress_percent": progress_pct,
        "total_tasks": turnaround.total_tasks,
        "completed_tasks": turnaround.completed_tasks,
        "in_progress_tasks": turnaround.in_progress_tasks,
        "pending_tasks": turnaround.pending_tasks,
        "estimated_turnaround_min": turnaround.estimated_turnaround_min,
        "actual_turnaround_min": turnaround.actual_turnaround_min,
        "departure_risk": turnaround.departure_risk,
        "delay_minutes": turnaround.delay_minutes,
        "delay_reason": turnaround.delay_reason,
        "issues_count": len(issues),
        "tasks": [_task_to_dict(t) for t in tasks],
    }


def _task_to_dict(t: TurnaroundTask) -> dict:
    return {
        "task_id": t.id,
        "task_type": t.task_type,
        "status": t.status,
        "assigned_crew_id": t.assigned_crew_id,
        "assigned_equipment_id": t.assigned_equipment_id,
        "estimated_duration_min": t.estimated_duration_min,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "actual_duration_min": t.actual_duration_min,
        "depends_on_task_id": t.depends_on_task_id,
        "notes": t.notes,
        "issue_flag": t.issue_flag,
        "issue_description": t.issue_description,
    }


async def list_turnarounds(
    db: AsyncSession, org_id: str | None = None, status: str | None = None,
    limit: int = 50, offset: int = 0,
) -> tuple[Sequence[Turnaround], int]:
    query = select(Turnaround)
    count_q = select(func.count(Turnaround.id))
    if org_id:
        query = query.where(Turnaround.org_id == org_id)
        count_q = count_q.where(Turnaround.org_id == org_id)
    if status:
        query = query.where(Turnaround.status == status)
        count_q = count_q.where(Turnaround.status == status)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(Turnaround.arrival_time.desc()).limit(limit).offset(offset))
    return result.scalars().all(), total


# ─── Task Management ───

async def get_task(db: AsyncSession, task_id: str) -> TurnaroundTask | None:
    result = await db.execute(select(TurnaroundTask).where(TurnaroundTask.id == task_id))
    return result.scalar_one_or_none()


async def update_task_status(
    db: AsyncSession, task_id: str, status: str,
    notes: str | None = None, issue_flag: bool = False,
    issue_description: str | None = None,
) -> TurnaroundTask | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    now = datetime.now(timezone.utc)
    task.status = status

    if status == "in_progress" and not task.started_at:
        task.started_at = now
    elif status == "completed":
        task.completed_at = now
        if task.started_at:
            delta = (now - task.started_at).total_seconds() / 60
            task.actual_duration_min = int(delta)
    elif status == "skipped":
        task.completed_at = now

    if notes:
        task.notes = notes
    if issue_flag:
        task.issue_flag = True
        task.issue_description = issue_description

    await db.flush()

    # Update turnaround counts
    await _update_turnaround_counts(db, task.turnaround_id)

    # Check if turnaround is complete
    turnaround = await db.get(Turnaround, task.turnaround_id)
    if turnaround and turnaround.completed_tasks == turnaround.total_tasks and turnaround.status != "completed":
        turnaround.status = "completed"
        turnaround.turnaround_end = now
        if turnaround.turnaround_start:
            delta = (now - turnaround.turnaround_start).total_seconds() / 60
            turnaround.actual_turnaround_min = int(delta)
        await db.flush()

    # Recalculate risk after task status change
    await recalculate_risk(db, task.turnaround_id)

    logger.info("task_status_updated", task_id=task_id, status=status, turnaround_id=task.turnaround_id)
    return task


async def list_turnaround_tasks(
    db: AsyncSession, turnaround_id: str,
) -> list[TurnaroundTask]:
    result = await db.execute(
        select(TurnaroundTask).where(TurnaroundTask.turnaround_id == turnaround_id)
        .order_by(TurnaroundTask.task_type)
    )
    return list(result.scalars().all())


# ─── Crew Assignment ───

async def assign_crew_to_task(
    db: AsyncSession, task_id: str, crew_id: str,
) -> TurnaroundTask | None:
    task = await get_task(db, task_id)
    if not task:
        return None

    # Verify crew is available
    crew = await db.get(GroundCrew, crew_id)
    if not crew:
        return None

    task.assigned_crew_id = crew_id
    if task.status == "pending":
        task.status = "assigned"
    crew.status = "assigned"
    crew.current_task_id = task_id

    await db.flush()
    logger.info("crew_assigned", crew_id=crew_id, task_id=task_id, task_type=task.task_type)
    return task


async def create_crew_member(
    db: AsyncSession, name: str, role: str,
    qualifications: list[str] | None = None,
    shift_start: datetime | None = None, shift_end: datetime | None = None,
    org_id: str | None = None,
) -> GroundCrew:
    crew = GroundCrew(
        id=str(uuid.uuid4()), name=name, role=role, status="available",
        qualifications=json.dumps(qualifications) if qualifications else None,
        shift_start=shift_start, shift_end=shift_end, org_id=org_id,
    )
    db.add(crew)
    await db.flush()
    logger.info("crew_member_created", name=name, role=role)
    return crew


async def list_crew(
    db: AsyncSession, org_id: str | None = None, status: str | None = None,
    role: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[Sequence[GroundCrew], int]:
    query = select(GroundCrew)
    count_q = select(func.count(GroundCrew.id))
    if org_id:
        query = query.where(GroundCrew.org_id == org_id)
        count_q = count_q.where(GroundCrew.org_id == org_id)
    if status:
        query = query.where(GroundCrew.status == status)
        count_q = count_q.where(GroundCrew.status == status)
    if role:
        query = query.where(GroundCrew.role == role)
        count_q = count_q.where(GroundCrew.role == role)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(GroundCrew.name).limit(limit).offset(offset))
    return result.scalars().all(), total


async def get_available_crew(
    db: AsyncSession, org_id: str | None = None, role: str | None = None,
) -> list[GroundCrew]:
    """Get crew members who are available for assignment."""
    query = select(GroundCrew).where(GroundCrew.status == "available")
    if org_id:
        query = query.where(GroundCrew.org_id == org_id)
    if role:
        query = query.where(GroundCrew.role == role)
    result = await db.execute(query)
    return list(result.scalars().all())


# ─── Equipment ───

async def create_equipment(
    db: AsyncSession, name: str, equipment_type: str,
    current_location: str | None = None,
    fuel_capacity_liters: int | None = None, current_fuel_liters: int | None = None,
    org_id: str | None = None,
) -> Equipment:
    equipment = Equipment(
        id=str(uuid.uuid4()), name=name, equipment_type=equipment_type,
        status="available", current_location=current_location,
        fuel_capacity_liters=fuel_capacity_liters, current_fuel_liters=current_fuel_liters,
        org_id=org_id,
    )
    db.add(equipment)
    await db.flush()
    logger.info("equipment_created", name=name, type=equipment_type)
    return equipment


async def list_equipment(
    db: AsyncSession, org_id: str | None = None, status: str | None = None,
    equipment_type: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[Sequence[Equipment], int]:
    query = select(Equipment)
    count_q = select(func.count(Equipment.id))
    if org_id:
        query = query.where(Equipment.org_id == org_id)
        count_q = count_q.where(Equipment.org_id == org_id)
    if status:
        query = query.where(Equipment.status == status)
        count_q = count_q.where(Equipment.status == status)
    if equipment_type:
        query = query.where(Equipment.equipment_type == equipment_type)
        count_q = count_q.where(Equipment.equipment_type == equipment_type)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.order_by(Equipment.name).limit(limit).offset(offset))
    return result.scalars().all(), total


async def assign_equipment_to_task(
    db: AsyncSession, task_id: str, equipment_id: str,
) -> TurnaroundTask | None:
    task = await get_task(db, task_id)
    if not task:
        return None
    equipment = await db.get(Equipment, equipment_id)
    if not equipment:
        return None

    task.assigned_equipment_id = equipment_id
    equipment.status = "in_use"
    if task.turnaround_id:
        turnaround = await db.get(Turnaround, task.turnaround_id)
        if turnaround:
            equipment.assigned_gate = turnaround.gate

    await db.flush()
    logger.info("equipment_assigned", equipment_id=equipment_id, task_id=task_id)
    return task


# ─── Delay Prediction ───

async def recalculate_risk(db: AsyncSession, turnaround_id: str) -> dict:
    """
    AI-powered departure risk assessment.
    Analyzes task completion velocity, time remaining, blocked tasks, and issues.
    Returns risk level and predicted delay.
    """
    turnaround = await db.get(Turnaround, turnaround_id)
    if not turnaround:
        return {"risk": "unknown", "delay_minutes": 0, "factors": []}

    now = datetime.now(timezone.utc)
    factors = []
    delay_minutes = 0

    # Time remaining until scheduled departure
    if turnaround.scheduled_departure:
        time_remaining_min = (turnaround.scheduled_departure - now).total_seconds() / 60
    else:
        time_remaining_min = 60  # assume 60 min if no schedule

    # Pending task time estimate
    tasks_result = await db.execute(
        select(TurnaroundTask).where(TurnaroundTask.turnaround_id == turnaround_id)
    )
    tasks = tasks_result.scalars().all()

    pending_time = sum(
        t.estimated_duration_min for t in tasks
        if t.status in ("pending", "assigned")
    )
    in_progress_remaining = sum(
        max(t.estimated_duration_min - (t.actual_duration_min or 0), 5) for t in tasks
        if t.status == "in_progress"
    )
    total_remaining = pending_time + in_progress_remaining

    # Factor 1: Time pressure
    if total_remaining > time_remaining_min:
        overrun = int(total_remaining - time_remaining_min)
        delay_minutes = max(delay_minutes, overrun)
        factors.append(f"Estimated task time ({int(total_remaining)} min) exceeds remaining time ({int(time_remaining_min)} min)")

    # Factor 2: Blocked tasks — only count if a task is ready to start
    # (assigned/in_progress) but its dependency is not completed or is delayed
    blocked_tasks = 0
    task_by_id = {t.id: t for t in tasks}
    for t in tasks:
        if t.depends_on_task_id and t.depends_on_task_id in task_by_id:
            dep = task_by_id[t.depends_on_task_id]
            # Only count as blocked if the dependent task is actively waiting
            # (assigned or in_progress) but dependency isn't done
            if t.status in ("assigned", "in_progress") and dep.status not in ("completed", "skipped"):
                blocked_tasks += 1
            # Also count if dependency was skipped/delayed with an issue
            elif dep.status == "delayed" and dep.issue_flag:
                blocked_tasks += 1
    if blocked_tasks > 0:
        delay_minutes += blocked_tasks * 5
        factors.append(f"{blocked_tasks} tasks blocked by incomplete dependencies")

    # Factor 3: Issues flagged on tasks
    issue_count = sum(1 for t in tasks if t.issue_flag)
    if issue_count > 0:
        delay_minutes += issue_count * 10
        factors.append(f"{issue_count} tasks have flagged issues")

    # Factor 4: Unassigned critical tasks
    critical_types = {"fueling", "boarding", "pushback"}
    unassigned_critical = sum(
        1 for t in tasks
        if t.task_type in critical_types and t.status == "pending" and not t.assigned_crew_id
    )
    if unassigned_critical > 0:
        delay_minutes += unassigned_critical * 3
        factors.append(f"{unassigned_critical} critical tasks unassigned")

    # Determine risk level
    if delay_minutes == 0 and total_remaining <= time_remaining_min * 0.8:
        risk = "low"
    elif delay_minutes <= 10:
        risk = "medium"
    elif delay_minutes <= 30:
        risk = "high"
    else:
        risk = "critical"

    # Update turnaround
    turnaround.departure_risk = risk
    turnaround.delay_minutes = delay_minutes
    await db.flush()

    # Create or update alert if high risk
    if risk in ("high", "critical"):
        await _create_delay_alert(
            db, turnaround, risk, delay_minutes, factors, org_id=turnaround.org_id
        )

    result = {
        "turnaround_id": turnaround_id,
        "risk": risk,
        "delay_minutes": delay_minutes,
        "time_remaining_min": int(time_remaining_min),
        "estimated_task_time_min": int(total_remaining),
        "blocked_tasks": blocked_tasks,
        "issues": issue_count,
        "unassigned_critical": unassigned_critical,
        "factors": factors,
    }
    logger.info("risk_calculated", turnaround_id=turnaround_id, risk=risk, delay=delay_minutes)
    return result


async def _create_delay_alert(
    db: AsyncSession, turnaround: Turnaround, risk: str,
    delay_minutes: int, factors: list[str], org_id: str | None = None,
) -> OperationsAlert:
    alert = OperationsAlert(
        id=str(uuid.uuid4()),
        alert_type="delay_prediction",
        severity=risk,
        title=f"Departure delay risk for {turnaround.flight_number} at gate {turnaround.gate or 'N/A'}",
        description=f"Predicted delay: {delay_minutes} minutes. Contributing factors: {'; '.join(factors)}",
        turnaround_id=turnaround.id,
        flight_number=turnaround.flight_number,
        gate=turnaround.gate,
        predicted_delay_min=delay_minutes,
        confidence_score=0.75 if risk == "critical" else 0.65,
        contributing_factors=json.dumps(factors),
        org_id=org_id,
    )
    db.add(alert)
    await db.flush()
    logger.info("delay_alert_created", flight=turnaround.flight_number, risk=risk, delay=delay_minutes)
    return alert


# ─── Alerts ───

async def list_alerts(
    db: AsyncSession, org_id: str | None = None, status: str = "active",
    severity: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[Sequence[OperationsAlert], int]:
    query = select(OperationsAlert).where(OperationsAlert.status == status)
    count_q = select(func.count(OperationsAlert.id)).where(OperationsAlert.status == status)
    if org_id:
        query = query.where(OperationsAlert.org_id == org_id)
        count_q = count_q.where(OperationsAlert.org_id == org_id)
    if severity:
        query = query.where(OperationsAlert.severity == severity)
        count_q = count_q.where(OperationsAlert.severity == severity)
    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(
        query.order_by(OperationsAlert.created_date.desc()).limit(limit).offset(offset)
    )
    return result.scalars().all(), total


async def acknowledge_alert(
    db: AsyncSession, alert_id: str, user_id: str,
) -> OperationsAlert | None:
    alert = await db.get(OperationsAlert, alert_id)
    if not alert:
        return None
    alert.status = "acknowledged"
    alert.acknowledged_by = user_id
    await db.flush()
    logger.info("alert_acknowledged", alert_id=alert_id, by=user_id)
    return alert


async def resolve_alert(db: AsyncSession, alert_id: str) -> OperationsAlert | None:
    alert = await db.get(OperationsAlert, alert_id)
    if not alert:
        return None
    alert.status = "resolved"
    await db.flush()
    logger.info("alert_resolved", alert_id=alert_id)
    return alert


async def create_manual_alert(
    db: AsyncSession, alert_type: str, severity: str, title: str, description: str,
    flight_number: str | None = None, gate: str | None = None,
    aircraft_id: str | None = None, org_id: str | None = None,
) -> OperationsAlert:
    alert = OperationsAlert(
        id=str(uuid.uuid4()), alert_type=alert_type, severity=severity,
        title=title, description=description,
        flight_number=flight_number, gate=gate, aircraft_id=aircraft_id,
        org_id=org_id,
    )
    db.add(alert)
    await db.flush()
    logger.info("manual_alert_created", alert_type=alert_type, severity=severity)
    return alert


# ─── Dashboard ───

async def get_dashboard(db: AsyncSession, org_id: str | None = None) -> dict:
    """Get the full operations dashboard — a snapshot of everything happening right now."""
    # Active aircraft
    aircraft_q = select(Aircraft).where(Aircraft.status.notin_(["departed", "cancelled"]))
    if org_id:
        aircraft_q = aircraft_q.where(Aircraft.org_id == org_id)
    aircraft_result = await db.execute(aircraft_q)
    active_aircraft = aircraft_result.scalars().all()

    # Active turnarounds
    turnaround_q = select(Turnaround).where(Turnaround.status.in_(["pending", "in_progress"]))
    if org_id:
        turnaround_q = turnaround_q.where(Turnaround.org_id == org_id)
    turnaround_result = await db.execute(turnaround_q)
    active_turnarounds = turnaround_result.scalars().all()

    # Active alerts
    alert_q = select(OperationsAlert).where(OperationsAlert.status == "active")
    if org_id:
        alert_q = alert_q.where(OperationsAlert.org_id == org_id)
    alert_result = await db.execute(alert_q.order_by(OperationsAlert.severity.desc()))
    active_alerts = alert_result.scalars().all()

    # Crew status
    crew_q = select(GroundCrew)
    if org_id:
        crew_q = crew_q.where(GroundCrew.org_id == org_id)
    crew_result = await db.execute(crew_q)
    all_crew = crew_result.scalars().all()
    available_crew = [c for c in all_crew if c.status == "available"]
    assigned_crew = [c for c in all_crew if c.status == "assigned"]

    # Equipment status
    equip_q = select(Equipment)
    if org_id:
        equip_q = equip_q.where(Equipment.org_id == org_id)
    equip_result = await db.execute(equip_q)
    all_equipment = equip_result.scalars().all()
    available_equipment = [e for e in all_equipment if e.status == "available"]

    # Risk distribution
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for t in active_turnarounds:
        risk_counts[t.departure_risk] = risk_counts.get(t.departure_risk, 0) + 1

    # Aircraft status distribution
    status_counts: dict[str, int] = {}
    for a in active_aircraft:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_aircraft_count": len(active_aircraft),
        "active_turnarounds_count": len(active_turnarounds),
        "active_alerts_count": len(active_alerts),
        "available_crew_count": len(available_crew),
        "assigned_crew_count": len(assigned_crew),
        "available_equipment_count": len(available_equipment),
        "total_equipment_count": len(all_equipment),
        "risk_distribution": risk_counts,
        "aircraft_status_distribution": status_counts,
        "aircraft": [
            {
                "id": a.id, "tail_number": a.tail_number, "flight_number": a.flight_number,
                "aircraft_type": a.aircraft_type, "airline": a.airline, "gate": a.gate,
                "status": a.status, "departure_risk": a.departure_risk,
                "delay_minutes": a.delay_minutes,
                "arrival_time": a.arrival_time.isoformat() if a.arrival_time else None,
                "scheduled_departure": a.scheduled_departure.isoformat() if a.scheduled_departure else None,
            }
            for a in active_aircraft
        ],
        "turnarounds": [
            {
                "id": t.id, "flight_number": t.flight_number, "tail_number": t.tail_number,
                "gate": t.gate, "status": t.status,
                "progress": int((t.completed_tasks / t.total_tasks * 100) if t.total_tasks > 0 else 0),
                "completed_tasks": t.completed_tasks, "total_tasks": t.total_tasks,
                "departure_risk": t.departure_risk, "delay_minutes": t.delay_minutes,
            }
            for t in active_turnarounds
        ],
        "alerts": [
            {
                "id": a.id, "alert_type": a.alert_type, "severity": a.severity,
                "title": a.title, "flight_number": a.flight_number, "gate": a.gate,
                "predicted_delay_min": a.predicted_delay_min,
                "created_date": a.created_date.isoformat(),
            }
            for a in active_alerts
        ],
    }
