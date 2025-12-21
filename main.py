# main.py
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import os

# ---- DB / models
from database import Base, engine , SessionLocal

from seed import seed



from routers import public, auth, profile, bookflow, supervisors, admin_portal, site_admin_portal


from jobs.expire_pending_bookings import start_expiry_loop


templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler:
    - starts background expiry loop on startup
    - cancels it on shutdown
    """
    task = asyncio.create_task(start_expiry_loop())
    try:
        yield
    finally:
        task.cancel()
        # Best-effort cancellation
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "CHANGE_ME_TO_A_RANDOM_SECRET"),
    same_site="lax",
    https_only=False,  # set True in production with HTTPS
)


# Static files (CSS, uploaded images, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

Base.metadata.create_all(bind=engine)

# Include routers
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(bookflow.router)
app.include_router(supervisors.router)
app.include_router(admin_portal.router)
app.include_router(site_admin_portal.router)

db = SessionLocal()
seed(db)

# Local run: python main.py
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
