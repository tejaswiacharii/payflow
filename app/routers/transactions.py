from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _to_item(txn: models.Transaction, user_id: int) -> schemas.TransactionHistoryItem:
    return schemas.TransactionHistoryItem(
        id=txn.id,
        type="sent" if txn.sender_id == user_id else "received",
        sender_id=txn.sender_id,
        receiver_id=txn.receiver_id,
        amount=txn.amount,
        currency=txn.currency,
        status=txn.status,
        created_at=txn.created_at,
    )


@router.get("", response_model=schemas.TransactionPage)
def list_transactions(
    status_filter: Literal["completed", "failed"] | None = Query(None, alias="status"),
    txn_type: Literal["sent", "received"] | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user.id
    T = models.Transaction

    sent = T.sender_id == uid
    # Receivers only ever see completed transfers, never failed attempts
    received = and_(T.receiver_id == uid, T.status == "completed")

    if txn_type == "sent":
        visibility = sent
    elif txn_type == "received":
        visibility = received
    else:
        visibility = or_(sent, received)

    conditions = [visibility]
    if status_filter:
        conditions.append(T.status == status_filter)

    total = db.scalar(select(func.count()).select_from(T).where(*conditions))
    rows = db.scalars(
        select(T)
        .where(*conditions)
        .order_by(T.created_at.desc(), T.id.desc())  # newest first
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return schemas.TransactionPage(
        items=[_to_item(t, uid) for t in rows],
        page=page,
        page_size=page_size,
        total=total,
    )