from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

import uvicorn

from security import get_password_hash
from database import Base, engine, SessionLocal
from models import User, SiteRole
from routers import bookings, properties, auth

Base.metadata.create_all(bind=engine)


def seed_users():
    db = SessionLocal()
    try:
        owner = db.query(User).filter(User.username == "site_owner").first()
        if not owner:
            db.add(
                User(
                    username="site_owner",
                    password=get_password_hash("owner123"),
                    site_role=SiteRole.site_owner,
                )
            )

        admin = db.query(User).filter(User.username == "site_admin").first()
        if not admin:
            db.add(
                User(
                    username="site_admin",
                    password=get_password_hash("admin123"),
                    site_role=SiteRole.site_admin,
                )
            )
        db.commit()
    finally:
        db.close()



seed_users()

app = FastAPI(title="LibyaBnB Booking System (FastAPI)")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.include_router(properties.router)
app.include_router(bookings.router)
app.include_router(auth.router)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
