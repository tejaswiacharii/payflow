"""Dev-only helper: set a user's wallet balance.  Usage: python seed.py alice@gmail.com 1000.00"""
import sys
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app import models
from app.database import SessionLocal


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python seed.py <email> <balance>")
    email = sys.argv[1].lower()
    try:
        balance = Decimal(sys.argv[2]).quantize(Decimal("0.01"))
    except InvalidOperation:
        sys.exit("Balance must be a number, e.g. 1000.00")
    if balance < 0:
        sys.exit("Balance cannot be negative")

    with SessionLocal() as db:
        user = db.scalar(select(models.User).where(models.User.email == email))
        if user is None:
            sys.exit(f"No user with email {email}")
        wallet = db.scalar(select(models.Wallet).where(models.Wallet.user_id == user.id))
        wallet.balance = balance
        db.commit()
        print(f"{email} (user id {user.id}) now has {balance} {wallet.currency}")


if __name__ == "__main__":
    main()