from fastapi import HTTPException, Request, status

from app.models import User


def get_current_user(request: Request) -> User:
    """Return the User object stored in the session, or raise 401."""
    user = request.state.user if hasattr(request.state, "user") else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_role(*roles: str):
    """Factory that returns a dependency checking the user has one of the given roles."""

    def _check(request: Request) -> User:
        user = get_current_user(request)
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _check
