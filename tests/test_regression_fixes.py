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
def regression_client(monkeypatch):
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
        lambda request: type("AdminUser", (), {"id": 1, "username": "admin", "role": "admin"})(),
    )

    session = TestingSessionLocal()
    now = datetime.utcnow()

    admin = User(username="admin", password_hash="x", role="admin")
    pilot = User(username="pilot_1", password_hash="x", role="pilot")
    copilot = User(username="copilot_1", password_hash="x", role="copilot")
    session.add_all([admin, pilot, copilot])
    session.flush()

    flight = Flight(
        flight_no="TK100",
        flight_date=date.today(),
        departure_airport="IST",
        arrival_airport="ESB",
        sched_dep=now - timedelta(hours=1),
        sched_arr=now + timedelta(hours=1),
        actual_dep=now - timedelta(hours=1),
        actual_arr=None,
    )
    session.add(flight)
    session.flush()

    session.add_all(
        [
            CrewAssignment(
                flight_id=flight.id,
                user_id=pilot.id,
                seat="CAPTAIN",
                start_time=now - timedelta(hours=1),
            ),
            CrewAssignment(
                flight_id=flight.id,
                user_id=copilot.id,
                seat="FIRST_OFFICER",
                start_time=now - timedelta(hours=1),
            ),
        ]
    )
    session.commit()
    session.close()

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    Base.metadata.drop_all(bind=engine)


def test_reports_and_crew_reports_render_with_i18n_context(regression_client):
    reports_response = regression_client.get("/reports-ui")
    assert reports_response.status_code == 200
    assert "Raporlar" in reports_response.text

    crew_reports_response = regression_client.get("/reports-ui/crew")
    assert crew_reports_response.status_code == 200
    assert "Ekip Raporları" in crew_reports_response.text


def test_change_password_page_uses_shared_layout_and_keeps_themed_background(regression_client):
    response = regression_client.get("/change-password")
    assert response.status_code == 200
    assert "Şifre Değiştir" in response.text
    assert '<header class="topbar">' in response.text
    assert 'url("/static/images/wolf.png")' in response.text
