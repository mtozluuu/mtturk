from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.database import Base
from app.models import CrewAssignment, Flight, User


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    def override_get_db():
        yield session

    main_module.app.dependency_overrides[main_module.get_db] = override_get_db
    monkeypatch.setattr(
        main_module,
        "get_session_user",
        lambda request: SimpleNamespace(id=1, username="admin", role="admin"),
    )

    yield session

    main_module.app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def seeded_flight(db_session):
    now = datetime.utcnow()

    pilot_old = User(username="pilot_old", password_hash="x", role="pilot")
    pilot_new = User(username="pilot_new", password_hash="x", role="pilot")
    copilot_old = User(username="copilot_old", password_hash="x", role="copilot")
    copilot_new = User(username="copilot_new", password_hash="x", role="copilot")

    db_session.add_all([pilot_old, pilot_new, copilot_old, copilot_new])
    db_session.flush()

    flight = Flight(
        flight_no="TK100",
        flight_date=date.today(),
        departure_airport="IST",
        arrival_airport="ESB",
        sched_dep=now,
        sched_arr=now + timedelta(hours=1),
        actual_dep=now,
    )
    db_session.add(flight)
    db_session.flush()

    captain_assignment = CrewAssignment(
        flight_id=flight.id,
        user_id=pilot_old.id,
        seat="CAPTAIN",
        start_time=now - timedelta(minutes=20),
    )
    first_officer_assignment = CrewAssignment(
        flight_id=flight.id,
        user_id=copilot_old.id,
        seat="FIRST_OFFICER",
        start_time=now - timedelta(minutes=20),
    )
    db_session.add_all([captain_assignment, first_officer_assignment])
    db_session.commit()

    return {
        "flight": flight,
        "pilot_old": pilot_old,
        "pilot_new": pilot_new,
        "copilot_old": copilot_old,
        "copilot_new": copilot_new,
        "captain_assignment": captain_assignment,
        "first_officer_assignment": first_officer_assignment,
    }


def test_handover_closes_active_assignments_and_creates_new_ones(db_session, seeded_flight):
    with TestClient(main_module.app, raise_server_exceptions=True) as client:
        response = client.post(
            f"/admin-ui/flights/{seeded_flight['flight'].id}/crew/change",
            data={
                "captain_user_id": seeded_flight["pilot_new"].id,
                "first_officer_user_id": seeded_flight["copilot_new"].id,
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{seeded_flight['flight'].id}/crew?success=crew_updated"
    )

    updated_captain = seeded_flight["captain_assignment"]
    updated_first_officer = seeded_flight["first_officer_assignment"]
    db_session.refresh(updated_captain)
    db_session.refresh(updated_first_officer)
    assert updated_captain.end_time is not None
    assert updated_first_officer.end_time is not None

    new_assignments = (
        db_session.query(CrewAssignment)
        .filter(
            CrewAssignment.flight_id == seeded_flight["flight"].id,
            CrewAssignment.end_time.is_(None),
        )
        .all()
    )
    assert len(new_assignments) == 2
    new_by_seat = {assignment.seat: assignment for assignment in new_assignments}
    assert new_by_seat["CAPTAIN"].user_id == seeded_flight["pilot_new"].id
    assert new_by_seat["FIRST_OFFICER"].user_id == seeded_flight["copilot_new"].id


def test_handover_rejects_missing_selection(seeded_flight):
    with TestClient(main_module.app, raise_server_exceptions=True) as client:
        response = client.post(
            f"/admin-ui/flights/{seeded_flight['flight'].id}/crew/change",
            data={"captain_user_id": seeded_flight["pilot_new"].id},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{seeded_flight['flight'].id}/crew?error=missing_crew_selection"
    )


def test_handover_rejects_role_mismatch(seeded_flight):
    with TestClient(main_module.app, raise_server_exceptions=True) as client:
        response = client.post(
            f"/admin-ui/flights/{seeded_flight['flight'].id}/crew/change",
            data={
                "captain_user_id": seeded_flight["copilot_new"].id,
                "first_officer_user_id": seeded_flight["pilot_new"].id,
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{seeded_flight['flight'].id}/crew?error=role_mismatch"
    )


def test_handover_rejects_same_user_for_both_roles(seeded_flight):
    with TestClient(main_module.app, raise_server_exceptions=True) as client:
        response = client.post(
            f"/admin-ui/flights/{seeded_flight['flight'].id}/crew/change",
            data={
                "captain_user_id": seeded_flight["pilot_new"].id,
                "first_officer_user_id": seeded_flight["pilot_new"].id,
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{seeded_flight['flight'].id}/crew?error=same_personnel"
    )
