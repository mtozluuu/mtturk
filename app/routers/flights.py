from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models import CrewAssignment, Flight, MaintenanceLog, User

router = APIRouter(prefix="/flights", tags=["flights"])

VALID_SEATS = {"CAPTAIN", "FIRST_OFFICER"}
SEAT_ROLE = {"CAPTAIN": "pilot", "FIRST_OFFICER": "copilot"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateFlightRequest(BaseModel):
    flight_no: str
    flight_date: date
    departure_airport: str
    arrival_airport: str
    sched_dep: datetime
    sched_arr: datetime
    actual_dep: Optional[datetime] = None
    actual_arr: Optional[datetime] = None


class CrewChangeRequest(BaseModel):
    user_id: int
    seat: str


class MaintenanceLogRequest(BaseModel):
    description: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_flight_or_404(flight_id: int, db: Session) -> Flight:
    flight = db.query(Flight).filter(Flight.id == flight_id).first()
    if flight is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")
    return flight


def _flight_dict(f: Flight) -> dict:
    return {
        "id": f.id,
        "flight_no": f.flight_no,
        "flight_date": f.flight_date,
        "departure_airport": f.departure_airport,
        "arrival_airport": f.arrival_airport,
        "sched_dep": f.sched_dep,
        "sched_arr": f.sched_arr,
        "actual_dep": f.actual_dep,
        "actual_arr": f.actual_arr,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_flight(
    body: CreateFlightRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    flight = Flight(
        flight_no=body.flight_no,
        flight_date=body.flight_date,
        departure_airport=body.departure_airport,
        arrival_airport=body.arrival_airport,
        sched_dep=body.sched_dep,
        sched_arr=body.sched_arr,
        actual_dep=body.actual_dep,
        actual_arr=body.actual_arr,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return _flight_dict(flight)


@router.get("")
def list_flights(
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Flight)
    if date is not None:
        try:
            parsed_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="date must be in YYYY-MM-DD format",
            )
        query = query.filter(Flight.flight_date == parsed_date)
    flights = query.order_by(Flight.sched_dep).all()
    return [_flight_dict(f) for f in flights]


@router.post("/{flight_id}/crew/change", status_code=status.HTTP_200_OK)
def change_crew(
    flight_id: int,
    body: CrewChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_flight_or_404(flight_id, db)

    seat = body.seat.upper()
    if seat not in VALID_SEATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"seat must be one of: {', '.join(sorted(VALID_SEATS))}",
        )

    new_user = db.query(User).filter(User.id == body.user_id).first()
    if new_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    required_role = SEAT_ROLE[seat]
    if new_user.role != required_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Seat {seat} requires a user with role '{required_role}'",
        )

    active = (
        db.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.seat == seat,
            CrewAssignment.end_time.is_(None),
        )
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if active:
        active.end_time = now

    assignment = CrewAssignment(
        flight_id=flight_id,
        user_id=body.user_id,
        seat=seat,
        start_time=now,
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat already actively assigned on this flight",
        )
    db.refresh(assignment)
    return {
        "id": assignment.id,
        "flight_id": assignment.flight_id,
        "user_id": assignment.user_id,
        "seat": assignment.seat,
        "start_time": assignment.start_time,
    }


@router.get("/{flight_id}/crew")
def get_crew(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_flight_or_404(flight_id, db)
    assignments = (
        db.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id)
        .order_by(CrewAssignment.start_time)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "seat": a.seat,
            "start_time": a.start_time,
            "end_time": a.end_time,
        }
        for a in assignments
    ]


@router.get("/{flight_id}/crew/active")
def get_active_crew(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_flight_or_404(flight_id, db)
    assignments = (
        db.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.end_time.is_(None),
        )
        .order_by(CrewAssignment.seat)
        .all()
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "seat": a.seat,
            "start_time": a.start_time,
        }
        for a in assignments
    ]


@router.post("/{flight_id}/maintenance-logs", status_code=status.HTTP_201_CREATED)
def create_maintenance_log(
    flight_id: int,
    body: MaintenanceLogRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_flight_or_404(flight_id, db)
    log = MaintenanceLog(
        flight_id=flight_id,
        user_id=1,
        description=body.description,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {
        "id": log.id,
        "flight_id": log.flight_id,
        "user_id": log.user_id,
        "description": log.description,
        "logged_at": log.logged_at,
    }


@router.get("/{flight_id}/maintenance-logs")
def get_maintenance_logs(
    flight_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    _get_flight_or_404(flight_id, db)
    logs = (
        db.query(MaintenanceLog)
        .filter(MaintenanceLog.flight_id == flight_id)
        .order_by(MaintenanceLog.logged_at)
        .all()
    )
    return [
        {
            "id": lg.id,
            "user_id": lg.user_id,
            "description": lg.description,
            "logged_at": lg.logged_at,
        }
        for lg in logs
    ]
