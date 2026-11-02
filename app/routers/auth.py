from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import hash_password
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    email = payload.email.lower()

    existing = db.scalar(select(models.User).where(models.User.email == email))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = models.User(email=email, password_hash=hash_password(payload.password))
    try:
        db.add(user)
        db.flush()  # assigns user.id without committing
        db.add(models.Wallet(user_id=user.id))
        db.commit()  # user and wallet are saved together, or not at all
    except IntegrityError:
        # Two simultaneous registrations can both pass the check above;
        # the UNIQUE constraint is the real safeguard.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    return user