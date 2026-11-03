from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app import models


def test_wallet_created_on_registration(client, make_user):
    alice = make_user("alice@example.com")
    r = client.get("/wallet", headers=alice["headers"])
    assert r.status_code == 200
    assert r.json()["balance"] == "0.00"
    assert r.json()["currency"] == "INR"


def test_wallet_requires_authentication(client):
    assert client.get("/wallet").status_code == 401

    r = client.get("/wallet", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired token"


def test_each_user_sees_only_their_own_wallet(client, make_user):
    alice = make_user("alice@example.com", "250.00")
    bob = make_user("bob@example.com", "75.50")

    assert client.get("/wallet", headers=alice["headers"]).json()["balance"] == "250.00"
    assert client.get("/wallet", headers=bob["headers"]).json()["balance"] == "75.50"


def test_database_enforces_one_wallet_per_user(client, make_user, session_factory):
    alice = make_user("alice@example.com")
    with session_factory() as db:
        db.add(models.Wallet(user_id=alice["id"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_database_rejects_negative_balance(client, make_user, session_factory):
    alice = make_user("alice@example.com")
    with session_factory() as db:
        wallet = db.query(models.Wallet).filter_by(user_id=alice["id"]).one()
        wallet.balance = Decimal("-1.00")
        with pytest.raises(IntegrityError):
            db.commit()


def test_health_check(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "connected"}