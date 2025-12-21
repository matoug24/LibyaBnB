from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import get_db, get_current_user_optional
from models import User, Property, PropertyMember, SiteRole
from security import hash_password

router = APIRouter(prefix="/supervisors", tags=["supervisors"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def list_supervisors(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    supervisors = (
        db.query(User)
        .filter(User.is_supervisor == True)
        .order_by(User.full_name.asc().nulls_last(), User.username.asc())
        .all()
    )
    return templates.TemplateResponse("supervisors.html", {"request": request, "supervisors": supervisors, "user": user})


@router.get("/signup", response_class=HTMLResponse)
def supervisor_signup_form(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse("signup.html", {"request": request, "user": user, "is_supervisor_signup": True})


@router.post("/signup", response_class=HTMLResponse)
def supervisor_signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    whatsapp_enabled: Optional[str] = Form(None),
    supervisor_districts: str = Form(""),
    supervisor_services: str = Form(""),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Username already exists", "is_supervisor_signup": True},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    u = User(
        username=username,
        password_hash=hash_password(password),
        site_role=SiteRole.standard,
        full_name=full_name or None,
        phone=phone or None,
        email=email or None,
        whatsapp_enabled=bool(whatsapp_enabled),
        is_supervisor=True,
        supervisor_districts=supervisor_districts.strip() or None,
        supervisor_services=supervisor_services.strip() or None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    request.session["user_id"] = u.id
    return RedirectResponse(url="/myprofile", status_code=status.HTTP_302_FOUND)


@router.get("/{user_id}", response_class=HTMLResponse)
def supervisor_profile(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    sup = db.query(User).filter(User.id == user_id, User.is_supervisor == True).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supervisor not found")
    return templates.TemplateResponse("supervisor_profile.html", {"request": request, "supervisor": sup, "user": user})


@router.get("/{user_id}/agentlistings", response_class=HTMLResponse)
def agent_listings(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    sup = db.query(User).filter(User.id == user_id, User.is_supervisor == True).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    memberships = db.query(PropertyMember).filter(PropertyMember.user_id == user_id, PropertyMember.is_supervisor == True).all()
    prop_ids = [m.property_id for m in memberships]
    props = []
    if prop_ids:
        props = db.query(Property).filter(Property.id.in_(prop_ids)).order_by(Property.id.desc()).all()

    return templates.TemplateResponse("agent_listings.html", {"request": request, "supervisor": sup, "properties": props, "user": user})
