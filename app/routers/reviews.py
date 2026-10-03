from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MentoringSession, Review, Role, SessionStatus, User
from app.schemas import ReviewCreate, ReviewOut, ReviewUpdate
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/reviews", tags=["Reviews & Ratings"])


def get_review_or_404(review_id: int, db: Session) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found")
    return review


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    data: ReviewCreate,
    user: User = Depends(require_roles(Role.STUDENT)),
    db: Session = Depends(get_db),
):
    session = db.get(MentoringSession, data.session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.student_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only review your own sessions")
    if session.status != SessionStatus.COMPLETED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can only review completed sessions")
    if db.scalar(select(Review).where(Review.session_id == session.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This session has already been reviewed")

    review = Review(
        session_id=session.id,
        student_id=user.id,
        mentor_id=session.mentor_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("", response_model=list[ReviewOut])
def list_reviews(
    mentor_id: int | None = Query(None, gt=0),
    min_rating: int | None = Query(None, ge=1, le=5),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Review)
    if mentor_id:
        stmt = stmt.where(Review.mentor_id == mentor_id)
    if min_rating:
        stmt = stmt.where(Review.rating >= min_rating)
    return db.scalars(stmt.order_by(Review.created_at.desc()).offset(skip).limit(limit)).all()


@router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    return get_review_or_404(review_id, db)


@router.put("/{review_id}", response_model=ReviewOut)
def update_review(
    review_id: int,
    data: ReviewUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    review = get_review_or_404(review_id, db)
    if review.student_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own reviews")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(review, field, value)
    db.commit()
    db.refresh(review)
    return review


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    review = get_review_or_404(review_id, db)
    if user.role != Role.ADMIN and review.student_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own reviews")
    db.delete(review)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
