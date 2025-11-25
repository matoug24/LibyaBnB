# models.py
from datetime import datetime
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
)
from sqlalchemy.orm import relationship

from database import Base
import enum


# -------- Site-level roles (who is this user on the whole site?) --------

class SiteRole(str, enum.Enum):
    standard = "standard"      # normal registered user
    site_owner = "site_owner"  # full site-wide control
    site_admin = "site_admin"  # almost full site-wide control


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    password = Column(String(128), nullable=False)  # plain for now (demo)
    site_role = Column(Enum(SiteRole), nullable=False, default=SiteRole.standard)

    property_memberships = relationship("PropertyMember", back_populates="user")
    bookings = relationship("Booking", back_populates="user")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)

    bookings = relationship("Booking", back_populates="property")
    members = relationship("PropertyMember", back_populates="property")


# -------- Per-property roles (what can this user do on THIS property?) --------

class PropertyRole(str, enum.Enum):
    owner = "owner"  # property owner-level
    admin = "admin"  # property admin-level


class PropertyMember(Base):
    """
    User assigned to a property with a role.
    is_supervisor=True means the user is acting as supervisor on behalf of the owner.
    """
    __tablename__ = "property_members"
    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_user_property"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    role = Column(Enum(PropertyRole), nullable=False)
    is_supervisor = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="property_memberships")
    property = relationship("Property", back_populates="members")


# -------- Bookings --------

class BookingStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    expired = "expired"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for guest

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
