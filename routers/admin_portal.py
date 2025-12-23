from __future__ import annotations

from typing import Optional, Dict, List
from datetime import date
from pathlib import Path
import os

from fastapi import APIRouter, Depends, Request, Form, status, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import (
    get_db,
    get_current_user_optional,
    require_property_admin_or_owner,
    property_accessible_to_admin,
    require_any_admin_portal_user
)
from models import User, Property, PropertyMember, PropertyRole, Booking, BookingStatus, SiteRole, PropertyImage, PriceRule
from security import verify_password

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")


@router.get("", response_class=HTMLResponse)
def entry(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
):
    if user:
        return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "mode": "admin"})


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
            {"request": request, "error": "Invalid username or password", "mode": "admin"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if user.site_role not in {SiteRole.site_admin, SiteRole.site_owner}:
        m = db.query(PropertyMember).filter(
            PropertyMember.user_id == user.id,
            PropertyMember.role.in_([PropertyRole.owner, PropertyRole.admin]),
            PropertyMember.is_supervisor == False
        ).first()
        if not m:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "This account is not a listing admin/owner.", "mode": "admin"},
                status_code=status.HTTP_403_FORBIDDEN,
            )

    request.session["user_id"] = user.id
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_any_admin_portal_user),
):
    properties: List[Property] = []
    role_by_property: Dict[int, str] = {}

    if user.site_role in {SiteRole.site_admin, SiteRole.site_owner}:
        properties = db.query(Property).order_by(Property.id.desc()).all()
        for p in properties: role_by_property[p.id] = "site"
        property_ids = [p.id for p in properties]
    else:
        memberships = db.query(PropertyMember).filter(
            PropertyMember.user_id == user.id,
            PropertyMember.role.in_([PropertyRole.owner, PropertyRole.admin]),
            PropertyMember.is_supervisor == False
        ).all()
        property_ids = [m.property_id for m in memberships]
        if property_ids:
            properties = db.query(Property).filter(Property.id.in_(property_ids)).order_by(Property.id.desc()).all()
        for m in memberships: role_by_property[m.property_id] = m.role.value

    pending = []
    confirmed = []
    if property_ids:
        pending = db.query(Booking).filter(Booking.property_id.in_(property_ids), Booking.status == BookingStatus.pending).order_by(Booking.created_at.asc()).all()
        confirmed = db.query(Booking).filter(Booking.property_id.in_(property_ids), Booking.status == BookingStatus.confirmed).order_by(Booking.start_date.desc()).all()

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {"request": request, "user": user, "properties": properties, "role_by_property": role_by_property, "pending": pending, "confirmed": confirmed}
    )


@router.post("/bookings/{booking_id}/approve")
def approve(booking_id: int, db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b or not property_accessible_to_admin(b.property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    b.status = BookingStatus.confirmed
    db.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.post("/bookings/{booking_id}/deny")
def deny(booking_id: int, db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    b = db.query(Booking).filter(Booking.id == booking_id).first()
    if not b or not property_accessible_to_admin(b.property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    b.status = BookingStatus.denied
    db.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/listings/{property_id}/edit", response_class=HTMLResponse)
def edit_listing_form(property_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop or not property_accessible_to_admin(property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    return templates.TemplateResponse("site_listing_form.html", {"request": request, "user": user, "mode": "edit_admin", "property": prop})


@router.post("/listings/{property_id}/edit")
async def edit_listing_submit(
    property_id: int,
    request: Request,
    name: str = Form(...),
    property_type: str = Form(...),
    short_description: str = Form(""),
    highlights: str = Form(""),
    city: str = Form(""),
    district: str = Form(""),
    address_line: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    is_exact_location: Optional[str] = Form(None),
    base_price_per_night: str = Form(""),
    social_link: str = Form(""),
    cancellation_policy: str = Form(""),
    property_rules: str = Form(""),
    amenities_check: list[str] = Form([], alias="amenities_check[]"),
    amenities_extra: str = Form(""),
    capacity: str = Form(""),
    delete_photo_ids: list[int] = Form([]),
    new_photos: list[UploadFile] = File([]),
    price_start_date: list[str] = Form([], alias="price_start_date[]"),
    price_end_date: list[str] = Form([], alias="price_end_date[]"),
    price_val: list[str] = Form([], alias="price_val[]"),
    price_weekday: list[str] = Form([], alias="price_weekday[]"),
    db: Session = Depends(get_db),
    user: User = Depends(require_property_admin_or_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop or not property_accessible_to_admin(property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Basic Info
    prop.name = name
    prop.property_type = property_type
    prop.short_description = short_description or None
    prop.highlights = highlights or None
    prop.city = city or None
    prop.district = district or None
    prop.address_line = address_line or None
    prop.latitude = float(latitude) if latitude else None
    prop.longitude = float(longitude) if longitude else None
    prop.is_exact_location = True if is_exact_location else False
    prop.base_price_per_night = float(base_price_per_night) if base_price_per_night else None
    prop.capacity = int(capacity) if capacity else None
    
    # New Policy & Social fields
    prop.social_link = social_link or None
    prop.cancellation_policy = cancellation_policy or None
    prop.property_rules = property_rules or None

    # Process Amenities: Checkboxes + Extra Text
    final_amenities = [a for a in amenities_check if a.strip()]
    if amenities_extra:
        extra_list = [a.strip() for a in amenities_extra.split(",") if a.strip()]
        final_amenities.extend(extra_list)
    prop.amenities = ",".join(final_amenities) if final_amenities else None

    # Handle Photo Deletion
    if delete_photo_ids:
        to_delete = db.query(PropertyImage).filter(PropertyImage.id.in_(delete_photo_ids), PropertyImage.property_id == property_id).all()
        for img in to_delete:
            p = Path("static") / img.file_path
            try:
                if p.exists(): p.unlink()
            except Exception: pass
            db.delete(img)

    # Handle New Photo Uploads
    if new_photos:
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

    # Update Pricing Rules
    db.query(PriceRule).filter(PriceRule.property_id == property_id).delete()
    for i in range(len(price_start_date)):
        start, end, val = price_start_date[i], price_end_date[i], price_val[i]
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
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


def _ensure_upload_dir(property_id: int) -> Path:
    d = Path("static") / "uploads" / "properties" / str(property_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/listings/{property_id}/photos", response_class=HTMLResponse)
def listing_photos_page(property_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop or not property_accessible_to_admin(property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    images = db.query(PropertyImage).filter(PropertyImage.property_id == property_id).order_by(PropertyImage.id.asc()).all()
    return templates.TemplateResponse("admin_listing_photos.html", {"request": request, "user": user, "property": prop, "images": images})


@router.post("/listings/{property_id}/photos")
async def upload_listing_photos(property_id: int, request: Request, files: list[UploadFile] = File(...), db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    if not property_accessible_to_admin(property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    upload_dir = _ensure_upload_dir(property_id)
    for f in files:
        if not f.filename: continue
        contents = await f.read()
        dest = upload_dir / os.path.basename(f.filename)
        with open(dest, "wb") as out: out.write(contents)
        db.add(PropertyImage(property_id=property_id, file_path=f"uploads/properties/{property_id}/{dest.name}"))
    db.commit()
    return RedirectResponse(url=f"/admin/listings/{property_id}/photos", status_code=status.HTTP_302_FOUND)


@router.post("/listings/{property_id}/photos/{photo_id}/delete")
def delete_listing_photo(property_id: int, photo_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_property_admin_or_owner)):
    if not property_accessible_to_admin(property_id, db, user):
        raise HTTPException(status_code=403, detail="Not allowed")
    img = db.query(PropertyImage).filter(PropertyImage.id == photo_id, PropertyImage.property_id == property_id).first()
    if img:
        file_path = Path("static") / img.file_path
        try:
            if file_path.exists(): file_path.unlink()
        except Exception: pass
        db.delete(img); db.commit()
    return RedirectResponse(url=f"/admin/listings/{property_id}/photos", status_code=status.HTTP_302_FOUND)