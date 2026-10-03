from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import Level, Role, SessionStatus


def as_utc(value: datetime) -> datetime:
    """Treat naive datetimes as UTC so comparisons always work."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth / Users ----------

class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    role: Literal["student", "mentor"] = "student"  # admin cannot self-register
    bio: str | None = Field(default=None, max_length=500)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one digit")
        if len(v.encode()) > 72:
            raise ValueError("password is too long")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    bio: str | None = Field(default=None, max_length=500)


class UserOut(ORMModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    bio: str | None
    is_active: bool
    created_at: datetime


class MentorSummary(BaseModel):
    id: int
    name: str
    bio: str | None
    average_rating: float | None
    review_count: int


class RoleUpdate(BaseModel):
    role: Role


class StatusUpdate(BaseModel):
    is_active: bool


# ---------- Skills ----------

class SkillCreate(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=2, max_length=50)
    level: Level
    description: str | None = Field(default=None, max_length=1000)


class SkillUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=100)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    level: Level | None = None
    description: str | None = Field(default=None, max_length=1000)


class SkillOut(ORMModel):
    id: int
    mentor_id: int
    title: str
    category: str
    level: Level
    description: str | None
    created_at: datetime


class MentorProfile(MentorSummary):
    skills: list[SkillOut]


# ---------- Sessions ----------

class SessionCreate(BaseModel):
    skill_id: int = Field(gt=0)
    scheduled_at: datetime
    duration_minutes: int = Field(ge=30, le=180, description="30 to 180 minutes")
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("scheduled_at")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        v = as_utc(v)
        if v <= datetime.now(timezone.utc):
            raise ValueError("scheduled_at must be in the future")
        return v


class SessionOut(ORMModel):
    id: int
    student_id: int
    mentor_id: int
    skill_id: int
    scheduled_at: datetime
    duration_minutes: int
    status: SessionStatus
    notes: str | None
    created_at: datetime


# ---------- Reviews ----------

class ReviewCreate(BaseModel):
    session_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=500)


class ReviewOut(ORMModel):
    id: int
    session_id: int
    student_id: int
    mentor_id: int
    rating: int
    comment: str | None
    created_at: datetime
