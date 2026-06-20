"""Aerumentis — Operations Module (Phase 3 Stub)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aerumentis.core.logging import get_logger
from aerumentis.core.security import Permission, require_permission

router = APIRouter(prefix="/operations", tags=["operations"])
logger = get_logger("aerumentis.modules.operations")


class TurnaroundTask(BaseModel):
    task_id: str
    task_type: str
    status: str
    assigned_to: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    estimated_duration_min: int | None = None


class TurnaroundStatus(BaseModel):
    flight_number: str
    aircraft_registration: str
    aircraft_type: str
    gate: str
    arrival_time: datetime
    scheduled_departure: datetime
    tasks: list[TurnaroundTask] = Field(default_factory=list)
    departure_risk: str = "low"
    delay_minutes: int = 0
    last_updated: datetime = Field(default_factory=datetime.utcnow)


@router.get("/aircraft", dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def list_aircraft_status():
    return {"aircraft": [], "total": 0,
            "message": "Ground operations dashboard is in Phase 3 development."}


@router.get("/aircraft/{flight_number}", response_model=TurnaroundStatus,
             dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_aircraft_turnaround(flight_number: str):
    return TurnaroundStatus(flight_number=flight_number, aircraft_registration="N/A (Phase 3)",
        aircraft_type="N/A (Phase 3)", gate="N/A (Phase 3)", arrival_time=datetime.utcnow(),
        scheduled_departure=datetime.utcnow(), tasks=[], departure_risk="low", delay_minutes=0)


@router.post("/crew/assign", dependencies=[Depends(require_permission(Permission.OPS_MANAGE))])
async def assign_crew(flight_number: str, crew_member: str, task_type: str):
    return {"assignment_id": "stub-assignment-id", "flight_number": flight_number,
            "crew_member": crew_member, "task_type": task_type, "status": "assigned",
            "message": "Crew assignment is in Phase 3 development."}


@router.get("/alerts", dependencies=[Depends(require_permission(Permission.OPS_VIEW))])
async def get_delay_predictions():
    return {"alerts": [], "total": 0,
            "message": "Predictive delay alerts are in Phase 3 development."}
