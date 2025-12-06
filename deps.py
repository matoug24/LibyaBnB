from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User, SiteRole, PropertyMember, PropertyRole

from fastapi.security import OAuth2PasswordBearer
from typing import Optional

from security import decode_access_token


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    username = request.cookies.get("session_username")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
        )
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Please log in again.",
        )
    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
):
    username = request.cookies.get("session_username")
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()


def require_site_owner(user: User = Depends(get_current_user)) -> User:
    if user.site_role != SiteRole.site_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires site owner role.",
        )
    return user


def require_site_admin_or_owner(user: User = Depends(get_current_user)) -> User:
    if user.site_role not in {SiteRole.site_owner, SiteRole.site_admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires site admin or site owner role.",
        )
    return user


def get_property_member(
    property_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PropertyMember | None:
    member = (
        db.query(PropertyMember)
        .filter(
            PropertyMember.user_id == user.id,
            PropertyMember.property_id == property_id,
        )
        .first()
    )
    if not member and user.site_role not in {SiteRole.site_owner, SiteRole.site_admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this property.",
        )
    return member


def require_property_owner(
    member: PropertyMember | None = Depends(get_property_member),
) -> PropertyMember | None:
    if member and member.role != PropertyRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner-level access required for this property.",
        )
    return member


def require_property_admin_or_owner(
    member: PropertyMember | None = Depends(get_property_member),
) -> PropertyMember | None:
    if member and member.role not in {PropertyRole.owner, PropertyRole.admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner access required for this property.",
        )
    return member

def get_current_user_jwt(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    For API endpoints using Authorization: Bearer <token>.
    """
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    username: str = payload["sub"]
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_current_user_jwt_optional(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Optional JWT user for API endpoints where guest is allowed.
    If no token is provided, returns None.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None
    username: str = payload["sub"]
    return db.query(User).filter(User.username == username).first()


def require_site_admin_or_owner_api(
    user: User = Depends(get_current_user_jwt),
) -> User:
    """
    API-only variant of site admin/owner check (uses JWT).
    """
    if user.site_role not in {SiteRole.site_owner, SiteRole.site_admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires site admin or site owner role.",
        )
    return user
