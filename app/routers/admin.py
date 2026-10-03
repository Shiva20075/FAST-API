from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MentoringSession, Review, Role, Skill, User
from app.schemas import RoleUpdate, StatusUpdate, UserOut
from app.security import require_roles

# Every route in this router requires the admin role
router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_roles(Role.ADMIN))])


def get_user_or_404(user_id: int, db: Session) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    role: Role | None = None,
    is_active: bool | None = None,
    q: str | None = Query(None, min_length=1, description="Search name or email"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if q:
        stmt = stmt.where(or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    return db.scalars(stmt.order_by(User.id).offset(skip).limit(limit)).all()


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return get_user_or_404(user_id, db)


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    data: RoleUpdate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
    user = get_user_or_404(user_id, db)
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/status", response_model=UserOut)
def change_status(
    user_id: int,
    data: StatusUpdate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    user = get_user_or_404(user_id, db)
    user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_roles(Role.ADMIN)), db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete yourself")
    user = get_user_or_404(user_id, db)
    db.delete(user)  # skills, sessions and reviews are removed by ON DELETE CASCADE
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(MentoringSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    users_by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    sessions_by_status = dict(
        db.execute(select(MentoringSession.status, func.count()).group_by(MentoringSession.status)).all()
    )
    return {
        "users_by_role": users_by_role,
        "total_skills": db.scalar(select(func.count(Skill.id))),
        "sessions_by_status": sessions_by_status,
        "total_reviews": db.scalar(select(func.count(Review.id))),
    }
