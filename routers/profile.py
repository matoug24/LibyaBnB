from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import get_db, get_current_user_optional, require_login
from models import User, Booking, SiteRole
from security import hash_password, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse("signup.html", {"request": request, "user": user, "is_supervisor_signup": False})


@router.post("/signup", response_class=HTMLResponse)
def signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    whatsapp_enabled: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Username already exists", "is_supervisor_signup": False},
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
        is_supervisor=False,
        supervisor_districts=None,
        supervisor_services=None,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    request.session["user_id"] = u.id
    return RedirectResponse(url="/myprofile", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse("login.html", {"request": request, "user": user, "mode": "standard"})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password", "mode": "standard"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/myprofile", status_code=status.HTTP_302_FOUND)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@router.get("/myprofile", response_class=HTMLResponse)
def myprofile(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
):
    bookings = db.query(Booking).filter(Booking.user_id == user.id).order_by(Booking.start_date.desc()).all()
    return templates.TemplateResponse("myprofile.html", {"request": request, "user": user, "bookings": bookings})


@router.post("/myprofile", response_class=HTMLResponse)
def update_profile(
    request: Request,
    full_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    whatsapp_enabled: Optional[str] = Form(None),
    is_supervisor: Optional[str] = Form(None),
    supervisor_districts: str = Form(""),
    supervisor_services: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
):
    user.full_name = full_name or None
    user.phone = phone or None
    user.email = email or None
    user.whatsapp_enabled = bool(whatsapp_enabled)

    user.is_supervisor = bool(is_supervisor)
    user.supervisor_districts = supervisor_districts.strip() or None
    user.supervisor_services = supervisor_services.strip() or None

    db.add(user)
    db.commit()
    db.refresh(user)

    bookings = db.query(Booking).filter(Booking.user_id == user.id).order_by(Booking.start_date.desc()).all()
    return templates.TemplateResponse("myprofile.html", {"request": request, "user": user, "bookings": bookings, "saved": True})
