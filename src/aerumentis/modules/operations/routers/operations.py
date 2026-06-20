"""
Aerumentis — Operations Module Router (Phase 3)
Full implementation: aircraft tracking, turnaround management, crew assignment,
equipment tracking, delay prediction, and the operations dashboard.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from aerumentis.core.database import get_db
from aerumentis.core.logging import get_logger
from aerumentis.core.security import AuthenticatedUser, Permission, get_current_user, require_permission
from aerumentis.models.schemas import MessageResponse
from aerumentis.services import operations_service

router = APIRouter(prefix="/operations", tags=["operations"])
logger = get_logger("aerumentis.api.operations")


# ─── Schemas ───

class AircraftCreate(BaseModel):
    tail_number: str = Field(..., min_length=2, max_length=20)
    flight_number: str = Field(..., min_length=2, max_length=20)
    aircraft_type: str = Field(..., min_length=2, max_length=50)
    airline: str | None = None
    gate: str | None = None
    arrival_time: datetime | None = None
    scheduled_departure: datetime | None = None


class AircraftResponse(BaseModel):
    id: str
    tail_number: str
    flight_number: str
    aircraft_type: str
    airline: str | None = None
    gate: str | None = None
    status: str
    arrival_time: str | None = None
    scheduled_departure: str | None = None
    actual_departure: str | None = None
    turnaround_id: str | None = None
    departure_risk: str
    delay_minutes: int
    created_date: str
    updated_date: str


class AircraftListResponse(BaseModel):
    aircraft: list[AircraftResponse]
    total: int
    limit: int
    offset: int


class AircraftStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(scheduled|arriving|landed|taxiing_to_gate|at_gate|boarding|taxiing_out|departed|delayed|cancelled)$")
    gate: str | None = None
    delay_minutes: int | None = Field(None, ge=0)


class TurnaroundCreate(BaseModel):
    aircraft_id: str
    flight_number: str
    tail_number: str
    gate: str | None = None
    arrival_time: datetime | None = None
    scheduled_departure: datetime | None = None
    auto_generate_tasks: bool = True


class TurnaroundResponse(BaseModel):
    id: str
    aircraft_id: str
    flight_number: str
    tail_number: str
    gate: str | None = None
    status: str
    arrival_time: str | None = None
    scheduled_departure: str | None = None
    actual_departure: str | None = None
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    estimated_turnaround_min: int
    actual_turnaround_min: int | None = None
    departure_risk: str
    delay_minutes: int
    delay_reason: str | None = None
    created_date: str
    updated_date: str


class TurnaroundListResponse(BaseModel):
    turnarounds: list[TurnaroundResponse]
    total: int
    limit: int
    offset: int


class TurnaroundDetailResponse(BaseModel):
    turnaround_id: str
    flight_number: str
    tail_number: str
    gate: str | None = None
    status: str
    arrival_time: str | None = None
    scheduled_departure: str | None = None
    actual_departure: str | None = None
    progress_percent: int
    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    pending_tasks: int
    estimated_turnaround_min: int
    actual_turnaround_min: int | None = None
    departure_risk: str
    delay_minutes: int
    delay_reason: str | None = None
    issues_count: int
    tasks: list[dict]


class TaskResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    assigned_crew_id: str | None = None
    assigned_equipment_id: str | None = None
    estimated_duration_min: int
    started_at: str | None = None
    completed_at: str | None = None
    actual_duration_min: int | None = None
    depends_on_task_id: str | None = None
    notes: str | None = None
    issue_flag: bool
    issue_description: str | None = None


class TaskStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|assigned|in_progress|completed|skipped|delayed)$")
    notes: str | None = None
    issue_flag: bool = False
    issue_description: str | None = None


class CrewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., pattern="^(ramp_agent|fueler|cleaner|baggage_handler|lavatory_service|caterer|mechanic|supervisor)$")
    qualifications: list[str] = Field(default_factory=list)
    shift_start: datetime | None = None
    shift_end: datetime | None = None


class CrewResponse(BaseModel):
    id: str
    name: str
    role: str
    status: str
    current_task_id: str | None = None
    current_gate: str | None = None
    qualifications: list[str] = Field(default_factory=list)
    shift_start: str | None = None
    shift_end: str | None = None
    created_date: str
    updated_date: str


class CrewListResponse(BaseModel):
    crew: list[CrewResponse]
    total: int
    limit: int
    offset: int


class CrewAssignRequest(BaseModel):
    task_id: str
    crew_id: str


class EquipmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    equipment_type: str = Field(..., min_length=2, max_length=50)
    current_location: str | None = None
    fuel_capacity_liters: int | None = Field(None, ge=0)
    current_fuel_liters: int | None = Field(None, ge=0)


class EquipmentResponse(BaseModel):
    id: str
    name: str
    equipment_type: str
    status: str
    current_location: str | None = None
    assigned_gate: str | None = None
    fuel_capacity_liters: int | None = None
    current_fuel_liters: int | None = None
    created_date: str
    updated_date: str


class EquipmentListResponse(BaseModel):
    equipment: list[EquipmentResponse]
    total: int
    limit: int
    offset: int


class EquipmentAssignRequest(BaseModel):
    task_id: str
    equipment_id: str


class AlertResponse(BaseModel):
    id: str
    alert_type: str
    severity: str
    title: str
    description: str
    flight_number: str | None = None
    gate: str | None = None
    status: str
    acknowledged_by: str | None = None
    predicted_delay_min: int | None = None
    confidence_score: float
    contributing_factors: list[str] = Field(default_factory=list)
    created_date: str
    updated_date: str


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int
    limit: int
    offset: int


class AlertCreate(BaseModel):
    alert_type: str = Field(..., pattern="^(delay_prediction|equipment_failure|crew_shortage|weather|maintenance_alert|security|gate_conflict)$")
    severity: str = Field("medium", pattern="^(info|low|medium|high|critical)$")
    title: str = Field(..., min_length=3, max_length=500)
    description: str = Field(..., min_length=3)
    flight_number: str | None = None
    gate: str | None = None
    aircraft_id: str | None = None


class RiskAssessmentResponse(BaseModel):
    turnaround_id: str
    risk: str
    delay_minutes: int
    time_remaining_min: int
    estimated_task_time_min: int
    blocked_tasks: int
    issues: int
    unassigned_critical: int
    factors: list[str]


class DashboardResponse(BaseModel):
    timestamp: str
    active_aircraft_count: int
    active_turnarounds_count: int
    active_alerts_count: int
    available_crew_count: int
    assigned_crew_count: int
    available_equipment_count: int
    total_equipment_count: int
    risk_distribution: dict[str, int]
    aircraft_status_distribution: dict[str, int]
    aircraft: list[dict]
    turnarounds: list[dict]
    alerts: list[dict]


# ─── Helpers ───

def _aircraft_to_response(a) -> AircraftResponse:
    return AircraftResponse(
        id=a.id, tail_number=a.tail_number, flight_number=a.flight_number,
        aircraft_type=a.aircraft_type, airline=a.airline, gate=a.gate,
        status=a.status,
        arrival_time=a.arrival_time.isoformat() if a.arrival_time else None,
        scheduled_departure=a.scheduled_departure.isoformat() if a.scheduled_departure else None,
        actual_departure=a.actual_departure.isoformat() if a.actual_departure else None,
        turnaround_id=a.turnaround_id,
        departure_risk=a.departure_risk, delay_minutes=a.delay_minutes,
        created_date=a.created_date.isoformat(), updated_date=a.updated_date.isoformat(),
    )


def _turnaround_to_response(t) -> TurnaroundResponse:
    return TurnaroundResponse(
        id=t.id, aircraft_id=t.aircraft_id, flight_number=t.flight_number,
        tail_number=t.tail_number, gate=t.gate, status=t.status,
        arrival_time=t.arrival_time.isoformat() if t.arrival_time else None,
        scheduled_departure=t.scheduled_departure.isoformat() if t.scheduled_departure else None,
        actual_departure=t.actual_departure.isoformat() if t.actual_departure else None,
        total_tasks=t.total_tasks, completed_tasks=t.completed_tasks,
        in_progress_tasks=t.in_progress_tasks, pending_tasks=t.pending_tasks,
        estimated_turnaround_min=t.estimated_turnaround_min,
        actual_turnaround_min=t.actual_turnaround_min,
        departure_risk=t.departure_risk, delay_minutes=t.delay_minutes,
        delay_reason=t.delay_reason,
        created_date=t.created_date.isoformat(), updated_date=t.updated_date.isoformat(),
    )


def _crew_to_response(c) -> CrewResponse:
    import json as _json
    quals = _json.loads(c.qualifications) if c.qualifications else []
    return CrewResponse(
        id=c.id, name=c.name, role=c.role, status=c.status,
        current_task_id=c.current_task_id, current_gate=c.current_gate,
        qualifications=quals,
        shift_start=c.shift_start.isoformat() if c.shift_start else None,
        shift_end=c.shift_end.isoformat() if c.shift_end else None,
        created_date=c.created_date.isoformat(), updated_date=c.updated_date.isoformat(),
    )


def _equipment_to_response(e) -> EquipmentResponse:
    return EquipmentResponse(
        id=e.id, name=e.name, equipment_type=e.equipment_type, status=e.status,
        current_location=e.current_location, assigned_gate=e.assigned_gate,
        fuel_capacity_liters=e.fuel_capacity_liters, current_fuel_liters=e.current_fuel_liters,
        created_date=e.created_date.isoformat(), updated_date=e.updated_date.isoformat(),
    )


def _alert_to_response(a) -> AlertResponse:
    import json as _json
    factors = _json.loads(a.contributing_factors) if a.contributing_factors else []
    return AlertResponse(
        id=a.id, alert_type=a.alert_type, severity=a.severity,
        title=a.title, description=a.description,
        flight_number=a.flight_number, gate=a.gate,
        status=a.status, acknowledged_by=a.acknowledged_by,
        predicted_delay_min=a.predicted_delay_min,
        confidence_score=a.confidence_score, contributing_factors=factors,
        created_date=a.created_date.isoformat(), updated_date=a.updated_date.isoformat(),
    )


# ─── Aircraft Endpoints ───

@router.post("/aircraft", response_model=AircraftResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def create_aircraft(
    request: AircraftCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    aircraft = await operations_service.create_aircraft(
        db=db, tail_number=request.tail_number, flight_number=request.flight_number,
        aircraft_type=request.aircraft_type, airline=request.airline, gate=request.gate,
        arrival_time=request.arrival_time, scheduled_departure=request.scheduled_departure,
        org_id=current_user.org_id,
    )
    await db.refresh(aircraft)
    return _aircraft_to_response(aircraft)


@router.get("/aircraft", response_model=AircraftListResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_aircraft(
    status_filter: str | None = Query(None, alias="status"),
    gate: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    aircraft_list, total = await operations_service.list_aircraft(
        db, org_id=current_user.org_id, status=status_filter, gate=gate,
        limit=limit, offset=offset,
    )
    return AircraftListResponse(
        aircraft=[_aircraft_to_response(a) for a in aircraft_list],
        total=total, limit=limit, offset=offset,
    )


@router.get("/aircraft/{aircraft_id}", response_model=AircraftResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_aircraft(aircraft_id: str, db: AsyncSession = Depends(get_db)):
    aircraft = await operations_service.get_aircraft(db, aircraft_id)
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    return _aircraft_to_response(aircraft)


@router.patch("/aircraft/{aircraft_id}/status", response_model=AircraftResponse,
              dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def update_aircraft_status(
    aircraft_id: str,
    request: AircraftStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    aircraft = await operations_service.update_aircraft_status(
        db, aircraft_id, request.status, request.gate, request.delay_minutes,
    )
    if not aircraft:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    await db.refresh(aircraft)
    return _aircraft_to_response(aircraft)


# ─── Turnaround Endpoints ───

@router.post("/turnarounds", response_model=TurnaroundResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def create_turnaround(
    request: TurnaroundCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    turnaround = await operations_service.create_turnaround(
        db=db, aircraft_id=request.aircraft_id,
        flight_number=request.flight_number, tail_number=request.tail_number,
        gate=request.gate, arrival_time=request.arrival_time,
        scheduled_departure=request.scheduled_departure,
        org_id=current_user.org_id, auto_generate_tasks=request.auto_generate_tasks,
    )
    await db.refresh(turnaround)
    return _turnaround_to_response(turnaround)


@router.get("/turnarounds", response_model=TurnaroundListResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_turnarounds(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    turnarounds, total = await operations_service.list_turnarounds(
        db, org_id=current_user.org_id, status=status_filter,
        limit=limit, offset=offset,
    )
    return TurnaroundListResponse(
        turnarounds=[_turnaround_to_response(t) for t in turnarounds],
        total=total, limit=limit, offset=offset,
    )


@router.get("/turnarounds/{turnaround_id}", response_model=TurnaroundDetailResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_turnaround_detail(
    turnaround_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from aerumentis.core.database import Turnaround
    from sqlalchemy import select as sel
    result = await db.execute(sel(Turnaround).where(Turnaround.id == turnaround_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Turnaround not found")
    detail = await operations_service.get_turnaround_by_flight(
        db, flight_number=t.flight_number, org_id=current_user.org_id,
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Turnaround detail not found")
    return TurnaroundDetailResponse(**detail)


@router.get("/turnarounds/flight/{flight_number}", response_model=TurnaroundDetailResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_turnaround_by_flight(
    flight_number: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full turnaround details for a flight — the control tower dashboard view."""
    detail = await operations_service.get_turnaround_by_flight(
        db, flight_number=flight_number, org_id=current_user.org_id,
    )
    if not detail:
        raise HTTPException(status_code=404, detail=f"No turnaround found for flight {flight_number}")
    return TurnaroundDetailResponse(**detail)


# ─── Task Endpoints ───

@router.patch("/tasks/{task_id}", response_model=TaskResponse,
              dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def update_task(
    task_id: str,
    request: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    task = await operations_service.update_task_status(
        db, task_id, request.status, request.notes,
        request.issue_flag, request.issue_description,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.refresh(task)
    return TaskResponse(
        task_id=task.id, task_type=task.task_type, status=task.status,
        assigned_crew_id=task.assigned_crew_id, assigned_equipment_id=task.assigned_equipment_id,
        estimated_duration_min=task.estimated_duration_min,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        actual_duration_min=task.actual_duration_min,
        depends_on_task_id=task.depends_on_task_id, notes=task.notes,
        issue_flag=task.issue_flag, issue_description=task.issue_description,
    )


@router.get("/turnarounds/{turnaround_id}/tasks", response_model=list[TaskResponse],
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_tasks(turnaround_id: str, db: AsyncSession = Depends(get_db)):
    tasks = await operations_service.list_turnaround_tasks(db, turnaround_id)
    return [
        TaskResponse(
            task_id=t.id, task_type=t.task_type, status=t.status,
            assigned_crew_id=t.assigned_crew_id, assigned_equipment_id=t.assigned_equipment_id,
            estimated_duration_min=t.estimated_duration_min,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            actual_duration_min=t.actual_duration_min,
            depends_on_task_id=t.depends_on_task_id, notes=t.notes,
            issue_flag=t.issue_flag, issue_description=t.issue_description,
        )
        for t in tasks
    ]


# ─── Crew Endpoints ───

@router.post("/crew", response_model=CrewResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def create_crew(
    request: CrewCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    crew = await operations_service.create_crew_member(
        db=db, name=request.name, role=request.role,
        qualifications=request.qualifications,
        shift_start=request.shift_start, shift_end=request.shift_end,
        org_id=current_user.org_id,
    )
    await db.refresh(crew)
    return _crew_to_response(crew)


@router.get("/crew", response_model=CrewListResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_crew(
    status_filter: str | None = Query(None, alias="status"),
    role: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    crew_list, total = await operations_service.list_crew(
        db, org_id=current_user.org_id, status=status_filter, role=role,
        limit=limit, offset=offset,
    )
    return CrewListResponse(
        crew=[_crew_to_response(c) for c in crew_list],
        total=total, limit=limit, offset=offset,
    )


@router.get("/crew/available", response_model=list[CrewResponse],
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_available_crew(
    role: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    crew_list = await operations_service.get_available_crew(
        db, org_id=current_user.org_id, role=role,
    )
    return [_crew_to_response(c) for c in crew_list]


@router.post("/crew/assign", response_model=TaskResponse,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def assign_crew(
    request: CrewAssignRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign a crew member to a specific turnaround task."""
    task = await operations_service.assign_crew_to_task(db, request.task_id, request.crew_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task or crew member not found")
    await db.refresh(task)
    return TaskResponse(
        task_id=task.id, task_type=task.task_type, status=task.status,
        assigned_crew_id=task.assigned_crew_id, assigned_equipment_id=task.assigned_equipment_id,
        estimated_duration_min=task.estimated_duration_min,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        actual_duration_min=task.actual_duration_min,
        depends_on_task_id=task.depends_on_task_id, notes=task.notes,
        issue_flag=task.issue_flag, issue_description=task.issue_description,
    )


# ─── Equipment Endpoints ───

@router.post("/equipment", response_model=EquipmentResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def create_equipment(
    request: EquipmentCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    equipment = await operations_service.create_equipment(
        db=db, name=request.name, equipment_type=request.equipment_type,
        current_location=request.current_location,
        fuel_capacity_liters=request.fuel_capacity_liters,
        current_fuel_liters=request.current_fuel_liters,
        org_id=current_user.org_id,
    )
    await db.refresh(equipment)
    return _equipment_to_response(equipment)


@router.get("/equipment", response_model=EquipmentListResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_equipment(
    status_filter: str | None = Query(None, alias="status"),
    equipment_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    equipment_list, total = await operations_service.list_equipment(
        db, org_id=current_user.org_id, status=status_filter,
        equipment_type=equipment_type, limit=limit, offset=offset,
    )
    return EquipmentListResponse(
        equipment=[_equipment_to_response(e) for e in equipment_list],
        total=total, limit=limit, offset=offset,
    )


@router.post("/equipment/assign", response_model=TaskResponse,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def assign_equipment(
    request: EquipmentAssignRequest,
    db: AsyncSession = Depends(get_db),
):
    """Assign equipment (fuel truck, tug, etc.) to a turnaround task."""
    task = await operations_service.assign_equipment_to_task(
        db, request.task_id, request.equipment_id,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task or equipment not found")
    await db.refresh(task)
    return TaskResponse(
        task_id=task.id, task_type=task.task_type, status=task.status,
        assigned_crew_id=task.assigned_crew_id, assigned_equipment_id=task.assigned_equipment_id,
        estimated_duration_min=task.estimated_duration_min,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        actual_duration_min=task.actual_duration_min,
        depends_on_task_id=task.depends_on_task_id, notes=task.notes,
        issue_flag=task.issue_flag, issue_description=task.issue_description,
    )


# ─── Risk & Delay Prediction ───

@router.get("/turnarounds/{turnaround_id}/risk", response_model=RiskAssessmentResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def assess_risk(turnaround_id: str, db: AsyncSession = Depends(get_db)):
    """Get AI-powered departure risk assessment for a turnaround."""
    result = await operations_service.recalculate_risk(db, turnaround_id)
    if result.get("risk") == "unknown":
        raise HTTPException(status_code=404, detail="Turnaround not found")
    return RiskAssessmentResponse(**result)


# ─── Alerts ───

@router.post("/alerts", response_model=AlertResponse, status_code=201,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def create_alert(
    request: AlertCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await operations_service.create_manual_alert(
        db=db, alert_type=request.alert_type, severity=request.severity,
        title=request.title, description=request.description,
        flight_number=request.flight_number, gate=request.gate,
        aircraft_id=request.aircraft_id, org_id=current_user.org_id,
    )
    await db.refresh(alert)
    return _alert_to_response(alert)


@router.get("/alerts", response_model=AlertListResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_alerts(
    status_filter: str = Query("active", alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alerts, total = await operations_service.list_alerts(
        db, org_id=current_user.org_id, status=status_filter,
        severity=severity, limit=limit, offset=offset,
    )
    return AlertListResponse(
        alerts=[_alert_to_response(a) for a in alerts],
        total=total, limit=limit, offset=offset,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse,
             dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def acknowledge_alert(
    alert_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await operations_service.acknowledge_alert(db, alert_id, current_user.user_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.refresh(alert)
    return _alert_to_response(alert)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse,
             dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def resolve_alert(
    alert_id: str, db: AsyncSession = Depends(get_db),
):
    alert = await operations_service.resolve_alert(db, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.refresh(alert)
    return _alert_to_response(alert)


# ─── Dashboard ───

@router.get("/dashboard", response_model=DashboardResponse,
            dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_dashboard(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full operations dashboard — a real-time snapshot of everything happening."""
    dashboard = await operations_service.get_dashboard(db, org_id=current_user.org_id)
    return DashboardResponse(**dashboard)
