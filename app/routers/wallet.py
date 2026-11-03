import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.dependencies import get_current_user
from app.services import wallet_service

router = APIRouter(prefix="/wallet", tags=["wallet"])

DEMO_FUNDING = os.getenv("DEMO_FUNDING", "").lower() == "true"


@router.get("", response_model=schemas.WalletOut)
def get_my_wallet(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = wallet_service.get_wallet_for_user(db, current_user.id)
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
    return wallet


# Demo only. The route does not exist at all unless DEMO_FUNDING=true is set.
if DEMO_FUNDING:

    @router.post("/demo-funds", response_model=schemas.WalletOut)
    def add_demo_funds(
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        try:
            return wallet_service.add_demo_funds(db, current_user.id)
        except wallet_service.DemoFundsError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc))