# models.py
from __future__ import annotations

import enum
import secrets
import string
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import relationship

from database import Base


# -----------------------------
# Enums
# -----------------------------
class SiteRole(str, enum.Enum):
    standard = "standard"
    site_admin = "site_admin"
    site_owner = "site_owner"


class PropertyRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"


class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"


# -----------------------------
# Models
# -----------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String(50), unique=True, index=True, nullable=False)

    # Store only a hash (bcrypt via passlib)
    password_hash = Column(String(255), nullable=False)

    # Profile
    full_name = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)  # exact match per your spec
    email = Column(String(255), nullable=True)
    whatsapp_enabled = Column(Boolean, nullable=False, default=False, server_default="0")

    # Supervisor profile
    is_supervisor = Column(Boolean, nullable=False, default=False, server_default="0")
    supervisor_districts = Column(Text, nullable=True)  # comma-separated
    supervisor_services = Column(Text, nullable=True)   # comma-separated

    # Site-level role
    site_role = Column(Enum(SiteRole), nullable=False, default=SiteRole.standard)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    property_memberships = relationship("PropertyMember", back_populates="user", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="user")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True)

    name = Column(String(200), nullable=False, index=True)

    short_description = Column(Text, nullable=True)

    address_line = Column(String(255), nullable=True)
    city = Column(String(120), nullable=True)
    district = Column(String(120), nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_exact_location = Column(Boolean, nullable=False, default=False, server_default="0")

    contact_name = Column(String(120), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(255), nullable=True)

    # New Fields
    social_link = Column(String(500), nullable=True)
    highlights = Column(Text, nullable=True)
    cancellation_policy = Column(Text, nullable=True)
    property_rules = Column(Text, nullable=True) # Stored as newline or comma separated

    # Airbnb-like listing fields
    amenities = Column(Text, nullable=True)   # comma-separated
    capacity = Column(Integer, nullable=True)
    property_type = Column(String(80), nullable=True)

    base_price_per_night = Column(Float, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    members = relationship("PropertyMember", back_populates="property", cascade="all, delete-orphan")
    images = relationship("PropertyImage", back_populates="property", cascade="all, delete-orphan")
    price_rules = relationship("PriceRule", back_populates="property", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="property", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="property", cascade="all, delete-orphan") #


class PropertyMember(Base):
    __tablename__ = "property_members"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)

    # owner/admin access
    role = Column(Enum(PropertyRole), nullable=False, default=PropertyRole.admin)

    # supervisor affiliation flag (your option A)
    is_supervisor = Column(Boolean, nullable=False, default=False, server_default="0")

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="property_memberships")
    property = relationship("Property", back_populates="members")

    __table_args__ = (
        UniqueConstraint("user_id", "property_id", name="uq_property_member_user_property"),
    )


class PropertyImage(Base):
    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)

    # path relative to /static, e.g. "uploads/properties/12/a.jpg"
    file_path = Column(String(500), nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="images")


class PriceRule(Base):
    """
    Dynamic pricing rule.
    - If start/end are set, applies in that date window
    - If weekday is set (0=Mon ... 6=Sun), applies on that weekday
    - If both are set, it applies when both conditions match
    """
    __tablename__ = "price_rules"

    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(200), nullable=True)

    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    weekday = Column(Integer, nullable=True)  # 0=Mon ... 6=Sun

    price_per_night = Column(Float, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    property = relationship("Property", back_populates="price_rules")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)

    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True)

    # nullable: guest booking has no account
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)

    # Snapshot guest fields (used for lookup by phone + booking_code)
    guest_name = Column(String(120), nullable=True)
    guest_phone = Column(String(50), nullable=True, index=True)   # exact match per your spec
    guest_email = Column(String(255), nullable=True)

    # Long-term fix: always non-null, unique
    booking_code = Column(String(20), nullable=False, unique=True, index=True)

    status = Column(Enum(BookingStatus), nullable=False, default=BookingStatus.pending)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    property = relationship("Property", back_populates="bookings")
    user = relationship("User", back_populates="bookings")

    __table_args__ = (
        # Helpful for preventing exact duplicates; optional, but usually desirable
        Index("ix_booking_property_dates", "property_id", "start_date", "end_date"),
    )


# ---------------------------------------------------------
# Long-term booking_code generation (works for all inserts)
# ---------------------------------------------------------
def _random_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@event.listens_for(Booking, "before_insert")
def booking_before_insert(mapper, connection, target: Booking):
    """
    Ensure booking_code is ALWAYS set and unique for any insert path:
    - seed scripts
    - API routes
    - HTML routes
    - admin tooling

    Uses the same DB connection for collision checks.
    """
    if getattr(target, "booking_code", None):
        return

    # Very low collision probability; still, enforce uniqueness.
    for _ in range(30):
        code = _random_code(8)
        exists = connection.execute(
            Booking.__table__.select()
            .with_only_columns(Booking.__table__.c.id)
            .where(Booking.__table__.c.booking_code == code)
            .limit(1)
        ).first()

        if not exists:
            target.booking_code = code
            return

    raise ValueError("Failed to generate unique booking_code after multiple attempts")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Integer, nullable=False) # e.g., 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    property = relationship("Property", back_populates="reviews")
    user = relationship("User")