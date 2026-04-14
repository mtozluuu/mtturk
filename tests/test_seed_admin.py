"""Tests for the startup admin seeding mechanism."""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import User


# ---------------------------------------------------------------------------
# In-memory SQLite database fixture (no Postgres required for unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session(monkeypatch):
    """Create a fresh in-memory SQLite session and patch app.seed to use it."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    session = Session()

    import app.seed as seed_module

    monkeypatch.setattr(seed_module, "SessionLocal", Session)

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_seed_admin_creates_user(monkeypatch, db_session):
    """When env vars are set and user does not exist, seed_admin creates the user."""
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Test1234!")
    monkeypatch.setenv("SEED_ADMIN_ROLE", "admin")

    from app.seed import seed_admin
    seed_admin()

    user = db_session.query(User).filter(User.username == "admin").first()
    assert user is not None
    assert user.role == "admin"
    assert user.password_hash != "Test1234!"  # must be hashed, never plain-text


def test_seed_admin_idempotent(monkeypatch, db_session):
    """Running seed_admin twice does not create a duplicate user."""
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Test1234!")
    monkeypatch.setenv("SEED_ADMIN_ROLE", "admin")

    from app.seed import seed_admin
    seed_admin()
    seed_admin()

    count = db_session.query(User).filter(User.username == "admin").count()
    assert count == 1


def test_seed_admin_no_op_without_env_vars(monkeypatch, db_session):
    """When env vars are absent, seed_admin does nothing."""
    monkeypatch.delenv("SEED_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

    from app.seed import seed_admin
    seed_admin()

    count = db_session.query(User).count()
    assert count == 0


def test_seed_admin_no_op_missing_password(monkeypatch, db_session):
    """When only SEED_ADMIN_USERNAME is set (no password), seed_admin does nothing."""
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "admin")
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)

    from app.seed import seed_admin
    seed_admin()

    count = db_session.query(User).count()
    assert count == 0


def test_seed_admin_invalid_role_defaults_to_admin(monkeypatch, db_session):
    """An invalid SEED_ADMIN_ROLE falls back to 'admin'."""
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "sysop")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Secret99!")
    monkeypatch.setenv("SEED_ADMIN_ROLE", "superuser")  # not a valid role

    from app.seed import seed_admin
    seed_admin()

    user = db_session.query(User).filter(User.username == "sysop").first()
    assert user is not None
    assert user.role == "admin"


def test_seed_admin_custom_role(monkeypatch, db_session):
    """SEED_ADMIN_ROLE is respected when it is a valid role."""
    monkeypatch.setenv("SEED_ADMIN_USERNAME", "captain")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "Fly1234!")
    monkeypatch.setenv("SEED_ADMIN_ROLE", "pilot")

    from app.seed import seed_admin
    seed_admin()

    user = db_session.query(User).filter(User.username == "captain").first()
    assert user is not None
    assert user.role == "pilot"
