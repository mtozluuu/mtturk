import os
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Flight, User
from app.routers import auth, admin, flights, reports
from app.seed import seed_admin

load_dotenv()

SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", "")
if not SESSION_SECRET_KEY:
    warnings.warn(
        "SESSION_SECRET_KEY is not set. Using an insecure default. "
        "Set SESSION_SECRET_KEY in your environment before deploying.",
        stacklevel=1,
    )
    SESSION_SECRET_KEY = "insecure-dev-key-do-not-use-in-production"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_admin()
    yield


app = FastAPI(title="Flight Management API", version="1.0.0", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")

templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY)


@app.middleware("http")
async def attach_user_to_request(request: Request, call_next):
    """Load the authenticated user from the session and attach to request.state."""
    
    session = request.scope.get("session")
    user_id = session.get("user_id") if session else None
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


@app.get("/", include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/flights-ui", include_in_schema=False)
def flights_ui(request: Request):
    """HTML page for browsing flights. Renders server-side with data when user is authenticated."""
    flight_list = []
    user = getattr(request.state, "user", None)
    if user is not None:
        _db = SessionLocal()
        try:
            flight_list = _db.query(Flight).order_by(Flight.sched_dep).all()
        finally:
            _db.close()
    return templates.TemplateResponse(request, "flights.html", {"flights": flight_list})


@app.get("/health")
def health():
    return {"status": "ok"}
