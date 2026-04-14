"""Startup admin seeding.

If SEED_ADMIN_USERNAME and SEED_ADMIN_PASSWORD are set in the environment, this
module creates the admin user on application startup (if they do not already
exist).  It is intentionally a no-op when those variables are absent so that
production deployments are safe by default.
"""

import logging
import os

from passlib.context import CryptContext

from app.database import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = {"admin", "pilot", "copilot", "technician"}


def seed_admin() -> None:
    """Create the seed admin user if env vars are set and the user does not exist."""
    username = os.environ.get("SEED_ADMIN_USERNAME", "").strip()
    password = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()

    if not username or not password:
        # Safe-by-default: do nothing unless both vars are explicitly set.
        return

    role = os.environ.get("SEED_ADMIN_ROLE", "admin").strip()
    if role not in VALID_ROLES:
        logger.warning(
            "SEED_ADMIN_ROLE '%s' is not a valid role %s – defaulting to 'admin'.",
            role,
            sorted(VALID_ROLES),
        )
        role = "admin"

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing is not None:
            logger.info("Seed: user '%s' already exists (id=%d) – skipping.", username, existing.id)
            return

        user = User(
            username=username,
            password_hash=_pwd_context.hash(password),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(
            "Seed: created user '%s' with role '%s' (id=%d).",
            username,
            role,
            user.id,
        )
    finally:
        db.close()
