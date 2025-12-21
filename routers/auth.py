from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from models import User, SiteRole
from security import (
    get_password_hash,
    verify_password,
    create_access_token,
)

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

    hashed_password = get_password_hash(password)

    user = User(
        username=username,
        email=email or None,
        password=hashed_password,
        site_role=SiteRole.standard,
    )
    db.add(user)
    db.commit()
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)


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
    if not user or not verify_password(password, user.password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    # Set session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=user.username,
        httponly=True,
    )

    # Decide where to send them AFTER cookie is set.
    # (We can't easily branch after returning, so we use query params or JS redirect if needed,
    # but a simpler approach: redirect to a small router that figures it out.)
    # We'll instead redirect to /auth/post-login which then routes correctly:
    response = RedirectResponse(url="/auth/post-login", status_code=status.HTTP_302_FOUND)
    response.set_cookie(SESSION_COOKIE_NAME, user.username, httponly=True)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# --- JWT-based login for API clients (Postman / SPA frontends etc.) ---

@router.get("/post-login")
def post_login_redirect(
    current_user: User = Depends(get_current_user),
):
    # Standard user → account page
    if current_user.site_role == SiteRole.standard:
        return RedirectResponse(url="/account", status_code=status.HTTP_302_FOUND)

    # Site owner / site admin → site admin dashboard
    if current_user.site_role in {SiteRole.site_owner, SiteRole.site_admin}:
        return RedirectResponse(url="/site-admin", status_code=status.HTTP_302_FOUND)

    # Fallback (shouldn't really happen)
    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)



@router.post("/token")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Standard OAuth2 password flow endpoint.

    Request:
      POST /auth/token
      Content-Type: application/x-www-form-urlencoded
      body: username=...&password=...

    Response:
      { "access_token": "...", "token_type": "bearer" }
    """
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token({"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
