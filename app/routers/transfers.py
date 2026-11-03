from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.services import transfer_service

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.post("", response_model=schemas.TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transfer(
    payload: schemas.TransferCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=255),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        txn, replayed = transfer_service.execute_transfer(
            db=db,
            sender=current_user,  # identity comes from the JWT, never from the body
            receiver_id=payload.receiver_id,
            amount=payload.amount,
            currency=payload.currency,
            idempotency_key=idempotency_key,
        )
    except transfer_service.TransferError as exc:
        raise HTTPException(exc.status_code, exc.detail)

    if replayed:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return txn