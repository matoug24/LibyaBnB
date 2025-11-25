# schemas.py
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
    description: Optional[str] = None


class PropertyOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

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
