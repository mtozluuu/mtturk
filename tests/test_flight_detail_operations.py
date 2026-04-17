from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base
from app.main import app
from app.models import CrewAssignment, Flight, FlightNote, User


@pytest.fixture()
def ops_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        main_module,
        "get_session_user",
        lambda request: type("OpsUser", (), {"id": 1, "username": "ops_user", "role": "pilot"})(),
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[main_module.get_db] = override_get_db

    session = TestingSessionLocal()
    now = datetime.utcnow()

    ops_user = User(id=1, username="ops_user", password_hash="x", role="pilot")
    pilot_user = User(username="pilot_user", password_hash="x", role="pilot")
    copilot_user = User(username="copilot_user", password_hash="x", role="copilot")
    session.add_all([ops_user, pilot_user, copilot_user])
    session.flush()

    flight = Flight(
        flight_no="TK500",
        flight_date=date.today(),
        departure_airport="IST",
        arrival_airport="ADB",
        sched_dep=now - timedelta(hours=1),
        sched_arr=now + timedelta(hours=1),
        actual_dep=None,
        actual_arr=None,
    )
    session.add(flight)
    session.flush()

    session.add_all(
        [
            CrewAssignment(
                flight_id=flight.id,
                user_id=pilot_user.id,
                seat="CAPTAIN",
                start_time=now - timedelta(hours=1),
                end_time=None,
            ),
            CrewAssignment(
                flight_id=flight.id,
                user_id=copilot_user.id,
                seat="FIRST_OFFICER",
                start_time=now - timedelta(hours=1),
                end_time=None,
            ),
        ]
    )
    session.commit()
    flight_id = flight.id
    pilot_user_id = pilot_user.id
    copilot_user_id = copilot_user.id
    session.close()

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client, TestingSessionLocal, flight_id, pilot_user_id, copilot_user_id

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_flight_detail_operational_page_shows_live_sections(ops_client):
    client, _, flight_id, _, _ = ops_client

    response = client.get(f"/flight-detail/{flight_id}")
    assert response.status_code == 200
    assert "mark-departure" in response.text
    assert "mark-arrival" in response.text
    assert f"/flight-detail/{flight_id}/crew" in response.text
    assert f"/flight-detail/{flight_id}/notes" in response.text


def test_mark_departure_now_sets_once_without_overwrite(ops_client):
    client, SessionLocal, flight_id, _, _ = ops_client

    first = client.post(f"/flight-detail/{flight_id}/mark-departure", follow_redirects=False)
    assert first.status_code == 303
    assert first.headers["location"].endswith(f"/flight-detail/{flight_id}?success=actual_departure_marked")

    session = SessionLocal()
    flight = session.query(Flight).filter(Flight.id == flight_id).first()
    assert flight.actual_dep is not None
    first_dep = flight.actual_dep
    session.close()

    second = client.post(f"/flight-detail/{flight_id}/mark-departure", follow_redirects=False)
    assert second.status_code == 303
    assert second.headers["location"].endswith(f"/flight-detail/{flight_id}?error=actual_departure_set")

    session = SessionLocal()
    flight = session.query(Flight).filter(Flight.id == flight_id).first()
    assert flight.actual_dep == first_dep
    session.close()


def test_mark_arrival_closes_open_assignments(ops_client):
    client, SessionLocal, flight_id, _, _ = ops_client

    mark_dep = client.post(f"/flight-detail/{flight_id}/mark-departure", follow_redirects=False)
    assert mark_dep.status_code == 303

    response = client.post(f"/flight-detail/{flight_id}/mark-arrival", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/flight-detail/{flight_id}?success=actual_arrival_marked")

    session = SessionLocal()
    flight = session.query(Flight).filter(Flight.id == flight_id).first()
    assert flight.actual_arr is not None

    open_assignments = (
        session.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id, CrewAssignment.end_time.is_(None))
        .all()
    )
    assert len(open_assignments) == 0
    session.close()


def test_add_flight_note_uses_dedicated_model_and_history(ops_client):
    client, SessionLocal, flight_id, _, _ = ops_client

    post_response = client.post(
        f"/flight-detail/{flight_id}/notes",
        data={"note": "Gate change confirmed"},
        follow_redirects=False,
    )
    assert post_response.status_code == 303
    assert post_response.headers["location"].endswith(f"/flight-detail/{flight_id}?success=flight_note_created")

    session = SessionLocal()
    notes = session.query(FlightNote).filter(FlightNote.flight_id == flight_id).all()
    assert len(notes) == 1
    assert notes[0].note == "Gate change confirmed"
    session.close()

    page = client.get(f"/flight-detail/{flight_id}")
    assert page.status_code == 200
    assert "Gate change confirmed" in page.text


def test_crew_update_allows_cross_role_assignments_and_blocks_same_person(ops_client):
    client, SessionLocal, flight_id, pilot_user_id, copilot_user_id = ops_client

    update_response = client.post(
        f"/flight-detail/{flight_id}/crew",
        data={
            "captain_user_id": str(copilot_user_id),
            "first_officer_user_id": str(pilot_user_id),
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303
    assert update_response.headers["location"].endswith(f"/flight-detail/{flight_id}?success=crew_updated")

    session = SessionLocal()
    active_captain = (
        session.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.seat == "CAPTAIN",
            CrewAssignment.end_time.is_(None),
        )
        .first()
    )
    active_first_officer = (
        session.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == flight_id,
            CrewAssignment.seat == "FIRST_OFFICER",
            CrewAssignment.end_time.is_(None),
        )
        .first()
    )
    assert active_captain.user_id == copilot_user_id
    assert active_first_officer.user_id == pilot_user_id
    session.close()

    same_user_response = client.post(
        f"/flight-detail/{flight_id}/crew",
        data={
            "captain_user_id": str(copilot_user_id),
            "first_officer_user_id": str(copilot_user_id),
        },
        follow_redirects=False,
    )
    assert same_user_response.status_code == 303
    assert same_user_response.headers["location"].endswith(f"/flight-detail/{flight_id}?error=same_personnel")
