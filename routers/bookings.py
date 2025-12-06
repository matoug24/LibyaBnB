from datetime import datetime, timedelta, date
import random
import string
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Form,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import (
    get_db,
    get_current_user_optional,
    get_current_user,
    get_current_user_jwt_optional,
)
from models import Booking, BookingStatus, Property, User, SiteRole, PropertyRole
from schemas import BookingCreate, BookingOut

router = APIRouter(prefix="/bookings", tags=["bookings"])

templates = Jinja2Templates(directory="templates")


def generate_booking_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def expire_old_pending_bookings(db: Session):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    outdated = (
        db.query(Booking)
        .filter(
            Booking.status == BookingStatus.pending,
            Booking.created_at < cutoff,
        )
        .all()
    )
    changed = False
    for b in outdated:
        b.status = BookingStatus.expired
        b.updated_at = datetime.utcnow()
        changed = True
    if changed:
        db.commit()


@router.get("/calendar/{property_id}", response_class=HTMLResponse)
def view_calendar(
    property_id: int, request: Request, db: Session = Depends(get_db)
):
    expire_old_pending_bookings(db)
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    bookings = (
        db.query(Booking)
        .filter(Booking.property_id == property_id)
        .order_by(Booking.start_date)
        .all()
    )
    return templates.TemplateResponse(
        "calendar.html",
        {"request": request, "property": prop, "bookings": bookings},
    )


@router.get("/new/{property_id}", response_class=HTMLResponse)
def new_booking_form(
    property_id: int, request: Request, db: Session = Depends(get_db)
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    return templates.TemplateResponse(
        "booking_form.html",
        {"request": request, "property": prop},
    )


@router.post("/html", response_class=HTMLResponse)
def create_booking_html(
    request: Request,
    property_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    guest_name: str = Form(...),
    guest_phone: str = Form(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    expire_old_pending_bookings(db)

    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except ValueError:
        return templates.TemplateResponse(
            "booking_success.html",
            {"request": request, "error": "Invalid date format.", "booking": None},
        )

    if ed < sd:
        return templates.TemplateResponse(
            "booking_success.html",
            {"request": request, "error": "End date must be after start date.", "booking": None},
        )

    overlap = (
        db.query(Booking)
        .filter(
            Booking.property_id == property_id,
            Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            Booking.start_date <= ed,
            Booking.end_date >= sd,
        )
        .first()
    )
    if overlap:
        return templates.TemplateResponse(
            "booking_success.html",
            {
                "request": request,
                "error": "Dates not available (already pending or confirmed).",
                "booking": None,
            },
        )

    code = generate_booking_code()
    booking = Booking(
        property_id=property_id,
        user_id=current_user.id if current_user else None,
        start_date=sd,
        end_date=ed,
        guest_name=guest_name,
        guest_phone=guest_phone,
        booking_code=code,
        status=BookingStatus.pending,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return templates.TemplateResponse(
        "booking_success.html",
        {"request": request, "error": None, "booking": booking, "property": prop},
    )


@router.get("/lookup/html", response_class=HTMLResponse)
def lookup_booking_form(request: Request):
    return templates.TemplateResponse(
        "booking_lookup.html",
        {"request": request, "error": None, "booking": None},
    )


@router.post("/lookup/html", response_class=HTMLResponse)
def lookup_booking_html(
    request: Request,
    booking_code: str = Form(...),
    db: Session = Depends(get_db),
):
    expire_old_pending_bookings(db)
    booking = (
        db.query(Booking)
        .filter(Booking.booking_code == booking_code.strip())
        .first()
    )
    if not booking:
        return templates.TemplateResponse(
            "booking_lookup.html",
            {
                "request": request,
                "error": "Booking not found. Please check your code.",
                "booking": None,
            },
        )
    return templates.TemplateResponse(
        "booking_detail.html",
        {"request": request, "booking": booking},
    )


@router.get("/admin/list", response_class=HTMLResponse)
def admin_list_bookings(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    expire_old_pending_bookings(db)

    if not current_user:
        raise HTTPException(status_code=401, detail="Login required")

    if current_user.site_role in {SiteRole.site_owner, SiteRole.site_admin}:
        bookings = db.query(Booking).order_by(Booking.created_at.desc()).all()
    else:
        property_ids = [m.property_id for m in current_user.property_memberships]
        bookings = (
            db.query(Booking)
            .filter(Booking.property_id.in_(property_ids))
            .order_by(Booking.created_at.desc())
            .all()
        )

    return templates.TemplateResponse(
        "admin_bookings.html",
        {"request": request, "bookings": bookings},
    )


@router.get("/{booking_id}/confirm/html")
def confirm_booking_html(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    expire_old_pending_bookings(db)
    if not current_user:
        raise HTTPException(status_code=401, detail="Login required")

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    allowed = False
    if current_user.site_role in {SiteRole.site_owner, SiteRole.site_admin}:
        allowed = True
    else:
        for m in current_user.property_memberships:
            if m.property_id == booking.property_id and m.role in {PropertyRole.owner, PropertyRole.admin}:
                allowed = True
                break

    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed to confirm this booking.")

    if booking.status == BookingStatus.expired:
        raise HTTPException(
            status_code=400,
            detail="Cannot confirm an expired booking.",
        )

    booking.status = BookingStatus.confirmed
    booking.updated_at = datetime.utcnow()
    db.commit()

    return RedirectResponse(url="/bookings/admin/list", status_code=status.HTTP_302_FOUND)


@router.get("/my/html", response_class=HTMLResponse)
def my_bookings_html(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expire_old_pending_bookings(db)
    bookings = (
        db.query(Booking)
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "my_bookings.html",
        {"request": request, "bookings": bookings},
    )


@router.post("/", response_model=BookingOut)
def create_booking_api(
    payload: BookingCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_jwt_optional),
):
    expire_old_pending_bookings(db)

    prop = db.query(Property).filter(Property.id == payload.property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    overlap = (
        db.query(Booking)
        .filter(
            Booking.property_id == payload.property_id,
            Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
            Booking.start_date <= payload.end_date,
            Booking.end_date >= payload.start_date,
        )
        .first()
    )
    if overlap:
        raise HTTPException(
            status_code=400,
            detail="Dates not available (already pending or confirmed).",
        )

    code = generate_booking_code()
    booking = Booking(
        property_id=payload.property_id,
        user_id=current_user.id if current_user else None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        guest_name=payload.guest_name,
        guest_phone=payload.guest_phone,
        booking_code=code,
        status=BookingStatus.pending,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking
