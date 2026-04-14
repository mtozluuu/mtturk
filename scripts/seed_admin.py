"""Seed an initial admin user into the database.

Usage:
    python scripts/seed_admin.py

Reads DATABASE_URL from .env or environment variables.
Prints the generated numeric user id on success.
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "admin123")

engine = create_engine(DATABASE_URL)

with engine.begin() as conn:
    hashed = pwd_context.hash(ADMIN_PASSWORD)
    result = conn.execute(
        text(
            "INSERT INTO users (password_hash, role) "
            "VALUES (:h, 'admin') RETURNING id"
        ),
        {"h": hashed},
    )
    new_id = result.fetchone()[0]
    print(f"Created admin user with id={new_id}. Use this id to log in.")
