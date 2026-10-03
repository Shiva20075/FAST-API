from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Role, User
from app.routers import admin, auth, reviews, sessions, skills, users
from app.security import hash_password


def create_default_admin():
    """Admins cannot self-register, so one admin is created from .env on startup."""
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == settings.admin_email)):
            db.add(User(
                name="Admin",
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                role=Role.ADMIN,
            ))
            db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    create_default_admin()
    yield


app = FastAPI(
    title="SkillSwap API",
    description="Student skill sharing platform: skill profiles, mentor search, session booking and reviews.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Safety net for duplicate records that slip past the explicit checks."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": "Duplicate or conflicting record"})


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(reviews.router)
app.include_router(admin.router)


@app.get("/", tags=["Health"])
def health():
    return {"status": "ok", "docs": "/docs"}
