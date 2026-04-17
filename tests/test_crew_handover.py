from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base
from app.models import CrewAssignment, Flight, User


@pytest.fixture()
def db_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main_module, "SessionLocal", Session)
    main_module.app.dependency_overrides[main_module.get_db] = override_get_db

    yield Session

    main_module.app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(monkeypatch, db_session_factory):
    monkeypatch.setattr(
        main_module,
        "get_session_user",
        lambda request: SimpleNamespace(id=999, username="admin", role="admin"),
    )
    with TestClient(main_module.app, raise_server_exceptions=True) as test_client:
        yield test_client


def _create_crew_users(db):
    captain = User(username="captain1", password_hash="x", role="pilot")
    first_officer = User(username="firstofficer1", password_hash="x", role="copilot")
    db.add_all([captain, first_officer])
    db.commit()
    db.refresh(captain)
    db.refresh(first_officer)
    return captain, first_officer


def _create_flight(db, *, active: bool):
    now = datetime.utcnow()
    flight = Flight(
        flight_no="TK100",
        flight_date=date.today(),
        departure_airport="IST",
        arrival_airport="ESB",
        sched_dep=now - timedelta(hours=2),
        sched_arr=now + timedelta(hours=1),
        actual_dep=(now - timedelta(hours=1)) if active else None,
        actual_arr=None,
    )
    db.add(flight)
    db.commit()
    db.refresh(flight)
    return flight


def test_same_active_crew_selection_is_noop(db_session_factory, client):
    db = db_session_factory()
    captain, first_officer = _create_crew_users(db)
    flight = _create_flight(db, active=True)
    captain_id = captain.id
    first_officer_id = first_officer.id
    flight_id = flight.id
    start_time = datetime.utcnow() - timedelta(minutes=20)
    db.add_all(
        [
            CrewAssignment(
                flight_id=flight_id,
                user_id=captain_id,
                seat="CAPTAIN",
                start_time=start_time,
            ),
            CrewAssignment(
                flight_id=flight_id,
                user_id=first_officer_id,
                seat="FIRST_OFFICER",
                start_time=start_time,
            ),
        ]
    )
    db.commit()
    db.close()

    response = client.post(
        f"/admin-ui/flights/{flight_id}/crew",
        data={
            "captain_user_id": str(captain_id),
            "first_officer_user_id": str(first_officer_id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin-ui/flights/{flight_id}/crew?success=crew_updated"

    verify_db = db_session_factory()
    assignments = (
        verify_db.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id)
        .order_by(CrewAssignment.id.asc())
        .all()
    )
    verify_db.close()

    assert len(assignments) == 2
    assert all(assignment.end_time is None for assignment in assignments)
    assert {assignment.seat for assignment in assignments} == {"CAPTAIN", "FIRST_OFFICER"}


def test_handover_rejected_when_flight_is_not_active(db_session_factory, client):
    db = db_session_factory()
    captain, first_officer = _create_crew_users(db)
    flight = _create_flight(db, active=False)
    captain_id = captain.id
    first_officer_id = first_officer.id
    flight_id = flight.id
    db.close()

    response = client.post(
        f"/admin-ui/flights/{flight_id}/crew",
        data={
            "captain_user_id": str(captain_id),
            "first_officer_user_id": str(first_officer_id),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/admin-ui/flights/{flight_id}/crew?error=flight_not_active"

    verify_db = db_session_factory()
    assignments_count = (
        verify_db.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id)
        .count()
    )
    verify_db.close()

    assert assignments_count == 0
