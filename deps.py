from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from typing import Optional
from database import SessionLocal
from models import User, SiteRole, PropertyMember, PropertyRole


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------
# Session-based authentication
# ---------------------------

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # stale / invalid session → clear it
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    return db.query(User).filter(User.id == user_id).first()


def require_login(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


# ---------------------------
# Authorization helpers
# ---------------------------

def require_site_admin_or_owner(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.site_role in (SiteRole.site_admin, SiteRole.site_owner):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Site admin access required",
    )


def require_property_admin_or_owner(
    property_id: Optional[int] = None, # Change this line
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.site_role in (SiteRole.site_admin, SiteRole.site_owner):
        return current_user
    if property_id is None:
            # If no ID provided, just ensure they are logged in or 
            # use another check like require_any_admin_portal_user
            return current_user
    membership = (
        db.query(PropertyMember)
        .filter(
            PropertyMember.user_id == current_user.id,
            PropertyMember.property_id == property_id,
            PropertyMember.role.in_([PropertyRole.owner, PropertyRole.admin]),
        )
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Property admin/owner access required",
        )

    return current_user


def require_any_admin_portal_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.site_role in (SiteRole.site_admin, SiteRole.site_owner):
        return current_user

    membership = (
        db.query(PropertyMember)
        .filter(
            PropertyMember.user_id == current_user.id,
            PropertyMember.role.in_([PropertyRole.owner, PropertyRole.admin]),
        )
        .first()
    )

    if membership:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin portal access required",
    )


def property_accessible_to_admin(
    property_id: int,
    db: Session,
    current_user: User,
) -> bool:
    if current_user.site_role in (SiteRole.site_admin, SiteRole.site_owner):
        return True

    membership = (
        db.query(PropertyMember)
        .filter(
            PropertyMember.user_id == current_user.id,
            PropertyMember.property_id == property_id,
            PropertyMember.role.in_([PropertyRole.owner, PropertyRole.admin]),
        )
        .first()
    )
    return membership is not None
