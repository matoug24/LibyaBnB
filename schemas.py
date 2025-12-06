from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional
from models import BookingStatus, SiteRole, PropertyRole


class BookingCreate(BaseModel):
    property_id: int
    start_date: date
    end_date: date
    guest_name: str
    guest_phone: str


class BookingOut(BaseModel):
    id: int
    property_id: int
    start_date: date
    end_date: date
    guest_name: str
    guest_phone: str
    booking_code: str
    status: BookingStatus
    created_at: datetime

    class Config:
        from_attributes = True


class BookingUpdateStatus(BaseModel):
    status: BookingStatus = Field(..., description="pending, confirmed, cancelled, or expired")


class PropertyCreate(BaseModel):
    name: str
    short_description: Optional[str] = None

    address_line: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_exact_location: bool = True

    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    base_price_per_night: Optional[float] = None

    # NEW FIELDS
    amenities: Optional[str] = None
    capacity: Optional[int] = None
    property_type: Optional[str] = None


class PropertyOut(BaseModel):
    id: int
    name: str
    short_description: Optional[str]
    address_line: Optional[str]
    city: Optional[str]
    country: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    is_exact_location: bool
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    base_price_per_night: Optional[float]

    # NEW FIELDS
    amenities: Optional[str]
    capacity: Optional[int]
    property_type: Optional[str]

    class Config:
        from_attributes = True



class PriceRuleCreate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    weekday: Optional[int] = Field(
        None, description="0=Monday ... 6=Sunday, or null for all days in range"
    )
    price_per_night: float


class PriceRuleOut(PriceRuleCreate):
    id: int
    property_id: int

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    site_role: SiteRole


class UserOut(UserBase):
    id: int

    class Config:
        from_attributes = True


class PropertyMemberCreate(BaseModel):
    user_id: int
    role: PropertyRole
    is_supervisor: bool = False


class PropertyMemberOut(BaseModel):
    id: int
    user_id: int
    property_id: int
    role: PropertyRole
    is_supervisor: bool

    class Config:
        from_attributes = True
