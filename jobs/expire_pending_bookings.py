import asyncio
from datetime import datetime, timedelta, timezone
from database import SessionLocal
from models import Booking, BookingStatus

CHECK_INTERVAL = 600  # 10 minutes

async def start_expiry_loop():
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        expire_old_bookings()

def expire_old_bookings():
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        bookings = (
            db.query(Booking)
            .filter(
                Booking.status == BookingStatus.pending,
                Booking.created_at < cutoff
            )
            .all()
        )
        for b in bookings:
            b.status = BookingStatus.expired
        db.commit()
    finally:
        db.close()
