from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import models

DEMO_TOPUP = Decimal("1000.00")
DEMO_BALANCE_LIMIT = Decimal("10000.00")


class DemoFundsError(Exception):
    pass


def get_wallet_for_user(db: Session, user_id: int) -> models.Wallet | None:
    """Business logic lives here, not in the route, so transfers can reuse it."""
    return db.scalar(select(models.Wallet).where(models.Wallet.user_id == user_id))


def add_demo_funds(db: Session, user_id: int) -> models.Wallet:
    """Demo only: credit a fixed amount, up to a balance limit."""
    wallet = get_wallet_for_user(db, user_id)
    if wallet is None:
        raise DemoFundsError("Wallet not found")

    new_balance = wallet.balance + DEMO_TOPUP
    if new_balance > DEMO_BALANCE_LIMIT:
        raise DemoFundsError("Demo balance limit reached")

    # Same compare-and-set pattern as transfers: only update if the balance is unchanged
    result = db.execute(
        update(models.Wallet)
        .where(models.Wallet.id == wallet.id, models.Wallet.balance == wallet.balance)
        .values(balance=new_balance)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise DemoFundsError("Wallet was updated by another request. Try again.")
    db.commit()
    db.refresh(wallet)
    return wallet