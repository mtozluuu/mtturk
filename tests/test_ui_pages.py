"""Tests for the HTML UI pages (/, /login, /flights-ui)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_index_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flight Management" in response.text


def test_index_links_present(client):
    response = client.get("/")
    assert response.status_code == 200
    for href in ["/docs", "/redoc", "/login", "/flights-ui"]:
        assert href in response.text, f"Expected link to {href} on index page"


def test_login_returns_html(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<form" in response.text


def test_login_page_has_fields(client):
    response = client.get("/login")
    assert "username" in response.text
    assert "password" in response.text


def test_flights_ui_returns_html(client):
    response = client.get("/flights-ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Flights" in response.text


def test_flights_ui_unauthenticated_shows_placeholder(client):
    """Unauthenticated visit should show a helpful message, not an error."""
    response = client.get("/flights-ui")
    assert response.status_code == 200
    # Should show a message guiding the user to log in
    assert "Log in" in response.text or "login" in response.text.lower()


def test_health_still_returns_json(client):
    """Existing /health JSON endpoint must remain unaffected."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_css_served(client):
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
