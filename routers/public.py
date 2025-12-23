from __future__ import annotations

from datetime import date, datetime, timedelta
import os
from typing import Optional, Dict, Any, List, Tuple

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from deps import get_db, get_current_user_optional
from models import Property, Booking, BookingStatus, PropertyImage, User, PriceRule

router = APIRouter(tags=["public"])
templates = Jinja2Templates(directory="templates")


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _iter_month_days(year: int, month: int) -> List[List[Optional[date]]]:
    """Return weeks matrix; each week is list of 7 dates (or None). Monday-first."""
    import calendar as _cal
    cal = _cal.Calendar(firstweekday=_cal.MONDAY)
    weeks: List[List[Optional[date]]] = []
    week: List[Optional[date]] = []
    for d in cal.itermonthdates(year, month):
        if d.month != month:
            week.append(None)
        else:
            week.append(d)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        while len(week) < 7:
            week.append(None)
        weeks.append(week)
    return weeks


def _date_status_map(bookings: List[Booking]) -> Dict[str, str]:
    """
    Map YYYY-MM-DD -> 'booked' | 'pending'
    Confirmed beats pending.
    """
    out: Dict[str, str] = {}
    for b in bookings:
        if b.status not in (BookingStatus.pending, BookingStatus.confirmed):
            continue
        cur = b.start_date
        # end_date is checkout; mark nights up to end_date-1
        while cur < b.end_date:
            k = cur.isoformat()
            if b.status == BookingStatus.confirmed:
                out[k] = "booked"
            else:
                out.setdefault(k, "pending")
            cur = cur.fromordinal(cur.toordinal() + 1)
    return out


def _approx_coords(property_id: int, lat: float, lon: float) -> tuple[float, float]:
    """
    Deterministic 'random' offset to protect exact location.
    ~500m-ish radius (varies). Uses property_id salt so it is stable per listing.
    """
    import hashlib, math
    h = hashlib.sha256(f"libyabnb:{property_id}".encode("utf-8")).digest()
    # angle 0..2pi
    angle = int.from_bytes(h[:2], "big") / 65535 * (2 * math.pi)
    # radius 200..800 meters
    radius_m = 200 + (int.from_bytes(h[2:4], "big") / 65535) * 600

    # meters -> degrees
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * math.cos(math.radians(lat)) + 1e-9)

    return (lat + dlat * math.cos(angle), lon + dlon * math.sin(angle))


@router.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    props = db.query(Property).order_by(Property.id.desc()).all()
    # Basic cover image mapping
    cover_map: Dict[int, str] = {}
    imgs = db.query(PropertyImage).all()
    for img in imgs:
        cover_map.setdefault(img.property_id, img.file_path)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "user": user, "properties": props, "cover_map": cover_map},
    )


@router.get("/listings/{property_id}", response_class=HTMLResponse)
def listing_detail(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Listing not found")

    # 1. Fetch 9 months of availability for client-side browsing
    start_window = date.today().replace(day=1)
    end_window = start_window + timedelta(days=270) # ~9 months
    
    bookings = db.query(Booking).filter(
        Booking.property_id == property_id,
        Booking.status.in_([BookingStatus.pending, BookingStatus.confirmed]),
        Booking.end_date >= start_window,
        Booking.start_date <= end_window
    ).all()
    
    full_status_map = _date_status_map(bookings)

    # 2. Fetch and serialize pricing rules
    price_rules_raw = db.query(PriceRule).filter(PriceRule.property_id == property_id).all()
    price_rules_json = [
        {
            "start_date": r.start_date.isoformat() if r.start_date else None,
            "end_date": r.end_date.isoformat() if r.end_date else None,
            "price_per_night": r.price_per_night,
            "weekday": r.weekday
        } for r in price_rules_raw
    ]

    images = db.query(PropertyImage).filter(PropertyImage.property_id == property_id).order_by(PropertyImage.id.asc()).all()
    
    map_lat, map_lon = prop.latitude, prop.longitude
    map_is_exact = bool(prop.is_exact_location)
    if map_lat is not None and map_lon is not None and not map_is_exact:
        map_lat, map_lon = _approx_coords(prop.id, float(map_lat), float(map_lon))

    return templates.TemplateResponse(
        "listing_detail.html",
        {
            "request": request,
            "user": user,
            "property": prop,
            "images": images,
            "status_map": full_status_map,
            "price_rules": price_rules_json,
            "map_lat": map_lat,
            "map_lon": map_lon,
            "map_is_exact": map_is_exact,
            "google_maps_key": os.getenv("GOOGLE_MAPS_EMBED_KEY", ""),
        },
    )