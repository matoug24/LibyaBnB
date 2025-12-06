from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Boolean,
    UniqueConstraint,
    Float,
)
from sqlalchemy.orm import relationship

from database import Base
import enum


class SiteRole(str, enum.Enum):
    standard = "standard"
    site_owner = "site_owner"
    site_admin = "site_admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    password = Column(String(128), nullable=False)
    site_role = Column(Enum(SiteRole), nullable=False, default=SiteRole.standard)

    property_memberships = relationship("PropertyMember", back_populates="user")
    bookings = relationship("Booking", back_populates="user")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False)
    short_description = Column(String(255), nullable=True)

    address_line = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_exact_location = Column(Boolean, default=True, nullable=False)

    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)

    base_price_per_night = Column(Float, nullable=True)

    # NEW FIELDS
    amenities = Column(String(255), nullable=True)      # e.g. "WiFi, Parking, Pool"
    capacity = Column(Integer, nullable=True)           # number of guests
    property_type = Column(String(50), nullable=True)   # e.g. "Apartment", "Villa"

    bookings = relationship("Booking", back_populates="property")
    members = relationship("PropertyMember", back_populates="property")
    images = relationship("PropertyImage", back_populates="property")
    price_rules = relationship("PriceRule", back_populates="property")


class PropertyRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"


class PropertyMember(Base):
    __tablename__ = "property_members"
    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_user_property"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    role = Column(Enum(PropertyRole), nullable=False)
    is_supervisor = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="property_memberships")
    property = relationship("Property", back_populates="members")


class PropertyImage(Base):
    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    file_path = Column(String(255), nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)

    property = relationship("Property", back_populates="images")


class PriceRule(Base):
    __tablename__ = "price_rules"

    id = Column(Integer, primary_key=True, index=True)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)

    name = Column(String(100), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    weekday = Column(Integer, nullable=True)  # 0=Mon .. 6=Sun

    price_per_night = Column(Float, nullable=False)

    property = relationship("Property", back_populates="price_rules")


class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    expired = "expired"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    guest_name = Column(String(100), nullable=False)
    guest_phone = Column(String(50), nullable=False)

    booking_code = Column(String(20), unique=True, index=True, nullable=False)
    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.pending)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    property = relationship("Property", back_populates="bookings")
    user = relationship("User", back_populates="bookings")
