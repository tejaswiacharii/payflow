from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services import transfer_service


def post_transfer(client, headers, receiver_id, amount, key="key-1", currency="INR", **extra):
    body = {"receiver_id": receiver_id, "amount": amount, "currency": currency, **extra}
    request_headers = dict(headers)
    if key is not None:
        request_headers["Idempotency-Key"] = key
    return client.post("/transfers", json=body, headers=request_headers)


def total(client, path, headers):
    return client.get(path, headers=headers).json()["total"]


def test_successful_transfer_moves_money_and_notifies(client, make_user, balance_of):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    r = post_transfer(client, alice["headers"], bob["id"], "500.00")

    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "completed"
    assert body["amount"] == "500.00"
    assert body["sender_id"] == alice["id"]
    assert body["receiver_id"] == bob["id"]
    assert balance_of(alice["id"]) == Decimal("500.00")
    assert balance_of(bob["id"]) == Decimal("500.00")

    alice_notes = client.get("/notifications", headers=alice["headers"]).json()
    bob_notes = client.get("/notifications", headers=bob["headers"]).json()
    assert alice_notes["total"] == 1 and "sent" in alice_notes["items"][0]["message"]
    assert bob_notes["total"] == 1 and "received" in bob_notes["items"][0]["message"]


def test_sender_comes_from_token_not_body(client, make_user, balance_of):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com", "1000.00")

    # A malicious client tries to say "the sender is Bob"
    r = post_transfer(client, alice["headers"], bob["id"], "100.00", sender_id=bob["id"])

    assert r.status_code == 201
    assert r.json()["sender_id"] == alice["id"]
    assert balance_of(alice["id"]) == Decimal("900.00")
    assert balance_of(bob["id"]) == Decimal("1100.00")


def test_insufficient_balance_moves_nothing(client, make_user, balance_of):
    alice = make_user("alice@example.com", "100.00")
    bob = make_user("bob@example.com")

    r = post_transfer(client, alice["headers"], bob["id"], "500.00")

    assert r.status_code == 402
    assert r.json()["detail"] == "Insufficient balance"
    assert balance_of(alice["id"]) == Decimal("100.00")
    assert balance_of(bob["id"]) == Decimal("0.00")
    # No notifications for a failed transfer
    assert total(client, "/notifications", alice["headers"]) == 0
    assert total(client, "/notifications", bob["headers"]) == 0
    # ...but the failed attempt is recorded for the sender
    assert total(client, "/transactions?status=failed", alice["headers"]) == 1


def test_invalid_receiver(client, make_user, balance_of):
    alice = make_user("alice@example.com", "100.00")

    r = post_transfer(client, alice["headers"], 99999, "10.00")

    assert r.status_code == 404
    assert r.json()["detail"] == "Receiver not found"
    assert balance_of(alice["id"]) == Decimal("100.00")
    assert total(client, "/transactions", alice["headers"]) == 0


@pytest.mark.parametrize("amount", ["-5.00", "0", "0.00", "abc", "10.999"])
def test_invalid_amounts_are_rejected(client, make_user, balance_of, amount):
    alice = make_user("alice@example.com", "100.00")
    bob = make_user("bob@example.com")

    r = post_transfer(client, alice["headers"], bob["id"], amount)

    assert r.status_code == 422
    assert balance_of(alice["id"]) == Decimal("100.00")
    assert balance_of(bob["id"]) == Decimal("0.00")


def test_transfer_to_self_is_rejected(client, make_user, balance_of):
    alice = make_user("alice@example.com", "100.00")

    r = post_transfer(client, alice["headers"], alice["id"], "10.00")

    assert r.status_code == 400
    assert r.json()["detail"] == "Cannot transfer money to yourself"
    assert balance_of(alice["id"]) == Decimal("100.00")


def test_currency_mismatch_is_rejected(client, make_user, balance_of):
    alice = make_user("alice@example.com", "100.00")
    bob = make_user("bob@example.com")

    r = post_transfer(client, alice["headers"], bob["id"], "10.00", currency="USD")

    assert r.status_code == 422
    assert balance_of(alice["id"]) == Decimal("100.00")


def test_missing_idempotency_key_is_rejected(client, make_user, balance_of):
    alice = make_user("alice@example.com", "100.00")
    bob = make_user("bob@example.com")

    r = post_transfer(client, alice["headers"], bob["id"], "10.00", key=None)

    assert r.status_code == 422
    assert balance_of(alice["id"]) == Decimal("100.00")


def test_transfer_requires_authentication(client, make_user):
    bob = make_user("bob@example.com")
    r = client.post(
        "/transfers",
        json={"receiver_id": bob["id"], "amount": "10.00", "currency": "INR"},
        headers={"Idempotency-Key": "k"},
    )
    assert r.status_code == 401


def test_duplicate_request_returns_original_result(client, make_user, balance_of):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    first = post_transfer(client, alice["headers"], bob["id"], "500.00", key="dup-1")
    second = post_transfer(client, alice["headers"], bob["id"], "500.00", key="dup-1")
    # "500" and "500.00" are the same amount, so this is still a replay
    third = post_transfer(client, alice["headers"], bob["id"], "500", key="dup-1")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert third.status_code == 200
    assert third.json()["id"] == first.json()["id"]

    # Money moved exactly once, with one transaction and one notification each
    assert balance_of(alice["id"]) == Decimal("500.00")
    assert balance_of(bob["id"]) == Decimal("500.00")
    assert total(client, "/transactions", alice["headers"]) == 1
    assert total(client, "/notifications", alice["headers"]) == 1
    assert total(client, "/notifications", bob["headers"]) == 1


def test_same_key_with_different_payload_is_rejected(client, make_user, balance_of):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    first = post_transfer(client, alice["headers"], bob["id"], "500.00", key="reuse-1")
    second = post_transfer(client, alice["headers"], bob["id"], "100.00", key="reuse-1")

    assert first.status_code == 201
    assert second.status_code == 422
    assert "different request payload" in second.json()["detail"]
    assert balance_of(alice["id"]) == Decimal("500.00")  # only the first transfer ran


def test_duplicate_key_race_returns_original_result(client, make_user, balance_of, monkeypatch):
    """Simulates two identical requests racing: the 'loser' doesn't see the winner's row
    at first, tries to insert, and the UNIQUE constraint stops it."""
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    first = post_transfer(client, alice["headers"], bob["id"], "500.00", key="race-1")
    assert first.status_code == 201

    real_find = transfer_service._find_existing
    calls = {"n": 0}

    def blind_on_first_call(db, sender_id, key):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(db, sender_id, key)

    monkeypatch.setattr(transfer_service, "_find_existing", blind_on_first_call)

    second = post_transfer(client, alice["headers"], bob["id"], "500.00", key="race-1")

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert balance_of(alice["id"]) == Decimal("500.00")  # debited only once
    assert balance_of(bob["id"]) == Decimal("500.00")


def test_failure_midway_rolls_back_everything(client, make_user, balance_of, monkeypatch):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    original = transfer_service._move_money

    def explode_after_moving_money(db, sender_wallet, receiver_wallet, amount):
        original(db, sender_wallet, receiver_wallet, amount)  # the real debit and credit run...
        raise SQLAlchemyError("simulated crash after balances were updated")

    monkeypatch.setattr(transfer_service, "_move_money", explode_after_moving_money)

    r = post_transfer(client, alice["headers"], bob["id"], "500.00", key="crash-1")

    assert r.status_code == 503
    # ...but nothing was kept: balances, transaction row and notifications are all rolled back
    assert balance_of(alice["id"]) == Decimal("1000.00")
    assert balance_of(bob["id"]) == Decimal("0.00")
    assert total(client, "/transactions", alice["headers"]) == 0
    assert total(client, "/notifications", alice["headers"]) == 0
    assert total(client, "/notifications", bob["headers"]) == 0

    # The same key is still usable afterwards, so a client retry is safe
    monkeypatch.setattr(transfer_service, "_move_money", original)
    retry = post_transfer(client, alice["headers"], bob["id"], "500.00", key="crash-1")
    assert retry.status_code == 201
    assert balance_of(alice["id"]) == Decimal("500.00")
    assert balance_of(bob["id"]) == Decimal("500.00")


def test_history_and_notifications_are_private(client, make_user):
    alice = make_user("alice@example.com", "100.00")
    bob = make_user("bob@example.com")
    carol = make_user("carol@example.com")

    ok = post_transfer(client, alice["headers"], bob["id"], "50.00", key="a")
    failed = post_transfer(client, alice["headers"], bob["id"], "5000.00", key="b")
    assert ok.status_code == 201 and failed.status_code == 402

    # Bob sees only the completed transfer, never Alice's failed attempt
    bob_history = client.get("/transactions", headers=bob["headers"]).json()
    assert bob_history["total"] == 1
    item = bob_history["items"][0]
    assert item["type"] == "received" and item["status"] == "completed"
    assert "idempotency_key" not in item  # the sender's key is not exposed

    # Carol is uninvolved and sees nothing
    assert total(client, "/transactions", carol["headers"]) == 0
    assert total(client, "/notifications", carol["headers"]) == 0

    # Both endpoints require authentication
    assert client.get("/transactions").status_code == 401
    assert client.get("/notifications").status_code == 401


def test_history_pagination_order_and_filters(client, make_user):
    alice = make_user("alice@example.com", "1000.00")
    bob = make_user("bob@example.com")

    ids = []
    for i in range(3):
        r = post_transfer(client, alice["headers"], bob["id"], "10.00", key=f"k{i}")
        assert r.status_code == 201
        ids.append(r.json()["id"])

    page1 = client.get("/transactions?page=1&page_size=2", headers=alice["headers"]).json()
    page2 = client.get("/transactions?page=2&page_size=2", headers=alice["headers"]).json()
    assert page1["total"] == 3
    assert [t["id"] for t in page1["items"]] == [ids[2], ids[1]]  # newest first
    assert [t["id"] for t in page2["items"]] == [ids[0]]

    assert total(client, "/transactions?type=sent", alice["headers"]) == 3
    assert total(client, "/transactions?type=received", alice["headers"]) == 0
    assert total(client, "/transactions?type=received", bob["headers"]) == 3
    assert total(client, "/transactions?type=sent", bob["headers"]) == 0
    assert total(client, "/transactions?status=failed", alice["headers"]) == 0
    assert client.get("/transactions?status=bogus", headers=alice["headers"]).status_code == 422