import hashlib
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.services import wallet_service


class TransferError(Exception):
    """A business-rule failure. The router turns it into an HTTP response."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def compute_request_hash(receiver_id: int, amount: Decimal, currency: str) -> str:
    """Fingerprint of the request, so we can detect a key reused with different data."""
    canonical = f"{receiver_id}|{amount:.2f}|{currency}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_existing(db: Session, sender_id: int, key: str) -> models.Transaction | None:
    return db.scalar(
        select(models.Transaction).where(
            models.Transaction.sender_id == sender_id,
            models.Transaction.idempotency_key == key,
        )
    )


def _replay(existing: models.Transaction, request_hash: str) -> models.Transaction:
    """This key was used before: return the original result, never run it twice."""
    if existing.request_hash != request_hash:
        raise TransferError(
            422, "Idempotency-Key was already used with a different request payload"
        )
    if existing.status == "failed":
        raise TransferError(402, "Insufficient balance")
    return existing


def _move_money(
    db: Session, sender_wallet: models.Wallet, receiver_wallet: models.Wallet, amount: Decimal
) -> None:
    """Compare-and-set updates. Each UPDATE only succeeds if the balance is still the
    value we read, so two racing requests can never both spend the same money.
    The arithmetic happens in Python Decimal, not in SQL floats."""
    debit = db.execute(
        update(models.Wallet)
        .where(
            models.Wallet.id == sender_wallet.id,
            models.Wallet.balance == sender_wallet.balance,
        )
        .values(balance=sender_wallet.balance - amount)
        .execution_options(synchronize_session=False)
    )
    credit = db.execute(
        update(models.Wallet)
        .where(
            models.Wallet.id == receiver_wallet.id,
            models.Wallet.balance == receiver_wallet.balance,
        )
        .values(balance=receiver_wallet.balance + amount)
        .execution_options(synchronize_session=False)
    )
    if debit.rowcount != 1 or credit.rowcount != 1:
        raise TransferError(
            409,
            "Wallet was modified by another request. "
            "Please retry with the same Idempotency-Key.",
        )


def execute_transfer(
    db: Session,
    sender: models.User,
    receiver_id: int,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
) -> tuple[models.Transaction, bool]:
    """Returns (transaction, replayed). Raises TransferError for business failures."""
    if receiver_id == sender.id:
        raise TransferError(400, "Cannot transfer money to yourself")

    request_hash = compute_request_hash(receiver_id, amount, currency)

    # Step 1: has this key been used already?
    existing = _find_existing(db, sender.id, idempotency_key)
    if existing is not None:
        return _replay(existing, request_hash), True

    # Step 2: validate receiver and wallets
    if db.get(models.User, receiver_id) is None:
        raise TransferError(404, "Receiver not found")

    sender_wallet = wallet_service.get_wallet_for_user(db, sender.id)
    receiver_wallet = wallet_service.get_wallet_for_user(db, receiver_id)
    if sender_wallet is None or receiver_wallet is None:
        raise TransferError(404, "Wallet not found")
    if sender_wallet.currency != currency or receiver_wallet.currency != currency:
        raise TransferError(422, "Currency does not match the wallets' currency")

    insufficient = sender_wallet.balance < amount

    # Step 3: one database transaction for everything
    txn = models.Transaction(
        sender_id=sender.id,
        receiver_id=receiver_id,
        amount=amount,
        currency=currency,
        status="failed" if insufficient else "completed",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    try:
        db.add(txn)
        db.flush()  # the UNIQUE (sender_id, idempotency_key) constraint is enforced here
        if not insufficient:
            _move_money(db, sender_wallet, receiver_wallet, amount)
            db.add_all(
                [
                    models.Notification(
                        user_id=sender.id,
                        message=f"You sent {amount:.2f} {currency} to user {receiver_id}",
                    ),
                    models.Notification(
                        user_id=receiver_id,
                        message=f"You received {amount:.2f} {currency} from user {sender.id}",
                    ),
                ]
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Two identical requests raced: the loser lands here. Return the winner's result.
        existing = _find_existing(db, sender.id, idempotency_key)
        if existing is not None:
            return _replay(existing, request_hash), True
        raise TransferError(500, "Transfer failed. No money was moved.")
    except TransferError:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise TransferError(
            503,
            "Transfer could not be completed. No money was moved. "
            "It is safe to retry with the same Idempotency-Key.",
        )

    if insufficient:
        raise TransferError(402, "Insufficient balance")
    return txn, False