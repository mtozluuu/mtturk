from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_role
from app.models import User

router = APIRouter(prefix="/admin", tags=["admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = {"admin", "pilot", "copilot", "technician"}


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )
    user = User(
        username=body.username,
        password_hash=pwd_context.hash(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.get("/users")
def list_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    query = db.query(User)
    if role is not None:
        query = query.filter(User.role == role)
    users = query.all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]
