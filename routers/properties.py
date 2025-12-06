from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Form,
    status,
    UploadFile,
    File,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import os

from deps import (
    get_db,
    require_site_admin_or_owner,
    require_property_owner,
    require_site_admin_or_owner_api,
)
from models import Property, User, PropertyMember, PropertyRole, SiteRole, PropertyImage, PriceRule
from schemas import PropertyCreate, PropertyOut
from security import get_password_hash  # NEW: for hashing owner passwords

router = APIRouter(prefix="/properties", tags=["properties"])

templates = Jinja2Templates(directory="templates")


# ---------- JSON API ----------


@router.post(
    "/",
    response_model=PropertyOut,
    dependencies=[Depends(require_site_admin_or_owner_api)],
)
def create_property_api(
    payload: PropertyCreate,
    db: Session = Depends(get_db),
):
    prop = Property(
        name=payload.name,
        short_description=payload.short_description,
        address_line=payload.address_line,
        city=payload.city,
        country=payload.country,
        latitude=payload.latitude,
        longitude=payload.longitude,
        is_exact_location=payload.is_exact_location,
        contact_name=payload.contact_name,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        base_price_per_night=payload.base_price_per_night,
        amenities=payload.amenities,
        capacity=payload.capacity,
        property_type=payload.property_type,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("/", response_model=List[PropertyOut])
def list_properties_api(db: Session = Depends(get_db)):
    return db.query(Property).all()


# ---------- HTML PAGES ----------


@router.get("/html", response_class=HTMLResponse)
def list_properties_html(request: Request, db: Session = Depends(get_db)):
    props = db.query(Property).all()
    return templates.TemplateResponse(
        "property_list.html",
        {"request": request, "properties": props},
    )


@router.get(
    "/new/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_site_admin_or_owner)],
)
def new_property_form(request: Request):
    return templates.TemplateResponse(
        "property_form.html",
        {"request": request},
    )


@router.post(
    "/new/html",
    response_class=HTMLResponse,
    dependencies=[Depends(require_site_admin_or_owner)],
)
def create_property_html(
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

    # NEW FIELDS
    amenities: str = Form(""),
    capacity: str = Form(""),
    property_type: str = Form(""),

    owner_username: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    lat = float(latitude) if latitude else None
    lon = float(longitude) if longitude else None
    base_price = float(base_price_per_night) if base_price_per_night else None
    exact = is_exact_location == "on" or is_exact_location is None

    capacity_int = int(capacity) if capacity else None

    prop = Property(
        name=name,
        short_description=short_description or None,
        address_line=address_line or None,
        city=city or None,
        country=country or None,
        latitude=lat,
        longitude=lon,
        is_exact_location=exact,
        contact_name=contact_name or None,
        contact_phone=contact_phone or None,
        contact_email=contact_email or None,
        base_price_per_night=base_price,
        amenities=amenities or None,
        capacity=capacity_int,
        property_type=property_type or None,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)

    # Optional owner assignment
    if owner_username:
        owner = db.query(User).filter(User.username == owner_username).first()
        if not owner:
            owner = User(
                username=owner_username,
                # hash the default password so login works with bcrypt
                password=get_password_hash("owner123"),
                site_role=SiteRole.standard,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)

        member = PropertyMember(
            user_id=owner.id,
            property_id=prop.id,
            role=PropertyRole.owner,
            is_supervisor=False,
        )
        db.add(member)
        db.commit()

    return RedirectResponse(url="/properties/html", status_code=status.HTTP_302_FOUND)


@router.get("/{property_id}/detail/html", response_class=HTMLResponse)
def property_detail_html(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return templates.TemplateResponse(
        "property_detail.html",
        {"request": request, "property": prop},
    )


@router.get("/{property_id}/members/html", response_class=HTMLResponse)
def list_property_members_html(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    members = (
        db.query(PropertyMember)
        .filter(PropertyMember.property_id == property_id)
        .all()
    )
    return templates.TemplateResponse(
        "property_members.html",
        {"request": request, "property": prop, "members": members, "error": None},
    )


@router.post("/{property_id}/members/html", response_class=HTMLResponse)
def add_property_member_html(
    property_id: int,
    request: Request,
    username: str = Form(...),
    role: str = Form(...),
    is_supervisor: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        members = (
            db.query(PropertyMember)
            .filter(PropertyMember.property_id == property_id)
            .all()
        )
        return templates.TemplateResponse(
            "property_members.html",
            {
                "request": request,
                "property": prop,
                "members": members,
                "error": "User not found. Ask them to sign up first.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    member = PropertyMember(
        user_id=user.id,
        property_id=property_id,
        role=PropertyRole(role),
        is_supervisor=bool(is_supervisor),
    )
    db.add(member)
    db.commit()
    return RedirectResponse(
        url=f"/properties/{property_id}/members/html",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/{property_id}/images/html", response_class=HTMLResponse)
def property_images_html(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return templates.TemplateResponse(
        "property_images.html",
        {"request": request, "property": prop},
    )


@router.post("/{property_id}/images/html", response_class=HTMLResponse)
async def upload_property_images_html(
    property_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    upload_dir = Path("static") / "uploads" / "properties" / str(property_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        contents = await file.read()
        dest = upload_dir / file.filename
        with open(dest, "wb") as f:
            f.write(contents)

        rel_path = str(Path("uploads") / "properties" / str(property_id) / file.filename)
        img = PropertyImage(property_id=property_id, file_path=rel_path)
        db.add(img)

    db.commit()
    return RedirectResponse(
        url=f"/properties/{property_id}/images/html",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/{property_id}/prices/html", response_class=HTMLResponse)
def property_prices_html(
    property_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    return templates.TemplateResponse(
        "property_prices.html",
        {"request": request, "property": prop},
    )


@router.post("/{property_id}/prices/html", response_class=HTMLResponse)
def add_price_rule_html(
    property_id: int,
    request: Request,
    name: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    weekday: str = Form(""),
    price_per_night: float = Form(...),
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    from datetime import date

    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    def parse_date(val: str):
        return date.fromisoformat(val) if val else None

    wd = int(weekday) if weekday != "" else None

    rule = PriceRule(
        property_id=property_id,
        name=name or None,
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
        weekday=wd,
        price_per_night=price_per_night,
    )
    db.add(rule)
    db.commit()

    return RedirectResponse(
        url=f"/properties/{property_id}/prices/html",
        status_code=status.HTTP_302_FOUND,
    )


# ---------- GENERIC PROPERTY FETCH (JSON) ----------
# Keep this at the BOTTOM so /html and other specific routes win first.


@router.get("/{property_id}", response_model=PropertyOut)
def get_property_api(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop
