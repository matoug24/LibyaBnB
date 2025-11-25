# routers/properties.py
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
from typing import List, Optional

from deps import (
    get_db,
    require_site_admin_or_owner,
    get_current_user,
    require_property_owner,
)
from models import Property, User, PropertyMember, PropertyRole, SiteRole
from schemas import PropertyCreate, PropertyOut, PropertyMemberCreate, PropertyMemberOut

router = APIRouter(prefix="/properties", tags=["properties"])

templates = Jinja2Templates(directory="templates")


# ---------- JSON API ----------

@router.post("/", response_model=PropertyOut, dependencies=[Depends(require_site_admin_or_owner)])
def create_property_api(
    payload: PropertyCreate,
    db: Session = Depends(get_db),
):
    prop = Property(name=payload.name, description=payload.description)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


@router.get("/", response_model=List[PropertyOut])
def list_properties_api(db: Session = Depends(get_db)):
    return db.query(Property).all()


@router.get("/{property_id}", response_model=PropertyOut)
def get_property_api(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


# ---------- HTML: list + create property ----------

@router.get("/html", response_class=HTMLResponse)
def list_properties_html(request: Request, db: Session = Depends(get_db)):
    props = db.query(Property).all()
    return templates.TemplateResponse(
        "property_list.html",
        {"request": request, "properties": props},
    )


@router.get("/new/html", response_class=HTMLResponse, dependencies=[Depends(require_site_admin_or_owner)])
def new_property_form(request: Request):
    return templates.TemplateResponse(
        "property_form.html",
        {"request": request},
    )


@router.post("/new/html", response_class=HTMLResponse, dependencies=[Depends(require_site_admin_or_owner)])
def create_property_html(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    owner_username: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    # Create property
    prop = Property(name=name, description=description or None)
    db.add(prop)
    db.commit()
    db.refresh(prop)

    # Optionally assign an owner by username if provided
    if owner_username:
        owner = db.query(User).filter(User.username == owner_username).first()
        if not owner:
            # create a new owner user with default password (to be changed later)
            owner = User(
                username=owner_username,
                password="owner123",  # TODO: change password later
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


# ---------- HTML: manage property members (owner/admin vs supervisor) ----------

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
        {
            "request": request,
            "property": prop,
            "members": members,
        },
    )


@router.post("/{property_id}/members/html", response_class=HTMLResponse)
def add_property_member_html(
    property_id: int,
    request: Request,
    username: str = Form(...),
    role: str = Form(...),  # "owner" or "admin"
    is_supervisor: bool = Form(False),
    db: Session = Depends(get_db),
    _owner=Depends(require_property_owner),
):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        return templates.TemplateResponse(
            "property_members.html",
            {
                "request": request,
                "property": prop,
                "members": prop.members,
                "error": "User not found. Ask them to sign up first.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    member = PropertyMember(
        user_id=user.id,
        property_id=property_id,
        role=PropertyRole(role),
        is_supervisor=is_supervisor,
    )
    db.add(member)
    db.commit()
    return RedirectResponse(
        url=f"/properties/{property_id}/members/html",
        status_code=status.HTTP_302_FOUND,
    )
