import os

# Set BEFORE importing the app, so the app can never touch the development database.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

PASSWORD = "StrongPass123"


@pytest.fixture()
def engine():
    """A brand-new in-memory database for every single test."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared connection, so the in-memory DB survives
    )

    @event.listens_for(eng, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Not used as a context manager on purpose: that would run the app's startup
    # (which creates tables in the real engine). We build the tables ourselves above.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def make_user(client, session_factory):
    """Register + log in a user, optionally with a starting balance."""

    def _make(email: str, balance: str = "0.00") -> dict:
        r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
        assert r.status_code == 201, r.text
        user_id = r.json()["id"]

        if Decimal(balance) > 0:
            with session_factory() as db:
                wallet = db.scalar(
                    select(models.Wallet).where(models.Wallet.user_id == user_id)
                )
                wallet.balance = Decimal(balance)
                db.commit()

        login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        return {"id": user_id, "email": email, "headers": {"Authorization": f"Bearer {token}"}}

    return _make


@pytest.fixture()
def balance_of(session_factory):
    def _balance(user_id: int) -> Decimal:
        with session_factory() as db:
            return db.scalar(
                select(models.Wallet.balance).where(models.Wallet.user_id == user_id)
            )

    return _balance