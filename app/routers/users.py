from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Review, Role, Skill, User
from app.schemas import MentorProfile, MentorSummary, UserOut, UserUpdate
from app.security import get_current_user

router = APIRouter(prefix="/users", tags=["Users & Mentors"])


def rating_subquery():
    return (
        select(
            Review.mentor_id,
            func.avg(Review.rating).label("avg_rating"),
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.mentor_id)
        .subquery()
    )


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_me(data: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.get("/mentors", response_model=list[MentorSummary])
def search_mentors(
    skill: str | None = Query(None, min_length=1, description="Part of a skill title, e.g. python"),
    category: str | None = Query(None, min_length=1),
    min_rating: float | None = Query(None, ge=1, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    ratings = rating_subquery()
    stmt = (
        select(User, ratings.c.avg_rating, ratings.c.review_count)
        .outerjoin(ratings, ratings.c.mentor_id == User.id)
        .where(User.role == Role.MENTOR, User.is_active.is_(True))
    )
    if skill or category:
        skill_filter = select(Skill.mentor_id)
        if skill:
            skill_filter = skill_filter.where(Skill.title.ilike(f"%{skill}%"))
        if category:
            skill_filter = skill_filter.where(Skill.category.ilike(category))
        stmt = stmt.where(User.id.in_(skill_filter))
    if min_rating is not None:
        stmt = stmt.where(ratings.c.avg_rating >= min_rating)

    rows = db.execute(stmt.order_by(User.id).offset(skip).limit(limit)).all()
    return [
        MentorSummary(
            id=u.id,
            name=u.name,
            bio=u.bio,
            average_rating=round(float(avg), 2) if avg is not None else None,
            review_count=count or 0,
        )
        for u, avg, count in rows
    ]


@router.get("/mentors/{mentor_id}", response_model=MentorProfile)
def get_mentor_profile(mentor_id: int, db: Session = Depends(get_db)):
    mentor = db.get(User, mentor_id)
    if mentor is None or mentor.role != Role.MENTOR:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mentor not found")
    avg, count = db.execute(
        select(func.avg(Review.rating), func.count(Review.id)).where(Review.mentor_id == mentor_id)
    ).one()
    skills = db.scalars(select(Skill).where(Skill.mentor_id == mentor_id)).all()
    return MentorProfile(
        id=mentor.id,
        name=mentor.name,
        bio=mentor.bio,
        average_rating=round(float(avg), 2) if avg is not None else None,
        review_count=count,
        skills=skills,
    )
