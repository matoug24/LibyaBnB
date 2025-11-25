# routers/auth.py
from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import SessionLocal
from deps import get_db, get_current_user
from models import User, SiteRole

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory="templates")
SESSION_COOKIE_NAME = "session_username"


@router.get("/signup", response_class=HTMLResponse)
def signup_form(request: Request):
    return templates.TemplateResponse(
        "signup.html",
        {"request": request, "error": None},
    )


@router.post("/signup", response_class=HTMLResponse)
def signup(
    request: Request,
    username: str = Form(...),
    email: str = Form(""),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Username already taken."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    user = User(
        username=username,
        email=email or None,
        password=password,
        site_role=SiteRole.standard,
    )
    db.add(user)
    db.commit()
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or user.password != password:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=user.username,
        httponly=True,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
