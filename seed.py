from sqlalchemy.orm import Session
from models import User, SiteRole
from security import hash_password

DEFAULT_PASSWORD = "Libya123"

def seed(db: Session) -> None:
    u = db.query(User).filter(User.username == "siteowner").first()
    if not u:
        u = User(
            username="siteowner",
            password_hash=hash_password(DEFAULT_PASSWORD),
            site_role=SiteRole.site_owner,
            full_name="Site Owner",
            phone="",
            email="",
            whatsapp_enabled=False,
            is_supervisor=False,
            supervisor_districts=None,
            supervisor_services=None,
        )
        db.add(u)
        db.commit()
