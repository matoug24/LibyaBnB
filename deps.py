# deps.py
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from database import SessionLocal
from models import User, SiteRole, PropertyMember, PropertyRole


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


# ---- Site-level permissions ----

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


# ---- Per-property permissions ----

def get_property_member(
    property_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PropertyMember:
    member = (
        db.query(PropertyMember)
        .filter(
            PropertyMember.user_id == user.id,
            PropertyMember.property_id == property_id,
        )
        .first()
    )
    if not member and user.site_role not in {SiteRole.site_owner, SiteRole.site_admin}:
        # site owner/admin can see all properties even without explicit membership
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this property.",
        )
    return member


def require_property_owner(
    member: PropertyMember = Depends(get_property_member),
) -> PropertyMember:
    if member and member.role != PropertyRole.owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner-level access required for this property.",
        )
    return member


def require_property_admin_or_owner(
    member: PropertyMember = Depends(get_property_member),
) -> PropertyMember:
    if member and member.role not in {PropertyRole.owner, PropertyRole.admin}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner access required for this property.",
        )
    return member
