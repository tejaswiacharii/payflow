from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def get_wallet_for_user(db: Session, user_id: int) -> models.Wallet | None:
    """Business logic lives here, not in the route, so transfers can reuse it."""
    return db.scalar(select(models.Wallet).where(models.Wallet.user_id == user_id))