import os
import warnings

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import User
from app.routers import auth, admin, flights, reports

load_dotenv()

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
if not SESSION_SECRET_KEY:
    warnings.warn(
        "SESSION_SECRET_KEY is not set. Using an insecure default. "
        "Set SESSION_SECRET_KEY in your environment before deploying.",
        stacklevel=1,
    )
    SESSION_SECRET_KEY = "insecure-dev-key-do-not-use-in-production"

app = FastAPI(title="Flight Management API", version="1.0.0")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)


@app.middleware("http")
async def attach_user_to_request(request: Request, call_next):
    """Load the authenticated user from the session and attach to request.state."""
    user_id = request.session.get("user_id")
    if user_id is not None:
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            request.state.user = user
        finally:
            db.close()
    else:
        request.state.user = None
    return await call_next(request)


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(flights.router)
app.include_router(reports.router)


@app.get("/health")
def health():
    return {"status": "ok"}
