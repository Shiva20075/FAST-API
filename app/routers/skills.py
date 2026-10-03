from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Level, MentoringSession, Role, SessionStatus, Skill, User
from app.schemas import SkillCreate, SkillOut, SkillUpdate
from app.security import require_roles

router = APIRouter(prefix="/skills", tags=["Skills"])


def get_skill_or_404(skill_id: int, db: Session) -> Skill:
    skill = db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    return skill


def check_owner(skill: Skill, user: User):
    if user.role != Role.ADMIN and skill.mentor_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only modify your own skills")


def check_duplicate_title(db: Session, mentor_id: int, title: str, exclude_id: int | None = None):
    stmt = select(Skill).where(Skill.mentor_id == mentor_id, Skill.title.ilike(title))
    if exclude_id:
        stmt = stmt.where(Skill.id != exclude_id)
    if db.scalar(stmt):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a skill with this title")


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(
    data: SkillCreate,
    user: User = Depends(require_roles(Role.MENTOR)),
    db: Session = Depends(get_db),
):
    check_duplicate_title(db, user.id, data.title)
    skill = Skill(mentor_id=user.id, **data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.get("", response_model=list[SkillOut])
def search_skills(
    q: str | None = Query(None, min_length=1, description="Search in title and description"),
    category: str | None = Query(None, min_length=1),
    level: Level | None = None,
    mentor_id: int | None = Query(None, gt=0),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Skill).join(Skill.mentor).where(User.is_active.is_(True))
    if q:
        stmt = stmt.where(or_(Skill.title.ilike(f"%{q}%"), Skill.description.ilike(f"%{q}%")))
    if category:
        stmt = stmt.where(Skill.category.ilike(category))
    if level:
        stmt = stmt.where(Skill.level == level)
    if mentor_id:
        stmt = stmt.where(Skill.mentor_id == mentor_id)
    return db.scalars(stmt.order_by(Skill.id).offset(skip).limit(limit)).all()


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(skill_id: int, db: Session = Depends(get_db)):
    return get_skill_or_404(skill_id, db)


@router.put("/{skill_id}", response_model=SkillOut)
def update_skill(
    skill_id: int,
    data: SkillUpdate,
    user: User = Depends(require_roles(Role.MENTOR, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    skill = get_skill_or_404(skill_id, db)
    check_owner(skill, user)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("title"):
        check_duplicate_title(db, skill.mentor_id, changes["title"], exclude_id=skill.id)
    for field, value in changes.items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    user: User = Depends(require_roles(Role.MENTOR, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    skill = get_skill_or_404(skill_id, db)
    check_owner(skill, user)
    # Business rule: cannot delete a skill that still has upcoming booked sessions
    upcoming = db.scalar(
        select(MentoringSession).where(
            MentoringSession.skill_id == skill.id,
            MentoringSession.status == SessionStatus.BOOKED,
            MentoringSession.scheduled_at > datetime.now(timezone.utc),
        )
    )
    if upcoming:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cancel upcoming sessions for this skill first")
    db.delete(skill)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
