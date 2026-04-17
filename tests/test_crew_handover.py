from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import Base
from app.main import app
from app.models import CrewAssignment, Flight, User


@pytest.fixture()
def test_env(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.delenv("SEED_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(main_module, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(main_module, "get_session_user", lambda request: type("AdminUser", (), {"role": "admin"})())

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[main_module.get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as client:
        session = TestingSessionLocal()
        now = datetime.utcnow()

        pilot_1 = User(username="pilot_1", password_hash="x", role="pilot")
        pilot_2 = User(username="pilot_2", password_hash="x", role="pilot")
        copilot_1 = User(username="copilot_1", password_hash="x", role="copilot")
        copilot_2 = User(username="copilot_2", password_hash="x", role="copilot")
        session.add_all([pilot_1, pilot_2, copilot_1, copilot_2])
        session.flush()

        active_flight = Flight(
            flight_no="TK100",
            flight_date=date.today(),
            departure_airport="IST",
            arrival_airport="ESB",
            sched_dep=now - timedelta(hours=1),
            sched_arr=now + timedelta(hours=1),
            actual_dep=now - timedelta(hours=1),
            actual_arr=None,
        )
        inactive_flight = Flight(
            flight_no="TK200",
            flight_date=date.today(),
            departure_airport="IST",
            arrival_airport="AYT",
            sched_dep=now - timedelta(hours=3),
            sched_arr=now - timedelta(hours=2),
            actual_dep=now - timedelta(hours=3),
            actual_arr=now - timedelta(hours=1),
        )
        not_departed_flight = Flight(
            flight_no="TK300",
            flight_date=date.today(),
            departure_airport="IST",
            arrival_airport="ADB",
            sched_dep=now + timedelta(hours=2),
            sched_arr=now + timedelta(hours=3),
            actual_dep=None,
            actual_arr=None,
        )
        session.add_all([active_flight, inactive_flight, not_departed_flight])
        session.flush()

        session.add_all(
            [
                CrewAssignment(
                    flight_id=active_flight.id,
                    user_id=pilot_1.id,
                    seat="CAPTAIN",
                    start_time=now - timedelta(hours=1),
                ),
                CrewAssignment(
                    flight_id=active_flight.id,
                    user_id=copilot_1.id,
                    seat="FIRST_OFFICER",
                    start_time=now - timedelta(hours=1),
                ),
                CrewAssignment(
                    flight_id=inactive_flight.id,
                    user_id=pilot_1.id,
                    seat="CAPTAIN",
                    start_time=now - timedelta(hours=4),
                    end_time=now - timedelta(hours=1),
                ),
                CrewAssignment(
                    flight_id=inactive_flight.id,
                    user_id=copilot_1.id,
                    seat="FIRST_OFFICER",
                    start_time=now - timedelta(hours=4),
                    end_time=now - timedelta(hours=1),
                ),
            ]
        )
        session.commit()

        ids = {
            "active_flight_id": active_flight.id,
            "inactive_flight_id": inactive_flight.id,
            "not_departed_flight_id": not_departed_flight.id,
            "pilot_1_id": pilot_1.id,
            "pilot_2_id": pilot_2.id,
            "copilot_1_id": copilot_1.id,
            "copilot_2_id": copilot_2.id,
        }
        session.close()

        yield client, TestingSessionLocal, ids

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _assignments_for(session, flight_id, seat):
    return (
        session.query(CrewAssignment)
        .filter(CrewAssignment.flight_id == flight_id, CrewAssignment.seat == seat)
        .order_by(CrewAssignment.id)
        .all()
    )


def test_handover_changes_only_pilot(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={"captain_user_id": str(ids["pilot_2_id"]), "first_officer_user_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?success=crew_updated")

    session = SessionLocal()
    captains = _assignments_for(session, ids["active_flight_id"], "CAPTAIN")
    first_officers = _assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")
    assert len(captains) == 2
    assert captains[0].end_time is not None
    assert captains[1].user_id == ids["pilot_2_id"]
    assert captains[1].end_time is None
    assert len(first_officers) == 1
    assert first_officers[0].user_id == ids["copilot_1_id"]
    assert first_officers[0].end_time is None
    session.close()


def test_handover_changes_only_copilot(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={"captain_user_id": "", "first_officer_user_id": str(ids["copilot_2_id"])},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?success=crew_updated")

    session = SessionLocal()
    captains = _assignments_for(session, ids["active_flight_id"], "CAPTAIN")
    first_officers = _assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")
    assert len(captains) == 1
    assert captains[0].user_id == ids["pilot_1_id"]
    assert captains[0].end_time is None
    assert len(first_officers) == 2
    assert first_officers[0].end_time is not None
    assert first_officers[1].user_id == ids["copilot_2_id"]
    assert first_officers[1].end_time is None
    session.close()


def test_handover_changes_both_roles(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={
            "captain_user_id": str(ids["pilot_2_id"]),
            "first_officer_user_id": str(ids["copilot_2_id"]),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?success=crew_updated")

    session = SessionLocal()
    captains = _assignments_for(session, ids["active_flight_id"], "CAPTAIN")
    first_officers = _assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")
    assert len(captains) == 2
    assert captains[0].end_time is not None
    assert captains[1].user_id == ids["pilot_2_id"]
    assert len(first_officers) == 2
    assert first_officers[0].end_time is not None
    assert first_officers[1].user_id == ids["copilot_2_id"]
    session.close()


def test_handover_rejects_when_both_selections_empty(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={"captain_user_id": "", "first_officer_user_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew?error=missing_crew_selection"
    )

    session = SessionLocal()
    assert len(_assignments_for(session, ids["active_flight_id"], "CAPTAIN")) == 1
    assert len(_assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")) == 1
    session.close()


def test_handover_rejects_same_user_for_both_roles(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={
            "captain_user_id": str(ids["pilot_2_id"]),
            "first_officer_user_id": str(ids["pilot_2_id"]),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?error=same_personnel")

    session = SessionLocal()
    assert len(_assignments_for(session, ids["active_flight_id"], "CAPTAIN")) == 1
    assert len(_assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")) == 1
    session.close()


def test_handover_same_active_person_for_one_role_is_noop_for_that_role(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={
            "captain_user_id": str(ids["pilot_1_id"]),
            "first_officer_user_id": str(ids["copilot_2_id"]),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?success=crew_updated")

    session = SessionLocal()
    captains = _assignments_for(session, ids["active_flight_id"], "CAPTAIN")
    first_officers = _assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")
    assert len(captains) == 1
    assert captains[0].user_id == ids["pilot_1_id"]
    assert captains[0].end_time is None
    assert len(first_officers) == 2
    assert first_officers[1].user_id == ids["copilot_2_id"]
    assert first_officers[1].end_time is None
    session.close()


def test_handover_same_active_people_for_both_roles_is_full_noop(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['active_flight_id']}/crew",
        data={
            "captain_user_id": str(ids["pilot_1_id"]),
            "first_officer_user_id": str(ids["copilot_1_id"]),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['active_flight_id']}/crew?success=crew_updated")

    session = SessionLocal()
    captains = _assignments_for(session, ids["active_flight_id"], "CAPTAIN")
    first_officers = _assignments_for(session, ids["active_flight_id"], "FIRST_OFFICER")
    assert len(captains) == 1
    assert captains[0].user_id == ids["pilot_1_id"]
    assert captains[0].end_time is None
    assert len(first_officers) == 1
    assert first_officers[0].user_id == ids["copilot_1_id"]
    assert first_officers[0].end_time is None
    session.close()


def test_handover_rejects_non_active_flight(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['inactive_flight_id']}/crew",
        data={"captain_user_id": str(ids["pilot_2_id"]), "first_officer_user_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/admin-ui/flights/{ids['inactive_flight_id']}/crew?error=inactive_flight")

    session = SessionLocal()
    assert len(_assignments_for(session, ids["inactive_flight_id"], "CAPTAIN")) == 1
    assert len(_assignments_for(session, ids["inactive_flight_id"], "FIRST_OFFICER")) == 1
    session.close()


def test_handover_rejects_not_departed_flight(test_env):
    client, SessionLocal, ids = test_env
    response = client.post(
        f"/admin-ui/flights/{ids['not_departed_flight_id']}/crew",
        data={"captain_user_id": str(ids["pilot_2_id"]), "first_officer_user_id": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith(
        f"/admin-ui/flights/{ids['not_departed_flight_id']}/crew?error=inactive_flight"
    )

    session = SessionLocal()
    assert len(_assignments_for(session, ids["not_departed_flight_id"], "CAPTAIN")) == 0
    assert len(_assignments_for(session, ids["not_departed_flight_id"], "FIRST_OFFICER")) == 0
    session.close()
