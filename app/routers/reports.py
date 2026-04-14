from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import CrewAssignment, User

router = APIRouter(prefix="/reports", tags=["reports"])


def _parse_utc_datetime(value: str) -> datetime:
    """Parse an ISO 8601 datetime string and return a UTC-aware datetime."""
    normalised = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalised)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@router.get("/seat-time")
def seat_time_report(
    start: str,
    end: str,
    user_id: Optional[int] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return total seat time (seconds) for crew assignments within a UTC time range.

    - Admins/managers can query any user (or all users when user_id is omitted).
    - Pilots only see their own seat time (user_id param is ignored).
    """
    try:
        start_dt = _parse_utc_datetime(start)
        end_dt = _parse_utc_datetime(end)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start and end must be ISO 8601 datetime strings",
        )

    # Pilots and copilots can only see their own data
    if current_user.role in ("pilot", "copilot"):
        target_user_id = current_user.id
    else:
        target_user_id = user_id  # None means all users

    query = db.query(CrewAssignment).filter(
        and_(
            CrewAssignment.start_time < end_dt,
            # Include assignments that are still active (end_time IS NULL) or ended after start
            (CrewAssignment.end_time.is_(None)) | (CrewAssignment.end_time > start_dt),
        )
    )

    if target_user_id is not None:
        query = query.filter(CrewAssignment.user_id == target_user_id)

    assignments = query.all()

    # Calculate seat time within the requested range
    now = datetime.now(timezone.utc)
    results: dict[int, float] = {}
    for a in assignments:
        effective_start = max(a.start_time.replace(tzinfo=timezone.utc) if a.start_time.tzinfo is None else a.start_time, start_dt)
        effective_end_raw = a.end_time if a.end_time is not None else now
        if effective_end_raw.tzinfo is None:
            effective_end_raw = effective_end_raw.replace(tzinfo=timezone.utc)
        effective_end = min(effective_end_raw, end_dt)
        seconds = max(0.0, (effective_end - effective_start).total_seconds())
        uid = a.user_id
        results[uid] = results.get(uid, 0.0) + seconds

    if target_user_id is not None:
        # Return single-user result
        return {
            "user_id": target_user_id,
            "seat_time_seconds": results.get(target_user_id, 0.0),
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        }

    return {
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "results": [
            {"user_id": uid, "seat_time_seconds": secs}
            for uid, secs in sorted(results.items())
        ],
    }
