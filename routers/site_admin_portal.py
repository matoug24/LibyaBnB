from __future__ import annotations

from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, Request, Form, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date
from fastapi import UploadFile, File
import os
from pathlib import Path
from deps import get_db, get_current_user_optional, require_site_admin_or_owner
from models import User, SiteRole, Property, PropertyMember, PropertyRole, PriceRule, PropertyImage
from security import verify_password, hash_password

DEFAULT_PASSWORD = "Libya123"

router = APIRouter(prefix="/site_admin", tags=["site_admin"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def entry(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if user and user.site_role in {SiteRole.site_admin, SiteRole.site_owner}:
        return RedirectResponse(url="/site_admin/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "mode": "site_admin"})


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
            {"request": request, "error": "Invalid username or password", "mode": "site_admin"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.site_role not in {SiteRole.site_admin, SiteRole.site_owner}:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "This account is not a site admin/owner.", "mode": "site_admin"},
            status_code=status.HTTP_403_FORBIDDEN,
        )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/site_admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    props = db.query(Property).order_by(Property.id.desc()).all()
    return templates.TemplateResponse("site_admin_dashboard.html", {"request": request, "user": user, "properties": props})


@router.get("/listings/new", response_class=HTMLResponse)
def new_listing_form(
    request: Request,
    user: User = Depends(require_site_admin_or_owner),
):
    return templates.TemplateResponse("site_listing_form.html", {"request": request, "user": user, "mode": "create", "property": None})


def _get_or_create_user(db: Session, username: str, make_supervisor: bool = False) -> User:
    u = db.query(User).filter(User.username == username).first()
    if u:
        if make_supervisor and not u.is_supervisor:
            u.is_supervisor = True
            db.add(u); db.commit(); db.refresh(u)
        return u
    u = User(
        username=username,
        password_hash=hash_password(DEFAULT_PASSWORD),
        site_role=SiteRole.standard,
        full_name=None,
        phone=None,
        email=None,
        whatsapp_enabled=False,
        is_supervisor=make_supervisor,
        supervisor_districts=None,
        supervisor_services=None,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _parse_usernames(raw: str) -> List[str]:
    items = [x.strip() for x in (raw or "").split(",")]
    return [x for x in items if x]


@router.post("/listings/new")
async def create_listing(
    request: Request,
    name: str = Form(...),
    short_description: str = Form(""),
    address_line: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    is_exact_location: Optional[str] = Form(None),
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    base_price_per_night: str = Form(""),
    amenities: str = Form(""),
    capacity: str = Form(""),
    property_type: str = Form(""),
    owner_username: str = Form(...),
    owner_create_if_missing: Optional[str] = Form(None),
    admin_usernames: str = Form(""),
    admins_create_if_missing: Optional[str] = Form(None),
    price_start_date: list[str] = Form([], alias="price_start_date[]"),
    price_end_date: list[str] = Form([], alias="price_end_date[]"),
    price_val: list[str] = Form([], alias="price_val[]"),
    price_weekday: list[str] = Form([], alias="price_weekday[]"),
    new_photos: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = Property(
        name=name,
        short_description=short_description or None,
        address_line=address_line or None,
        city=city or None,
        country=country or None,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
        is_exact_location=True if is_exact_location else False,
        contact_name=contact_name or None,
        contact_phone=contact_phone or None,
        contact_email=contact_email or None,
        base_price_per_night=float(base_price_per_night) if base_price_per_night else None,
        amenities=amenities or None,
        capacity=int(capacity) if capacity else None,
        property_type=property_type or None,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)

    owner = db.query(User).filter(User.username == owner_username).first()
    if not owner:
        if owner_create_if_missing:
            owner = _get_or_create_user(db, owner_username, make_supervisor=False)
        else:
            raise HTTPException(status_code=400, detail="Owner user does not exist.")
    db.add(PropertyMember(user_id=owner.id, property_id=prop.id, role=PropertyRole.owner))

    for uname in _parse_usernames(admin_usernames):
        admin = db.query(User).filter(User.username == uname).first()
        if not admin and admins_create_if_missing:
            admin = _get_or_create_user(db, uname, make_supervisor=False)
        if admin:
            db.add(PropertyMember(user_id=admin.id, property_id=prop.id, role=PropertyRole.admin))

    for i in range(len(price_start_date)):
        start = price_start_date[i]
        end = price_end_date[i]
        val = price_val[i]
        wd = price_weekday[i] if i < len(price_weekday) else ""
        if not start or not end or not val:
            continue
        weekday_val = int(wd) if (wd is not None and str(wd).strip() != "") else None
        rule = PriceRule(
            property_id=prop.id,
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            price_per_night=float(val),
            weekday=weekday_val
        )
        db.add(rule)

    if new_photos:
        from routers.admin_portal import _ensure_upload_dir
        upload_dir = _ensure_upload_dir(prop.id)
        for f in new_photos:
            if not f.filename: continue
            contents = await f.read()
            dest = upload_dir / os.path.basename(f.filename)
            with open(dest, "wb") as out:
                out.write(contents)
            rel_path = f"uploads/properties/{prop.id}/{dest.name}"
            db.add(PropertyImage(property_id=prop.id, file_path=rel_path))

    db.commit()
    return RedirectResponse(url="/site_admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/listings/{property_id}/edit", response_class=HTMLResponse)
def edit_listing_form(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")
    return templates.TemplateResponse("site_listing_form.html", {"request": request, "user": user, "mode": "edit", "property": prop})


@router.post("/listings/{property_id}/edit")
async def edit_listing_submit(
    property_id: int,
    request: Request,
    name: str = Form(...),
    short_description: str = Form(""),
    address_line: str = Form(""),
    city: str = Form(""),
    country: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    is_exact_location: Optional[str] = Form(None),
    contact_name: str = Form(""),
    contact_phone: str = Form(""),
    contact_email: str = Form(""),
    base_price_per_night: str = Form(""),
    amenities: str = Form(""),
    capacity: str = Form(""),
    property_type: str = Form(""),
    delete_photo_ids: list[int] = Form([]),
    new_photos: list[UploadFile] = File([]),
    price_start_date: list[str] = Form([], alias="price_start_date[]"),
    price_end_date: list[str] = Form([], alias="price_end_date[]"),
    price_val: list[str] = Form([], alias="price_val[]"),
    price_weekday: list[str] = Form([], alias="price_weekday[]"),
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    prop.name = name
    prop.short_description = short_description or None
    prop.address_line = address_line or None
    prop.city = city or None
    prop.country = country or None
    prop.latitude = float(latitude) if latitude else None
    prop.longitude = float(longitude) if longitude else None
    prop.is_exact_location = True if is_exact_location else False
    prop.contact_name = contact_name or None
    prop.contact_phone = contact_phone or None
    prop.contact_email = contact_email or None
    prop.base_price_per_night = float(base_price_per_night) if base_price_per_night else None
    prop.amenities = amenities or None
    prop.capacity = int(capacity) if capacity else None
    prop.property_type = property_type or None

    if delete_photo_ids:
        to_delete = db.query(PropertyImage).filter(PropertyImage.id.in_(delete_photo_ids), PropertyImage.property_id == property_id).all()
        for img in to_delete:
            file_path = Path("static") / img.file_path
            try:
                if file_path.exists(): file_path.unlink()
            except Exception: pass
            db.delete(img)

    if new_photos:
        from routers.admin_portal import _ensure_upload_dir
        upload_dir = _ensure_upload_dir(property_id)
        for f in new_photos:
            if not f.filename: continue
            contents = await f.read()
            safe_name = os.path.basename(f.filename)
            dest = upload_dir / safe_name
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                i = 1
                while (upload_dir / f"{stem}_{i}{suffix}").exists(): i += 1
                dest = upload_dir / f"{stem}_{i}{suffix}"
            with open(dest, "wb") as out:
                out.write(contents)
            rel_path = f"uploads/properties/{property_id}/{dest.name}"
            db.add(PropertyImage(property_id=property_id, file_path=rel_path))

    db.query(PriceRule).filter(PriceRule.property_id == property_id).delete()
    for i in range(len(price_start_date)):
        start = price_start_date[i]
        end = price_end_date[i]
        val = price_val[i]
        wd = price_weekday[i] if i < len(price_weekday) else ""
        if not start or not end or not val: continue
        weekday_val = int(wd) if (wd is not None and str(wd).strip() != "") else None
        db.add(PriceRule(
            property_id=property_id,
            start_date=date.fromisoformat(start),
            end_date=date.fromisoformat(end),
            price_per_night=float(val),
            weekday=weekday_val
        ))

    db.commit()
    return RedirectResponse(url="/site_admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.post("/listings/{property_id}/delete")
def delete_listing(
    property_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")
    db.delete(prop); db.commit()
    return RedirectResponse(url="/site_admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/listings/{property_id}/members", response_class=HTMLResponse)
def members_form(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    members = db.query(PropertyMember).filter(PropertyMember.property_id == property_id).all()
    u_ids = [m.user_id for m in members]
    users_by_id = {u.id: u for u in db.query(User).filter(User.id.in_(u_ids if u_ids else [0])).all()}

    owner_username = ""
    admin_usernames = []
    supervisor_usernames = []
    for m in members:
        u = users_by_id.get(m.user_id)
        if not u: continue
        if m.role == PropertyRole.owner and not m.is_supervisor:
            owner_username = u.username
        elif m.role == PropertyRole.admin and not m.is_supervisor:
            admin_usernames.append(u.username)
        elif m.is_supervisor:
            supervisor_usernames.append(u.username)

    return templates.TemplateResponse(
        "site_assign_members.html",
        {
            "request": request,
            "user": user,
            "property": prop,
            "owner_username": owner_username,
            "admin_usernames": ", ".join(sorted(set(admin_usernames))),
            "supervisor_usernames": ", ".join(sorted(set(supervisor_usernames))),
        },
    )


@router.post("/listings/{property_id}/members")
def members_submit(
    property_id: int,
    request: Request,
    owner_username: str = Form(""),
    owner_create_if_missing: Optional[str] = Form(None),
    admin_usernames: str = Form(""),
    admins_create_if_missing: Optional[str] = Form(None),
    supervisor_usernames: str = Form(""),
    supervisors_create_if_missing: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_site_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    def ensure_user(uname: str, create_flag: Optional[str], make_supervisor: bool) -> Optional[User]:
        if not uname: return None
        u = db.query(User).filter(User.username == uname).first()
        if u:
            if make_supervisor and not u.is_supervisor:
                u.is_supervisor = True
                db.add(u); db.commit()
            return u
        if create_flag:
            return _get_or_create_user(db, uname, make_supervisor=make_supervisor)
        return None

    owner_user = ensure_user(owner_username.strip(), owner_create_if_missing, False)
    admin_users = [ensure_user(u, admins_create_if_missing, False) for u in _parse_usernames(admin_usernames)]
    sup_users = [ensure_user(u, supervisors_create_if_missing, True) for u in _parse_usernames(supervisor_usernames)]

    db.query(PropertyMember).filter(PropertyMember.property_id == property_id).delete()
    if owner_user:
        db.add(PropertyMember(user_id=owner_user.id, property_id=property_id, role=PropertyRole.owner, is_supervisor=False))
    for au in filter(None, admin_users):
        db.add(PropertyMember(user_id=au.id, property_id=property_id, role=PropertyRole.admin, is_supervisor=False))
    for su in filter(None, sup_users):
        db.add(PropertyMember(user_id=su.id, property_id=property_id, role=PropertyRole.admin, is_supervisor=True))

    db.commit()
    return RedirectResponse(url=f"/site_admin/dashboard", status_code=status.HTTP_302_FOUND)