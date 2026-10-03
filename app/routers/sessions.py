from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MentoringSession, Role, SessionStatus, Skill, User
from app.schemas import SessionCreate, SessionOut, as_utc
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/sessions", tags=["Mentoring Sessions"])


def get_session_for_user(session_id: int, user: User, db: Session) -> MentoringSession:
    """Return the session if it exists (404) and the user takes part in it or is admin (403)."""
    session = db.get(MentoringSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if user.role != Role.ADMIN and user.id not in (session.student_id, session.mentor_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This is not your session")
    return session


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def book_session(
    data: SessionCreate,
    user: User = Depends(require_roles(Role.STUDENT)),
    db: Session = Depends(get_db),
):
    skill = db.get(Skill, data.skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    if not skill.mentor.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This mentor is not available")

    # Business rule: the mentor cannot have two booked sessions that overlap
    new_start = data.scheduled_at
    new_end = new_start + timedelta(minutes=data.duration_minutes)
    booked = db.scalars(
        select(MentoringSession).where(
            MentoringSession.mentor_id == skill.mentor_id,
            MentoringSession.status == SessionStatus.BOOKED,
        )
    ).all()
    for s in booked:
        start = as_utc(s.scheduled_at)
        end = start + timedelta(minutes=s.duration_minutes)
        if start < new_end and new_start < end:
            raise HTTPException(status.HTTP_409_CONFLICT, "Mentor already has a session booked at this time")

    session = MentoringSession(
        student_id=user.id,
        mentor_id=skill.mentor_id,
        skill_id=skill.id,
        scheduled_at=data.scheduled_at,
        duration_minutes=data.duration_minutes,
        notes=data.notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
def session_history(
    status_filter: SessionStatus | None = Query(None, alias="status"),
    from_date: datetime | None = Query(None, description="Only sessions on/after this time"),
    to_date: datetime | None = Query(None, description="Only sessions on/before this time"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Students/mentors see their own sessions; admins see all sessions."""
    stmt = select(MentoringSession)
    if user.role != Role.ADMIN:
        stmt = stmt.where(or_(MentoringSession.student_id == user.id, MentoringSession.mentor_id == user.id))
    if status_filter:
        stmt = stmt.where(MentoringSession.status == status_filter)
    if from_date:
        stmt = stmt.where(MentoringSession.scheduled_at >= as_utc(from_date))
    if to_date:
        stmt = stmt.where(MentoringSession.scheduled_at <= as_utc(to_date))
    stmt = stmt.order_by(MentoringSession.scheduled_at.desc()).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_session_for_user(session_id, user, db)


@router.patch("/{session_id}/cancel", response_model=SessionOut)
def cancel_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_session_for_user(session_id, user, db)
    if session.status != SessionStatus.BOOKED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot cancel a {session.status} session")
    if as_utc(session.scheduled_at) <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot cancel a session that has already started")
    session.status = SessionStatus.CANCELLED
    db.commit()
    db.refresh(session)
    return session


@router.patch("/{session_id}/complete", response_model=SessionOut)
def complete_session(
    session_id: int,
    user: User = Depends(require_roles(Role.MENTOR, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    session = get_session_for_user(session_id, user, db)
    if session.status != SessionStatus.BOOKED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot complete a {session.status} session")
    session.status = SessionStatus.COMPLETED
    db.commit()
    db.refresh(session)
    return session
