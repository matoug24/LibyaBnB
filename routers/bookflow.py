from __future__ import annotations

import secrets
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import get_db, get_current_user_optional, require_login
from models import Property, Booking, BookingStatus, User

# IMPORTANT:
# - No router prefix so we can support BOTH:
#   - /book/* booking flow routes
#   - /my-booking lookup at root
router = APIRouter(tags=["booking"])
templates = Jinja2Templates(directory="templates")


def _overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start < b_end and b_start < a_end


def _generate_code() -> str:
    # Short, URL-friendly, low collision probability for small scale.
    return secrets.token_hex(4).upper()


def _create_booking(
    db: Session,
    property_id: int,
    start: date,
    end: date,
    guest_name: str,
    guest_phone: str,
    guest_email: str,
    user_id: Optional[int],
) -> Booking:
    # conflict check
    existing = (
        db.query(Booking)
        .filter(
            Booking.property_id == property_id,
            Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
        )
        .all()
    )
    for b in existing:
        if _overlaps(start, end, b.start_date, b.end_date):
            raise HTTPException(status_code=409, detail="Selected dates are not available")

    # generate unique code (safe even if you also generate in model; this wins)
    for _ in range(20):
        code = _generate_code()
        if not db.query(Booking).filter(Booking.booking_code == code).first():
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate booking code")

    booking = Booking(
        property_id=property_id,
        user_id=user_id,
        start_date=start,
        end_date=end,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        booking_code=code,
        status=BookingStatus.pending,
        created_at=datetime.now(timezone.utc),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


# ------------------------------------------------------------
# My Booking (public lookup): GET/POST /my-booking
# Requires exact phone + booking_code per your spec.
# ------------------------------------------------------------
@router.get("/my-booking", response_class=HTMLResponse)
def my_booking_form(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
):
    return templates.TemplateResponse(
        "my_booking_lookup.html",
        {"request": request, "user": user, "error": None},
    )


@router.post("/my-booking", response_class=HTMLResponse)
def my_booking_lookup(
    request: Request,
    booking_code: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    booking_code = booking_code.strip()
    phone = phone.strip()

    b = (
        db.query(Booking)
        .filter(
            Booking.booking_code == booking_code,
            Booking.guest_phone == phone,
        )
        .first()
    )
    if not b:
        return templates.TemplateResponse(
            "my_booking_lookup.html",
            {
                "request": request,
                "user": user,
                "error": "Booking not found. Please verify the booking code and phone number.",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return RedirectResponse(url=f"/book/success/{b.booking_code}", status_code=status.HTTP_302_FOUND)


# ------------------------------------------------------------
# Booking flow: /book/*
# ------------------------------------------------------------
@router.get("/book/start", response_class=HTMLResponse)
def start_page(
    request: Request,
    property_id: int,
    start: str,
    end: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    return templates.TemplateResponse(
        "booking_start.html",
        {"request": request, "listing_id": property_id, "start": start, "end": end, "user": user},
    )


@router.get("/book/guest", response_class=HTMLResponse)
def guest_details_form(
    request: Request,
    listing_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    prop = db.query(Property).filter(Property.id == listing_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    return templates.TemplateResponse(
        "booking_guest_details.html",
        {
            "request": request,
            "property": prop,
            "listing_id": listing_id,
            "start": start,
            "end": end,
            "user": user,
        },
    )


@router.post("/book/guest", response_class=HTMLResponse)
def guest_details_submit(
    request: Request,
    listing_id: int = Form(...),
    start: str = Form(...),
    end: str = Form(...),
    guest_name: str = Form(...),
    guest_phone: str = Form(...),
    guest_email: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates")
    if e <= s:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    b = _create_booking(
        db=db,
        property_id=listing_id,
        start=s,
        end=e,
        guest_name=guest_name.strip(),
        guest_phone=guest_phone.strip(),
        guest_email=guest_email.strip(),
        user_id=None,
    )
    return RedirectResponse(url=f"/book/success/{b.booking_code}", status_code=status.HTTP_302_FOUND)


@router.get("/book/confirm")
def confirm_logged_in(
    request: Request,
    property_id: int,
    start: str,
    end: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_login),
):
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dates")
    if e <= s:
        raise HTTPException(status_code=400, detail="End date must be after start date")

    # Snapshot user info; dates already chosen on listing page.
    b = _create_booking(
        db=db,
        property_id=property_id,
        start=s,
        end=e,
        guest_name=(user.full_name or user.username),
        guest_phone=(user.phone or ""),
        guest_email=(user.email or ""),
        user_id=user.id,
    )
    return RedirectResponse(url=f"/book/success/{b.booking_code}", status_code=status.HTTP_302_FOUND)


@router.get("/book/success/{booking_code}", response_class=HTMLResponse)
def booking_success(
    booking_code: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    b = db.query(Booking).filter(Booking.booking_code == booking_code).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")

    prop = db.query(Property).filter(Property.id == b.property_id).first()
    return templates.TemplateResponse(
        "booking_success.html",
        {"request": request, "booking": b, "property": prop, "user": user},
    )

# test/routers/bookflow.py

@router.post("/my-booking/cancel", response_class=HTMLResponse)
def cancel_booking(
    request: Request,
    booking_code: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    booking_code = booking_code.strip()
    phone = phone.strip()

    # Find the booking that matches both code and phone
    b = db.query(Booking).filter(
        Booking.booking_code == booking_code,
        Booking.guest_phone == phone
    ).first()

    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Only allow cancellation if it's currently pending or confirmed
    if b.status in [BookingStatus.pending, BookingStatus.confirmed]:
        b.status = BookingStatus.cancelled
        db.add(b)
        db.commit()
        db.refresh(b)

    # Redirect back to the success page which shows the updated status
    return RedirectResponse(
        url=f"/book/success/{b.booking_code}", 
        status_code=status.HTTP_302_FOUND
    )