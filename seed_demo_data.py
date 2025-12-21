"""
seed_demo_data.py

One-time seeding script to create demo data:
- Users (site owner/admin, owners, listing admins, supervisors, standard users)
- ~15 Properties/Listings
- PropertyMember relationships (owner/admin + supervisor affiliations)
- Optional demo bookings (pending + confirmed)

Usage:
  (myenv) alembic upgrade head
  (myenv) python seed_demo_data.py

Optional:
  (myenv) python seed_demo_data.py --reset
  (myenv) python seed_demo_data.py --with-bookings
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from database import SessionLocal

# Models (based on your project)
from models import (
    User,
    SiteRole,
    Property,
    PropertyMember,
    PropertyRole,
    Booking,
    BookingStatus,
    PriceRule,
)

# Security helpers (support both naming styles)
from security import verify_password
try:
    from security import get_password_hash as _hash
except ImportError:
    from security import hash_password as _hash


DEFAULT_PASSWORD = "Libya123"
SEED_TAG = "DEMO"  # used in usernames and listing names to avoid duplicates


def get_or_create_user(
    db: Session,
    username: str,
    *,
    full_name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    whatsapp_enabled: bool = False,
    is_supervisor: bool = False,
    supervisor_districts: str | None = None,
    supervisor_services: str | None = None,
    site_role: SiteRole = SiteRole.standard,
    password: str = DEFAULT_PASSWORD,
) -> User:
    u = db.query(User).filter(User.username == username).first()
    if u:
        # Light “ensure fields exist”
        changed = False
        for k, v in {
            "full_name": full_name,
            "phone": phone,
            "email": email,
            "whatsapp_enabled": whatsapp_enabled,
            "is_supervisor": is_supervisor,
            "supervisor_districts": supervisor_districts,
            "supervisor_services": supervisor_services,
            "site_role": site_role,
        }.items():
            if v is not None and getattr(u, k, None) != v:
                setattr(u, k, v)
                changed = True
        if changed:
            db.add(u)
            db.commit()
            db.refresh(u)
        return u

    u = User(
        username=username,
        full_name=full_name,
        phone=phone,
        email=email,
        whatsapp_enabled=whatsapp_enabled,
        is_supervisor=is_supervisor,
        supervisor_districts=supervisor_districts,
        supervisor_services=supervisor_services,
        site_role=site_role,
        password_hash=_hash(password),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def get_or_create_property(
    db: Session,
    name: str,
    *,
    city: str | None = None,
    country: str | None = "Libya",
    address_line: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    is_exact_location: bool = False,
    short_description: str | None = None,
    amenities: str | None = None,
    capacity: int | None = None,
    property_type: str | None = None,
    base_price_per_night: float | None = None,
) -> Property:
    p = db.query(Property).filter(Property.name == name).first()
    if p:
        return p

    p = Property(
        name=name,
        city=city,
        country=country,
        address_line=address_line,
        latitude=latitude,
        longitude=longitude,
        is_exact_location=is_exact_location,
        short_description=short_description,
        amenities=amenities,
        capacity=capacity,
        property_type=property_type,
        base_price_per_night=base_price_per_night,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def ensure_membership(
    db: Session,
    user_id: int,
    property_id: int,
    role: PropertyRole | None = None,
    *,
    is_supervisor: bool = False,
):
    q = db.query(PropertyMember).filter(
        PropertyMember.user_id == user_id,
        PropertyMember.property_id == property_id,
    )
    m = q.first()
    if m:
        changed = False
        if role is not None and m.role != role:
            m.role = role
            changed = True
        if hasattr(m, "is_supervisor") and m.is_supervisor != is_supervisor:
            m.is_supervisor = is_supervisor
            changed = True
        if changed:
            db.add(m)
            db.commit()
        return

    m = PropertyMember(
        user_id=user_id,
        property_id=property_id,
        role=role if role is not None else PropertyRole.admin,
        is_supervisor=is_supervisor,
    )
    db.add(m)
    db.commit()


def ensure_price_rules(db: Session, property_id: int, base: float):
    # Keep it simple: weekend premium rule + seasonal rule
    existing = db.query(PriceRule).filter(PriceRule.property_id == property_id).first()
    if existing:
        return

    # Weekend premium (Fri=4, Sat=5 in many systems; your model uses weekday int)
    weekend = PriceRule(
        property_id=property_id,
        name="Weekend premium",
        weekday=5,  # Saturday
        price_per_night=base * 1.25,
    )
    summer = PriceRule(
        property_id=property_id,
        name="Summer season",
        start_date=date(date.today().year, 6, 1),
        end_date=date(date.today().year, 8, 31),
        price_per_night=base * 1.15,
    )

    db.add(weekend)
    db.add(summer)
    db.commit()


def ensure_demo_bookings(
    db: Session,
    property_id: int,
    *,
    user: User | None,
    guest_name: str,
    guest_phone: str,
    guest_email: str,
    status: BookingStatus,
    start: date,
    end: date,
):
    # Don’t duplicate: same property + same dates + same phone
    existing = (
        db.query(Booking)
        .filter(
            Booking.property_id == property_id,
            Booking.start_date == start,
            Booking.end_date == end,
            Booking.guest_phone == guest_phone,
        )
        .first()
    )
    if existing:
        return

    b = Booking(
        property_id=property_id,
        user_id=user.id if user else None,
        start_date=start,
        end_date=end,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        status=status,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db.add(b)
    db.commit()


def reset_database(db: Session):
    # Order matters due to FK constraints
    for model in (Booking, PriceRule, PropertyMember, Property, User):
        db.query(model).delete()
        db.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Wipe existing data and reseed")
    parser.add_argument("--with-bookings", action="store_true", help="Create sample bookings")
    args = parser.parse_args()

    random.seed(42)

    db = SessionLocal()
    try:
        if args.reset:
            print("[SEED] Resetting database...")
            reset_database(db)

        print("[SEED] Creating users...")

        # Site super users
        site_owner = get_or_create_user(
            db,
            f"{SEED_TAG.lower()}_siteowner",
            full_name="Demo Site Owner",
            phone="+218900000001",
            email="siteowner@example.com",
            site_role=SiteRole.site_owner,
            password=DEFAULT_PASSWORD,
        )
        site_admin = get_or_create_user(
            db,
            f"{SEED_TAG.lower()}_siteadmin",
            full_name="Demo Site Admin",
            phone="+218900000002",
            email="siteadmin@example.com",
            site_role=SiteRole.site_admin,
            password=DEFAULT_PASSWORD,
        )

        # Owners / listing admins (shared across listings)
        owners = []
        for i in range(1, 5):
            owners.append(
                get_or_create_user(
                    db,
                    f"{SEED_TAG.lower()}_owner{i}",
                    full_name=f"Demo Owner {i}",
                    phone=f"+21891000000{i}",
                    email=f"owner{i}@example.com",
                    site_role=SiteRole.standard,
                    password=DEFAULT_PASSWORD,
                )
            )

        listing_admins = []
        for i in range(1, 5):
            listing_admins.append(
                get_or_create_user(
                    db,
                    f"{SEED_TAG.lower()}_ladmin{i}",
                    full_name=f"Demo Listing Admin {i}",
                    phone=f"+21892000000{i}",
                    email=f"ladmin{i}@example.com",
                    site_role=SiteRole.standard,
                    password=DEFAULT_PASSWORD,
                )
            )

        # Supervisors
        supervisors = []
        districts = ["Tripoli", "Benghazi", "Misrata", "Zawiya", "Sabha"]
        services = ["Check-in", "Cleaning", "Maintenance", "Guest Support", "Key Delivery"]

        for i in range(1, 6):
            supervisors.append(
                get_or_create_user(
                    db,
                    f"{SEED_TAG.lower()}_super{i}",
                    full_name=f"Demo Supervisor {i}",
                    phone=f"+21893000000{i}",
                    email=f"super{i}@example.com",
                    whatsapp_enabled=True,
                    is_supervisor=True,
                    supervisor_districts=", ".join(random.sample(districts, k=2)),
                    supervisor_services=", ".join(random.sample(services, k=3)),
                    site_role=SiteRole.standard,
                    password=DEFAULT_PASSWORD,
                )
            )

        # Standard users
        standard_users = []
        for i in range(1, 8):
            standard_users.append(
                get_or_create_user(
                    db,
                    f"{SEED_TAG.lower()}_user{i}",
                    full_name=f"Demo User {i}",
                    phone=f"+21894000000{i}",
                    email=f"user{i}@example.com",
                    whatsapp_enabled=bool(i % 2),
                    site_role=SiteRole.standard,
                    password=DEFAULT_PASSWORD,
                )
            )

        print("[SEED] Creating ~15 listings...")

        cities = ["Tripoli", "Benghazi", "Misrata", "Zliten", "Zawiya"]
        types = ["Apartment", "Villa", "Studio", "House", "Guesthouse"]
        amen_pool = ["WiFi", "AC", "Kitchen", "Parking", "Washer", "TV", "Balcony", "Hot Water"]

        properties: list[Property] = []
        for n in range(1, 16):
            city = random.choice(cities)
            ptype = random.choice(types)
            cap = random.choice([2, 3, 4, 5, 6, 8])
            base = float(random.choice([120, 150, 180, 220, 260, 300]))

            p = get_or_create_property(
                db,
                name=f"{SEED_TAG} Listing {n} - {city}",
                city=city,
                address_line=f"Block {random.randint(1, 50)}, {city}",
                latitude=32.8 + random.random(),
                longitude=13.1 + random.random(),
                is_exact_location=bool(n % 3 == 0),
                short_description=f"Comfortable {ptype} in {city} (demo data).",
                amenities=", ".join(random.sample(amen_pool, k=5)),
                capacity=cap,
                property_type=ptype,
                base_price_per_night=base,
            )
            properties.append(p)
            ensure_price_rules(db, p.id, base)

        print("[SEED] Assigning owners/admins/supervisors to listings...")

        # Ownership/admin patterns:
        # - some listings share the same owner
        # - some listings share the same admin
        # - some listings have only owner + one admin
        for idx, p in enumerate(properties):
            owner = owners[idx % len(owners)]
            admin = listing_admins[(idx + 1) % len(listing_admins)]
            ensure_membership(db, owner.id, p.id, PropertyRole.owner, is_supervisor=False)
            ensure_membership(db, admin.id, p.id, PropertyRole.admin, is_supervisor=False)

            # Attach a supervisor to some listings
            if idx % 2 == 0:
                sup = supervisors[idx % len(supervisors)]
                # supervisor membership: role can remain admin or a separate enum; we keep role=admin but is_supervisor=True
                ensure_membership(db, sup.id, p.id, PropertyRole.admin, is_supervisor=True)

        if args.with_bookings:
            print("[SEED] Creating sample bookings (pending + confirmed)...")
            today = date.today()

            # Create a few bookings per some properties
            for i, p in enumerate(properties[:8]):
                # confirmed booking (standard user)
                user = standard_users[i % len(standard_users)]
                start = today + timedelta(days=3 + i * 3)
                end = start + timedelta(days=2)
                ensure_demo_bookings(
                    db,
                    p.id,
                    user=user,
                    guest_name=user.full_name or user.username,
                    guest_phone=user.phone or f"+21895000000{i}",
                    guest_email=user.email or f"u{i}@example.com",
                    status=BookingStatus.confirmed,
                    start=start,
                    end=end,
                )

                # pending booking (guest)
                start2 = today + timedelta(days=1 + i * 2)
                end2 = start2 + timedelta(days=2)
                ensure_demo_bookings(
                    db,
                    p.id,
                    user=None,
                    guest_name=f"Guest {i+1}",
                    guest_phone=f"+21896000000{i+1}",
                    guest_email=f"guest{i+1}@example.com",
                    status=BookingStatus.pending,
                    start=start2,
                    end=end2,
                )

        print("\n[SEED] Done.")
        print("Demo accounts (password is Libya123):")
        print(f"  site owner:   {site_owner.username}")
        print(f"  site admin:   {site_admin.username}")
        print("  owners:       " + ", ".join(u.username for u in owners))
        print("  listing admins: " + ", ".join(u.username for u in listing_admins))
        print("  supervisors:  " + ", ".join(u.username for u in supervisors))
        print("  standard users: " + ", ".join(u.username for u in standard_users))

    finally:
        db.close()


if __name__ == "__main__":
    main()
