"""Seed an initial admin user into the database.

Usage:
    SEED_ADMIN_USERNAME=admin SEED_ADMIN_PASSWORD=secret python scripts/seed_admin.py

Reads DATABASE_URL, SEED_ADMIN_USERNAME, SEED_ADMIN_PASSWORD and optionally
SEED_ADMIN_ROLE (default: "admin") from .env or the environment.

The script is idempotent: if a user with SEED_ADMIN_USERNAME already exists it
exits without making any changes.  The password is NEVER printed.
"""

import os
import sys

from dotenv import load_dotenv
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
    sys.exit(1)

ADMIN_USERNAME = os.environ.get("SEED_ADMIN_USERNAME", "").strip()
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    print(
        "ERROR: SEED_ADMIN_USERNAME and SEED_ADMIN_PASSWORD must both be set.",
        file=sys.stderr,
    )
    sys.exit(1)

ADMIN_ROLE = os.environ.get("SEED_ADMIN_ROLE", "admin").strip()
VALID_ROLES = {"admin", "pilot", "copilot", "technician"}
if ADMIN_ROLE not in VALID_ROLES:
    print(
        f"WARNING: SEED_ADMIN_ROLE '{ADMIN_ROLE}' is not valid. Using 'admin'.",
        file=sys.stderr,
    )
    ADMIN_ROLE = "admin"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    row = conn.execute(
        text("SELECT id FROM users WHERE username = :u"),
        {"u": ADMIN_USERNAME},
    ).fetchone()

    if row is not None:
        print(f"User '{ADMIN_USERNAME}' already exists (id={row[0]}). Nothing to do.")
        sys.exit(0)

    hashed = pwd_context.hash(ADMIN_PASSWORD)
    result = conn.execute(
        text(
            "INSERT INTO users (username, password_hash, role) "
            "VALUES (:u, :h, :r) RETURNING id"
        ),
        {"u": ADMIN_USERNAME, "h": hashed, "r": ADMIN_ROLE},
    )
    new_id = result.fetchone()[0]
    print(f"Created user '{ADMIN_USERNAME}' with role '{ADMIN_ROLE}' (id={new_id}).")
