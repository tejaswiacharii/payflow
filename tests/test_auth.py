from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth import ALGORITHM, SECRET_KEY

PASSWORD = "StrongPass123"


def test_register_success(client):
    r = client.post("/auth/register", json={"email": "Alice@Example.com", "password": PASSWORD})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "alice@example.com"  # normalised to lowercase
    assert "password" not in body
    assert "password_hash" not in body


def test_register_duplicate_email(client):
    payload = {"email": "alice@example.com", "password": PASSWORD}
    assert client.post("/auth/register", json=payload).status_code == 201
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 409
    assert r.json()["detail"] == "Email already registered"


@pytest.mark.parametrize(
    "email,password",
    [
        ("not-an-email", PASSWORD),
        ("a@example.com", "short"),
        ("a@example.com", "x" * 73),  # bcrypt only uses 72 bytes, so we cap it
    ],
)
def test_register_invalid_payload(client, email, password):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 422


def test_login_success_returns_token(client):
    client.post("/auth/register", json={"email": "alice@example.com", "password": PASSWORD})
    r = client.post("/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_invalid_credentials_give_same_message(client):
    client.post("/auth/register", json={"email": "alice@example.com", "password": PASSWORD})

    wrong_password = client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "WrongPass999"}
    )
    unknown_email = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    # Same message, so the API doesn't reveal which emails are registered
    assert wrong_password.json() == unknown_email.json()


def test_me_requires_authentication(client):
    r = client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"] == "Not authenticated"


def test_me_rejects_garbage_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired token"


def test_me_rejects_expired_token(client, make_user):
    user = make_user("alice@example.com")
    expired = jwt.encode(
        {"sub": str(user["id"]), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid or expired token"


def test_me_returns_current_user(client, make_user):
    user = make_user("alice@example.com")
    r = client.get("/auth/me", headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["id"] == user["id"]