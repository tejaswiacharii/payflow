from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=schemas.NotificationPage)
def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    N = models.Notification
    condition = N.user_id == current_user.id  # only the caller's own notifications

    total = db.scalar(select(func.count()).select_from(N).where(condition))
    rows = db.scalars(
        select(N)
        .where(condition)
        .order_by(N.created_at.desc(), N.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return schemas.NotificationPage(
        items=[schemas.NotificationOut.model_validate(n) for n in rows],
        page=page,
        page_size=page_size,
        total=total,
    )